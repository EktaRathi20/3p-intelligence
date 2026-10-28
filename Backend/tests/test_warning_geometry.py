"""Tests for CAP-footprint matching and evidence-gated risk zones.

Covers: CAP parsing, point-in-polygon, local-impact verdicts, zone
gating (no precise circles from broad warnings alone), expired and
missing geometry, and feed failures. All fixtures are synthetic.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingestion_layer import signals
from ingestion_layer import official_warnings as official_warnings_module
from ingestion_layer.official_warnings import parse_cap_footprint

try:
    from ingestion_layer import disaster_intelligence

    _INTELLIGENCE_IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - reported as skip reason
    disaster_intelligence = None  # type: ignore[assignment]
    _INTELLIGENCE_IMPORT_ERROR = exc


def _fixture_cap():
    return b"""<?xml version="1.0" encoding="utf-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>TEST-TC-1</identifier>
  <sender>test@example.org</sender>
  <sent>2026-10-28T05:00:00+00:00</sent>
  <status>Actual</status>
  <msgType>Alert</msgType>
  <scope>Public</scope>
  <info>
    <category>Met</category>
    <event>Tropical Cyclone</event>
    <urgency>Immediate</urgency>
    <severity>Extreme</severity>
    <certainty>Likely</certainty>
    <headline>Test headline</headline>
    <area>
      <areaDesc>Test polygon</areaDesc>
      <polygon>19.0,85.0 19.0,86.5 20.5,86.5 20.5,85.0 19.0,85.0</polygon>
    </area>
    <area>
      <areaDesc>Test circle</areaDesc>
      <circle>13.0,80.2 50.0</circle>
    </area>
  </info>
</alert>"""


def _square():
    return [[19.0, 85.0], [19.0, 86.5], [20.5, 86.5], [20.5, 85.0]]


class ParseCapFootprintTest(unittest.TestCase):
    def test_extracts_polygons_circles_and_metadata(self):
        footprint = parse_cap_footprint(_fixture_cap(), "https://example.test/cap.xml")
        self.assertEqual(len(footprint["polygons"]), 1)
        self.assertEqual(footprint["polygons"][0][0], [19.0, 85.0])
        self.assertEqual(
            footprint["circles"],
            [{"center": [13.0, 80.2], "radius_km": 50.0}],
        )
        self.assertEqual(footprint["cap_severity"], "Extreme")
        self.assertEqual(footprint["cap_headline"], "Test headline")
        self.assertFalse(footprint["simplified"])
        self.assertEqual(footprint["source_url"], "https://example.test/cap.xml")

    def test_malformed_cap_raises(self):
        with self.assertRaises(ValueError):
            parse_cap_footprint(b"<alert><info>", "https://example.test/x.xml")
        with self.assertRaises(ValueError):
            parse_cap_footprint(b"<note><to>x</to></note>", "https://example.test/x.xml")

    def test_malformed_pairs_dropped(self):
        cap = _fixture_cap().replace(
            b"19.0,85.0 19.0,86.5", b"bogus 19.0,85.0 19.0,86.5,extra 19.0,86.5"
        )
        footprint = parse_cap_footprint(cap, "https://example.test/x.xml")
        self.assertEqual(len(footprint["polygons"][0]), 5)

    def test_oversized_polygon_simplified(self):
        ring = " ".join(f"{19.0 + i * 0.001},{85.0}" for i in range(2100))
        cap = (
            b'<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">'
            b"<info><area><polygon>" + ring.encode() + b"</polygon></area></info></alert>"
        )
        footprint = parse_cap_footprint(cap, "https://example.test/x.xml")
        self.assertTrue(footprint["simplified"])
        self.assertLessEqual(len(footprint["polygons"][0]), 2000)


class PointInPolygonTest(unittest.TestCase):
    def test_inside_outside_edges(self):
        square = _square()
        self.assertTrue(signals.point_in_polygon(19.8, 85.8, square))
        self.assertFalse(signals.point_in_polygon(19.07, 72.87, square))
        self.assertFalse(signals.point_in_polygon(25.0, 85.8, square))

    def test_malformed_input_is_false(self):
        self.assertFalse(signals.point_in_polygon(None, 85.8, _square()))
        self.assertFalse(signals.point_in_polygon(19.8, None, _square()))
        self.assertFalse(signals.point_in_polygon(19.8, 85.8, None))
        self.assertFalse(signals.point_in_polygon(19.8, 85.8, [[19.0, 85.0]]))
        self.assertFalse(signals.point_in_polygon(19.8, 85.8, [["a", "b"]] * 4))

    def test_bbox_and_distance(self):
        bbox = signals.polygon_bbox(_square())
        assert bbox is not None
        self.assertEqual(
            bbox, {"lonmin": 85.0, "lonmax": 86.5, "latmin": 19.0, "latmax": 20.5}
        )
        self.assertIsNone(signals.polygon_bbox(None))
        self.assertAlmostEqual(
            signals.approx_distance_to_polygon_km(19.0, 85.0, _square()), 0.0
        )
        far = signals.approx_distance_to_polygon_km(19.07, 72.87, _square())
        assert far is not None
        self.assertGreater(far, 1000.0)
        self.assertIsNone(signals.approx_distance_to_polygon_km(None, 1.0, _square()))


class AssessLocalImpactTest(unittest.TestCase):
    def _footprint(self):
        return {
            "polygons": [_square()],
            "circles": [],
            "source_url": "https://example.test/cap.xml",
        }

    def test_inside_footprint(self):
        result = signals.assess_local_impact(19.8, 85.8, [self._footprint()])
        self.assertEqual(result["verdict"], "inside_footprint")
        self.assertEqual(result["distance_to_footprint_km"], 0.0)
        self.assertEqual(result["geometry_source"], "https://example.test/cap.xml")

    def test_inside_circle(self):
        footprint = {
            "polygons": [],
            "circles": [{"center": [13.0, 80.2], "radius_km": 50.0}],
            "source_url": "https://example.test/cap.xml",
        }
        result = signals.assess_local_impact(13.1, 80.25, [footprint])
        self.assertEqual(result["verdict"], "inside_footprint")

    def test_outside_footprint_keeps_regional_caveat(self):
        result = signals.assess_local_impact(19.07, 72.87, [self._footprint()])
        self.assertEqual(result["verdict"], "outside_footprint")
        assert result["distance_to_footprint_km"] is not None
        self.assertGreater(result["distance_to_footprint_km"], 1000.0)
        self.assertIn("regional warning still applies", result["basis"][0])

    def test_missing_geometry_is_uncertain(self):
        self.assertEqual(
            signals.assess_local_impact(19.8, 85.8, [])["verdict"], "uncertain"
        )
        self.assertEqual(
            signals.assess_local_impact(19.8, 85.8, [{"polygons": []}])["verdict"],
            "uncertain",
        )
        self.assertEqual(
            signals.assess_local_impact(None, None, [self._footprint()])["verdict"],
            "uncertain",
        )


class FootprintFetchingTest(unittest.TestCase):
    def _event(self):
        now = datetime.now(timezone.utc)
        return {
            "event_id": "1",
            "episode_id": "1",
            "event_name": "SYNTH-26",
            "event_type": "TC",
            "alert_level": "RED",
            "episode_alert_level": "ORANGE",
            "iso3": "IND",
            "country": "India",
            "bbox": {"lonmin": 71.0, "lonmax": 97.0, "latmin": 3.8, "latmax": 29.8},
            "is_current": True,
            "todate": (now - timedelta(hours=6)).isoformat(),
            "datemodified": (now - timedelta(hours=6)).isoformat(),
            "cap_url": "https://example.test/cap.xml",
            "latitude": 16.4,
            "longitude": 81.8,
            "max_wind_kmh": 222.2,
            "population_affected": 100,
        }

    def test_region_gets_footprint_and_inside_verdict(self):
        footprint = parse_cap_footprint(_fixture_cap(), "https://example.test/cap.xml")
        with mock.patch.object(
            official_warnings_module, "_get_cached_events",
            return_value=[self._event()],
        ), mock.patch.object(
            official_warnings_module, "fetch_footprint_for_event",
            return_value=footprint,
        ):
            result = official_warnings_module.fetch_warnings_for_region("odisha")
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(
            result["warnings"][0]["footprint"]["cap_severity"], "Extreme"
        )
        self.assertEqual(result["local_impact"]["verdict"], "inside_footprint")

    def test_far_anchor_reports_outside(self):
        footprint = parse_cap_footprint(_fixture_cap(), "https://example.test/cap.xml")
        with mock.patch.object(
            official_warnings_module, "_get_cached_events",
            return_value=[self._event()],
        ), mock.patch.object(
            official_warnings_module, "fetch_footprint_for_event",
            return_value=footprint,
        ):
            # Mumbai anchor (19.07, 72.88) lies outside the fixture square,
            # but the coarse bbox still matches, so the warning applies
            # regionally while local impact stays outside.
            result = official_warnings_module.fetch_warnings_for_region("mumbai")
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["local_impact"]["verdict"], "outside_footprint")

    def test_cap_failure_yields_uncertain_without_losing_warning(self):
        with mock.patch.object(
            official_warnings_module, "_get_cached_events",
            return_value=[self._event()],
        ), mock.patch.object(
            official_warnings_module, "fetch_footprint_for_event",
            return_value=None,
        ):
            result = official_warnings_module.fetch_warnings_for_region("odisha")
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIsNone(result["warnings"][0]["footprint"])
        self.assertEqual(result["local_impact"]["verdict"], "uncertain")

    def test_cap_download_failure_returns_none(self):
        import requests

        event = {"event_id": "9", "cap_url": "https://example.test/missing.xml"}
        with mock.patch(
            "requests.get", side_effect=requests.RequestException("down")
        ), mock.patch.object(
            official_warnings_module, "load_json_cache", return_value=None
        ):
            self.assertIsNone(
                official_warnings_module.fetch_footprint_for_event(event)
            )

    def test_malformed_cap_returns_none(self):
        event = {"event_id": "9", "cap_url": "https://example.test/bad.xml"}
        response = mock.Mock()
        response.status_code = 200
        response.content = b"<alert><broken"
        response.raise_for_status.return_value = None
        with mock.patch("requests.get", return_value=response), mock.patch.object(
            official_warnings_module, "load_json_cache", return_value=None
        ):
            self.assertIsNone(
                official_warnings_module.fetch_footprint_for_event(event)
            )


@unittest.skipIf(
    disaster_intelligence is None,
    f"intelligence import unavailable: {_INTELLIGENCE_IMPORT_ERROR}",
)
class ZoneGatingTest(unittest.IsolatedAsyncioTestCase):
    def _payload(self, *, wind, pressure, wave, warnings, local_impact):
        return {
            "region_metadata": {
                "min_lon": 85.75, "min_lat": 19.75,
                "max_lon": 85.95, "max_lat": 19.85,
            },
            "meteorological_telemetry": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "region_target": "odisha",
                "system_name": "Test Telemetry",
                "wind_speed_kmh": wind,
                "pressure_hpa": pressure,
            },
            "marine": {"wave_height_m": wave},
            "active_systems": {"systems": []},
            "warnings": {
                "warnings": warnings,
                "local_impact": local_impact,
                "source": "GDACS test",
            },
            "history": {"historical_analogs": []},
            "forecast": {"forecast": []},
            "demography": {"total_population": 1000},
            "places": {"hospitals": [], "shelters": []},
        }

    def _red_warning(self):
        return {
            "event_name": "SYNTH-26",
            "alert_level": "RED",
            "episode_alert_level": "ORANGE",
            "max_wind_kmh": 222.2,
            "iso3": "IND",
            "footprint": {"polygons": [], "circles": []},
        }

    async def _build(self, **kwargs):
        with mock.patch.object(
            disaster_intelligence, "run_ingestion",
            return_value=self._payload(**kwargs),
        ), mock.patch.object(
            disaster_intelligence.hazard_model, "score", return_value=None
        ):
            return await disaster_intelligence.build_disaster_intelligence(
                "odisha", None
            )

    async def test_floor_red_draws_no_city_circles(self):
        body = await self._build(
            wind=30.0, pressure=1005.0, wave=1.5,
            warnings=[self._red_warning()],
            local_impact={"verdict": "inside_footprint", "basis": ["inside."],
                          "distance_to_footprint_km": 0.0,
                          "geometry_source": "test"},
        )
        self.assertEqual(body["risk_assessment"]["level"], "RED")
        self.assertEqual(body["risk_zones"], [])
        self.assertEqual(body["local_impact"]["verdict"], "inside_footprint")
        self.assertTrue(
            any("Local impact (inside_footprint)" in factor
                for factor in body["risk_assessment"]["factors"])
        )

    async def test_screening_red_draws_verified_circles(self):
        body = await self._build(
            wind=130.0, pressure=975.0, wave=None,
            warnings=[], local_impact={},
        )
        self.assertEqual(body["risk_assessment"]["level"], "RED")
        zone_ids = [zone["id"] for zone in body["risk_zones"]]
        self.assertIn("red-zone", zone_ids)

    async def test_calm_without_floor_keeps_green_zone(self):
        body = await self._build(
            wind=30.0, pressure=1005.0, wave=1.5,
            warnings=[], local_impact={},
        )
        self.assertEqual(body["risk_assessment"]["level"], "GREEN")
        zone_ids = [zone["id"] for zone in body["risk_zones"]]
        self.assertIn("green-zone", zone_ids)

    async def test_uncertain_local_impact_draws_no_circles(self):
        body = await self._build(
            wind=30.0, pressure=1005.0, wave=1.5,
            warnings=[self._red_warning()],
            local_impact={"verdict": "uncertain",
                          "basis": ["No verified footprint geometry."],
                          "distance_to_footprint_km": None,
                          "geometry_source": None},
        )
        self.assertEqual(body["risk_assessment"]["level"], "RED")
        self.assertEqual(body["risk_zones"], [])
        self.assertTrue(
            any("Local impact (uncertain)" in factor
                for factor in body["risk_assessment"]["factors"])
        )


if __name__ == "__main__":
    unittest.main()

"""Local vs regional cyclone-impact classification tests.

Regression coverage for the Surat/Mumbai vs Rajahmundry assessments: an
official regional RED warning must stay RED at region level, while the
LOCAL impact zone must reflect only documented evidence (verified
footprint intersection plus local observations) and never assign RED
merely because the wider event is RED.

Geometry fixtures use the verified GDACS CAP polygon for ARNAB-26
(``fixtures_arnab26_cap_footprint.json``) and the real managed-region
anchors for Surat, Mumbai, and Rajahmundry. All warning-dict fixtures
are synthetic.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ingestion_layer import signals
from ingestion_layer import official_warnings as official_warnings_module
from ingestion_layer.signals import classify_local_cyclone_impact

try:
    from ingestion_layer import disaster_intelligence

    _INTELLIGENCE_IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - reported as skip reason
    disaster_intelligence = None  # type: ignore[assignment]
    _INTELLIGENCE_IMPORT_ERROR = exc

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures_arnab26_cap_footprint.json"
)
_FIXTURE = None


def fixture():
    global _FIXTURE
    if _FIXTURE is None:
        with open(FIXTURE_PATH, encoding="utf-8") as handle:
            _FIXTURE = json.load(handle)
    return _FIXTURE


def real_footprint():
    return {
        "polygons": [fixture()["polygon"]],
        "circles": [],
        "source_url": (
            "https://www.gdacs.org/contentdata/resources/TC/1001345/"
            "cap_1001345.xml"
        ),
    }


def anchor(name):
    reference = fixture()["reference_anchors"][name]
    return reference["lat"], reference["lon"]


def region_box(name):
    """Managed-region box, as register_managed_regions builds it."""
    lat, lon = anchor(name)
    return {
        "min_lon": lon - 0.1,
        "min_lat": lat - 0.1,
        "max_lon": lon + 0.1,
        "max_lat": lat + 0.1,
    }


def red_warning(**overrides):
    now = datetime.now(timezone.utc)
    event = {
        "event_name": "ARNAB-26",
        "alert_level": "RED",
        "episode_alert_level": "ORANGE",
        "max_wind_kmh": 222.2,
        "population_affected": 4007943,
        "iso3": "IND",
        "country": "India",
        "is_current": True,
        "todate": (now - timedelta(hours=6)).isoformat(),
        "datemodified": (now - timedelta(hours=6)).isoformat(),
        "footprint": real_footprint(),
    }
    event.update(overrides)
    return event


def assess_against_real_footprint(name):
    lat, lon = anchor(name)
    return signals.assess_local_impact(lat, lon, [real_footprint()])


class RealGeometryRelationshipsTest(unittest.TestCase):
    def test_surat_outside_real_polygon(self):
        result = assess_against_real_footprint("surat_in_gj_srt")
        self.assertEqual(result["verdict"], "outside_footprint")
        self.assertEqual(result["distance_to_footprint_km"], 856.0)

    def test_mumbai_outside_real_polygon(self):
        result = assess_against_real_footprint("mumbai_in_mh_mmb")
        self.assertEqual(result["verdict"], "outside_footprint")
        self.assertEqual(result["distance_to_footprint_km"], 821.6)

    def test_rajahmundry_inside_real_polygon(self):
        result = assess_against_real_footprint("rajahmundry_in_ap_rjh")
        self.assertEqual(result["verdict"], "inside_footprint")
        self.assertEqual(result["distance_to_footprint_km"], 0.0)

    def test_event_bbox_overlaps_without_footprint_intersection(self):
        """Bounding-box overlap must not count as direct local impact."""
        event_bbox = fixture()["event_bbox"]
        for name in ("surat_in_gj_srt", "mumbai_in_mh_mmb"):
            with self.subTest(region=name):
                self.assertTrue(
                    official_warnings_module._bbox_intersects(
                        region_box(name), event_bbox
                    )
                )
                verdict = assess_against_real_footprint(name)["verdict"]
                self.assertEqual(verdict, "outside_footprint")


class ClassifyContractTest(unittest.TestCase):
    def _classify(self, name, **overrides):
        impact = assess_against_real_footprint(name)
        params = {
            "warnings": [red_warning()],
            "inactive_warnings": [],
            "warnings_source": "GDACS test",
            "warnings_timestamp": "2026-10-29T00:00:00+00:00",
            "warnings_error": None,
            "verdict": impact["verdict"],
            "distance_km": impact["distance_to_footprint_km"],
            "geometry_source": impact["geometry_source"],
            "screening_level": "GREEN",
            "screening_score": 0,
            "telemetry_status": "AVAILABLE",
        }
        params.update(overrides)
        return classify_local_cyclone_impact(**params)

    def test_contract_shape(self):
        assessment = self._classify("surat_in_gj_srt")
        self.assertEqual(
            set(assessment),
            {
                "regional_warning_level",
                "regional_warning_status",
                "local_impact_status",
                "local_impact_zone",
                "distance_to_footprint_km",
                "reason",
                "source",
                "updated_at",
            },
        )

    def test_surat_regional_red_with_green_local(self):
        assessment = self._classify("surat_in_gj_srt")
        self.assertEqual(assessment["regional_warning_level"], "RED")
        self.assertEqual(assessment["regional_warning_status"], "active")
        self.assertEqual(assessment["local_impact_status"], "outside_footprint")
        self.assertEqual(assessment["local_impact_zone"], "GREEN")
        self.assertEqual(assessment["distance_to_footprint_km"], 856.0)
        self.assertIn("still applies", assessment["reason"])
        self.assertEqual(assessment["source"], "GDACS test")

    def test_mumbai_regional_red_with_green_local(self):
        assessment = self._classify("mumbai_in_mh_mmb")
        self.assertEqual(assessment["regional_warning_level"], "RED")
        self.assertEqual(assessment["regional_warning_status"], "active")
        self.assertEqual(assessment["local_impact_status"], "outside_footprint")
        self.assertEqual(assessment["local_impact_zone"], "GREEN")
        self.assertEqual(assessment["distance_to_footprint_km"], 821.6)

    def test_rajahmundry_inside_keeps_red_local(self):
        assessment = self._classify("rajahmundry_in_ap_rjh")
        self.assertEqual(assessment["regional_warning_level"], "RED")
        self.assertEqual(assessment["local_impact_status"], "inside_footprint")
        self.assertEqual(assessment["local_impact_zone"], "RED")
        self.assertIn("verified", assessment["reason"])
        self.assertIn("ARNAB-26", assessment["reason"])

    def test_elevated_screening_outside_stays_elevated(self):
        assessment = self._classify(
            "surat_in_gj_srt", screening_level="ORANGE", screening_score=55
        )
        self.assertEqual(assessment["local_impact_zone"], "ORANGE")

    def test_screening_red_outside_is_valid_local_red(self):
        assessment = self._classify(
            "mumbai_in_mh_mmb", screening_level="RED", screening_score=80
        )
        self.assertEqual(assessment["local_impact_zone"], "RED")

    def test_outside_without_telemetry_is_unknown(self):
        assessment = self._classify(
            "surat_in_gj_srt",
            screening_level="UNKNOWN",
            screening_score=0,
            telemetry_status="NO_CURRENT_MEASUREMENTS",
        )
        self.assertEqual(assessment["local_impact_zone"], "UNKNOWN")
        self.assertEqual(assessment["regional_warning_level"], "RED")

    def test_uncertain_geometry_with_calm_screening_is_unknown(self):
        assessment = self._classify(
            "surat_in_gj_srt",
            verdict="uncertain",
            distance_km=None,
            geometry_source=None,
        )
        self.assertEqual(assessment["local_impact_zone"], "UNKNOWN")
        self.assertEqual(assessment["local_impact_status"], "uncertain")

    def test_invalid_geometry_classifies_unknown(self):
        malformed = [["a", "b"], ["c", "d"], ["e", "f"], ["g", "h"]]
        impact = signals.assess_local_impact(
            *anchor("surat_in_gj_srt"),
            [{"polygons": [malformed], "circles": []}],
        )
        self.assertEqual(impact["verdict"], "uncertain")
        assessment = self._classify(
            "surat_in_gj_srt",
            verdict=impact["verdict"],
            distance_km=impact["distance_to_footprint_km"],
            geometry_source=impact["geometry_source"],
        )
        self.assertEqual(assessment["local_impact_zone"], "UNKNOWN")

    def test_inside_without_active_warning_is_unknown(self):
        assessment = self._classify(
            "rajahmundry_in_ap_rjh",
            warnings=[],
            inactive_warnings=[{"event_name": "OLD-26"}],
        )
        self.assertEqual(assessment["local_impact_zone"], "UNKNOWN")
        self.assertIsNone(assessment["regional_warning_level"])
        self.assertEqual(assessment["regional_warning_status"], "expired")

    def test_expired_warnings_leave_screening_only(self):
        assessment = self._classify(
            "surat_in_gj_srt",
            warnings=[],
            inactive_warnings=[{"event_name": "OLD-26"}],
            verdict="uncertain",
            distance_km=None,
            geometry_source=None,
        )
        self.assertIsNone(assessment["regional_warning_level"])
        self.assertEqual(assessment["regional_warning_status"], "expired")
        self.assertEqual(assessment["local_impact_zone"], "GREEN")

    def test_calm_day_without_warnings_is_green(self):
        assessment = self._classify(
            "surat_in_gj_srt",
            warnings=[],
            verdict="uncertain",
            distance_km=None,
            geometry_source=None,
        )
        self.assertEqual(assessment["regional_warning_status"], "none")
        self.assertEqual(assessment["local_impact_zone"], "GREEN")

    def test_source_failure_without_observations_is_unknown(self):
        assessment = self._classify(
            "surat_in_gj_srt",
            warnings=[],
            warnings_error="feed down",
            verdict="uncertain",
            distance_km=None,
            geometry_source=None,
            screening_level="UNKNOWN",
            telemetry_status="UNAVAILABLE",
        )
        self.assertEqual(assessment["regional_warning_status"], "unavailable")
        self.assertEqual(assessment["local_impact_zone"], "UNKNOWN")

    def test_source_failure_keeps_observed_elevated_screening(self):
        assessment = self._classify(
            "surat_in_gj_srt",
            warnings=[],
            warnings_error="feed down",
            verdict="uncertain",
            distance_km=None,
            geometry_source=None,
            screening_level="RED",
            screening_score=80,
        )
        self.assertEqual(assessment["local_impact_zone"], "RED")


class InactiveWarningTrackingTest(unittest.TestCase):
    def _event(self, **overrides):
        now = datetime.now(timezone.utc)
        event = {
            "event_id": "1",
            "episode_id": "1",
            "event_name": "SYNTH-26",
            "event_type": "TC",
            "alert_level": "RED",
            "episode_alert_level": "ORANGE",
            "iso3": "IND",
            "country": "India",
            "bbox": {
                "lonmin": 71.0,
                "lonmax": 97.0,
                "latmin": 3.8,
                "latmax": 29.8,
            },
            "is_current": True,
            "todate": (now - timedelta(hours=6)).isoformat(),
            "datemodified": (now - timedelta(hours=6)).isoformat(),
            "cap_url": "https://example.test/cap.xml",
        }
        event.update(overrides)
        return event

    def _fetch(self, events):
        with mock.patch.object(
            official_warnings_module, "_get_cached_events",
            return_value=events,
        ), mock.patch.object(
            official_warnings_module,
            "fetch_footprint_for_event",
            return_value=None,
        ) as fetch_footprint:
            result = official_warnings_module.fetch_warnings_for_region(
                "odisha"
            )
        return result, fetch_footprint

    def test_expired_despite_current_flag_is_inactive(self):
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        result, fetch_footprint = self._fetch(
            [self._event(todate=old, is_current=True)]
        )
        self.assertEqual(result["warnings"], [])
        self.assertEqual(len(result["inactive_warnings"]), 1)
        inactive = result["inactive_warnings"][0]
        self.assertEqual(inactive["exclusion_reason"], "expired")
        self.assertEqual(inactive["alert_level"], "RED")
        self.assertEqual(inactive["matched_region"], "odisha")
        fetch_footprint.assert_not_called()

    def test_not_current_event_is_inactive(self):
        result, _ = self._fetch([self._event(is_current=False)])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(
            result["inactive_warnings"][0]["exclusion_reason"], "not_current"
        )

    def test_fresh_event_stays_active(self):
        result, fetch_footprint = self._fetch([self._event()])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["inactive_warnings"], [])
        fetch_footprint.assert_called_once()

    def test_feed_failure_reports_empty_inactive(self):
        with mock.patch.object(
            official_warnings_module, "_get_cached_events",
            side_effect=RuntimeError("feed down"),
        ):
            result = official_warnings_module.fetch_warnings_for_region(
                "odisha"
            )
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["inactive_warnings"], [])
        self.assertIn("feed down", result["source_error"])


@unittest.skipIf(
    disaster_intelligence is None,
    f"intelligence import unavailable: {_INTELLIGENCE_IMPORT_ERROR}",
)
class LocalAssessmentIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """End-to-end: combined level stays regional, local block separates."""

    def _payload(self, fixture_anchor, region_key, *, wind, pressure,
                 wave, warnings):
        lat, lon = anchor(fixture_anchor)
        impact = signals.assess_local_impact(lat, lon, [real_footprint()])
        return {
            "region_metadata": {
                "min_lon": lon - 0.1,
                "min_lat": lat - 0.1,
                "max_lon": lon + 0.1,
                "max_lat": lat + 0.1,
            },
            "meteorological_telemetry": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "region_target": region_key,
                "system_name": "Test Telemetry",
                "wind_speed_kmh": wind,
                "pressure_hpa": pressure,
            },
            "marine": {"wave_height_m": wave},
            "active_systems": {"systems": []},
            "warnings": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "warnings": warnings,
                "inactive_warnings": [],
                "local_impact": impact,
                "source": "GDACS test",
            },
            "history": {"historical_analogs": []},
            "forecast": {"forecast": []},
            "demography": {"total_population": 1000},
            "places": {"hospitals": [], "shelters": []},
        }

    async def _build(self, fixture_anchor, region_key, **kwargs):
        with mock.patch.object(
            disaster_intelligence, "run_ingestion",
            return_value=self._payload(fixture_anchor, region_key, **kwargs),
        ), mock.patch.object(
            disaster_intelligence.hazard_model, "score", return_value=None
        ):
            return await disaster_intelligence.build_disaster_intelligence(
                region_key, None
            )

    async def test_surat_combined_red_with_green_local(self):
        body = await self._build(
            "surat_in_gj_srt",
            "in-gj-srt",
            wind=10.0,
            pressure=1012.0,
            wave=0.14,
            warnings=[red_warning()],
        )
        self.assertEqual(body["risk_assessment"]["level"], "RED")
        local = body["local_impact_assessment"]
        self.assertEqual(local["regional_warning_level"], "RED")
        self.assertEqual(local["regional_warning_status"], "active")
        self.assertEqual(local["local_impact_status"], "outside_footprint")
        self.assertEqual(local["local_impact_zone"], "GREEN")
        self.assertEqual(local["distance_to_footprint_km"], 856.0)
        self.assertTrue(
            any(
                "Local cyclone impact: GREEN" in factor
                for factor in body["risk_assessment"]["factors"]
            )
        )

    async def test_mumbai_combined_red_with_green_local(self):
        body = await self._build(
            "mumbai_in_mh_mmb",
            "in-mh-mmb",
            wind=14.0,
            pressure=1009.62,
            wave=0.54,
            warnings=[red_warning()],
        )
        self.assertEqual(body["risk_assessment"]["level"], "RED")
        local = body["local_impact_assessment"]
        self.assertEqual(local["local_impact_status"], "outside_footprint")
        self.assertEqual(local["local_impact_zone"], "GREEN")
        self.assertEqual(local["distance_to_footprint_km"], 821.6)

    async def test_rajahmundry_inside_stays_red_local(self):
        body = await self._build(
            "rajahmundry_in_ap_rjh",
            "in-ap-rjh",
            wind=12.0,
            pressure=1010.0,
            wave=0.3,
            warnings=[red_warning()],
        )
        self.assertEqual(body["risk_assessment"]["level"], "RED")
        local = body["local_impact_assessment"]
        self.assertEqual(local["local_impact_status"], "inside_footprint")
        self.assertEqual(local["local_impact_zone"], "RED")
        self.assertEqual(local["regional_warning_level"], "RED")
        self.assertTrue(
            any(
                "Local cyclone impact: RED" in factor
                for factor in body["risk_assessment"]["factors"]
            )
        )


if __name__ == "__main__":
    unittest.main()

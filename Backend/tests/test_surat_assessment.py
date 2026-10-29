"""Surat assessment regression tests: RED warning vs local screening.

Observed shape (2026-10-29, Surat IN-GJ-SRT): GDACS RED cyclone ARNAB-26
applies regionally, the Surat anchor lies ~856 km outside the verified CAP
footprint polygon, deterministic screening scores 0/100 (GREEN), the H2O
severity probability is near zero, yet the reported level is RED via the
official-warning floor. All fixtures below are synthetic; no real storm is
hardcoded.

Covers: RED warning with an outside-footprint location, zero screening
score alongside a warning, missing/invalid footprint geometry, incorrect
coordinates and stale warnings, near-zero model probability with a
warning, warning-source failures, and cyclone-only history filters.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingestion_layer import disaster_history, signals
from ingestion_layer import official_warnings as official_warnings_module
from ingestion_layer.constant import get_region_coords

try:
    from ingestion_layer import disaster_intelligence

    _INTELLIGENCE_IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - reported as skip reason
    disaster_intelligence = None  # type: ignore[assignment]
    _INTELLIGENCE_IMPORT_ERROR = exc

# Surat anchor from the managed-region geography (synthetic precision is
# fine; the point is west-coast vs Bay-of-Bengal separation).
SURAT_LAT = 21.17801
SURAT_LON = 72.81189


def _bay_of_bengal_square():
    """Synthetic footprint polygon far from the Surat anchor."""
    return [[14.3, 88.4], [14.3, 90.0], [22.4, 90.0], [22.4, 88.4]]


def _footprint(polygons, circles=None):
    return {
        "polygons": polygons,
        "circles": circles if circles is not None else [],
        "source_url": "https://example.test/cap.xml",
    }


class OutsideFootprintTest(unittest.TestCase):
    def test_surat_shape_reports_outside_with_distance(self):
        result = signals.assess_local_impact(
            SURAT_LAT, SURAT_LON, [_footprint([_bay_of_bengal_square()])]
        )
        self.assertEqual(result["verdict"], "outside_footprint")
        assert result["distance_to_footprint_km"] is not None
        self.assertGreater(result["distance_to_footprint_km"], 800.0)
        self.assertIn("regional warning still applies", result["basis"][0])

    def test_vertex_distance_matches_haversine_to_nearest_vertex(self):
        polygon = _bay_of_bengal_square()
        result = signals.assess_local_impact(
            SURAT_LAT, SURAT_LON, [_footprint([polygon])]
        )
        expected = min(
            signals.haversine_km(SURAT_LAT, SURAT_LON, lat, lon)
            for lat, lon in polygon
        )
        assert result["distance_to_footprint_km"] is not None
        self.assertAlmostEqual(
            result["distance_to_footprint_km"], round(expected, 1), places=1
        )


class InvalidGeometryTest(unittest.TestCase):
    def test_malformed_polygon_is_uncertain_not_outside(self):
        malformed = [["a", "b"], ["c", "d"], ["e", "f"], ["g", "h"]]
        result = signals.assess_local_impact(
            SURAT_LAT, SURAT_LON, [_footprint([malformed])]
        )
        self.assertEqual(result["verdict"], "uncertain")
        self.assertIsNone(result["distance_to_footprint_km"])

    def test_malformed_circle_is_uncertain_not_outside(self):
        bad_circle = {"center": ["nowhere", None], "radius_km": -5}
        result = signals.assess_local_impact(
            SURAT_LAT, SURAT_LON, [_footprint([], [bad_circle])]
        )
        self.assertEqual(result["verdict"], "uncertain")
        self.assertIsNone(result["distance_to_footprint_km"])

    def test_non_finite_geometry_is_uncertain(self):
        nan_polygon = [
            [float("nan"), 88.4], [14.3, 90.0], [22.4, 90.0], [22.4, 88.4]
        ]
        nan_circle = {"center": [13.0, float("nan")], "radius_km": 50.0}
        for footprint in (
            _footprint([nan_polygon]),
            _footprint([], [nan_circle]),
        ):
            with self.subTest(footprint=footprint):
                result = signals.assess_local_impact(
                    SURAT_LAT, SURAT_LON, [footprint]
                )
                self.assertEqual(result["verdict"], "uncertain")
                self.assertIsNone(result["distance_to_footprint_km"])

    def test_valid_geometry_still_evaluated_alongside_malformed(self):
        malformed = [["a", "b"]] * 4
        result = signals.assess_local_impact(
            SURAT_LAT,
            SURAT_LON,
            [_footprint([malformed, _bay_of_bengal_square()])],
        )
        self.assertEqual(result["verdict"], "outside_footprint")
        assert result["distance_to_footprint_km"] is not None

    def test_missing_geometry_is_uncertain(self):
        self.assertEqual(
            signals.assess_local_impact(SURAT_LAT, SURAT_LON, [])["verdict"],
            "uncertain",
        )
        self.assertEqual(
            signals.assess_local_impact(SURAT_LAT, SURAT_LON, None)["verdict"],
            "uncertain",
        )
        self.assertEqual(
            signals.assess_local_impact(
                SURAT_LAT, SURAT_LON, [{"polygons": [], "circles": []}]
            )["verdict"],
            "uncertain",
        )

    def test_incorrect_coordinates_are_uncertain(self):
        footprint = _footprint([_bay_of_bengal_square()])
        for latitude, longitude in (
            (None, None),
            ("bad", SURAT_LON),
            (SURAT_LAT, float("nan")),
            (None, 72.8),
        ):
            with self.subTest(latitude=latitude, longitude=longitude):
                result = signals.assess_local_impact(
                    latitude, longitude, [footprint]
                )
                self.assertEqual(result["verdict"], "uncertain")
                self.assertIsNone(result["distance_to_footprint_km"])

    def test_unknown_region_coordinates_rejected(self):
        with self.assertRaises(ValueError):
            get_region_coords("atlantis")


class WarningFreshnessTest(unittest.TestCase):
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
            # No cap_url: keeps the test offline; footprint stays None.
            "latitude": 16.4,
            "longitude": 81.8,
            "max_wind_kmh": 222.2,
            "population_affected": 100,
        }
        event.update(overrides)
        return event

    def _fetch(self, events):
        with mock.patch.object(
            official_warnings_module, "_get_cached_events",
            return_value=events,
        ):
            return official_warnings_module.fetch_warnings_for_region("odisha")

    def test_current_recent_warning_applies(self):
        result = self._fetch([self._event()])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["warnings"][0]["event_name"], "SYNTH-26")

    def test_non_current_warning_excluded(self):
        result = self._fetch([self._event(is_current=False)])
        self.assertEqual(result["warnings"], [])

    def test_expired_warning_excluded(self):
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        result = self._fetch([self._event(todate=old)])
        self.assertEqual(result["warnings"], [])

    def test_malformed_todate_excluded(self):
        result = self._fetch([self._event(todate="not-a-date")])
        self.assertEqual(result["warnings"], [])

    def test_feed_failure_reports_error_without_warnings(self):
        with mock.patch.object(
            official_warnings_module, "_get_cached_events",
            side_effect=RuntimeError("feed down"),
        ):
            result = official_warnings_module.fetch_warnings_for_region("odisha")
        self.assertEqual(result["warnings"], [])
        self.assertIn("feed down", result["source_error"])
        self.assertEqual(result["local_impact"]["verdict"], "uncertain")


@unittest.skipIf(
    disaster_intelligence is None,
    f"intelligence import unavailable: {_INTELLIGENCE_IMPORT_ERROR}",
)
class SuratIntelligenceTest(unittest.IsolatedAsyncioTestCase):
    """End-to-end shape: RED floor + 0/100 screening + outside footprint."""

    def _payload(self, *, warnings, local_impact, warnings_source_error=None):
        warnings_block: dict = {
            "warnings": warnings,
            "local_impact": local_impact,
            "source": "GDACS test",
        }
        if warnings_source_error is not None:
            warnings_block["source_error"] = warnings_source_error
        return {
            "region_metadata": {
                "min_lon": 72.71189, "min_lat": 21.07801,
                "max_lon": 72.91189, "max_lat": 21.27801,
                "name": "Surat",
            },
            "meteorological_telemetry": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "region_target": "in-gj-srt",
                "system_name": "Test Telemetry",
                # Calm observations: below every screening band.
                "wind_speed_kmh": 10.0,
                "pressure_hpa": 1012.0,
            },
            "marine": {"wave_height_m": 0.14},
            "active_systems": {"systems": []},
            "warnings": warnings_block,
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
            "population_affected": 4007943,
            "iso3": "IND",
            "datemodified": datetime.now(timezone.utc).isoformat(),
            "footprint": _footprint([_bay_of_bengal_square()]),
        }

    def _outside_impact(self):
        return signals.assess_local_impact(
            SURAT_LAT, SURAT_LON, [_footprint([_bay_of_bengal_square()])]
        )

    async def _build(self, payload, model_score=None):
        with mock.patch.object(
            disaster_intelligence, "run_ingestion", return_value=payload
        ), mock.patch.object(
            disaster_intelligence.hazard_model, "score",
            return_value=model_score,
        ):
            return await disaster_intelligence.build_disaster_intelligence(
                "in-gj-srt", None
            )

    async def test_zero_screening_with_red_warning_stays_red(self):
        body = await self._build(
            self._payload(
                warnings=[self._red_warning()],
                local_impact=self._outside_impact(),
            )
        )
        assessment = body["risk_assessment"]
        self.assertEqual(assessment["score"], 0)
        self.assertEqual(assessment["screening_level"], "GREEN")
        self.assertEqual(assessment["warning_floor"], "RED")
        self.assertEqual(assessment["level"], "RED")
        self.assertEqual(assessment["level_basis"], "official_warning")
        self.assertTrue(assessment["official_warning"])
        # Outside the modeled footprint: no precise city circles, and the
        # official warning values are preserved untouched.
        self.assertEqual(body["local_impact"]["verdict"], "outside_footprint")
        self.assertEqual(body["risk_zones"], [])
        self.assertEqual(body["official_warnings"][0]["alert_level"], "RED")
        self.assertEqual(body["official_warnings"][0]["max_wind_kmh"], 222.2)

    async def test_near_zero_model_probability_does_not_lower_warning(self):
        body = await self._build(
            self._payload(
                warnings=[self._red_warning()],
                local_impact=self._outside_impact(),
            ),
            model_score={
                "probability": 0.001,
                "model_id": "test-model",
                "features_used": {
                    "latitude": 21.17,
                    "longitude": 72.81,
                    "month": 10,
                    "wind_speed_kmh": 10.0,
                    "pressure_hpa": 1012.0,
                },
            },
        )
        assessment = body["risk_assessment"]
        self.assertEqual(body["ml_probability"]["status"], "SCORED")
        self.assertAlmostEqual(body["ml_probability"]["probability"], 0.001)
        self.assertEqual(assessment["level"], "RED")
        self.assertEqual(assessment["level_basis"], "official_warning")
        self.assertTrue(
            any(
                "H2O severity probability" in factor
                for factor in assessment["factors"]
            )
        )

    async def test_missing_footprint_keeps_warning_with_uncertain_local(self):
        warning = self._red_warning()
        warning["footprint"] = None
        body = await self._build(
            self._payload(
                warnings=[warning],
                local_impact=signals.assess_local_impact(None, None, []),
            )
        )
        self.assertEqual(body["risk_assessment"]["level"], "RED")
        self.assertEqual(body["local_impact"]["verdict"], "uncertain")
        self.assertEqual(len(body["official_warnings"]), 1)

    async def test_unavailable_model_reports_unavailable_not_zero(self):
        body = await self._build(
            self._payload(warnings=[], local_impact={})
        )
        self.assertEqual(body["ml_probability"]["status"], "UNAVAILABLE")
        self.assertIsNone(body["ml_probability"]["probability"])

    async def test_warning_source_error_surfaces_in_data_quality(self):
        body = await self._build(
            self._payload(
                warnings=[],
                local_impact={},
                warnings_source_error="provider timed out",
            )
        )
        self.assertIn("warnings", body["data_quality"]["source_errors"])


class CycloneOnlyHistoryTest(unittest.TestCase):
    def _tracks(self):
        return {
            "storms_by_region": {
                "vizag": [
                    {
                        "matched_cyclone": "Storm A (2020)",
                        "historical_peak_wind_kmh": 100,
                        "historical_surge_meters": None,
                        "closest_approach_km": 10,
                        "reference_period": {
                            "start_date": "2020-01-01",
                            "end_date": "2020-01-02",
                        },
                        "source": "NOAA IBTrACS",
                    },
                ],
            },
            "recent_fixes_by_region": {"vizag": []},
            "dataset_max_observed_at": datetime.now(timezone.utc).isoformat(),
        }

    def test_history_tags_cyclone_only_with_explicit_coverage(self):
        with mock.patch.object(
            disaster_history, "get_region_coords"
        ), mock.patch.object(
            disaster_history, "_get_cached_tracks", return_value=self._tracks()
        ):
            result = disaster_history.fetch_historical_disasters("vizag")
        self.assertEqual(result["available_hazards"], ["cyclone"])
        self.assertEqual(result["hazards_with_records"], ["cyclone"])
        self.assertFalse(result["history_coverage"]["complete"])
        self.assertIn("IBTrACS", result["history_coverage"]["note"])
        self.assertTrue(result["historical_analogs"])
        for event in result["historical_analogs"]:
            self.assertEqual(event["hazard_type"], "cyclone")


if __name__ == "__main__":
    unittest.main()

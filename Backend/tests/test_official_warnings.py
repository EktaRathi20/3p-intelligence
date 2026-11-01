"""Regression tests for the 2026-10-28 Odisha missed-cyclone incident.

Incident shape (no real storm is hardcoded): calm point telemetry and an
empty IBTrACS active-system list coincided with a verified Red tropical-
cyclone warning covering the region, yet the API reported GREEN. These
tests prove the warning floor now prevents that outcome.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingestion_layer import disaster_history, signals
from ingestion_layer import official_warnings as official_warnings_module
from ingestion_layer.official_warnings import (
    fetch_warnings_for_region,
    parse_tc_events,
)

try:
    from ingestion_layer import disaster_intelligence

    _INTELLIGENCE_IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - reported as skip reason
    disaster_intelligence = None  # type: ignore[assignment]
    _INTELLIGENCE_IMPORT_ERROR = exc


def _rss_date(moment):
    return moment.strftime("%a, %d %b %Y %H:%M:%S GMT")


def _item_xml(*, name, level, episode_level, iso3, country, bbox, wind,
              population, lat, lon, todate, event_id="1", is_current="true"):
    return f"""
    <item>
      <title>{level} notification for tropical cyclone {name}</title>
      <description> affects {country}.</description>
      <link>http://www.gdacs.org/report.aspx?eventtype=TC&amp;eventid={event_id}</link>
      <gdacs:iscurrent>{is_current}</gdacs:iscurrent>
      <gdacs:todate>{todate}</gdacs:todate>
      <gdacs:datemodified>{todate}</gdacs:datemodified>
      <geo:Point><geo:lat>{lat}</geo:lat><geo:long>{lon}</geo:long></geo:Point>
      <gdacs:bbox>{bbox}</gdacs:bbox>
      <gdacs:eventtype>TC</gdacs:eventtype>
      <gdacs:alertlevel>{level}</gdacs:alertlevel>
      <gdacs:episodealertlevel>{episode_level}</gdacs:episodealertlevel>
      <gdacs:eventname>{name}</gdacs:eventname>
      <gdacs:eventid>{event_id}</gdacs:eventid>
      <gdacs:severity unit="km/h" value="{wind}">Tropical Cyclone</gdacs:severity>
      <gdacs:population unit="Pop74" value="{population}">affected</gdacs:population>
      <gdacs:iso3>{iso3}</gdacs:iso3>
      <gdacs:country>{country}</gdacs:country>
    </item>"""


def _fixture_rss(now):
    fresh = _rss_date(now - timedelta(hours=6))
    stale = _rss_date(now - timedelta(days=10))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:gdacs="http://www.gdacs.org"
     xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">
  <channel>
    {_item_xml(name="SYNTH-26", level="Red", episode_level="Orange",
               iso3="IND", country="India", bbox="71.0 97.0 3.8 29.8",
               wind="222.2", population="4007943", lat="16.4", lon="81.8",
               todate=fresh, event_id="1001345")}
    {_item_xml(name="REMOTE-26", level="Red", episode_level="Red",
               iso3="IND", country="India", bbox="130.0 140.0 5.0 15.0",
               wind="150.0", population="10", lat="10.0", lon="135.0",
               todate=fresh, event_id="1001346")}
    {_item_xml(name="FOREIGN-26", level="Red", episode_level="Red",
               iso3="GUM", country="Guam", bbox="71.0 97.0 3.8 29.8",
               wind="150.0", population="10", lat="16.4", lon="81.8",
               todate=fresh, event_id="1001347")}
    {_item_xml(name="STALE-26", level="Red", episode_level="Red",
               iso3="IND", country="India", bbox="71.0 97.0 3.8 29.8",
               wind="150.0", population="10", lat="16.4", lon="81.8",
               todate=stale, event_id="1001348")}
    <item>
      <title>Green earthquake</title>
      <gdacs:eventtype>EQ</gdacs:eventtype>
      <gdacs:alertlevel>Green</gdacs:alertlevel>
    </item>
  </channel>
</rss>""".encode("utf-8")


class ParseTcEventsTest(unittest.TestCase):
    def test_extracts_verified_fields(self):
        now = datetime.now(timezone.utc)
        events = parse_tc_events(_fixture_rss(now))
        # Only TC items; the earthquake item is ignored.
        self.assertEqual(len(events), 4)
        red = next(event for event in events if event["event_name"] == "SYNTH-26")
        self.assertEqual(red["alert_level"], "RED")
        self.assertEqual(red["episode_alert_level"], "ORANGE")
        self.assertEqual(red["iso3"], "IND")
        self.assertEqual(red["max_wind_kmh"], 222.2)
        self.assertEqual(red["population_affected"], 4007943)
        self.assertEqual(red["latitude"], 16.4)
        self.assertEqual(red["longitude"], 81.8)
        self.assertEqual(
            red["bbox"],
            {"lonmin": 71.0, "lonmax": 97.0, "latmin": 3.8, "latmax": 29.8},
        )
        self.assertTrue(red["is_current"])
        self.assertTrue(red["link"].endswith("eventid=1001345"))

    def test_malformed_xml_raises(self):
        with self.assertRaises(ValueError):
            parse_tc_events(b"<rss><channel><item>")


class RegionMatchingTest(unittest.TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        self.events = parse_tc_events(_fixture_rss(now))
        patcher = mock.patch.object(
            official_warnings_module, "_get_cached_events",
            return_value=self.events,
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_red_tc_matches_odisha(self):
        result = fetch_warnings_for_region("odisha")
        self.assertEqual(len(result["warnings"]), 1)
        warning = result["warnings"][0]
        self.assertEqual(warning["event_name"], "SYNTH-26")
        self.assertEqual(warning["matched_region"], "odisha")
        self.assertIn("GDACS", result["source"])

    def test_remote_bbox_iso_mismatch_and_stale_excluded(self):
        result = fetch_warnings_for_region("odisha")
        names = [warning["event_name"] for warning in result["warnings"]]
        self.assertNotIn("REMOTE-26", names)  # bbox misses the region box
        self.assertNotIn("FOREIGN-26", names)  # wrong country
        self.assertNotIn("STALE-26", names)  # episode ended 10 days ago

    def test_unknown_region_rejected(self):
        with self.assertRaises(ValueError):
            fetch_warnings_for_region("atlantis")

    def test_feed_failure_is_honest(self):
        with mock.patch.object(
            official_warnings_module, "_get_cached_events",
            side_effect=RuntimeError("feed down"),
        ):
            result = fetch_warnings_for_region("odisha")
        self.assertEqual(result["warnings"], [])
        self.assertIn("feed down", result["source_error"])


class WarningFloorTest(unittest.TestCase):
    def test_strongest_level_wins(self):
        warnings = [
            {"alert_level": "ORANGE", "episode_alert_level": "GREEN"},
            {"alert_level": "RED", "episode_alert_level": "ORANGE"},
        ]
        self.assertEqual(signals.warning_floor_level(warnings), "RED")

    def test_episode_level_counts(self):
        warnings = [{"alert_level": "GREEN", "episode_alert_level": "ORANGE"}]
        self.assertEqual(signals.warning_floor_level(warnings), "ORANGE")

    def test_green_and_invalid_yield_no_floor(self):
        self.assertIsNone(signals.warning_floor_level(
            [{"alert_level": "GREEN", "episode_alert_level": "GREEN"}]
        ))
        self.assertIsNone(signals.warning_floor_level([]))
        self.assertIsNone(signals.warning_floor_level(None))
        self.assertIsNone(signals.warning_floor_level("nope"))

    def test_combine_levels_matrix(self):
        self.assertEqual(
            signals.combine_levels("GREEN", "RED"), ("RED", "official_warning")
        )
        self.assertEqual(
            signals.combine_levels("ORANGE", "YELLOW"), ("ORANGE", "screening")
        )
        self.assertEqual(
            signals.combine_levels("UNKNOWN", "RED"), ("RED", "official_warning")
        )
        self.assertEqual(
            signals.combine_levels("GREEN", None), ("GREEN", "screening")
        )
        self.assertEqual(
            signals.combine_levels("RED", "RED"), ("RED", "both")
        )
        self.assertEqual(
            signals.combine_levels("UNKNOWN", None), ("UNKNOWN", "screening")
        )

    def test_warning_lines_cite_source(self):
        lines = signals.summarize_warning_lines([
            {"alert_level": "RED", "event_name": "SYNTH-26",
             "max_wind_kmh": 222.2, "population_affected": 4007943,
             "datemodified": "2026-10-28T14:09:15+00:00"},
            "not-a-dict",
        ])
        self.assertEqual(len(lines), 1)
        self.assertIn("Official Red warning: SYNTH-26", lines[0])
        self.assertIn("222 km/h", lines[0])
        self.assertIn("4.0M", lines[0])
        self.assertIn("GDACS/UN", lines[0])
        self.assertEqual(signals.summarize_warning_lines(None), [])


class FreshnessInfoTest(unittest.TestCase):
    def test_stale_dataset_flagged(self):
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        info = disaster_history._freshness_info({"dataset_max_observed_at": old})
        self.assertEqual(info["dataset_age_days"], 30)
        self.assertTrue(info["dataset_stale_for_active_detection"])

    def test_fresh_dataset_not_flagged(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        info = disaster_history._freshness_info({"dataset_max_observed_at": recent})
        self.assertFalse(info["dataset_stale_for_active_detection"])

    def test_missing_timestamp_is_stale(self):
        info = disaster_history._freshness_info({})
        self.assertTrue(info["dataset_stale_for_active_detection"])


@unittest.skipIf(
    disaster_intelligence is None,
    f"intelligence import unavailable: {_INTELLIGENCE_IMPORT_ERROR}",
)
class IncidentRegressionTest(unittest.IsolatedAsyncioTestCase):
    def _unified_payload(self, warnings):
        return {
            "region_metadata": {
                "min_lon": 85.75, "min_lat": 19.75,
                "max_lon": 85.95, "max_lat": 19.85,
            },
            "meteorological_telemetry": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "region_target": "odisha",
                "system_name": "Test Telemetry",
                "wind_speed_kmh": 30.0,
                "pressure_hpa": 1005.0,
            },
            "marine": {"wave_height_m": 1.5},
            "active_systems": {"systems": []},
            "warnings": {"warnings": warnings, "source": "GDACS test"},
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
        }

    async def _build(self, warnings):
        with mock.patch.object(
            disaster_intelligence, "run_ingestion",
            return_value=self._unified_payload(warnings),
        ), mock.patch.object(
            disaster_intelligence.hazard_model, "score", return_value=None
        ):
            return await disaster_intelligence.build_disaster_intelligence(
                "odisha", None
            )

    async def test_red_warning_overrides_green_screening(self):
        """The incident: calm telemetry + empty systems + Red warning => RED."""
        body = await self._build([self._red_warning()])
        assessment = body["risk_assessment"]
        self.assertEqual(assessment["screening_level"], "GREEN")
        self.assertEqual(assessment["warning_floor"], "RED")
        self.assertEqual(assessment["level"], "RED")
        self.assertEqual(assessment["level_basis"], "official_warning")
        self.assertNotEqual(assessment["level"], "GREEN")
        self.assertTrue(
            any("Official Red warning" in factor for factor in assessment["factors"])
        )
        self.assertEqual(len(body["official_warnings"]), 1)
        # ML and AI stay honestly unavailable, not fabricated.
        self.assertEqual(body["ml_probability"]["status"], "UNAVAILABLE")
        self.assertIsNone(body["ai_analysis"]["summary"])

    async def test_calm_without_warnings_stays_green(self):
        """No warning => screening stands on its own (calm is GREEN)."""
        body = await self._build([])
        assessment = body["risk_assessment"]
        self.assertEqual(assessment["level"], "GREEN")
        self.assertEqual(assessment["level_basis"], "screening")
        self.assertIsNone(assessment["warning_floor"])


@unittest.skipIf(
    disaster_intelligence is None,
    f"intelligence import unavailable: {_INTELLIGENCE_IMPORT_ERROR}",
)
class OfficialWarningFlagTest(unittest.IsolatedAsyncioTestCase):
    """The official_warning flag mirrors the verified warning floor."""

    def _payload(self, *, wind, pressure, wave, warnings):
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
            "warnings": {"warnings": warnings, "source": "GDACS test"},
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
        }

    async def _assess(self, **kwargs):
        with mock.patch.object(
            disaster_intelligence, "run_ingestion",
            return_value=self._payload(**kwargs),
        ), mock.patch.object(
            disaster_intelligence.hazard_model, "score", return_value=None
        ):
            body = await disaster_intelligence.build_disaster_intelligence(
                "odisha", None
            )
        return body["risk_assessment"]

    async def test_warning_driven_red_sets_flag(self):
        assessment = await self._assess(
            wind=30.0, pressure=1005.0, wave=1.5,
            warnings=[self._red_warning()],
        )
        self.assertEqual(assessment["level"], "RED")
        self.assertEqual(assessment["level_basis"], "official_warning")
        self.assertTrue(assessment["official_warning"])

    async def test_screening_only_red_clears_flag(self):
        assessment = await self._assess(
            wind=130.0, pressure=975.0, wave=None, warnings=[],
        )
        self.assertEqual(assessment["level"], "RED")
        self.assertEqual(assessment["level_basis"], "screening")
        self.assertFalse(assessment["official_warning"])

    async def test_green_without_warning_clears_flag(self):
        assessment = await self._assess(
            wind=30.0, pressure=1005.0, wave=1.5, warnings=[],
        )
        self.assertEqual(assessment["level"], "GREEN")
        self.assertFalse(assessment["official_warning"])

    async def test_unknown_without_warning_clears_flag(self):
        assessment = await self._assess(
            wind=None, pressure=None, wave=None, warnings=[],
        )
        self.assertEqual(assessment["level"], "UNKNOWN")
        self.assertFalse(assessment["official_warning"])

    async def test_unknown_with_red_floor_sets_flag(self):
        assessment = await self._assess(
            wind=None, pressure=None, wave=None,
            warnings=[self._red_warning()],
        )
        self.assertEqual(assessment["level"], "RED")
        self.assertEqual(assessment["level_basis"], "official_warning")
        self.assertTrue(assessment["official_warning"])


@unittest.skipIf(
    disaster_intelligence is None,
    f"intelligence import unavailable: {_INTELLIGENCE_IMPORT_ERROR}",
)
class AiInsightsCacheTest(unittest.IsolatedAsyncioTestCase):
    """Identical evidence must reuse the cached advisory, not regenerate."""

    def _payload(self):
        return {
            "region_metadata": {
                "min_lon": 85.75, "min_lat": 19.75,
                "max_lon": 85.95, "max_lat": 19.85,
            },
            "meteorological_telemetry": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "region_target": "odisha",
                "system_name": "Test Telemetry",
                "wind_speed_kmh": 30.0,
                "pressure_hpa": 1005.0,
            },
            "marine": {"wave_height_m": 1.5},
            "active_systems": {"systems": []},
            "warnings": {"warnings": [], "source": "GDACS test"},
            "history": {"historical_analogs": []},
            "forecast": {"forecast": []},
            "demography": {"total_population": 1000},
            "places": {"hospitals": [], "shelters": []},
        }

    def _client(self, generated):
        client = mock.Mock()
        client.generate_json = mock.Mock(return_value=generated)
        return client

    async def test_cache_miss_generates_and_saves(self):
        generated = {
            "summary": "Live advisory.",
            "recommended_tasks": [{"title": "Stage pumps"}],
            "reasoning_context": ["Calm telemetry observed."],
        }
        with mock.patch.object(
            disaster_intelligence, "run_ingestion",
            return_value=self._payload(),
        ), mock.patch.object(
            disaster_intelligence.hazard_model, "score", return_value=None
        ), mock.patch.object(
            disaster_intelligence, "_load_ai_insights", return_value=None
        ) as loader, mock.patch.object(
            disaster_intelligence, "_save_ai_insights"
        ) as saver:
            client = self._client(generated)
            body = await disaster_intelligence.build_disaster_intelligence(
                "odisha", client
            )
        client.generate_json.assert_called_once()
        loader.assert_called_once()
        saver.assert_called_once()
        saved_region, saved_fingerprint, saved_insights = saver.call_args[0]
        self.assertEqual(saved_region, "odisha")
        self.assertIsInstance(saved_fingerprint, str)
        self.assertEqual(saved_insights["summary"], "Live advisory.")
        self.assertEqual(body["ai_analysis"]["summary"], "Live advisory.")
        self.assertEqual(body["data_quality"]["ai_source"], "live")

    async def test_cache_hit_skips_generation(self):
        cached = {
            "summary": "Cached advisory.",
            "recommended_tasks": [{"title": "Cached task"}],
            "reasoning_context": ["Cached evidence."],
        }
        with mock.patch.object(
            disaster_intelligence, "run_ingestion",
            return_value=self._payload(),
        ), mock.patch.object(
            disaster_intelligence.hazard_model, "score", return_value=None
        ), mock.patch.object(
            disaster_intelligence, "_load_ai_insights", return_value=cached
        ), mock.patch.object(
            disaster_intelligence, "_save_ai_insights"
        ) as saver:
            client = self._client({"summary": "Must not be used."})
            body = await disaster_intelligence.build_disaster_intelligence(
                "odisha", client
            )
        client.generate_json.assert_not_called()
        saver.assert_not_called()
        self.assertEqual(body["ai_analysis"], cached)
        self.assertEqual(body["data_quality"]["ai_source"], "cache")


@unittest.skipIf(
    disaster_intelligence is None,
    f"intelligence import unavailable: {_INTELLIGENCE_IMPORT_ERROR}",
)
class AiFingerprintTest(unittest.TestCase):
    """The advisory fingerprint tracks the evidence it is reasoned from."""

    def test_fingerprint_changes_with_evidence(self):
        context = {
            "current_telemetry": {"wind_speed_kmh": 30.0},
            "ml_probability": {"probability": 0.1},
            "active_systems": [],
            "official_warnings": [],
            "risk_assessment": {"level": "GREEN"},
            "historical_analogs": [],
            "forecast": {"forecast": []},
            "demography": {"total_population": 1000},
            "places": {"hospitals": [], "shelters": []},
        }
        same = dict(context)
        changed = dict(context, current_telemetry={"wind_speed_kmh": 130.0})
        fingerprint = disaster_intelligence._ai_fingerprint
        self.assertEqual(fingerprint(context), fingerprint(same))
        self.assertNotEqual(fingerprint(context), fingerprint(changed))


if __name__ == "__main__":
    unittest.main()

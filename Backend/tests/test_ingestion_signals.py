"""Unit tests for ingestion signals, Meta client, H2O scoring, and training rows.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
No network, credentials, Java, or h2o install required: provider calls
are mocked and the h2o module is faked where needed.
"""

import csv
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import requests

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "scripts")
)

import train_risk_model
from ingestion_layer import disaster_history, hazard_model, signals, weather
from services.meta_client import MetaClient, MetaClientError


class WindClassificationTest(unittest.TestCase):
    def test_imd_boundaries(self):
        self.assertEqual(signals.classify_wind_kmh(130)[0], 45)
        self.assertEqual(signals.classify_wind_kmh(118)[0], 45)
        self.assertEqual(signals.classify_wind_kmh(117.9)[0], 35)
        self.assertEqual(signals.classify_wind_kmh(88)[0], 35)
        self.assertEqual(signals.classify_wind_kmh(87.9)[0], 20)
        self.assertEqual(signals.classify_wind_kmh(62)[0], 20)
        self.assertEqual(signals.classify_wind_kmh(61.9), (0, None))

    def test_missing_and_invalid_wind_scores_zero(self):
        for bad in (None, "fast", True, float("nan")):
            self.assertEqual(signals.classify_wind_kmh(bad), (0, None))

    def test_factor_message_names_observation(self):
        points, factor = signals.classify_wind_kmh(90)
        self.assertEqual(points, 35)
        assert factor is not None
        self.assertIn("90.0", factor)


class PressureClassificationTest(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(signals.classify_pressure_hpa(975)[0], 30)
        self.assertEqual(signals.classify_pressure_hpa(980)[0], 30)
        self.assertEqual(signals.classify_pressure_hpa(990)[0], 20)
        self.assertEqual(signals.classify_pressure_hpa(995)[0], 20)
        self.assertEqual(signals.classify_pressure_hpa(996), (0, None))
        self.assertEqual(signals.classify_pressure_hpa(None), (0, None))


class WaveClassificationTest(unittest.TestCase):
    def test_wmo_bands(self):
        self.assertEqual(signals.classify_wave_height_m(7)[0], 30)
        self.assertEqual(signals.classify_wave_height_m(6)[0], 30)
        self.assertEqual(signals.classify_wave_height_m(5)[0], 20)
        self.assertEqual(signals.classify_wave_height_m(4)[0], 20)
        self.assertEqual(signals.classify_wave_height_m(3)[0], 10)
        self.assertEqual(signals.classify_wave_height_m(2.5)[0], 10)
        self.assertEqual(signals.classify_wave_height_m(2.4), (0, None))
        self.assertEqual(signals.classify_wave_height_m(None), (0, None))


class ScreenRiskTest(unittest.TestCase):
    def test_aggregates_and_caps(self):
        score, factors = signals.screen_risk(
            wind=130, pressure=975, wave_height_m=7
        )
        self.assertEqual(score, 100)
        self.assertEqual(len(factors), 3)

    def test_missing_data_scores_zero(self):
        self.assertEqual(signals.screen_risk(), (0, []))
        self.assertEqual(
            signals.screen_risk(wind=None, pressure=None, wave_height_m=None),
            (0, []),
        )

    def test_levels(self):
        self.assertEqual(signals.score_to_level(100), "RED")
        self.assertEqual(signals.score_to_level(75), "RED")
        self.assertEqual(signals.score_to_level(74), "ORANGE")
        self.assertEqual(signals.score_to_level(50), "ORANGE")
        self.assertEqual(signals.score_to_level(49), "YELLOW")
        self.assertEqual(signals.score_to_level(25), "YELLOW")
        self.assertEqual(signals.score_to_level(24), "GREEN")
        self.assertEqual(signals.score_to_level(0), "GREEN")


class ActiveSystemSummaryTest(unittest.TestCase):
    def test_lines_cite_provisional_source(self):
        lines = signals.summarize_active_systems([
            {"matched_cyclone": "Remal (2024)", "latest_wind_kmh": 120,
             "closest_approach_km": 90.4, "latest_observed_at": "2024-05-26T00:00:00+00:00"},
            "not-a-dict",
        ])
        self.assertEqual(len(lines), 1)
        self.assertIn("Remal (2024)", lines[0])
        self.assertIn("120 km/h", lines[0])
        self.assertIn("IBTrACS provisional", lines[0])

    def test_invalid_input_yields_no_lines(self):
        self.assertEqual(signals.summarize_active_systems(None), [])
        self.assertEqual(signals.summarize_active_systems("x"), [])
        self.assertEqual(signals.summarize_active_systems([None]), [])


class BuildModelFeaturesTest(unittest.TestCase):
    def test_complete_features(self):
        features = signals.build_model_features(
            latitude=17.68, longitude=83.21, month=10,
            wind_speed_kmh=90, pressure_hpa=990,
        )
        self.assertEqual(
            features,
            {"latitude": 17.68, "longitude": 83.21, "month": 10.0,
             "wind_speed_kmh": 90.0, "pressure_hpa": 990.0},
        )

    def test_month_defaults_to_current(self):
        features = signals.build_model_features(
            latitude=17.0, longitude=83.0, wind_speed_kmh=50,
            pressure_hpa=1005,
        )
        assert features is not None
        self.assertEqual(features["month"], float(datetime.now(timezone.utc).month))

    def test_missing_or_bad_values_return_none(self):
        self.assertIsNone(signals.build_model_features(
            latitude=17.0, longitude=83.0, wind_speed_kmh=None,
            pressure_hpa=1005,
        ))
        self.assertIsNone(signals.build_model_features(
            latitude=17.0, longitude=83.0, wind_speed_kmh=50,
            pressure_hpa=None,
        ))
        self.assertIsNone(signals.build_model_features(
            latitude=None, longitude=83.0, wind_speed_kmh=50,
            pressure_hpa=1005,
        ))
        self.assertIsNone(signals.build_model_features(
            latitude=True, longitude=83.0, wind_speed_kmh=50,
            pressure_hpa=1005,
        ))
        self.assertIsNone(signals.build_model_features(
            latitude=17.0, longitude=83.0, month=13, wind_speed_kmh=50,
            pressure_hpa=1005,
        ))


class MetaClientTest(unittest.TestCase):
    def _client(self):
        return MetaClient(
            api_key="test-key", api_url="https://meta.example/v1",
            model="test-model",
        )

    def _response(self, status=200, payload=None, text=""):
        response = mock.Mock()
        response.status_code = status
        response.text = text
        if payload is None:
            response.json.side_effect = ValueError("no json")
        else:
            response.json.return_value = payload
        return response

    def test_generate_json_success(self):
        payload = {"choices": [{"message": {"content": '{"a": 1}'}}]}
        with mock.patch.object(
            requests, "post",
            return_value=self._response(payload=payload, text="{}"),
        ) as post_mock:
            result = self._client().generate_json(
                [{"role": "user", "content": "hi"}]
            )
        self.assertEqual(result, {"a": 1})
        sent = post_mock.call_args
        assert sent is not None
        self.assertTrue(sent.args[0].endswith("/chat/completions"))
        self.assertEqual(sent.kwargs["json"]["model"], "test-model")

    def test_generate_json_failures(self):
        client = self._client()
        with self.assertRaises(MetaClientError):
            client.generate_json([])
        cases = [
            self._response(status=401, text="unauthorized"),
            self._response(payload={"choices": []}, text="{}"),
            self._response(payload={"choices": [{"message": {}}]}, text="{}"),
            self._response(
                payload={"choices": [{"message": {"content": "nope"}}]},
                text="{}",
            ),
            self._response(
                payload={"choices": [{"message": {"content": "[1,2]"}}]},
                text="{}",
            ),
        ]
        for response in cases:
            with mock.patch("requests.post", return_value=response):
                with self.assertRaises(MetaClientError):
                    client.generate_json([{"role": "user", "content": "hi"}])
        with mock.patch(
            "requests.post",
            side_effect=requests.RequestException("down"),
        ):
            with self.assertRaises(MetaClientError):
                client.generate_json([{"role": "user", "content": "hi"}])

    def test_from_env_requires_all_three(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(MetaClient.from_env())
        with mock.patch.dict(
            os.environ,
            {"META_API_KEY": "k", "META_API_URL": "u", "META_MODEL": "m"},
            clear=True,
        ):
            client = MetaClient.from_env()
            assert client is not None
            self.assertEqual(client.model, "m")

    def test_list_models(self):
        payload = {"data": [{"id": "a"}, {"id": "b"}, "junk"]}
        with mock.patch(
            "requests.get", return_value=self._response(payload=payload)
        ):
            self.assertEqual(self._client().list_models(), ["a", "b"])
        with mock.patch(
            "requests.get",
            return_value=self._response(payload={"data": "nope"}),
        ):
            with self.assertRaises(MetaClientError):
                self._client().list_models()


class HazardModelTest(unittest.TestCase):
    def setUp(self):
        hazard_model.reset_for_tests()
        self.addCleanup(hazard_model.reset_for_tests)

    def test_score_rejects_incomplete_features(self):
        self.assertIsNone(hazard_model.score({}))
        self.assertIsNone(hazard_model.score(
            {"latitude": 1, "longitude": 2, "month": 3,
             "wind_speed_kmh": 4, "pressure_hpa": None}
        ))

    def test_score_without_model_file(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(hazard_model.score(
                {"latitude": 1, "longitude": 2, "month": 3,
                 "wind_speed_kmh": 4, "pressure_hpa": 5}
            ))
            status = hazard_model.get_model_status()
            self.assertFalse(status["available"])

    def test_status_reports_missing_h2o(self):
        with mock.patch.dict(sys.modules, {"h2o": None}):
            status = hazard_model.get_model_status()
        self.assertFalse(status["available"])
        self.assertIn("h2o", status["reason"].lower())

    def test_score_with_fake_h2o(self):
        handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        handle.close()
        self.addCleanup(os.unlink, handle.name)

        class FakeFrame:
            def __init__(self, rows):
                # Contract: column-name -> single-value lists.
                assert isinstance(rows, dict)
                assert all(isinstance(v, list) and len(v) == 1 for v in rows.values())
                assert sorted(rows) == sorted(signals.MODEL_FEATURES)
                self.rows = rows

        class FakePrediction:
            columns = ["predict", "p0", "p1"]

            def __init__(self, probability):
                self._probability = probability

            def as_data_frame(self, *args, **kwargs):
                assert kwargs.get("use_pandas") is False
                return [["1", 1.0 - self._probability, self._probability]]

        class FakeModel:
            model_id = "fake-leader"

            def __init__(self, probability):
                self._probability = probability

            def predict(self, frame):
                assert isinstance(frame, FakeFrame)
                return FakePrediction(self._probability)

        fake_h2o = mock.Mock()
        fake_h2o.H2OFrame = FakeFrame
        fake_h2o.load_model.return_value = FakeModel(0.72)

        with mock.patch.dict(os.environ, {"H2O_MODEL_PATH": handle.name}):
            with mock.patch.dict(sys.modules, {"h2o": fake_h2o}):
                result = hazard_model.score(
                    {"latitude": 17.0, "longitude": 83.0, "month": 10,
                     "wind_speed_kmh": 90, "pressure_hpa": 990}
                )
        assert result is not None
        self.assertAlmostEqual(result["probability"], 0.72)
        self.assertEqual(result["model_id"], "fake-leader")
        self.assertIn("118 km/h", result["label"])

    def test_score_accepts_model_directory(self):
        # h2o.save_model persists a directory, not a single file.
        tmpdir = tempfile.mkdtemp(prefix="h2o_model_dir_")
        self.addCleanup(shutil.rmtree, tmpdir, True)

        class FakePrediction:
            columns = ["predict", "p0", "p1"]

            def as_data_frame(self, *args, **kwargs):
                return [["0", 0.9, 0.1]]

        fake_h2o = mock.Mock()
        fake_h2o.H2OFrame.side_effect = lambda rows: rows
        model = mock.Mock()
        model.predict.return_value = FakePrediction()
        model.model_id = "dir-model"
        fake_h2o.load_model.return_value = model

        with mock.patch.dict(os.environ, {"H2O_MODEL_PATH": tmpdir}):
            with mock.patch.dict(sys.modules, {"h2o": fake_h2o}):
                result = hazard_model.score(
                    {"latitude": 17.0, "longitude": 83.0, "month": 10,
                     "wind_speed_kmh": 50, "pressure_hpa": 1008}
                )
        assert result is not None
        self.assertAlmostEqual(result["probability"], 0.1)

    def test_score_rejects_bad_probability(self):
        handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        handle.close()
        self.addCleanup(os.unlink, handle.name)

        class BadPrediction:
            columns = ["predict", "p0", "p1"]

            def as_data_frame(self, *args, **kwargs):
                return [["1", -6.0, 7.0]]

        fake_h2o = mock.Mock()
        fake_h2o.H2OFrame.side_effect = lambda rows: rows
        bad = mock.Mock()
        bad.predict.return_value = BadPrediction()
        bad.model_id = "bad"
        fake_h2o.load_model.return_value = bad

        with mock.patch.dict(os.environ, {"H2O_MODEL_PATH": handle.name}):
            with mock.patch.dict(sys.modules, {"h2o": fake_h2o}):
                self.assertIsNone(hazard_model.score(
                    {"latitude": 17.0, "longitude": 83.0, "month": 10,
                     "wind_speed_kmh": 90, "pressure_hpa": 990}
                ))


class ActiveSystemsTest(unittest.TestCase):
    def _tracks(self, fixes):
        return {
            "storms_by_region": {"vizag": []},
            "recent_fixes_by_region": {"vizag": fixes},
        }

    def test_groups_recent_fixes_per_storm(self):
        now = datetime.now(timezone.utc)
        fixes = [
            {"storm_id": "s1", "matched_cyclone": "Test (2024)",
             "observed_at": (now - timedelta(hours=6)).isoformat(),
             "latitude": 17.5, "longitude": 83.2, "wind_kmh": 100,
             "distance_km": 50.0},
            {"storm_id": "s1", "matched_cyclone": "Test (2024)",
             "observed_at": (now - timedelta(hours=12)).isoformat(),
             "latitude": 17.0, "longitude": 83.0, "wind_kmh": 80,
             "distance_km": 120.0},
            {"storm_id": "s2", "matched_cyclone": "Old (2024)",
             "observed_at": (now - timedelta(days=30)).isoformat(),
             "latitude": 17.5, "longitude": 83.2, "wind_kmh": 60,
             "distance_km": 40.0},
        ]
        with mock.patch.object(
            disaster_history, "_get_cached_tracks",
            return_value=self._tracks(fixes),
        ):
            result = disaster_history.fetch_active_systems("vizag")
        self.assertEqual(len(result["systems"]), 1)
        system = result["systems"][0]
        self.assertEqual(system["storm_id"], "s1")
        self.assertEqual(system["fixes_count"], 2)
        self.assertEqual(system["latest_wind_kmh"], 100)
        self.assertEqual(system["closest_approach_km"], 50.0)
        self.assertIn("latency", result["latency_note"].lower())

    def test_radius_filter(self):
        now = datetime.now(timezone.utc)
        fixes = [
            {"storm_id": "s1", "matched_cyclone": "Far (2024)",
             "observed_at": now.isoformat(), "latitude": 10.0,
             "longitude": 80.0, "wind_kmh": 100, "distance_km": 900.0},
        ]
        with mock.patch.object(
            disaster_history, "_get_cached_tracks",
            return_value=self._tracks(fixes),
        ):
            result = disaster_history.fetch_active_systems(
                "vizag", radius_km=250
            )
        self.assertEqual(result["systems"], [])

    def test_parse_observed_at(self):
        parsed = disaster_history._parse_observed_at("2024-10-24 06:00:00")
        assert parsed is not None
        self.assertEqual(parsed.year, 2024)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertIsNone(disaster_history._parse_observed_at("bogus"))
        self.assertIsNone(disaster_history._parse_observed_at(None))


class MarineConditionsTest(unittest.TestCase):
    def _payload(self, current=None, daily=None):
        return {"current": current or {}, "daily": daily or {}}

    def test_success_merges_groups_and_caches(self):
        calls = []

        def fake_request(latitude, longitude, **params):
            calls.append(params)
            if "daily" in params:
                return self._payload(daily={
                    "time": ["2024-01-01", "2024-01-02"],
                    "wave_height_max": [3.1, 2.2],
                })
            if "wave_direction" in params.get("current", ""):
                return self._payload(current={
                    "wave_direction": 180, "wave_period": 9.5,
                    "ocean_current_velocity": 0.4,
                    "sea_level_height_msl": 0.12,
                })
            return self._payload(current={
                "wave_height": 2.8, "sea_surface_temperature": 29.1,
            })

        saved = {}
        with mock.patch.object(
            weather, "_marine_request", side_effect=fake_request
        ), mock.patch.object(
            weather, "load_json_cache", return_value=None
        ), mock.patch.object(
            weather, "save_json_cache",
            side_effect=lambda name, payload: saved.update(payload),
        ):
            result = weather.fetch_marine_conditions("vizag")
        self.assertEqual(result["wave_height_m"], 2.8)
        self.assertEqual(result["sea_surface_temperature_c"], 29.1)
        self.assertEqual(result["wave_direction_deg"], 180.0)
        self.assertEqual(result["sea_level_msl_m"], 0.12)
        self.assertEqual(len(result["forecast_wave_height_max_7d"]), 2)
        self.assertEqual(result["source_errors"], {})
        self.assertEqual(saved["wave_height_m"], 2.8)

    def test_partial_failure_keeps_core_data(self):
        def fake_request(latitude, longitude, **params):
            if "daily" in params or "wave_direction" in params.get("current", ""):
                raise RuntimeError("unsupported variable")
            return self._payload(current={"wave_height": 1.5})

        with mock.patch.object(
            weather, "_marine_request", side_effect=fake_request
        ), mock.patch.object(
            weather, "load_json_cache", return_value=None
        ), mock.patch.object(weather, "save_json_cache"):
            result = weather.fetch_marine_conditions("vizag")
        self.assertEqual(result["wave_height_m"], 1.5)
        self.assertIsNone(result["sea_level_msl_m"])
        self.assertIn("extended", result["source_errors"])
        self.assertIn("forecast", result["source_errors"])

    def test_total_failure_returns_errors_without_caching(self):
        with mock.patch.object(
            weather, "_marine_request", side_effect=RuntimeError("down")
        ), mock.patch.object(
            weather, "load_json_cache", return_value=None
        ), mock.patch.object(
            weather, "save_json_cache"
        ) as save_mock:
            result = weather.fetch_marine_conditions("vizag")
        self.assertIsNone(result["wave_height_m"])
        self.assertEqual(len(result["source_errors"]), 3)
        save_mock.assert_not_called()

    def test_cached_result_short_circuits(self):
        cached = {"wave_height_m": 9.9, "region_target": "vizag"}
        with mock.patch.object(
            weather, "load_json_cache", return_value=cached
        ), mock.patch.object(
            weather, "_marine_request",
            side_effect=AssertionError("must not fetch"),
        ):
            self.assertEqual(
                weather.fetch_marine_conditions("vizag"), cached
            )


class TrainingRowsTest(unittest.TestCase):
    def _fixture_csv(self):
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8",
            newline="",
        )
        self.addCleanup(os.unlink, handle.name)
        writer = csv.DictWriter(handle, fieldnames=[
            "SID", "SEASON", "NAME", "LAT", "LON", "ISO_TIME",
            "WMO_WIND", "USA_WIND", "WMO_PRES", "USA_PRES",
        ])
        writer.writeheader()
        writer.writerow({key: "units" for key in writer.fieldnames})
        base = datetime(2024, 10, 24, 0, 0, 0)
        # Escalating storm near Vizag: 40kt -> 70kt (129.6 km/h >= 118).
        winds = [40, 50, 60, 70]
        for index, knots in enumerate(winds):
            moment = base + timedelta(hours=6 * index)
            writer.writerow({
                "SID": "2024299N12345", "SEASON": "2024", "NAME": "TEST",
                "LAT": "17.6", "LON": "83.2",
                "ISO_TIME": moment.strftime("%Y-%m-%d %H:%M:%S"),
                "WMO_WIND": str(knots), "USA_WIND": "",
                "WMO_PRES": "990", "USA_PRES": "",
            })
        # Weak storm: never reaches 118 km/h.
        for index, knots in enumerate([30, 35]):
            moment = base + timedelta(hours=6 * index)
            writer.writerow({
                "SID": "2024299N99999", "SEASON": "2024", "NAME": "WEAK",
                "LAT": "17.6", "LON": "83.2",
                "ISO_TIME": moment.strftime("%Y-%m-%d %H:%M:%S"),
                "WMO_WIND": str(knots), "USA_WIND": "",
                "WMO_PRES": "1002", "USA_PRES": "",
            })
        # Row with missing wind: must be dropped.
        writer.writerow({
            "SID": "2024299N99999", "SEASON": "2024", "NAME": "WEAK",
            "LAT": "17.6", "LON": "83.2",
            "ISO_TIME": base.strftime("%Y-%m-%d %H:%M:%S"),
            "WMO_WIND": "", "USA_WIND": "",
            "WMO_PRES": "1002", "USA_PRES": "",
        })
        handle.close()
        return handle.name

    def test_labels_and_drops(self):
        from pathlib import Path

        rows, stats = train_risk_model.build_rows(Path(self._fixture_csv()))
        self.assertEqual(stats["kept"], 6)
        self.assertEqual(stats["dropped"], 1)
        # Escalating storm: every fix sees >=118 km/h within 24h.
        escalating = [row for row in rows if row["wind_speed_kmh"] >= 40 * 1.852]
        self.assertTrue(escalating)
        self.assertTrue(all(row["severe_next24h"] == 1 for row in escalating))
        weak = [row for row in rows if row["wind_speed_kmh"] < 40 * 1.852]
        self.assertEqual(len(weak), 2)
        self.assertTrue(all(row["severe_next24h"] == 0 for row in weak))
        # Contract check: features match the serving contract exactly.
        for row in rows:
            self.assertEqual(
                sorted(row), sorted([*signals.MODEL_FEATURES, "severe_next24h"])
            )

    def test_write_dataset_roundtrip(self):
        from pathlib import Path

        rows, _ = train_risk_model.build_rows(Path(self._fixture_csv()))
        dest = Path(tempfile.mkdtemp()) / "out.csv"
        self.addCleanup(shutil.rmtree, str(dest.parent), True)
        train_risk_model.write_dataset(rows, dest)
        with open(dest, encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(
                reader.fieldnames, [*signals.MODEL_FEATURES, "severe_next24h"]
            )
            self.assertEqual(len(list(reader)), len(rows))


if __name__ == "__main__":
    unittest.main()

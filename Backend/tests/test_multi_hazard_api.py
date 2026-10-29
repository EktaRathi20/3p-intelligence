import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("JWT_SECRET", "test-only-secret")
os.environ.setdefault("DEMO_LOGIN_PIN", "test-only-pin")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def load_route(filename: str):
    path = BACKEND_DIR / "api" / "routes" / filename
    spec = importlib.util.spec_from_file_location(
        f"multi_hazard_route_{path.stem}", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from services import hazard_intelligence, json_store
    from ingestion_layer import disaster_history, disaster_intelligence

    data_routes = load_route("data.py")
    intelligence_routes = load_route("intelligence.py")
    IMPORT_ERROR = None
except Exception as error:
    TestClient = None
    hazard_intelligence = None
    json_store = None
    disaster_history = None
    disaster_intelligence = None
    data_routes = None
    intelligence_routes = None
    IMPORT_ERROR = error


@unittest.skipIf(TestClient is None, f"FastAPI test dependencies unavailable: {IMPORT_ERROR}")
class MultiHazardApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_database_dir = os.environ.get("DATABASE_DIR")
        os.environ["DATABASE_DIR"] = self.temp_dir.name
        json_store.clear_cache()
        json_store.write_collection("hazards", {
            "cyclone": {"name": "Cyclone", "code": "CYCLONE", "active": True},
            "drought": {"name": "Drought", "code": "DROUGHT", "active": True},
            "flood": {"name": "Flood", "code": "FLOOD", "active": True},
            "wildfire": {"name": "Wildfire", "code": "WILDFIRE", "active": True},
        })
        json_store.write_collection("regions", {
            "managed-vizag": {
                "name": "Vizag",
                "code": "vizag",
                "active": True,
                "hazardIds": ["drought"],
            },
            "managed-jodhpur": {
                "name": "Jodhpur",
                "code": "IN-RJ-JDH",
                "active": True,
                "hazardIds": ["drought"],
            },
        })

        app = FastAPI()
        app.include_router(data_routes.router)
        app.include_router(intelligence_routes.router)
        app.state.socket_server = object()
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close()
        if self.previous_database_dir is None:
            os.environ.pop("DATABASE_DIR", None)
        else:
            os.environ["DATABASE_DIR"] = self.previous_database_dir
        json_store.clear_cache()
        self.temp_dir.cleanup()

    def test_unknown_region_returns_404(self):
        response = self.client.get("/api/disaster-intelligence/unknown")
        self.assertEqual(response.status_code, 404)

    def test_configured_but_unimplemented_hazard_has_explicit_status(self):
        response = self.client.get(
            "/api/disaster-intelligence/vizag?hazard=drought"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_implemented")
        self.assertFalse(response.json()["supported"])

    def test_capabilities_separate_configuration_handlers_and_history(self):
        response = self.client.get(
            "/api/disaster-intelligence/jodhpur/capabilities"
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("drought", body["configured_hazards"])
        self.assertIn("cyclone", body["implemented_hazards"])
        self.assertIn("drought", body["not_implemented_hazards"])
        self.assertEqual(body["historical_hazards"], ["cyclone"])
        self.assertFalse(body["history_coverage"]["complete"])
        wildfire = next(item for item in body["hazards"] if item["id"] == "wildfire")
        self.assertFalse(wildfire["implemented"])
        self.assertEqual(wildfire["intelligence_status"], "not_configured")

    def test_unconfigured_hazard_has_explicit_status(self):
        response = self.client.get(
            "/api/disaster-intelligence/vizag?hazard=cyclone"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_configured")
        self.assertFalse(response.json()["supported"])

    def test_invalid_hazard_returns_422(self):
        response = self.client.get(
            "/api/disaster-intelligence/vizag?hazard=volcanic"
        )
        self.assertEqual(response.status_code, 422)

    def test_configured_cyclone_runs_existing_handler(self):
        json_store.update_document("regions", "managed-vizag", {
            "hazardIds": ["cyclone"],
        })
        expected = {
            "region": "vizag",
            "status": "success",
            "data_quality": {
                "ingestion_status": "SUCCESS",
                "telemetry_status": "AVAILABLE",
            },
            "risk_assessment": {"level": "YELLOW", "score": 25},
        }

        async def handler(region, client):
            self.assertEqual(region, "vizag")
            return dict(expected)

        with mock.patch.dict(
            hazard_intelligence.INTELLIGENCE_HANDLERS,
            {"cyclone": handler},
        ), mock.patch.object(
            intelligence_routes,
            "emit_risk_assessment_alert",
        ):
            response = self.client.get(
                "/api/disaster-intelligence/vizag?hazard=cyclone"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["risk_assessment"], expected["risk_assessment"])
        self.assertEqual(response.json()["hazard"], "cyclone")
        self.assertTrue(response.json()["supported"])

    def test_managed_region_is_registered_before_running_cyclone_handler(self):
        json_store.update_document("regions", "managed-jodhpur", {
            "hazardIds": ["cyclone"],
        })
        expected = {
            "region": "in-rj-jdh",
            "data_quality": {
                "ingestion_status": "SUCCESS",
                "telemetry_status": "AVAILABLE",
            },
            "risk_assessment": {"level": "YELLOW", "score": 25},
        }
        handled_regions = []

        async def handler(region, client):
            handled_regions.append(region)
            return dict(expected)

        with mock.patch.dict(intelligence_routes.REGION_DATA, {}), mock.patch.object(
            intelligence_routes,
            "register_managed_regions",
            side_effect=lambda: intelligence_routes.REGION_DATA.update({
                "in-rj-jdh": {
                    "min_lon": 73.0,
                    "min_lat": 26.0,
                    "max_lon": 73.2,
                    "max_lat": 26.2,
                    "name": "Jodhpur",
                },
            }),
        ) as register, mock.patch.dict(
            hazard_intelligence.INTELLIGENCE_HANDLERS,
            {"cyclone": handler},
        ), mock.patch.object(
            intelligence_routes,
            "emit_risk_assessment_alert",
        ):
            response = self.client.get(
                "/api/disaster-intelligence/jodhpur?hazard=cyclone"
            )

        self.assertEqual(response.status_code, 200)
        register.assert_called_once()
        self.assertEqual(handled_regions, ["in-rj-jdh"])

    @unittest.skipIf(disaster_intelligence is None, "Cyclone intelligence dependencies unavailable")
    def test_registered_cyclone_handler_runs_existing_engine(self):
        json_store.update_document("regions", "managed-vizag", {
            "hazardIds": ["cyclone"],
        })
        payload = {
            "region_metadata": {
                "min_lon": 83.15, "min_lat": 17.65,
                "max_lon": 83.35, "max_lat": 17.75,
            },
            "meteorological_telemetry": {
                "timestamp": "2026-10-29T00:00:00+00:00",
                "system_name": "Test telemetry",
                "wind_speed_kmh": 30,
                "pressure_hpa": 1005,
            },
            "marine": {"wave_height_m": 1.5},
            "active_systems": {"systems": []},
            "warnings": {"warnings": []},
            "history": {"historical_analogs": []},
            "forecast": {"forecast": []},
            "demography": {"total_population": 1000},
            "places": {"hospitals": [], "shelters": []},
        }
        with mock.patch.object(
            disaster_intelligence,
            "run_ingestion",
            return_value=payload,
        ), mock.patch.object(
            disaster_intelligence.hazard_model,
            "score",
            return_value=None,
        ), mock.patch.object(
            intelligence_routes,
            "emit_risk_assessment_alert",
        ):
            response = self.client.get(
                "/api/disaster-intelligence/vizag?hazard=CYCLONE"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["risk_assessment"]["level"], "GREEN")
        self.assertEqual(body["risk_assessment"]["score"], 0)
        self.assertEqual(body["hazard"], "cyclone")
        self.assertTrue(body["supported"])

    def test_failed_intelligence_ingestion_returns_502(self):
        json_store.update_document("regions", "managed-vizag", {
            "hazardIds": ["cyclone"],
        })

        async def handler(region, client):
            return {
                "data_quality": {
                    "ingestion_status": "FAILED",
                    "ingestion_error": "upstream timeout",
                },
                "risk_assessment": {"level": "GREEN", "score": 0},
            }

        with mock.patch.dict(
            hazard_intelligence.INTELLIGENCE_HANDLERS,
            {"cyclone": handler},
        ):
            response = self.client.get(
                "/api/disaster-intelligence/vizag?hazard=cyclone"
            )
        self.assertEqual(response.status_code, 502)

    def test_warning_source_failure_returns_error_not_green(self):
        json_store.update_document("regions", "managed-vizag", {
            "hazardIds": ["cyclone"],
        })

        async def handler(region, client):
            return {
                "data_quality": {
                    "ingestion_status": "SUCCESS",
                    "telemetry_status": "AVAILABLE",
                    "source_errors": {"warnings": "provider timed out"},
                },
                "risk_assessment": {"level": "GREEN", "score": 0},
            }

        with mock.patch.dict(
            hazard_intelligence.INTELLIGENCE_HANDLERS,
            {"cyclone": handler},
        ):
            response = self.client.get(
                "/api/disaster-intelligence/vizag?hazard=cyclone"
            )
        self.assertEqual(response.status_code, 502)

    def test_missing_current_evidence_does_not_return_green_assessment(self):
        json_store.update_document("regions", "managed-vizag", {
            "hazardIds": ["cyclone"],
        })

        async def handler(region, client):
            return {
                "data_quality": {
                    "ingestion_status": "SUCCESS",
                    "telemetry_status": "NO_CURRENT_MEASUREMENTS",
                },
                "risk_assessment": {"level": "GREEN", "score": 0, "warning_floor": None},
            }

        with mock.patch.dict(
            hazard_intelligence.INTELLIGENCE_HANDLERS,
            {"cyclone": handler},
        ):
            response = self.client.get(
                "/api/disaster-intelligence/vizag?hazard=cyclone"
            )
        self.assertEqual(response.status_code, 503)

    def test_common_population_api_does_not_require_cyclone_configuration(self):
        with mock.patch.object(
            data_routes,
            "fetch_population",
            return_value={"region_target": "vizag", "total_population": 123},
        ) as fetch:
            response = self.client.get("/api/population?region=vizag")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_population"], 123)
        fetch.assert_called_once_with(region_key="vizag")

    def test_history_returns_records_and_filters_by_hazard(self):
        events = [
            {
                "matched_cyclone": "Storm A (2020)",
                "hazard_type": "cyclone",
                "historical_peak_wind_kmh": 100,
                "historical_surge_meters": None,
                "closest_approach_km": 10,
                "reference_period": {"start_date": "2020-01-01", "end_date": "2020-01-02"},
                "source": "NOAA IBTrACS",
            },
        ]
        history = {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "region_target": "vizag",
            "source": "NOAA IBTrACS",
            "source_url": "https://example.invalid/ibtracs",
            "total_historical_events_analyzed": 1,
            "historical_analogs": events,
            "available_hazards": ["cyclone"],
            "hazards_with_records": ["cyclone"],
            "history_coverage": {"complete": False},
        }

        with mock.patch.object(data_routes, "fetch_historical_disasters", return_value=history):
            all_records = self.client.get("/api/history?region=vizag")
            filtered = self.client.get("/api/history?region=vizag&hazard=cyclone")
            no_matches = self.client.get("/api/history?region=vizag&hazard=flood")
            wildfire_no_matches = self.client.get(
                "/api/history?region=vizag&hazard=wildfire"
            )
            invalid = self.client.get("/api/history?region=vizag&hazard=invalid")
            unknown_region = self.client.get("/api/history?region=unknown")

        self.assertEqual(all_records.status_code, 200)
        self.assertEqual(all_records.json()["historical_analogs"][0]["hazard_type"], "cyclone")
        self.assertEqual(filtered.json()["matching_events"], 1)
        self.assertEqual(all_records.json()["hazards_with_records"], ["cyclone"])
        self.assertEqual(no_matches.json()["historical_analogs"], [])
        self.assertEqual(no_matches.json()["matching_events"], 0)
        self.assertEqual(wildfire_no_matches.status_code, 200)
        self.assertEqual(wildfire_no_matches.json()["historical_analogs"], [])
        self.assertEqual(wildfire_no_matches.json()["matching_events"], 0)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(unknown_region.status_code, 404)

    def test_history_source_tags_only_the_hazard_it_observes(self):
        event = {
            "matched_cyclone": "Storm A (2020)",
            "historical_peak_wind_kmh": 100,
            "historical_surge_meters": None,
            "closest_approach_km": 10,
            "reference_period": {"start_date": "2020-01-01", "end_date": "2020-01-02"},
            "source": "NOAA IBTrACS",
        }
        tracks = {
            "storms_by_region": {"vizag": [event]},
            "dataset_max_observed_at": "2026-01-01T00:00:00+00:00",
        }
        with mock.patch.object(disaster_history, "get_region_coords"), mock.patch.object(
            disaster_history, "_get_cached_tracks", return_value=tracks
        ):
            result = disaster_history.fetch_historical_disasters("vizag")

        self.assertEqual(result["historical_analogs"][0]["hazard_type"], "cyclone")
        self.assertEqual(result["historical_analogs"][0]["matched_cyclone"], event["matched_cyclone"])
        self.assertEqual(result["available_hazards"], ["cyclone"])
        self.assertEqual(result["hazards_with_records"], ["cyclone"])
        self.assertFalse(result["history_coverage"]["complete"])


if __name__ == "__main__":
    unittest.main()

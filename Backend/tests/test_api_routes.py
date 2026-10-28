"""API smoke tests for the JSON-backed routes.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
Exercises roles, users, auth, hazards, regions, geo, and
region-configuration endpoints against a temporary ``DATABASE_DIR``.
Skipped when ``httpx`` (required by FastAPI's TestClient) is missing.
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

# Auth requires these at import time; keep real values when already set.
os.environ.setdefault("JWT_SECRET", "test-only-secret")
os.environ.setdefault("DEMO_LOGIN_PIN", "test-only-pin")

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _load_route_module(name, filename):
    """Load one route module by path, bypassing the app package init.

    ``api.routes.__init__`` pulls every router (including ones needing
    optional third-party packages); these tests only need the four
    JSON-backed routers, which depend solely on fastapi/pydantic/jwt.
    """
    path = os.path.join(_BACKEND_DIR, "api", "routes", filename)
    spec = importlib.util.spec_from_file_location(
        f"route_under_test_{name}", os.path.abspath(path)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from services import geo_service, json_store

    _AUTH_ROUTES = _load_route_module("auth", "auth.py")
    _ROLES_USERS_ROUTES = _load_route_module("roles_users", "roles_users.py")
    _REGIONS_ROUTES = _load_route_module("regions", "regions.py")
    _GEO_ROUTES = _load_route_module("geo", "geo.py")

    def _build_app():
        app = FastAPI()
        app.include_router(_AUTH_ROUTES.router)
        app.include_router(_ROLES_USERS_ROUTES.router)
        app.include_router(_REGIONS_ROUTES.router)
        app.include_router(_GEO_ROUTES.router)
        return app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - reported as skip reason
    TestClient = None  # type: ignore[assignment]
    geo_service = None  # type: ignore[assignment]
    json_store = None  # type: ignore[assignment]
    _build_app = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


def seed_store():
    json_store.write_collection("roles", {
        "role_1": {"name": "Role One", "level": 1, "isActive": True},
        "role_2": {"name": "Role Two", "level": 2, "isActive": False},
    })
    json_store.write_collection("users", {
        "user_1": {"name": "Active Ana", "email": "ana@example.com",
                   "roleId": "role_1", "isActive": True},
        "user_2": {"name": "Inactive Ivo", "email": "ivo@example.com",
                   "roleId": "role_1", "isActive": False},
        "user_3": {"name": "Roleless Ria", "email": "ria@example.com",
                   "isActive": True},
    })
    json_store.write_collection("hazards", {
        "flood": {"name": "Flood", "code": "FLOOD", "active": True},
        "fire": {"name": "Fire", "code": "FIRE", "active": False},
    })
    json_store.write_collection("regions", {})
    json_store.write_collection("countries", {
        "IN": {"code": "IN", "name": "India"},
        "SG": {"code": "SG", "name": "Singapore"},
    })
    json_store.write_collection("states", {
        "2": {"countryCode": "IN", "code": "RJ", "name": "Rajasthan"},
    })
    json_store.write_collection("cities", {
        "102": {"countryCode": "IN", "stateCode": "RJ",
                "stateName": "Rajasthan", "name": "Jodhpur",
                "nameLower": "jodhpur"},
    })
    json_store.write_collection("settings", {
        "geoSync": {"countries": 2, "states": 1, "cities": 1,
                    "datasetRef": "test-fixture",
                    "syncedAt": "2026-01-01T00:00:00+00:00"},
    })


@unittest.skipIf(TestClient is None, f"TestClient unavailable: {_IMPORT_ERROR}")
class ApiRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(_build_app())

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="api_routes_test_")
        patcher = mock.patch.dict(
            os.environ, {"DATABASE_DIR": self.tmpdir}
        )
        self.addCleanup(patcher.stop)
        patcher.start()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        geo_service.clear_cache()
        self.addCleanup(geo_service.clear_cache)
        seed_store()

    # ---------------- roles & users ----------------

    def test_roles_endpoints(self):
        response = self.client.get("/api/roles")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["count"], 2)
        self.assertEqual(
            [role["id"] for role in body["roles"]], ["role_1", "role_2"]
        )

        one = self.client.get("/api/roles/role_1")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["role"]["name"], "Role One")

        missing = self.client.get("/api/roles/nope")
        self.assertEqual(missing.status_code, 404)

    def test_users_endpoints(self):
        response = self.client.get("/api/users")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["count"], 3)

        one = self.client.get("/api/users/user_1")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["user"]["email"], "ana@example.com")

        missing = self.client.get("/api/users/nope")
        self.assertEqual(missing.status_code, 404)

    # ---------------- auth ----------------

    def test_login_and_me(self):
        login = self.client.post("/api/auth/login", json={"user_id": "user_1"})
        self.assertEqual(login.status_code, 200)
        body = login.json()
        self.assertIn("access_token", body)
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(body["user"]["id"], "user_1")
        self.assertEqual(body["user"]["roleName"], "Role One")

        me = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["id"], "user_1")

    def test_login_rejections(self):
        self.assertEqual(
            self.client.post(
                "/api/auth/login", json={"user_id": "nope"}
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/login", json={"user_id": "user_2"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/login", json={"user_id": "user_3"}
            ).status_code,
            403,
        )

    def test_me_rejections(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        bad = self.client.get(
            "/api/auth/me", headers={"Authorization": "Bearer bogus"}
        )
        self.assertEqual(bad.status_code, 401)

    # ---------------- hazards & geo ----------------

    def test_hazard_types(self):
        active = self.client.get("/api/hazard-types")
        self.assertEqual(active.status_code, 200)
        self.assertEqual(active.json()["count"], 1)

        everything = self.client.get("/api/hazard-types?activeOnly=false")
        self.assertEqual(everything.json()["count"], 2)

    def test_geo_endpoints(self):
        countries = self.client.get("/api/countries")
        self.assertEqual(countries.status_code, 200)
        self.assertEqual(countries.json()["count"], 2)

        filtered = self.client.get("/api/countries?search=india")
        self.assertEqual(filtered.json()["count"], 1)

        states = self.client.get("/api/states?countryCode=IN")
        self.assertEqual(states.status_code, 200)
        self.assertTrue(states.json()["hasSubdivisions"])
        self.assertEqual(states.json()["states"][0]["code"], "RJ")

        no_subdivisions = self.client.get("/api/states?countryCode=SG")
        self.assertFalse(no_subdivisions.json()["hasSubdivisions"])

        cities = self.client.get("/api/cities?countryCode=IN&stateCode=RJ")
        self.assertEqual(cities.status_code, 200)
        self.assertEqual(cities.json()["total"], 1)
        self.assertEqual(cities.json()["cities"][0]["name"], "Jodhpur")

        status = self.client.get("/api/geo/status")
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()["synced"])
        self.assertEqual(status.json()["cities"], 1)

    # ---------------- regions ----------------

    def _create_region(self, **overrides):
        payload = {
            "name": "Jodhpur Metro",
            "countryCode": "IN",
            "stateCode": "RJ",
            "cityId": "102",
            "hazardIds": ["flood"],
            "code": "IN-RJ-JDH",
        }
        payload.update(overrides)
        return self.client.post("/api/regions", json=payload)

    def test_region_crud(self):
        created = self._create_region()
        self.assertEqual(created.status_code, 201)
        region = created.json()["region"]
        region_id = region["id"]
        self.assertEqual(region["countryName"], "India")
        self.assertEqual(region["stateName"], "Rajasthan")
        self.assertEqual(region["cityName"], "Jodhpur")
        self.assertIn("createdAt", region)

        listed = self.client.get("/api/regions")
        self.assertEqual(listed.json()["count"], 1)

        fetched = self.client.get(f"/api/regions/{region_id}")
        self.assertEqual(fetched.status_code, 200)

        updated = self.client.put(
            f"/api/regions/{region_id}", json={"name": "Jodhpur Urban"}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["region"]["name"], "Jodhpur Urban")

        deleted = self.client.delete(f"/api/regions/{region_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/regions/{region_id}").status_code, 404
        )

    def test_region_validation(self):
        self.assertEqual(
            self._create_region(countryCode="XX").status_code, 400
        )
        self.assertEqual(
            self._create_region(hazardIds=["bogus"]).status_code, 400
        )
        self.assertEqual(
            self._create_region(stateCode="ZZ").status_code, 400
        )
        self.assertEqual(self._create_region().status_code, 201)
        self.assertEqual(self._create_region().status_code, 409)

    def test_region_delete_guards(self):
        parent_id = self._create_region(code="PARENT").json()["region"]["id"]
        child = self._create_region(
            code="CHILD", parentRegionId=parent_id, name="Child region"
        )
        self.assertEqual(child.status_code, 201)
        self.assertEqual(
            self.client.delete(f"/api/regions/{parent_id}").status_code, 409
        )

        config = self.client.post(
            "/api/region-configuration",
            json={"defaultRegionId": parent_id},
        )
        self.assertEqual(config.status_code, 201)
        self.assertEqual(
            self.client.delete(
                f"/api/regions/{child.json()['region']['id']}"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.delete(f"/api/regions/{parent_id}").status_code, 409
        )

    # ---------------- region configuration ----------------

    def test_region_configuration_crud(self):
        missing = self.client.get("/api/region-configuration")
        self.assertEqual(missing.status_code, 200)
        self.assertFalse(missing.json()["exists"])

        region_id = self._create_region().json()["region"]["id"]

        created = self.client.post(
            "/api/region-configuration",
            json={"defaultRegionId": region_id},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["defaultRegionId"], region_id)

        duplicate = self.client.post(
            "/api/region-configuration",
            json={"defaultRegionId": region_id},
        )
        self.assertEqual(duplicate.status_code, 409)

        updated = self.client.put(
            "/api/region-configuration", json={"defaultRegionId": None}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertIsNone(updated.json()["defaultRegionId"])

        bad_default = self.client.put(
            "/api/region-configuration",
            json={"defaultRegionId": "nope"},
        )
        self.assertEqual(bad_default.status_code, 400)

        deleted = self.client.delete("/api/region-configuration")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.client.delete("/api/region-configuration").status_code, 404
        )
        self.assertEqual(
            self.client.put(
                "/api/region-configuration",
                json={"defaultRegionId": region_id},
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()

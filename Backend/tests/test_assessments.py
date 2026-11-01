"""Tests for Role 4 disaster assessment, review, and official reports.

Run from ``Backend/``: ``python -m unittest tests.test_assessments -v``.
Covers AI assessment generation with transparent workings, reason-required
edits with versioning, accept/reject decisions with immutability, verified
vs unverified feedback, PDF reports for approved assessments only, and
role enforcement. Skipped when FastAPI's TestClient is unavailable.
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("JWT_SECRET", "test-only-secret")
os.environ.setdefault("DEMO_LOGIN_PIN", "test-only-pin")

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _load_route_module(name, filename):
    path = os.path.join(_BACKEND_DIR, "api", "routes", filename)
    spec = importlib.util.spec_from_file_location(
        f"route_under_test_assess_{name}", os.path.abspath(path)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from services import json_store

    _AUTH_ROUTES = _load_route_module("auth", "auth.py")
    _ASSESS_ROUTES = _load_route_module("assessments", "assessments.py")

    def _build_app():
        app = FastAPI()
        app.include_router(_AUTH_ROUTES.router)
        app.include_router(_ASSESS_ROUTES.router)
        return app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - reported as skip reason
    TestClient = None  # type: ignore[assignment]
    json_store = None  # type: ignore[assignment]
    _build_app = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


def seed_store():
    json_store.write_collection("roles", {
        "role_1": {"name": "Disaster Assessment Officer", "level": 1, "isActive": True},
        "role_3": {"name": "Field Operations Officer", "level": 3, "isActive": True},
        "role_4": {"name": "Insurance Recovery Officer", "level": 4, "isActive": True},
    })
    json_store.write_collection("users", {
        "user_1": {"name": "Aarav Sharma", "email": "aarav.demo@example.com",
                   "roleId": "role_1", "isActive": True},
        "user_3": {"name": "Rahul Singh", "email": "rahul.demo@example.com",
                   "roleId": "role_3", "isActive": True},
        "user_4": {"name": "Ananya Patel", "email": "ananya.demo@example.com",
                   "roleId": "role_4", "isActive": True},
    })
    json_store.write_collection("regions", {
        "reg_1": {"name": "Test District", "code": "test-district",
                  "countryName": "India", "stateName": "Test State",
                  "active": True},
    })
    json_store.write_collection("hazards", {
        "cyclone": {"name": "Cyclone", "code": "cyclone", "active": True},
    })
    json_store.write_collection("tasks", {})
    json_store.write_collection("assessments", {})
    json_store.write_collection("assessment_feedback", {})


OBSERVED = {
    "householdsAffected": 500,
    "housesDamaged": 120,
    "housesDestroyed": 30,
    "cropHectares": 250.5,
    "livestockLost": 40,
    "infraSites": 3,
    "roadsKm": 12.5,
}


@unittest.skipIf(TestClient is None, f"TestClient unavailable: {_IMPORT_ERROR}")
class AssessmentFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(_build_app())

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="assess_flow_test_")
        patcher = mock.patch.dict(os.environ, {"DATABASE_DIR": self.tmpdir})
        self.addCleanup(patcher.stop)
        patcher.start()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        seed_store()
        self.role1 = self._login("user_1")
        self.role3 = self._login("user_3")
        self.role4 = self._login("user_4")

    def _login(self, user_id):
        response = self.client.post("/api/auth/login", json={"user_id": user_id})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _generate(self, observed=None):
        response = self.client.post("/api/assessments", json={
            "regionKey": "test-district",
            "hazardId": "cyclone",
            "observed": observed if observed is not None else OBSERVED,
            "notes": "Post-landfall review.",
        }, headers=self.role4)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["assessment"]

    def test_generate_explains_every_figure(self):
        assessment = self._generate()
        self.assertEqual(assessment["status"], "pending_review")
        self.assertTrue(assessment["publicId"].startswith("ASM-"))
        ai = assessment["aiAssessment"]
        self.assertIn("engineVersion", ai)
        self.assertTrue(ai["reasoning"])
        self.assertIn("disclaimer", ai)
        keys = {f["key"] for f in ai["figures"]}
        for expected in ("affected_people", "housing_loss_inr", "crop_loss_inr",
                          "total_damage_inr", "preparation_cost_inr",
                          "recovery_cost_inr", "indicative_relief_inr"):
            self.assertIn(expected, keys)
        for figure in ai["figures"]:
            for field in ("calculation", "assumptions", "sources", "confidence", "explanation"):
                self.assertIn(field, figure, figure.get("key"))
            self.assertTrue(figure["calculation"], figure.get("key"))
            self.assertTrue(figure["sources"], figure.get("key"))
        housing = next(f for f in ai["figures"] if f["key"] == "housing_loss_inr")
        self.assertEqual(housing["value"], 120 * 150000 + 30 * 500000)

    def test_role_enforcement(self):
        denied = self.client.post("/api/assessments", json={
            "regionKey": "test-district", "hazardId": "cyclone", "observed": {},
        }, headers=self.role3)
        self.assertEqual(denied.status_code, 403)
        denied1 = self.client.post("/api/assessments", json={
            "regionKey": "test-district", "hazardId": "cyclone", "observed": {},
        }, headers=self.role1)
        self.assertEqual(denied1.status_code, 403)
        # Role 1 may read for oversight.
        assessment = self._generate()
        fetched = self.client.get(f"/api/assessments/{assessment['id']}", headers=self.role1)
        self.assertEqual(fetched.status_code, 200)
        listed = self.client.get("/api/assessments", headers=self.role1)
        self.assertEqual(listed.json()["count"], 1)
        # Role 3 may not read assessments.
        forbidden = self.client.get("/api/assessments", headers=self.role3)
        self.assertEqual(forbidden.status_code, 403)

    def test_edit_requires_reason_and_preserves_ai(self):
        assessment = self._generate()
        task_id = assessment["id"]
        bad = self.client.patch(f"/api/assessments/{task_id}", json={
            "edits": [{"path": "figures.crop_loss_inr", "newValue": 100, "reason": "  "}],
        }, headers=self.role4)
        self.assertEqual(bad.status_code, 422)
        unknown = self.client.patch(f"/api/assessments/{task_id}", json={
            "edits": [{"path": "figures.nope", "newValue": 100, "reason": "test"}],
        }, headers=self.role4)
        self.assertEqual(unknown.status_code, 422)

        ai_value = next(
            f["value"] for f in assessment["aiAssessment"]["figures"]
            if f["key"] == "crop_loss_inr"
        )
        edited = self.client.patch(f"/api/assessments/{task_id}", json={
            "edits": [{"path": "figures.crop_loss_inr", "newValue": 999,
                       "reason": "Crop-cutting data revised the area."}],
        }, headers=self.role4)
        self.assertEqual(edited.status_code, 200, edited.text)
        updated = edited.json()["assessment"]
        self.assertEqual(updated["version"], 2)
        # AI record untouched; current reflects the correction.
        ai_after = next(
            f["value"] for f in updated["aiAssessment"]["figures"]
            if f["key"] == "crop_loss_inr"
        )
        self.assertEqual(ai_after, ai_value)
        current = next(
            f for f in updated["current"]["figures"] if f["key"] == "crop_loss_inr"
        )
        self.assertEqual(current["currentValue"], 999)
        self.assertTrue(current["edited"])
        self.assertEqual(len(updated["officialEdits"]), 1)
        self.assertEqual(updated["officialEdits"][0]["byId"], "user_4")
        self.assertTrue(any(h["action"] == "edited" for h in updated["approvalHistory"]))

    def test_accept_freezes_snapshot_and_verifies_feedback(self):
        assessment = self._generate()
        task_id = assessment["id"]
        self.client.patch(f"/api/assessments/{task_id}", json={
            "edits": [{"path": "figures.crop_loss_inr", "newValue": 999,
                       "reason": "Crop-cutting data revised the area."}],
        }, headers=self.role4)
        decided = self.client.post(f"/api/assessments/{task_id}/decision", json={
            "action": "accept", "reason": "Verified against block reports.",
        }, headers=self.role4)
        self.assertEqual(decided.status_code, 200, decided.text)
        updated = decided.json()["assessment"]
        self.assertEqual(updated["status"], "approved")
        self.assertIsNotNone(updated["approvedSnapshot"])
        snap = next(
            f for f in updated["approvedSnapshot"]["figures"] if f["key"] == "crop_loss_inr"
        )
        self.assertEqual(snap["currentValue"], 999)

        # Decided records are immutable.
        frozen = self.client.patch(f"/api/assessments/{task_id}", json={
            "edits": [{"path": "figures.crop_loss_inr", "newValue": 1, "reason": "late"}],
        }, headers=self.role4)
        self.assertEqual(frozen.status_code, 409)
        twice = self.client.post(f"/api/assessments/{task_id}/decision", json={
            "action": "reject", "reason": "late",
        }, headers=self.role4)
        self.assertEqual(twice.status_code, 409)

        feedback = self.client.get("/api/assessment-feedback", headers=self.role4).json()
        self.assertEqual(feedback["count"], 1)
        self.assertEqual(feedback["feedback"][0]["status"], "verified")
        self.assertEqual(feedback["feedback"][0]["path"], "figures.crop_loss_inr")

    def test_reject_keeps_feedback_unverified(self):
        assessment = self._generate()
        task_id = assessment["id"]
        self.client.patch(f"/api/assessments/{task_id}", json={
            "edits": [{"path": "figures.crop_loss_inr", "newValue": 5,
                       "reason": "Suspect input data."}],
        }, headers=self.role4)
        decided = self.client.post(f"/api/assessments/{task_id}/decision", json={
            "action": "reject", "reason": "Inputs unreliable; regenerate after survey.",
        }, headers=self.role4)
        self.assertEqual(decided.json()["assessment"]["status"], "rejected")
        feedback = self.client.get("/api/assessment-feedback", headers=self.role4).json()
        self.assertEqual(feedback["feedback"][0]["status"], "unverified")
        analysis = self.client.get("/api/assessment-feedback/analysis", headers=self.role4).json()
        self.assertEqual(analysis["count"], 0)

    def test_report_only_for_approved_and_versioned(self):
        assessment = self._generate()
        task_id = assessment["id"]
        early = self.client.get(f"/api/assessments/{task_id}/report.pdf", headers=self.role4)
        self.assertEqual(early.status_code, 409)

        self.client.post(f"/api/assessments/{task_id}/decision", json={
            "action": "accept", "reason": "Verified.",
        }, headers=self.role4)
        pdf = self.client.get(f"/api/assessments/{task_id}/report.pdf", headers=self.role4)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        again = self.client.get(f"/api/assessments/{task_id}/reports", headers=self.role4).json()
        self.assertEqual(again["count"], 1)
        regen = self.client.post(
            f"/api/assessments/{task_id}/reports/regenerate",
            json={"reason": "Reissued with corrected header."},
            headers=self.role4,
        )
        self.assertEqual(regen.status_code, 201)
        self.assertEqual(regen.json()["count"], 2)
        old = self.client.get(f"/api/assessments/{task_id}/report.pdf?version=1", headers=self.role4)
        self.assertEqual(old.status_code, 200)
        self.assertTrue(old.content.startswith(b"%PDF"))

    def test_verified_feedback_calibrates_future_estimates(self):
        for value in (11_000_000, 12_000_000, 13_000_000):
            assessment = self._generate()
            task_id = assessment["id"]
            self.client.patch(f"/api/assessments/{task_id}", json={
                "edits": [{"path": "figures.crop_loss_inr", "newValue": value,
                           "reason": "Mandi prices higher than plan rate."}],
            }, headers=self.role4)
            self.client.post(f"/api/assessments/{task_id}/decision", json={
                "action": "accept", "reason": "Verified.",
            }, headers=self.role4)
        analysis = self.client.get(
            "/api/assessment-feedback/analysis?hazardId=cyclone", headers=self.role4
        ).json()
        rows = [r for r in analysis["rows"] if r["path"] == "figures.crop_loss_inr"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["count"], 3)

        fresh = self._generate()
        crop = next(
            f for f in fresh["aiAssessment"]["figures"] if f["key"] == "crop_loss_inr"
        )
        self.assertIsNotNone(crop["calibratedFrom"])
        self.assertEqual(crop["calibratedFrom"]["feedbackCount"], 3)
        self.assertIn("Calibrated by", crop["calculation"])


if __name__ == "__main__":
    unittest.main()

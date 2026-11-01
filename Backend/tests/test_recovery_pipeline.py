"""Tests for the Recovery & Compensation assessment data pipeline.

Run from ``Backend/``: ``python -m unittest tests.test_recovery_pipeline -v``.
Covers engine figures built from real sources (tasks + field reports,
officer damage submissions, expense records, evidence attachments, local
geo/intelligence context), damage/expense/evidence CRUD with role
enforcement, and honest Unknown-with-reason behavior. Skipped when
FastAPI's TestClient is unavailable.
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
        f"route_under_test_recov_{name}", os.path.abspath(path)
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
    _TASKS_ROUTES = _load_route_module("tasks", "tasks.py")
    _ASSESS_ROUTES = _load_route_module("assessments", "assessments.py")
    _DAMAGE_ROUTES = _load_route_module("damage_assessments", "damage_assessments.py")
    _EXPENSE_ROUTES = _load_route_module("expenses", "expenses.py")
    _EVIDENCE_ROUTES = _load_route_module("evidence", "evidence.py")

    def _build_app():
        app = FastAPI()
        app.include_router(_AUTH_ROUTES.router)
        app.include_router(_TASKS_ROUTES.router)
        app.include_router(_ASSESS_ROUTES.router)
        app.include_router(_DAMAGE_ROUTES.router)
        app.include_router(_EXPENSE_ROUTES.router)
        app.include_router(_EVIDENCE_ROUTES.router)
        return app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - reported as skip reason
    TestClient = None  # type: ignore[assignment]
    json_store = None  # type: ignore[assignment]
    _build_app = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


REGION_CODE = "IN-PY-YNM"
REGION_INTEL_KEY = "in-py-ynm"
EMPTY_REGION = "IN-XX-ZZZ"
HAZARD = "cyclone"

PHOTO = {
    "filename": "ward-8-damage.jpg",
    "mimeType": "image/jpeg",
    "size": 12345,
    "dataUrl": "data:image/jpeg;base64,AAA",
}


def seed_store():
    json_store.write_collection("roles", {
        "role_1": {"name": "Disaster Assessment Officer", "level": 1, "isActive": True},
        "role_2": {"name": "Operations Planner", "level": 2, "isActive": True},
        "role_3": {"name": "Field Operations Officer", "level": 3, "isActive": True},
        "role_4": {"name": "Insurance Recovery Officer", "level": 4, "isActive": True},
    })
    json_store.write_collection("users", {
        "user_1": {"name": "Aarav Sharma", "email": "aarav.demo@example.com",
                   "roleId": "role_1", "isActive": True},
        "user_2": {"name": "Priya Verma", "email": "priya.demo@example.com",
                   "roleId": "role_2", "isActive": True},
        "user_3": {"name": "Rahul Singh", "email": "rahul.demo@example.com",
                   "roleId": "role_3", "isActive": True},
        "user_4": {"name": "Ananya Patel", "email": "ananya.demo@example.com",
                   "roleId": "role_4", "isActive": True},
    })
    json_store.write_collection("regions", {
        "reg_1": {"name": "Yanam", "code": REGION_CODE,
                  "countryName": "India", "stateName": "Puducherry",
                  "countryCode": "IN", "active": True},
        "reg_empty": {"name": "Empty District", "code": EMPTY_REGION,
                      "countryName": "India", "stateName": "Test State",
                      "active": True},
    })
    json_store.write_collection("hazards", {
        "cyclone": {"name": "Cyclone", "code": "cyclone", "active": True},
        "flood": {"name": "Flood", "code": "flood", "active": True},
    })
    json_store.write_collection("tasks", {})
    json_store.write_collection("assessments", {})
    json_store.write_collection("assessment_feedback", {})
    json_store.write_collection("damage_assessments", {})
    json_store.write_collection("expenses", {})
    json_store.write_collection("evidence_attachments", {})


@unittest.skipIf(TestClient is None, f"TestClient unavailable: {_IMPORT_ERROR}")
class RecoveryPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(_build_app())

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="recov_pipeline_test_")
        patcher = mock.patch.dict(os.environ, {"DATABASE_DIR": self.tmpdir})
        self.addCleanup(patcher.stop)
        patcher.start()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        seed_store()
        self.role1 = self._login("user_1")
        self.role2 = self._login("user_2")
        self.role3 = self._login("user_3")
        self.role4 = self._login("user_4")

    def _login(self, user_id):
        response = self.client.post("/api/auth/login", json={"user_id": user_id})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _mk_task_with_report(self, region_key=REGION_INTEL_KEY, people_assisted=42):
        created = self.client.post("/api/tasks", json={
            "title": "Assess ward damage",
            "department": "NDRF",
            "location": "Ward 08",
            "priority": "High",
            "assigneeUserId": "user_3",
            "regionKey": region_key,
        }, headers=self.role2)
        self.assertEqual(created.status_code, 201, created.text)
        task_id = created.json()["task"]["id"]
        updated = self.client.patch(f"/api/tasks/{task_id}", json={
            "report": {
                "text": "Roofs blown off along the canal road.",
                "peopleAssisted": people_assisted,
                "locationNote": "Canal Road, Ward 08",
                "photos": [PHOTO],
            },
        }, headers=self.role3)
        self.assertEqual(updated.status_code, 200, updated.text)
        return task_id

    def _post_damage(self, headers, **overrides):
        payload = {
            "regionKey": REGION_INTEL_KEY,
            "hazardId": HAZARD,
            "housesDamaged": 10,
            **overrides,
        }
        return self.client.post("/api/damage-assessments", json=payload, headers=headers)

    def _post_expense(self, headers, **overrides):
        payload = {
            "regionKey": REGION_INTEL_KEY,
            "hazardId": HAZARD,
            "kind": "preparedness",
            "category": "fuel",
            "amountInr": 50000,
            **overrides,
        }
        return self.client.post("/api/expenses", json=payload, headers=headers)

    def _generate(self, region_key=REGION_CODE, hazard_id=HAZARD, observed=None):
        response = self.client.post("/api/assessments", json={
            "regionKey": region_key,
            "hazardId": hazard_id,
            "observed": observed if observed is not None else {},
            "notes": "Pipeline check.",
        }, headers=self.role4)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["assessment"]

    def _figures(self, assessment):
        return {f["key"]: f for f in assessment["aiAssessment"]["figures"]}

    def test_engine_uses_damage_and_expense_evidence(self):
        self._mk_task_with_report()
        first = self._post_damage(self.role3, householdsAffected=100, housesDamaged=10)
        self.assertEqual(first.status_code, 201, first.text)
        second = self._post_damage(
            self.role1, householdsAffected=50, housesDamaged=5, housesDestroyed=2
        )
        self.assertEqual(second.status_code, 201, second.text)
        prep = self._post_expense(self.role2, kind="preparedness", amountInr=500000,
                                  receiptRef="R-001")
        self.assertEqual(prep.status_code, 201, prep.text)
        rec = self._post_expense(self.role4, kind="recovery", amountInr=200000,
                                 receiptRef="R-002")
        self.assertEqual(rec.status_code, 201, rec.text)

        assessment = self._generate(observed={})
        figures = self._figures(assessment)
        # 150 households x 4.4 from summed submissions.
        self.assertEqual(figures["affected_people"]["value"], round(150 * 4.4))
        self.assertIn("damage submission", figures["affected_people"]["calculation"])
        # (10+5) damaged x 150k + 2 destroyed x 500k from summed submissions.
        self.assertEqual(figures["housing_loss_inr"]["value"], 15 * 150000 + 2 * 500000)
        # Observed spend beats modelled proxies.
        self.assertEqual(figures["preparation_cost_inr"]["value"], 500000)
        self.assertEqual(figures["recovery_cost_inr"]["value"], 200000)
        self.assertIn("expense record", figures["preparation_cost_inr"]["calculation"])
        # Every figure carries workings and cites the new sources.
        for figure in figures.values():
            for field in ("calculation", "assumptions", "sources", "confidence", "explanation"):
                self.assertIn(field, figure, figure.get("key"))
            names = {s["name"] for s in figure["sources"]}
            self.assertIn("damage_assessments.json", names, figure.get("key"))
            self.assertIn("expenses.json", names, figure.get("key"))
        summary = assessment["aiAssessment"]["evidenceSummary"]
        self.assertEqual(summary["damageAssessmentCount"], 2)
        self.assertEqual(summary["expenseCount"], 2)
        self.assertEqual(summary["observedPreparednessInr"], 500000)
        self.assertEqual(summary["observedRecoveryInr"], 200000)
        self.assertEqual(summary["reportCount"], 1)
        self.assertEqual(summary["peopleAssistedSum"], 42)
        self.assertGreaterEqual(summary["photoCount"], 1)

    def test_observed_inputs_beat_submitted_sums(self):
        self._post_damage(self.role3, housesDamaged=100)
        self._post_expense(self.role2, kind="preparedness", amountInr=999999)
        assessment = self._generate(
            observed={"housesDamaged": 7, "preparationCostInr": 111}
        )
        figures = self._figures(assessment)
        self.assertEqual(figures["housing_loss_inr"]["value"], 7 * 150000)
        self.assertIn("officer observation", figures["housing_loss_inr"]["calculation"].lower())
        self.assertEqual(figures["preparation_cost_inr"]["value"], 111)

    def test_unknown_with_reason_when_no_evidence(self):
        assessment = self._generate(region_key=EMPTY_REGION, observed={})
        figures = self._figures(assessment)
        for key in ("affected_people", "housing_loss_inr", "crop_loss_inr",
                    "livestock_loss_inr", "infrastructure_loss_inr",
                    "preparation_cost_inr", "recovery_cost_inr",
                    "indicative_relief_inr"):
            self.assertIsNone(figures[key]["value"], key)
            self.assertIn("cannot compute", figures[key]["calculation"], key)
            self.assertTrue(figures[key]["explanation"], key)
        # The total names its missing lines instead: nothing to sum.
        self.assertIsNone(figures["total_damage_inr"]["value"])
        self.assertIn("nothing to sum", figures["total_damage_inr"]["calculation"])
        self.assertTrue(figures["total_damage_inr"]["explanation"])
        # The missing data is named, not just "unknown".
        self.assertIn("damage submissions", figures["housing_loss_inr"]["calculation"])
        self.assertIn("expense records", figures["preparation_cost_inr"]["calculation"])
        summary = assessment["aiAssessment"]["evidenceSummary"]
        self.assertTrue(summary["gaps"])

    def test_assisted_lower_bound_labelled_not_a_headcount(self):
        self._mk_task_with_report(people_assisted=42)
        assessment = self._generate(observed={})
        affected = self._figures(assessment)["affected_people"]
        self.assertEqual(affected["value"], 42)
        self.assertIn("lower bound", affected["calculation"])
        self.assertIn("lower bound", affected["explanation"])
        self.assertEqual(affected["confidence"], "Low")

    def test_regional_population_never_used_as_affected(self):
        self._post_damage(self.role3, householdsAffected=10)
        assessment = self._generate(observed={})
        figures = self._figures(assessment)
        summary = assessment["aiAssessment"]["evidenceSummary"]
        # No cached ambient total exists locally; the slot stays None.
        self.assertIsNone(summary["regionalPopulation"])
        self.assertIn("context only", summary["regionalPopulationNote"])
        # The guard travels with the affected figure in every branch.
        guard = [a for a in figures["affected_people"]["assumptions"] if "context only" in a]
        self.assertTrue(guard)
        empty = self._generate(region_key=EMPTY_REGION, observed={})
        self.assertIsNone(self._figures(empty)["affected_people"]["value"])

    def test_damage_crud_and_role_enforcement(self):
        denied = self._post_damage(self.role2)
        self.assertEqual(denied.status_code, 403)
        empty = self.client.post("/api/damage-assessments", json={
            "regionKey": REGION_CODE, "hazardId": HAZARD,
        }, headers=self.role3)
        self.assertEqual(empty.status_code, 422)

        own = self._post_damage(self.role3, housesDamaged=4)
        self.assertEqual(own.status_code, 201, own.text)
        own_id = own.json()["damageAssessment"]["id"]
        other = self._post_damage(self.role1, housesDamaged=6)
        self.assertEqual(other.status_code, 201, other.text)

        mine = self.client.get("/api/damage-assessments", headers=self.role3).json()
        self.assertEqual(mine["count"], 1)
        oversight = self.client.get("/api/damage-assessments", headers=self.role1).json()
        self.assertEqual(oversight["count"], 2)
        planner = self.client.get("/api/damage-assessments", headers=self.role2)
        self.assertEqual(planner.status_code, 403)

        forbidden = self.client.get(
            f"/api/damage-assessments/{other.json()['damageAssessment']['id']}",
            headers=self.role3,
        )
        self.assertEqual(forbidden.status_code, 403)

        no_reason = self.client.patch(f"/api/damage-assessments/{own_id}", json={
            "housesDamaged": 5, "reason": "  ",
        }, headers=self.role3)
        self.assertEqual(no_reason.status_code, 422)
        fixed = self.client.patch(f"/api/damage-assessments/{own_id}", json={
            "housesDamaged": 5, "reason": "Recount from ward list.",
        }, headers=self.role3)
        self.assertEqual(fixed.status_code, 200, fixed.text)
        self.assertEqual(fixed.json()["damageAssessment"]["housesDamaged"], 5)

        removed = self.client.delete(f"/api/damage-assessments/{own_id}", headers=self.role3)
        self.assertEqual(removed.status_code, 200)
        gone = self.client.get(f"/api/damage-assessments/{own_id}", headers=self.role4)
        self.assertEqual(gone.status_code, 404)

    def test_expense_crud_and_role_enforcement(self):
        denied = self._post_expense(self.role1)
        self.assertEqual(denied.status_code, 403)
        bad_kind = self._post_expense(self.role2, kind="relief")
        self.assertEqual(bad_kind.status_code, 422)
        bad_amount = self._post_expense(self.role2, amountInr=0)
        self.assertEqual(bad_amount.status_code, 422)

        planner = self._post_expense(self.role2, category="tarpaulin", amountInr=75000)
        self.assertEqual(planner.status_code, 201, planner.text)
        field = self._post_expense(self.role3, kind="recovery", category="debris",
                                   amountInr=20000)
        self.assertEqual(field.status_code, 201, field.text)
        field_id = field.json()["expense"]["id"]

        mine = self.client.get("/api/expenses", headers=self.role3).json()
        self.assertEqual(mine["count"], 1)
        oversight = self.client.get("/api/expenses", headers=self.role1).json()
        self.assertEqual(oversight["count"], 2)
        self.assertEqual(oversight["totalInr"], 95000)

        fixed = self.client.patch(f"/api/expenses/{field_id}", json={
            "amountInr": 25000, "receiptRef": "R-9", "reason": "Bill total corrected.",
        }, headers=self.role3)
        self.assertEqual(fixed.status_code, 200, fixed.text)
        self.assertEqual(fixed.json()["expense"]["amountInr"], 25000)

        stranger = self.client.delete(
            f"/api/expenses/{field_id}", headers=self.role2
        )
        self.assertEqual(stranger.status_code, 403)
        removed = self.client.delete(f"/api/expenses/{field_id}", headers=self.role4)
        self.assertEqual(removed.status_code, 200)

    def test_evidence_upload_validation_and_linking(self):
        task_id = self._mk_task_with_report()
        ok = self.client.post("/api/evidence", json={
            "linkedKind": "task",
            "linkedId": task_id,
            "caption": "Canal road roof damage.",
            "photos": [PHOTO],
        }, headers=self.role3)
        self.assertEqual(ok.status_code, 201, ok.text)
        body = ok.json()["evidence"]
        # Region backfilled from the linked task record.
        self.assertEqual(body["regionKey"], REGION_INTEL_KEY)
        self.assertEqual(body["photoCount"], 1)

        non_image = self.client.post("/api/evidence", json={
            "linkedKind": "task", "linkedId": task_id,
            "photos": [{**PHOTO, "mimeType": "application/pdf"}],
        }, headers=self.role3)
        self.assertEqual(non_image.status_code, 422)
        too_many = self.client.post("/api/evidence", json={
            "linkedKind": "task", "linkedId": task_id, "photos": [PHOTO] * 6,
        }, headers=self.role3)
        self.assertEqual(too_many.status_code, 422)
        too_big = self.client.post("/api/evidence", json={
            "linkedKind": "task", "linkedId": task_id,
            "photos": [{**PHOTO, "size": 8_000_001}],
        }, headers=self.role3)
        self.assertEqual(too_big.status_code, 422)
        missing = self.client.post("/api/evidence", json={
            "linkedKind": "task", "linkedId": "no-such-task", "photos": [PHOTO],
        }, headers=self.role3)
        self.assertEqual(missing.status_code, 404)

        # Lists trim dataUrl bytes; single fetch keeps them.
        listed = self.client.get("/api/evidence", headers=self.role4).json()
        self.assertEqual(listed["count"], 1)
        self.assertNotIn("dataUrl", listed["evidence"][0]["photos"][0])
        single = self.client.get(f"/api/evidence/{body['id']}", headers=self.role4).json()
        self.assertIn("dataUrl", single["evidence"]["photos"][0])

        assessment = self._generate(observed={})
        summary = assessment["aiAssessment"]["evidenceSummary"]
        self.assertEqual(summary["evidenceAttachmentCount"], 1)
        # 1 field-report photo + 1 linked evidence photo.
        self.assertEqual(summary["photoCount"], 2)

    def test_expense_totals_ignore_other_region_and_hazard(self):
        self._post_expense(self.role2, amountInr=100000)
        self._post_expense(self.role2, amountInr=50000, hazardId=None)
        self._post_expense(self.role2, amountInr=999999, regionKey=EMPTY_REGION)
        self._post_expense(self.role2, amountInr=888888, hazardId="flood")
        assessment = self._generate(observed={})
        figures = self._figures(assessment)
        # Only same-region cyclone (or unassigned-hazard) spend counts.
        self.assertEqual(figures["preparation_cost_inr"]["value"], 150000)


if __name__ == "__main__":
    unittest.main()

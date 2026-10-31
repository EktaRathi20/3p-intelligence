"""Tests for operational tasks and notifications (Role 2 -> Role 3).

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
Covers the Role 2 assignment flow: task creation persists server-side,
Role 3 sees only their own assignments and inbox notifications, and
role enforcement rejects unauthorized writes.
Skipped when ``httpx`` (required by FastAPI's TestClient) is missing.
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
        f"route_under_test_ops_{name}", os.path.abspath(path)
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
    _NOTIFICATIONS_ROUTES = _load_route_module("notifications", "notifications.py")

    def _build_app():
        app = FastAPI()
        app.include_router(_AUTH_ROUTES.router)
        app.include_router(_TASKS_ROUTES.router)
        app.include_router(_NOTIFICATIONS_ROUTES.router)
        return app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - reported as skip reason
    TestClient = None  # type: ignore[assignment]
    json_store = None  # type: ignore[assignment]
    _build_app = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


def seed_store():
    json_store.write_collection("roles", {
        "role_2": {"name": "Operations Planner", "level": 2, "isActive": True},
        "role_3": {"name": "Field Operations Officer", "level": 3, "isActive": True},
        "role_4": {"name": "Insurance Recovery Officer", "level": 4, "isActive": True},
    })
    json_store.write_collection("users", {
        "user_2": {"name": "Priya Verma", "email": "priya.demo@example.com",
                   "roleId": "role_2", "isActive": True},
        "user_3": {"name": "Rahul Singh", "email": "rahul.demo@example.com",
                   "roleId": "role_3", "isActive": True},
        "user_4": {"name": "Ananya Patel", "email": "ananya.demo@example.com",
                   "roleId": "role_4", "isActive": True},
    })
    json_store.write_collection("tasks", {})
    json_store.write_collection("notifications", {})


@unittest.skipIf(TestClient is None, f"TestClient unavailable: {_IMPORT_ERROR}")
class OperationalFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(_build_app())

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ops_flow_test_")
        patcher = mock.patch.dict(os.environ, {"DATABASE_DIR": self.tmpdir})
        self.addCleanup(patcher.stop)
        patcher.start()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        seed_store()
        self.role2 = self._login("user_2")
        self.role3 = self._login("user_3")
        self.role4 = self._login("user_4")

    def _login(self, user_id):
        response = self.client.post("/api/auth/login", json={"user_id": user_id})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_role2_assigns_task_role3_sees_it(self):
        created = self.client.post("/api/tasks", json={
            "title": "Assess flood impact in affected ward",
            "department": "NDRF",
            "location": "Ward 08",
            "priority": "Critical",
            "assigneeUserId": "user_3",
            "instructions": "Record water level",
            "deadline": "2026-11-01T14:30:00+05:30",
            "source": "ai",
            "sourceRef": "AI-01",
            "regionKey": "surat",
        }, headers=self.role2)
        self.assertEqual(created.status_code, 201, created.text)
        task = created.json()["task"]
        self.assertEqual(task["assigneeUserId"], "user_3")
        self.assertEqual(task["status"], "Assigned")

        # Role 3 inbox: sees the assignment.
        mine = self.client.get("/api/tasks", headers=self.role3)
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.json()["count"], 1)
        self.assertEqual(mine.json()["tasks"][0]["id"], task["id"])

        # Role 4 is not the assignee and not Role 2: cannot update.
        forbidden = self.client.patch(
            f"/api/tasks/{task['id']}", json={"status": "In Progress"},
            headers=self.role4,
        )
        self.assertEqual(forbidden.status_code, 403)

        # Assignee can progress and submit a field report.
        progress = self.client.patch(
            f"/api/tasks/{task['id']}", json={"status": "In Progress"},
            headers=self.role3,
        )
        self.assertEqual(progress.status_code, 200)
        self.assertEqual(progress.json()["task"]["status"], "In Progress")

        reported = self.client.patch(
            f"/api/tasks/{task['id']}",
            json={"report": {"text": "Water receding, road passable",
                             "peopleAssisted": 12,
                             "locationNote": "Ward 08 bridge"}},
            headers=self.role3,
        )
        self.assertEqual(reported.status_code, 200)
        updated = reported.json()["task"]
        self.assertEqual(updated["status"], "Submitted")
        self.assertEqual(len(updated["reports"]), 1)

    def test_role3_only_sees_own_tasks(self):
        self.client.post("/api/tasks", json={
            "title": "Task A", "department": "NDRF", "location": "Ward 1",
            "assigneeUserId": "user_3",
        }, headers=self.role2)
        # Role 2 sees everything.
        all_tasks = self.client.get("/api/tasks", headers=self.role2)
        self.assertEqual(all_tasks.json()["count"], 1)
        # Role 3 cannot list another officer's work via query override.
        filtered = self.client.get(
            "/api/tasks?assigneeUserId=user_4", headers=self.role3
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["count"], 1)
        self.assertEqual(filtered.json()["tasks"][0]["assigneeUserId"], "user_3")

    def test_role3_cannot_create_tasks(self):
        response = self.client.post("/api/tasks", json={
            "title": "Sneaky", "department": "NDRF", "location": "Ward 9",
            "assigneeUserId": "user_3",
        }, headers=self.role3)
        self.assertEqual(response.status_code, 403)

    def test_notification_reaches_role3_inbox(self):
        sent = self.client.post("/api/notifications", json={
            "recipientUserId": "user_3",
            "message": "Task AI-01 assigned: assess Ward 08 flooding today.",
            "priority": "Critical",
            "regionKey": "surat",
        }, headers=self.role2)
        self.assertEqual(sent.status_code, 201, sent.text)

        inbox = self.client.get("/api/notifications?box=inbox", headers=self.role3)
        self.assertEqual(inbox.status_code, 200)
        body = inbox.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["unread"], 1)
        self.assertEqual(body["notifications"][0]["message"][:4], "Task")

        outbox = self.client.get("/api/notifications?box=sent", headers=self.role2)
        self.assertEqual(outbox.json()["count"], 1)

        marked = self.client.patch(
            f"/api/notifications/{body['notifications'][0]['id']}/read",
            headers=self.role3,
        )
        self.assertEqual(marked.status_code, 200)
        inbox2 = self.client.get("/api/notifications?box=inbox", headers=self.role3)
        self.assertEqual(inbox2.json()["unread"], 0)

    def test_role3_cannot_send_notifications(self):
        response = self.client.post("/api/notifications", json={
            "recipientUserId": "user_3",
            "message": "Trying to send as field officer, should fail.",
        }, headers=self.role3)
        self.assertEqual(response.status_code, 403)

    def test_assignment_auto_notifies_role3_inbox(self):
        created = self.client.post("/api/tasks", json={
            "title": "Clear blocked drain on Main Road",
            "department": "Municipal Corp",
            "location": "Ward 05",
            "priority": "High",
            "assigneeUserId": "user_3",
            "regionKey": "surat",
        }, headers=self.role2)
        self.assertEqual(created.status_code, 201, created.text)
        task_id = created.json()["task"]["id"]

        inbox = self.client.get("/api/notifications?box=inbox", headers=self.role3)
        self.assertEqual(inbox.status_code, 200)
        body = inbox.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["unread"], 1)
        notification = body["notifications"][0]
        self.assertEqual(notification["recipientUserId"], "user_3")
        self.assertEqual(notification["taskId"], task_id)
        self.assertIn("assigned", notification["message"].lower())

    def test_assignment_without_notify_skips_notification(self):
        created = self.client.post("/api/tasks", json={
            "title": "Silent task without notification",
            "department": "NDRF",
            "location": "Ward 06",
            "assigneeUserId": "user_3",
            "notifyAssignee": False,
        }, headers=self.role2)
        self.assertEqual(created.status_code, 201, created.text)

        inbox = self.client.get("/api/notifications?box=inbox", headers=self.role3)
        self.assertEqual(inbox.json()["count"], 0)

    def test_start_sets_progress_50_and_submit_sets_100(self):
        created = self.client.post("/api/tasks", json={
            "title": "Inspect shelter readiness",
            "department": "Revenue Department",
            "location": "Ward 07",
            "assigneeUserId": "user_3",
        }, headers=self.role2)
        task_id = created.json()["task"]["id"]

        started = self.client.patch(
            f"/api/tasks/{task_id}",
            json={"status": "In Progress", "progress": 50},
            headers=self.role3,
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["task"]["progress"], 50)

        submitted = self.client.patch(
            f"/api/tasks/{task_id}", json={"status": "Submitted"},
            headers=self.role3,
        )
        self.assertEqual(submitted.status_code, 200)
        updated = submitted.json()["task"]
        self.assertEqual(updated["status"], "Submitted")
        self.assertEqual(updated["progress"], 100)

    def test_start_without_progress_defaults_to_50(self):
        created = self.client.post("/api/tasks", json={
            "title": "Check waterlogging near station",
            "department": "PWD Water Supply",
            "location": "Ward 09",
            "assigneeUserId": "user_3",
        }, headers=self.role2)
        task_id = created.json()["task"]["id"]

        started = self.client.patch(
            f"/api/tasks/{task_id}", json={"status": "In Progress"},
            headers=self.role3,
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["task"]["progress"], 50)

    def test_field_report_with_photos_notifies_role2(self):
        created = self.client.post("/api/tasks", json={
            "title": "Document damage on Bridge Road",
            "department": "PWD Water Supply",
            "location": "Ward 11",
            "priority": "Critical",
            "assigneeUserId": "user_3",
        }, headers=self.role2)
        task_id = created.json()["task"]["id"]

        reported = self.client.patch(
            f"/api/tasks/{task_id}",
            json={"report": {
                "text": "Crack across the carriageway, needs barricading",
                "peopleAssisted": 4,
                "locationNote": "Bridge Road junction",
                "photos": [{
                    "filename": "crack.jpg",
                    "mimeType": "image/jpeg",
                    "size": 1234,
                    "dataUrl": "data:image/jpeg;base64,/9j/4AAQ",
                }],
            }},
            headers=self.role3,
        )
        self.assertEqual(reported.status_code, 200, reported.text)
        updated = reported.json()["task"]
        self.assertEqual(updated["status"], "Submitted")
        self.assertEqual(updated["progress"], 100)
        self.assertEqual(len(updated["reports"]), 1)
        self.assertEqual(len(updated["reports"][0]["photos"]), 1)
        self.assertEqual(updated["reports"][0]["photos"][0]["filename"], "crack.jpg")

        inbox = self.client.get("/api/notifications?box=inbox", headers=self.role2)
        self.assertEqual(inbox.status_code, 200)
        body = inbox.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["notifications"][0]["recipientUserId"], "user_2")
        self.assertEqual(body["notifications"][0]["taskId"], task_id)
        self.assertIn("submitted", body["notifications"][0]["message"].lower())

    def test_mark_submitted_without_report_notifies_role2(self):
        created = self.client.post("/api/tasks", json={
            "title": "Clear debris from service lane",
            "department": "Municipal Corp",
            "location": "Ward 13",
            "priority": "High",
            "assigneeUserId": "user_3",
        }, headers=self.role2)
        self.assertEqual(created.status_code, 201, created.text)
        task_id = created.json()["task"]["id"]

        submitted = self.client.patch(
            f"/api/tasks/{task_id}", json={"status": "Submitted"},
            headers=self.role3,
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["task"]["status"], "Submitted")

        inbox = self.client.get("/api/notifications?box=inbox", headers=self.role2)
        self.assertEqual(inbox.status_code, 200)
        body = inbox.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["notifications"][0]["recipientUserId"], "user_2")
        self.assertEqual(body["notifications"][0]["taskId"], task_id)
        message = body["notifications"][0]["message"].lower()
        self.assertIn("submitted", message)
        self.assertTrue(
            "complet" in message or "done" in message,
            f"Role 2 completion notice should say the task is done: {message}",
        )

    def test_completion_notifies_all_role2_officers(self):
        json_store.set_document("users", "user_2b", {
            "name": "Second Planner", "email": "planner2.demo@example.com",
            "roleId": "role_2", "isActive": True,
        })
        role2b = self._login("user_2b")

        created = self.client.post("/api/tasks", json={
            "title": "Restore power to shelter",
            "department": "Power Utility",
            "location": "Ward 14",
            "assigneeUserId": "user_3",
        }, headers=self.role2)
        task_id = created.json()["task"]["id"]

        submitted = self.client.patch(
            f"/api/tasks/{task_id}", json={"status": "Submitted"},
            headers=self.role3,
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)

        for headers, user_id in ((self.role2, "user_2"), (role2b, "user_2b")):
            inbox = self.client.get("/api/notifications?box=inbox", headers=headers)
            self.assertEqual(inbox.status_code, 200)
            body = inbox.json()
            self.assertEqual(body["count"], 1, f"expected Role 2 inbox for {user_id}")
            self.assertEqual(body["notifications"][0]["taskId"], task_id)

    def test_report_rejects_non_image_evidence(self):
        created = self.client.post("/api/tasks", json={
            "title": "Task with bad attachment",
            "department": "NDRF",
            "location": "Ward 12",
            "assigneeUserId": "user_3",
        }, headers=self.role2)
        task_id = created.json()["task"]["id"]

        response = self.client.patch(
            f"/api/tasks/{task_id}",
            json={"report": {
                "text": "Attempt with a non-image file",
                "photos": [{
                    "filename": "notes.txt",
                    "mimeType": "text/plain",
                    "size": 10,
                    "dataUrl": "data:text/plain;base64,aGk=",
                }],
            }},
            headers=self.role3,
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()

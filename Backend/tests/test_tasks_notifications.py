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


if __name__ == "__main__":
    unittest.main()

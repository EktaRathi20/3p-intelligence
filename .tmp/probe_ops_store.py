"""Throwaway runtime probe: tasks/notifications collections via real json_store.

Exercises the exact persistence surface the new /api/tasks and
/api/notifications routes use, against a temp DATABASE_DIR. Run from
Backend/: <python> ../.tmp/probe_ops_store.py
"""
import os
import sys
import tempfile

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Backend"))
sys.path.insert(0, BACKEND_DIR)

tmpdir = tempfile.mkdtemp(prefix="ops_store_probe_")
os.environ["DATABASE_DIR"] = tmpdir

from services import json_store  # noqa: E402

failures = []


def check(name, condition, detail=""):
    print(("PASS " if condition else "FAIL ") + name + (f" ({detail})" if detail and not condition else ""))
    if not condition:
        failures.append(name)


# 1. New collections are registered and start empty.
check("tasks collection registered", "tasks" in json_store.COLLECTION_FILES)
check("notifications collection registered", "notifications" in json_store.COLLECTION_FILES)
check("tasks starts empty", json_store.list_documents("tasks") == [])
check("notifications starts empty", json_store.list_documents("notifications") == [])

# 2. Task write/read round-trip with id injection (mirrors create_task).
task_id = json_store.generate_id()
task = json_store.set_document("tasks", task_id, {
    "title": "Assess flood impact", "department": "NDRF", "location": "Ward 08",
    "priority": "Critical", "assigneeUserId": "user_3", "assigneeName": "Rahul Singh",
    "instructions": "", "deadline": "2026-11-01T14:30:00+05:30", "status": "Assigned",
    "progress": 0, "source": "ai", "sourceRef": "AI-01", "regionKey": "surat",
    "createdAt": json_store.utcnow_iso(), "createdById": "user_2",
    "createdByName": "Priya Verma", "updatedAt": json_store.utcnow_iso(), "reports": [],
})
check("task id injected", task["id"] == task_id)
fetched = json_store.get_document("tasks", task_id)
check("task readable", fetched is not None and fetched["assigneeUserId"] == "user_3")

# 3. Task update merges fields and preserves the rest (mirrors update_task).
updated = json_store.update_document("tasks", task_id, {"status": "Submitted", "progress": 100})
check("task status updated", updated["status"] == "Submitted" and updated["progress"] == 100)
check("task fields preserved", updated["title"] == "Assess flood impact" and updated["sourceRef"] == "AI-01")

# 4. Role-3 style filtering works on stored shape.
json_store.set_document("tasks", json_store.generate_id(), {
    "title": "Other", "assigneeUserId": "user_9", "status": "Assigned"})
mine = [t for t in json_store.list_documents("tasks") if t.get("assigneeUserId") == "user_3"]
check("assignee filter isolates Role 3 work", len(mine) == 1 and mine[0]["id"] == task_id)

# 5. Notification write/read round-trip (mirrors create_notification).
notif_id = json_store.generate_id()
notif = json_store.set_document("notifications", notif_id, {
    "recipientUserId": "user_3", "recipientName": "Rahul Singh",
    "senderId": "user_2", "senderName": "Priya Verma",
    "message": "Task AI-01 assigned: assess Ward 08 flooding today.",
    "priority": "Critical", "taskId": task_id, "regionKey": "surat",
    "read": False, "createdAt": json_store.utcnow_iso(),
})
check("notification id injected", notif["id"] == notif_id)
inbox = [n for n in json_store.list_documents("notifications")
         if n.get("recipientUserId") == "user_3"]
check("inbox filter finds notification", len(inbox) == 1)
marked = json_store.update_document("notifications", notif_id, {"read": True})
check("mark-read persists", marked["read"] is True)

# 6. Files landed on disk as JSON objects keyed by id.
import json  # noqa: E402
raw_tasks = json.load(open(os.path.join(tmpdir, "tasks.json"), encoding="utf-8"))
raw_notifs = json.load(open(os.path.join(tmpdir, "notifications.json"), encoding="utf-8"))
check("tasks.json keyed by id", task_id in raw_tasks and "id" not in raw_tasks[task_id])
check("notifications.json keyed by id", notif_id in raw_notifs)

# 7. Unknown collections still rejected.
try:
    json_store.list_documents("bogus")
    check("unknown collection rejected", False, "no error raised")
except KeyError:
    check("unknown collection rejected", True)

print(f"\n{len(failures)} failures")
sys.exit(1 if failures else 0)

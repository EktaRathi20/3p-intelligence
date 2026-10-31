"""Operational task endpoints (Role 2 assigns, Role 3 executes).

Backed by the local JSON database (``tasks.json`` via ``json_store``).
Role 2 (Operations Planner) creates assignments; Role 3 (Field Operations
Officer) lists work assigned to them and reports progress. Reads return an
object envelope (``{success, count, tasks}``) so empty lists are valid
responses for the frontend HTTP client.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import json_store
from services.auth_context import is_role_2, is_role_3, require_current_user

router = APIRouter()

TASKS_COLLECTION = "tasks"
USERS_COLLECTION = "users"
NOTIFICATIONS_COLLECTION = "notifications"

TaskStatus = Literal["Assigned", "In Progress", "Submitted"]
TaskPriority = Literal["Critical", "High", "Medium", "Low"]
TaskSource = Literal["ai", "manual"]

MAX_REPORT_PHOTOS = 5
MAX_PHOTO_BYTES = 8_000_000
MAX_PHOTO_DATA_URL_CHARS = 12_000_000


class PhotoAttachmentInput(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mimeType: str = Field(default="image/jpeg", max_length=100)
    size: int = Field(default=0, ge=0, le=MAX_PHOTO_BYTES)
    dataUrl: str = Field(min_length=1, max_length=MAX_PHOTO_DATA_URL_CHARS)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    department: str = Field(min_length=1, max_length=150)
    location: str = Field(min_length=1, max_length=300)
    priority: TaskPriority = "Medium"
    assigneeUserId: str = Field(min_length=1, max_length=100)
    instructions: str = Field(default="", max_length=2000)
    deadline: Optional[str] = Field(default=None, max_length=64)
    source: TaskSource = "manual"
    sourceRef: Optional[str] = Field(default=None, max_length=64)
    regionKey: Optional[str] = Field(default=None, max_length=150)
    notifyAssignee: bool = True


class FieldReportInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    peopleAssisted: Optional[int] = Field(default=None, ge=0, le=1000000)
    locationNote: Optional[str] = Field(default=None, max_length=300)
    photos: Optional[list[PhotoAttachmentInput]] = Field(default=None, max_length=MAX_REPORT_PHOTOS)


class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    department: Optional[str] = Field(default=None, min_length=1, max_length=150)
    location: Optional[str] = Field(default=None, min_length=1, max_length=300)
    priority: Optional[TaskPriority] = None
    instructions: Optional[str] = Field(default=None, max_length=2000)
    deadline: Optional[str] = Field(default=None, max_length=64)
    assigneeUserId: Optional[str] = Field(default=None, min_length=1, max_length=100)
    report: Optional[FieldReportInput] = None
    notifyAssignee: Optional[bool] = None


def _resolve_assignee(assignee_user_id: str) -> dict[str, Any]:
    assignee = json_store.get_document(USERS_COLLECTION, assignee_user_id)
    if assignee is None:
        raise HTTPException(status_code=422, detail="Assigned user not found")
    if not assignee.get("isActive", False):
        raise HTTPException(status_code=422, detail="Assigned user is inactive")
    return assignee


def _task_sort_key(task: dict[str, Any]) -> str:
    return str(task.get("createdAt") or task.get("id") or "")


def _create_inapp_notification(
    *,
    recipient_user_id: str,
    sender_id: str,
    sender_name: str,
    message: str,
    priority: str,
    task_id: Optional[str],
    region_key: Optional[str],
) -> Optional[dict[str, Any]]:
    """Write one in-app notification; never raises (task flow must not fail)."""
    try:
        recipient = json_store.get_document(USERS_COLLECTION, str(recipient_user_id))
        if recipient is None or not recipient.get("isActive", False):
            return None
        if str(recipient_user_id) == str(sender_id):
            return None
        record = {
            "recipientUserId": str(recipient_user_id),
            "recipientName": str(recipient.get("name", "")),
            "senderId": str(sender_id),
            "senderName": str(sender_name),
            "message": str(message).strip(),
            "priority": str(priority or "Medium"),
            "taskId": task_id,
            "regionKey": region_key,
            "read": False,
            "createdAt": json_store.utcnow_iso(),
        }
        return json_store.set_document(
            NOTIFICATIONS_COLLECTION, json_store.generate_id(), record
        )
    except Exception:
        return None


def _assignment_message(task: dict[str, Any]) -> str:
    title = str(task.get("title") or "a new field task")
    location = str(task.get("location") or "the assigned area")
    priority = str(task.get("priority") or "Medium")
    return (
        f"You have been assigned a new task: {title} "
        f"({location}, {priority} priority). Open Field Operations to start it."
    )


def _submission_message(task: dict[str, Any], submitter_name: str) -> str:
    title = str(task.get("title") or "a field task")
    location = str(task.get("location") or "")
    suffix = f" at {location}" if location else ""
    return (
        f"Field report submitted for '{title}'{suffix} "
        f"by {submitter_name or 'the field officer'}. Please review it."
    )


@router.post("/api/tasks", status_code=201)
def create_task(
    payload: TaskCreate, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    """Create an operational task. Role 2 only."""
    if not is_role_2(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only the Operations Planner (Role 2) can assign tasks",
        )
    try:
        assignee = _resolve_assignee(payload.assigneeUserId)
        now = json_store.utcnow_iso()
        task_id = json_store.generate_id()
        record = {
            "title": payload.title.strip(),
            "department": payload.department.strip(),
            "location": payload.location.strip(),
            "priority": payload.priority,
            "assigneeUserId": str(payload.assigneeUserId),
            "assigneeName": str(assignee.get("name", "")),
            "instructions": payload.instructions.strip(),
            "deadline": payload.deadline,
            "status": "Assigned",
            "progress": 0,
            "source": payload.source,
            "sourceRef": payload.sourceRef,
            "regionKey": payload.regionKey,
            "createdAt": now,
            "createdById": current_user["id"],
            "createdByName": current_user.get("name", ""),
            "updatedAt": now,
            "reports": [],
        }
        task = json_store.set_document(TASKS_COLLECTION, task_id, record)
        if payload.notifyAssignee:
            _create_inapp_notification(
                recipient_user_id=str(payload.assigneeUserId),
                sender_id=str(current_user["id"]),
                sender_name=str(current_user.get("name", "")),
                message=_assignment_message(task),
                priority=str(payload.priority),
                task_id=task_id,
                region_key=payload.regionKey,
            )
        return {"success": True, "task": task}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to create the task")


@router.get("/api/tasks")
def list_tasks(
    current_user: dict = Depends(require_current_user),
    assigneeUserId: Optional[str] = Query(default=None),
    regionKey: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """List operational tasks.

    Role 3 officers only ever see tasks assigned to themselves; Role 2 (and
    other reviewer roles) see all tasks, optionally filtered by query params.
    """
    try:
        tasks = json_store.list_documents(TASKS_COLLECTION)
        if is_role_3(current_user):
            wanted = str(current_user["id"])
            tasks = [t for t in tasks if str(t.get("assigneeUserId") or "") == wanted]
        elif assigneeUserId:
            tasks = [t for t in tasks if str(t.get("assigneeUserId") or "") == str(assigneeUserId)]
        if regionKey:
            tasks = [t for t in tasks if str(t.get("regionKey") or "") == str(regionKey)]
        if status:
            tasks = [t for t in tasks if str(t.get("status") or "") == str(status)]
        tasks.sort(key=_task_sort_key, reverse=True)
        return {"success": True, "count": len(tasks), "tasks": tasks}
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch tasks")


@router.get("/api/tasks/{task_id}")
def get_task(
    task_id: str, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    try:
        task = json_store.get_document(TASKS_COLLECTION, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if is_role_3(current_user) and str(task.get("assigneeUserId") or "") != str(
            current_user["id"]
        ):
            raise HTTPException(status_code=403, detail="Not assigned to you")
        return {"success": True, "task": task}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch the task")


@router.patch("/api/tasks/{task_id}")
def update_task(
    task_id: str,
    payload: TaskUpdate,
    current_user: dict = Depends(require_current_user),
) -> dict[str, Any]:
    """Update a task.

    Role 2 may edit assignment fields; the Role 3 assignee may update status,
    progress, and field reports. Other roles get read-only access.
    """
    try:
        task = json_store.get_document(TASKS_COLLECTION, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        planner = is_role_2(current_user)
        assignee = str(task.get("assigneeUserId") or "") == str(current_user["id"])
        if not planner and not assignee:
            raise HTTPException(status_code=403, detail="Not allowed to update this task")

        updates: dict[str, Any] = {}
        data = payload.model_dump(exclude_unset=True)

        if planner:
            for field in (
                "title",
                "department",
                "location",
                "priority",
                "instructions",
                "deadline",
                "status",
                "progress",
            ):
                if field in data and data[field] is not None:
                    value = data[field]
                    updates[field] = value.strip() if isinstance(value, str) else value
            if data.get("assigneeUserId"):
                new_assignee = _resolve_assignee(str(data["assigneeUserId"]))
                updates["assigneeUserId"] = str(data["assigneeUserId"])
                updates["assigneeName"] = str(new_assignee.get("name", ""))
        else:
            # Field officer: status / progress / reports only.
            if data.get("status") is not None:
                updates["status"] = data["status"]
            if data.get("progress") is not None:
                updates["progress"] = data["progress"]

        if payload.report is not None:
            if not planner and not assignee:
                raise HTTPException(status_code=403, detail="Not allowed to report on this task")
            photos: list[dict[str, Any]] = []
            for photo in payload.report.photos or []:
                mime = str(photo.mimeType or "")
                if not mime.lower().startswith("image/"):
                    raise HTTPException(
                        status_code=422, detail="Photo evidence must be an image file"
                    )
                photos.append(
                    {
                        "filename": photo.filename.strip(),
                        "mimeType": mime,
                        "size": photo.size,
                        "dataUrl": photo.dataUrl,
                    }
                )
            reports = list(task.get("reports") or [])
            reports.append(
                {
                    "at": json_store.utcnow_iso(),
                    "byId": current_user["id"],
                    "byName": current_user.get("name", ""),
                    "text": payload.report.text.strip(),
                    "peopleAssisted": payload.report.peopleAssisted,
                    "locationNote": (payload.report.locationNote or "").strip() or None,
                    "photos": photos,
                }
            )
            updates["reports"] = reports
            # A submitted field report marks the task submitted.
            updates["status"] = "Submitted"
            updates["progress"] = 100

        if "status" in updates and updates["status"] == "Submitted" and "progress" not in updates:
            updates["progress"] = 100
        if "status" in updates and updates["status"] == "In Progress" and "progress" not in updates:
            # Starting field work moves the progress bar to 50%.
            current_progress = int(task.get("progress") or 0)
            updates["progress"] = current_progress if current_progress >= 50 else 50

        if not updates:
            return {"success": True, "task": task}

        previous_assignee = str(task.get("assigneeUserId") or "")
        previous_status = str(task.get("status") or "")
        updates["updatedAt"] = json_store.utcnow_iso()
        updated = json_store.update_document(TASKS_COLLECTION, task_id, updates)

        notify_new_assignee = payload.notifyAssignee
        if notify_new_assignee is None:
            notify_new_assignee = True
        new_assignee = str(updated.get("assigneeUserId") or "")
        if (
            notify_new_assignee
            and "assigneeUserId" in updates
            and new_assignee
            and new_assignee != previous_assignee
        ):
            _create_inapp_notification(
                recipient_user_id=new_assignee,
                sender_id=str(current_user["id"]),
                sender_name=str(current_user.get("name", "")),
                message=_assignment_message(updated),
                priority=str(updated.get("priority") or "Medium"),
                task_id=str(updated.get("id") or task_id),
                region_key=updated.get("regionKey"),
            )

        submitted_now = (
            payload.report is not None
            or (updates.get("status") == "Submitted" and previous_status != "Submitted")
        )
        creator_id = str(task.get("createdById") or "")
        if submitted_now and creator_id:
            _create_inapp_notification(
                recipient_user_id=creator_id,
                sender_id=str(current_user["id"]),
                sender_name=str(current_user.get("name", "")),
                message=_submission_message(updated, str(current_user.get("name", ""))),
                priority=str(updated.get("priority") or "Medium"),
                task_id=str(updated.get("id") or task_id),
                region_key=updated.get("regionKey"),
            )

        return {"success": True, "task": updated}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to update the task")

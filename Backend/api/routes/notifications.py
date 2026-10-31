"""Operational notifications (Role 2 -> field teams).

Distinct from climate alerts (``/api/alerts``): these are task assignment
and coordination messages that must show up in the recipient's notification
page. Backed by ``notifications.json`` via ``json_store``.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import json_store
from services.auth_context import is_role_2, require_current_user

router = APIRouter()

NOTIFICATIONS_COLLECTION = "notifications"
USERS_COLLECTION = "users"

NotificationPriority = Literal["Critical", "High", "Medium", "Low"]


class NotificationCreate(BaseModel):
    recipientUserId: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=10, max_length=2000)
    priority: NotificationPriority = "High"
    taskId: Optional[str] = Field(default=None, max_length=100)
    regionKey: Optional[str] = Field(default=None, max_length=150)


@router.post("/api/notifications", status_code=201)
def create_notification(
    payload: NotificationCreate, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    """Send an operational notification. Role 2 only."""
    if not is_role_2(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only the Operations Planner (Role 2) can send operational alerts",
        )
    try:
        recipient = json_store.get_document(USERS_COLLECTION, payload.recipientUserId)
        if recipient is None:
            raise HTTPException(status_code=422, detail="Recipient user not found")
        if not recipient.get("isActive", False):
            raise HTTPException(status_code=422, detail="Recipient user is inactive")

        now = json_store.utcnow_iso()
        notification_id = json_store.generate_id()
        record = {
            "recipientUserId": str(payload.recipientUserId),
            "recipientName": str(recipient.get("name", "")),
            "senderId": current_user["id"],
            "senderName": current_user.get("name", ""),
            "message": payload.message.strip(),
            "priority": payload.priority,
            "taskId": payload.taskId,
            "regionKey": payload.regionKey,
            "read": False,
            "createdAt": now,
        }
        notification = json_store.set_document(
            NOTIFICATIONS_COLLECTION, notification_id, record
        )
        return {"success": True, "notification": notification}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to send the notification")


@router.get("/api/notifications")
def list_notifications(
    current_user: dict = Depends(require_current_user),
    box: str = Query(default="mine"),
) -> dict[str, Any]:
    """List operational notifications for the current officer.

    ``box=mine`` (default) returns items where the officer is the recipient
    or the sender, newest first. ``box=inbox`` returns received only,
    ``box=sent`` returns sent only.
    """
    try:
        items = json_store.list_documents(NOTIFICATIONS_COLLECTION)
        me = str(current_user["id"])
        normalized = (box or "mine").strip().lower()
        if normalized == "inbox":
            items = [n for n in items if str(n.get("recipientUserId") or "") == me]
        elif normalized == "sent":
            items = [n for n in items if str(n.get("senderId") or "") == me]
        else:
            items = [
                n
                for n in items
                if str(n.get("recipientUserId") or "") == me
                or str(n.get("senderId") or "") == me
            ]
        items.sort(key=lambda n: str(n.get("createdAt") or ""), reverse=True)
        unread = sum(
            1
            for n in items
            if str(n.get("recipientUserId") or "") == me and not n.get("read", False)
        )
        return {"success": True, "count": len(items), "unread": unread, "notifications": items}
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch notifications")


@router.patch("/api/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    try:
        notification = json_store.get_document(NOTIFICATIONS_COLLECTION, notification_id)
        if notification is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        if str(notification.get("recipientUserId") or "") != str(current_user["id"]):
            raise HTTPException(status_code=403, detail="Not your notification")
        updated = json_store.update_document(
            NOTIFICATIONS_COLLECTION, notification_id, {"read": True}
        )
        return {"success": True, "notification": updated}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to update the notification")

"""Evidence-attachment endpoints (photo proof linked to field records).

Links photo evidence to a damage submission, operational task, assessment,
or expense record. Follows the task field-report photo pattern
(``api/routes/tasks.py``): inline ``dataUrl`` storage, image MIME only.

Size/count limits (same as task reports):
- at most ``MAX_EVIDENCE_PHOTOS`` (5) photos per attachment record;
- each photo at most ``MAX_PHOTO_BYTES`` (8 MB, ``size`` field);
- each ``dataUrl`` at most ``MAX_PHOTO_DATA_URL_CHARS`` (12M chars);
- ``mimeType`` must start with ``image/`` (422 otherwise).

The assessment engine counts linked attachments (and their photos) as
corroborating evidence; full image bytes stay on these records while
assessments carry only filename/type/size metadata. Backed by
``evidence_attachments.json`` via ``json_store``.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import json_store
from services.auth_context import (
    can_review_assessments,
    is_role_1,
    is_role_2,
    is_role_3,
    is_role_4,
    require_current_user,
)

router = APIRouter()

EVIDENCE_COLLECTION = "evidence_attachments"

LinkedKind = Literal["damage_assessment", "task", "assessment", "expense"]

MAX_EVIDENCE_PHOTOS = 5
MAX_PHOTO_BYTES = 8_000_000
MAX_PHOTO_DATA_URL_CHARS = 12_000_000

_LINKED_COLLECTIONS = {
    "damage_assessment": "damage_assessments",
    "task": "tasks",
    "assessment": "assessments",
    "expense": "expenses",
}


class EvidencePhotoInput(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mimeType: str = Field(default="image/jpeg", max_length=100)
    size: int = Field(default=0, ge=0, le=MAX_PHOTO_BYTES)
    dataUrl: str = Field(min_length=1, max_length=MAX_PHOTO_DATA_URL_CHARS)


class EvidenceCreate(BaseModel):
    linkedKind: LinkedKind
    linkedId: str = Field(min_length=1, max_length=100)
    regionKey: Optional[str] = Field(default=None, max_length=150)
    hazardId: Optional[str] = Field(default=None, max_length=100)
    caption: Optional[str] = Field(default=None, max_length=300)
    photos: list[EvidencePhotoInput] = Field(min_length=1, max_length=MAX_EVIDENCE_PHOTOS)


def _can_submit(user: dict) -> bool:
    return is_role_1(user) or is_role_2(user) or is_role_3(user) or is_role_4(user)


def _require_submit(user: dict) -> None:
    if not _can_submit(user):
        raise HTTPException(
            status_code=403,
            detail="Only officers in Roles 1-4 can attach evidence",
        )


def _require_read(user: dict) -> None:
    if not _can_submit(user):
        raise HTTPException(
            status_code=403, detail="Evidence attachments are visible to Roles 1-4 only"
        )


def _visible(items: list[dict[str, Any]], user: dict) -> list[dict[str, Any]]:
    # Field officers see only their own uploads; others see all.
    if is_role_3(user) and not can_review_assessments(user):
        me = str(user["id"])
        return [e for e in items if str(e.get("uploadedById") or "") == me]
    return items


def _linked_region(linked_kind: str, linked: dict[str, Any]) -> Optional[str]:
    if linked_kind == "assessment":
        return (linked.get("aiAssessment") or {}).get("regionKey")
    return linked.get("regionKey")


@router.post("/api/evidence", status_code=201)
def create_evidence(
    payload: EvidenceCreate, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    """Attach photo evidence to a field record. Roles 1-4 only."""
    _require_submit(current_user)
    try:
        linked = json_store.get_document(
            _LINKED_COLLECTIONS[payload.linkedKind], payload.linkedId
        )
        if linked is None:
            raise HTTPException(
                status_code=404,
                detail=f"Linked {payload.linkedKind} record not found",
            )
        photos: list[dict[str, Any]] = []
        for photo in payload.photos:
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
        now = json_store.utcnow_iso()
        region_key = (payload.regionKey or "").strip() or _linked_region(
            payload.linkedKind, linked
        )
        record = {
            "linkedKind": payload.linkedKind,
            "linkedId": payload.linkedId,
            "regionKey": region_key,
            "hazardId": (payload.hazardId or "").strip() or None,
            "caption": (payload.caption or "").strip() or None,
            "photos": photos,
            "photoCount": len(photos),
            "uploadedAt": now,
            "uploadedById": current_user["id"],
            "uploadedByName": current_user.get("name", ""),
        }
        saved = json_store.set_document(
            EVIDENCE_COLLECTION, json_store.generate_id(), record
        )
        return {"success": True, "evidence": saved}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to save the evidence")


@router.get("/api/evidence")
def list_evidence(
    current_user: dict = Depends(require_current_user),
    regionKey: Optional[str] = Query(default=None),
    linkedKind: Optional[str] = Query(default=None),
    linkedId: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """List evidence attachments (Role 3 sees own uploads only).

    List responses carry photo metadata without ``dataUrl`` bytes; fetch
    one record to retrieve the images.
    """
    _require_read(current_user)
    try:
        items = _visible(json_store.list_documents(EVIDENCE_COLLECTION), current_user)
        if regionKey:
            wanted = regionKey.strip().lower()
            items = [
                e for e in items
                if str(e.get("regionKey") or "").strip().lower() == wanted
            ]
        if linkedKind:
            items = [e for e in items if str(e.get("linkedKind") or "") == linkedKind]
        if linkedId:
            items = [e for e in items if str(e.get("linkedId") or "") == linkedId]
        items.sort(key=lambda e: str(e.get("uploadedAt") or ""), reverse=True)
        trimmed = [
            {
                **item,
                "photos": [
                    {k: p.get(k) for k in ("filename", "mimeType", "size")}
                    for p in (item.get("photos") or [])
                ],
            }
            for item in items
        ]
        return {"success": True, "count": len(trimmed), "evidence": trimmed}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch evidence")


@router.get("/api/evidence/{evidence_id}")
def get_evidence(
    evidence_id: str, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    _require_read(current_user)
    try:
        item = json_store.get_document(EVIDENCE_COLLECTION, evidence_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Evidence record not found")
        if is_role_3(current_user) and not can_review_assessments(current_user):
            if str(item.get("uploadedById") or "") != str(current_user["id"]):
                raise HTTPException(status_code=403, detail="Not uploaded by you")
        return {"success": True, "evidence": item}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch the evidence")


@router.delete("/api/evidence/{evidence_id}")
def delete_evidence(
    evidence_id: str, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    """Withdraw an upload. The uploader or Role 4 only.

    Attachments are immutable (no PATCH): withdraw and re-upload to fix.
    """
    _require_submit(current_user)
    try:
        item = json_store.get_document(EVIDENCE_COLLECTION, evidence_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Evidence record not found")
        owner = str(item.get("uploadedById") or "") == str(current_user["id"])
        if not owner and not is_role_4(current_user):
            raise HTTPException(
                status_code=403, detail="Only the uploader or Role 4 can withdraw this"
            )
        json_store.delete_document(EVIDENCE_COLLECTION, evidence_id)
        return {"success": True, "deletedId": evidence_id}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to delete the evidence")

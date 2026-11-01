"""Officer damage-submission endpoints (per-region-per-hazard observed counts).

Field, assessment, and recovery officers record observed damage counts
(households, houses, crops, livestock, infrastructure, roads) for one
region + hazard. The assessment engine sums these submissions per damage
field and uses the sums when the generating officer did not supply a
direct observation (direct observations always win). Assessment records
snapshot figures at generation time, so later submissions never rewrite
history. Backed by ``damage_assessments.json`` via ``json_store``.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import json_store
from services.auth_context import (
    can_review_assessments,
    is_role_1,
    is_role_3,
    is_role_4,
    require_current_user,
)

router = APIRouter()

DAMAGE_COLLECTION = "damage_assessments"

COUNT_FIELDS = (
    "householdsAffected",
    "housesDamaged",
    "housesDestroyed",
    "cropHectares",
    "livestockLost",
    "infraSites",
    "roadsKm",
)


class DamageAssessmentCreate(BaseModel):
    regionKey: str = Field(min_length=1, max_length=150)
    hazardId: str = Field(min_length=1, max_length=100)
    householdsAffected: Optional[int] = Field(default=None, ge=0, le=100_000_000)
    housesDamaged: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    housesDestroyed: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    cropHectares: Optional[float] = Field(default=None, ge=0, le=100_000_000)
    livestockLost: Optional[int] = Field(default=None, ge=0, le=100_000_000)
    infraSites: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    roadsKm: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    locationNote: Optional[str] = Field(default=None, max_length=300)
    notes: str = Field(default="", max_length=2000)


class DamageAssessmentPatch(BaseModel):
    householdsAffected: Optional[int] = Field(default=None, ge=0, le=100_000_000)
    housesDamaged: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    housesDestroyed: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    cropHectares: Optional[float] = Field(default=None, ge=0, le=100_000_000)
    livestockLost: Optional[int] = Field(default=None, ge=0, le=100_000_000)
    infraSites: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    roadsKm: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    locationNote: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = Field(default=None, max_length=2000)
    reason: str = Field(min_length=1, max_length=1000)


def _can_submit(user: dict) -> bool:
    return is_role_1(user) or is_role_3(user) or is_role_4(user)


def _require_submit(user: dict) -> None:
    if not _can_submit(user):
        raise HTTPException(
            status_code=403,
            detail="Only Assessment (Role 1), Field Operations (Role 3), or "
            "Insurance Recovery (Role 4) officers can submit damage assessments",
        )


def _require_read(user: dict) -> None:
    if not (_can_submit(user)):
        raise HTTPException(
            status_code=403,
            detail="Damage submissions are visible to Roles 1, 3, and 4 only",
        )


def _visible(items: list[dict[str, Any]], user: dict) -> list[dict[str, Any]]:
    # Field officers see only their own submissions; reviewers see all.
    if is_role_3(user) and not can_review_assessments(user):
        me = str(user["id"])
        return [d for d in items if str(d.get("createdById") or "") == me]
    return items


def _has_any_count(data: dict[str, Any]) -> bool:
    return any(data.get(field) is not None for field in COUNT_FIELDS)


@router.post("/api/damage-assessments", status_code=201)
def create_damage_assessment(
    payload: DamageAssessmentCreate, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    """Submit observed damage counts. Roles 1, 3, and 4 only."""
    _require_submit(current_user)
    try:
        data = payload.model_dump()
        if not _has_any_count(data):
            raise HTTPException(
                status_code=422,
                detail="At least one observed damage count is required",
            )
        now = json_store.utcnow_iso()
        record = {
            "regionKey": payload.regionKey.strip(),
            "hazardId": payload.hazardId.strip(),
            **{field: data.get(field) for field in COUNT_FIELDS},
            "locationNote": (payload.locationNote or "").strip() or None,
            "notes": payload.notes.strip(),
            "createdAt": now,
            "createdById": current_user["id"],
            "createdByName": current_user.get("name", ""),
            "updatedAt": now,
        }
        saved = json_store.set_document(
            DAMAGE_COLLECTION, json_store.generate_id(), record
        )
        return {"success": True, "damageAssessment": saved}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to save the damage assessment")


@router.get("/api/damage-assessments")
def list_damage_assessments(
    current_user: dict = Depends(require_current_user),
    regionKey: Optional[str] = Query(default=None),
    hazardId: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """List damage submissions (Role 3 sees own only)."""
    _require_read(current_user)
    try:
        items = _visible(json_store.list_documents(DAMAGE_COLLECTION), current_user)
        if regionKey:
            wanted = regionKey.strip().lower()
            items = [
                d for d in items
                if str(d.get("regionKey") or "").strip().lower() == wanted
            ]
        if hazardId:
            items = [d for d in items if str(d.get("hazardId") or "") == hazardId]
        items.sort(key=lambda d: str(d.get("createdAt") or ""), reverse=True)
        return {"success": True, "count": len(items), "damageAssessments": items}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch damage assessments")


@router.get("/api/damage-assessments/{damage_id}")
def get_damage_assessment(
    damage_id: str, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    _require_read(current_user)
    try:
        item = json_store.get_document(DAMAGE_COLLECTION, damage_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Damage assessment not found")
        if is_role_3(current_user) and not can_review_assessments(current_user):
            if str(item.get("createdById") or "") != str(current_user["id"]):
                raise HTTPException(status_code=403, detail="Not submitted by you")
        return {"success": True, "damageAssessment": item}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch the damage assessment")


@router.patch("/api/damage-assessments/{damage_id}")
def update_damage_assessment(
    damage_id: str,
    payload: DamageAssessmentPatch,
    current_user: dict = Depends(require_current_user),
) -> dict[str, Any]:
    """Correct a submission. The submitter or Role 4; reason required."""
    _require_submit(current_user)
    try:
        item = json_store.get_document(DAMAGE_COLLECTION, damage_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Damage assessment not found")
        owner = str(item.get("createdById") or "") == str(current_user["id"])
        if not owner and not is_role_4(current_user):
            raise HTTPException(
                status_code=403, detail="Only the submitter or Role 4 can correct this"
            )
        reason = payload.reason.strip()
        if not reason:
            raise HTTPException(status_code=422, detail="A correction reason is required")
        data = payload.model_dump(exclude_unset=True)
        data.pop("reason", None)
        updates: dict[str, Any] = {}
        for field in (*COUNT_FIELDS, "locationNote", "notes"):
            if field in data and data[field] is not None:
                value = data[field]
                updates[field] = value.strip() if isinstance(value, str) else value
        if not updates:
            return {"success": True, "damageAssessment": item}
        merged = dict(item)
        merged.update(updates)
        if not _has_any_count(merged):
            raise HTTPException(
                status_code=422, detail="At least one observed damage count is required"
            )
        updates["updatedAt"] = json_store.utcnow_iso()
        updated = json_store.update_document(DAMAGE_COLLECTION, damage_id, updates)
        return {"success": True, "damageAssessment": updated}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to update the damage assessment")


@router.delete("/api/damage-assessments/{damage_id}")
def delete_damage_assessment(
    damage_id: str, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    """Withdraw a submission. The submitter or Role 4 only."""
    _require_submit(current_user)
    try:
        item = json_store.get_document(DAMAGE_COLLECTION, damage_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Damage assessment not found")
        owner = str(item.get("createdById") or "") == str(current_user["id"])
        if not owner and not is_role_4(current_user):
            raise HTTPException(
                status_code=403, detail="Only the submitter or Role 4 can withdraw this"
            )
        json_store.delete_document(DAMAGE_COLLECTION, damage_id)
        return {"success": True, "deletedId": damage_id}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to delete the damage assessment")

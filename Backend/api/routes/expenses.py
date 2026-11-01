"""Preparedness and recovery expense records (observed spend).

Operations, field, and recovery officers record categorized spend with
receipt references. The assessment engine sums these per region (+hazard
when set) and uses the observed totals BEFORE modelled proxies:
preparedness spend replaces the task-day proxy, recovery spend replaces
the share-of-damage proxy. Direct observations on the assessment itself
still win over everything. Backed by ``expenses.json`` via ``json_store``.
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

EXPENSES_COLLECTION = "expenses"

ExpenseKind = Literal["preparedness", "recovery"]


class ExpenseCreate(BaseModel):
    regionKey: str = Field(min_length=1, max_length=150)
    hazardId: Optional[str] = Field(default=None, max_length=100)
    kind: ExpenseKind
    category: str = Field(min_length=1, max_length=100)
    amountInr: float = Field(gt=0, le=1e15)
    receiptRef: Optional[str] = Field(default=None, max_length=200)
    vendor: Optional[str] = Field(default=None, max_length=200)
    spentAt: Optional[str] = Field(default=None, max_length=64)
    notes: str = Field(default="", max_length=2000)
    assessmentId: Optional[str] = Field(default=None, max_length=100)


class ExpensePatch(BaseModel):
    category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    amountInr: Optional[float] = Field(default=None, gt=0, le=1e15)
    receiptRef: Optional[str] = Field(default=None, max_length=200)
    vendor: Optional[str] = Field(default=None, max_length=200)
    spentAt: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=2000)
    reason: str = Field(min_length=1, max_length=1000)


def _can_submit(user: dict) -> bool:
    return is_role_2(user) or is_role_3(user) or is_role_4(user)


def _require_submit(user: dict) -> None:
    if not _can_submit(user):
        raise HTTPException(
            status_code=403,
            detail="Only Operations (Role 2), Field Operations (Role 3), or "
            "Insurance Recovery (Role 4) officers can record expenses",
        )


def _require_read(user: dict) -> None:
    if not (_can_submit(user) or is_role_1(user)):
        raise HTTPException(
            status_code=403, detail="Expense records are visible to Roles 1-4 only"
        )


def _visible(items: list[dict[str, Any]], user: dict) -> list[dict[str, Any]]:
    # Field officers see only their own records; others see all.
    if is_role_3(user) and not can_review_assessments(user):
        me = str(user["id"])
        return [e for e in items if str(e.get("createdById") or "") == me]
    return items


@router.post("/api/expenses", status_code=201)
def create_expense(
    payload: ExpenseCreate, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    """Record categorized spend. Roles 2, 3, and 4 only."""
    _require_submit(current_user)
    try:
        now = json_store.utcnow_iso()
        record = {
            "regionKey": payload.regionKey.strip(),
            "hazardId": (payload.hazardId or "").strip() or None,
            "kind": payload.kind,
            "category": payload.category.strip(),
            "amountInr": float(payload.amountInr),
            "receiptRef": (payload.receiptRef or "").strip() or None,
            "vendor": (payload.vendor or "").strip() or None,
            "spentAt": payload.spentAt,
            "notes": payload.notes.strip(),
            "assessmentId": payload.assessmentId,
            "createdAt": now,
            "createdById": current_user["id"],
            "createdByName": current_user.get("name", ""),
            "updatedAt": now,
        }
        saved = json_store.set_document(EXPENSES_COLLECTION, json_store.generate_id(), record)
        return {"success": True, "expense": saved}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to save the expense record")


@router.get("/api/expenses")
def list_expenses(
    current_user: dict = Depends(require_current_user),
    regionKey: Optional[str] = Query(default=None),
    hazardId: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """List expense records (Role 3 sees own only)."""
    _require_read(current_user)
    try:
        items = _visible(json_store.list_documents(EXPENSES_COLLECTION), current_user)
        if regionKey:
            wanted = regionKey.strip().lower()
            items = [
                e for e in items
                if str(e.get("regionKey") or "").strip().lower() == wanted
            ]
        if hazardId:
            items = [e for e in items if str(e.get("hazardId") or "") == hazardId]
        if kind:
            items = [e for e in items if str(e.get("kind") or "") == kind]
        items.sort(key=lambda e: str(e.get("createdAt") or ""), reverse=True)
        total_inr = round(sum(float(e.get("amountInr") or 0.0) for e in items), 2)
        return {
            "success": True,
            "count": len(items),
            "totalInr": total_inr,
            "expenses": items,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch expense records")


@router.get("/api/expenses/{expense_id}")
def get_expense(
    expense_id: str, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    _require_read(current_user)
    try:
        item = json_store.get_document(EXPENSES_COLLECTION, expense_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Expense record not found")
        if is_role_3(current_user) and not can_review_assessments(current_user):
            if str(item.get("createdById") or "") != str(current_user["id"]):
                raise HTTPException(status_code=403, detail="Not recorded by you")
        return {"success": True, "expense": item}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch the expense record")


@router.patch("/api/expenses/{expense_id}")
def update_expense(
    expense_id: str,
    payload: ExpensePatch,
    current_user: dict = Depends(require_current_user),
) -> dict[str, Any]:
    """Correct a record (kind/region/hazard are immutable). Recorder or Role 4; reason required."""
    _require_submit(current_user)
    try:
        item = json_store.get_document(EXPENSES_COLLECTION, expense_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Expense record not found")
        owner = str(item.get("createdById") or "") == str(current_user["id"])
        if not owner and not is_role_4(current_user):
            raise HTTPException(
                status_code=403, detail="Only the recorder or Role 4 can correct this"
            )
        reason = payload.reason.strip()
        if not reason:
            raise HTTPException(status_code=422, detail="A correction reason is required")
        data = payload.model_dump(exclude_unset=True)
        data.pop("reason", None)
        updates: dict[str, Any] = {}
        for field in ("category", "amountInr", "receiptRef", "vendor", "spentAt", "notes"):
            if field in data and data[field] is not None:
                value = data[field]
                updates[field] = value.strip() if isinstance(value, str) else value
        if not updates:
            return {"success": True, "expense": item}
        updates["updatedAt"] = json_store.utcnow_iso()
        updated = json_store.update_document(EXPENSES_COLLECTION, expense_id, updates)
        return {"success": True, "expense": updated}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to update the expense record")


@router.delete("/api/expenses/{expense_id}")
def delete_expense(
    expense_id: str, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    """Withdraw a record. The recorder or Role 4 only."""
    _require_submit(current_user)
    try:
        item = json_store.get_document(EXPENSES_COLLECTION, expense_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Expense record not found")
        owner = str(item.get("createdById") or "") == str(current_user["id"])
        if not owner and not is_role_4(current_user):
            raise HTTPException(
                status_code=403, detail="Only the recorder or Role 4 can withdraw this"
            )
        json_store.delete_document(EXPENSES_COLLECTION, expense_id)
        return {"success": True, "deletedId": expense_id}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to delete the expense record")

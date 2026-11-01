"""Disaster assessment, cost & compensation endpoints (Role 4).

AI recommends with transparent reasoning; Role 4 officers verify and decide;
verified corrections become structured feedback for learning. Approved and
rejected assessments are immutable; every edit requires a reason and every
decision, version, and report is preserved for audit.
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from services import assessment_engine, assessment_report, json_store
from services.ai_client import client as ai_reasoning_client
from services.auth_context import can_review_assessments, is_role_4, require_current_user

router = APIRouter()

ASSESSMENTS_COLLECTION = "assessments"
FEEDBACK_COLLECTION = "assessment_feedback"

DecisionAction = Literal["accept", "reject"]


class ObservedInputs(BaseModel):
    householdsAffected: Optional[int] = Field(default=None, ge=0, le=100_000_000)
    housesDamaged: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    housesDestroyed: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    cropHectares: Optional[float] = Field(default=None, ge=0, le=100_000_000)
    livestockLost: Optional[int] = Field(default=None, ge=0, le=100_000_000)
    infraSites: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    roadsKm: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    preparationCostInr: Optional[float] = Field(default=None, ge=0, le=1e15)
    recoveryCostInr: Optional[float] = Field(default=None, ge=0, le=1e15)


class AssessmentCreate(BaseModel):
    regionKey: str = Field(min_length=1, max_length=150)
    hazardId: str = Field(min_length=1, max_length=100)
    observed: ObservedInputs = Field(default_factory=ObservedInputs)
    notes: str = Field(default="", max_length=2000)


class AssessmentEdit(BaseModel):
    path: str = Field(min_length=1, max_length=100)
    newValue: Optional[float] = Field(default=None, ge=0, le=1e18)
    reason: str = Field(min_length=1, max_length=1000)


class AssessmentPatch(BaseModel):
    edits: list[AssessmentEdit] = Field(min_length=1, max_length=50)


class AssessmentDecision(BaseModel):
    action: DecisionAction
    reason: str = Field(min_length=1, max_length=1000)


class ReportRegenerate(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


def _require_reviewer(current_user: dict) -> None:
    if not can_review_assessments(current_user):
        raise HTTPException(
            status_code=403,
            detail="Assessment review requires the Insurance Recovery (Role 4) or Assessment (Role 1) role",
        )


def _require_role4(current_user: dict) -> None:
    if not is_role_4(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only the Insurance Recovery Officer (Role 4) can change assessments",
        )


def _public_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    for _ in range(10):
        suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        candidate = f"ASM-{stamp}-{suffix}"
        existing = json_store.read_collection(ASSESSMENTS_COLLECTION)
        if all(doc.get("publicId") != candidate for doc in existing.values()):
            return candidate
    return f"ASM-{stamp}-{json_store.generate_id(6).upper()}"


def _figure_label(ai_assessment: dict[str, Any], key: str) -> str:
    for figure in ai_assessment.get("figures") or []:
        if figure.get("key") == key:
            return str(figure.get("label") or key)
    return key


def _with_current(assessment: dict[str, Any]) -> dict[str, Any]:
    current = assessment_engine.compute_current(
        assessment.get("aiAssessment") or {}, assessment.get("officialEdits") or []
    )
    return {**assessment, "current": current}


def _summary(assessment: dict[str, Any]) -> dict[str, Any]:
    current = assessment_engine.compute_current(
        assessment.get("aiAssessment") or {}, assessment.get("officialEdits") or []
    )
    ai = assessment.get("aiAssessment") or {}
    return {
        "id": assessment.get("id"),
        "publicId": assessment.get("publicId"),
        "regionKey": ai.get("regionKey"),
        "regionName": ai.get("regionName"),
        "hazardId": ai.get("hazardId"),
        "hazardName": ai.get("hazardName"),
        "status": assessment.get("status"),
        "version": assessment.get("version"),
        "overallConfidence": ai.get("overallConfidence"),
        "totals": current.get("totals"),
        "editCount": len(assessment.get("officialEdits") or []),
        "reportCount": len(assessment.get("reportVersions") or []),
        "createdAt": assessment.get("createdAt"),
        "createdByName": assessment.get("createdByName"),
        "updatedAt": assessment.get("updatedAt"),
    }


def _edit_category(key: str) -> str:
    if key in ("housing_loss_inr", "crop_loss_inr", "livestock_loss_inr",
               "infrastructure_loss_inr", "total_damage_inr"):
        return "damage"
    if key in ("preparation_cost_inr", "recovery_cost_inr"):
        return "cost"
    if key == "indicative_relief_inr":
        return "compensation"
    return "coverage"


@router.post("/api/assessments", status_code=201)
def create_assessment(
    payload: AssessmentCreate, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    """Generate a new AI assessment for Role 4 review. Role 4 only."""
    _require_role4(current_user)
    try:
        region_key = payload.regionKey.strip()
        hazard_id = payload.hazardId.strip()
        observed = {k: v for k, v in payload.observed.model_dump().items() if v is not None}
        ai = assessment_engine.build_ai_assessment(
            region_key, hazard_id, observed, payload.notes.strip(), ai_reasoning_client
        )
        now = json_store.utcnow_iso()
        record = {
            "publicId": _public_id(),
            "status": "pending_review",
            "version": 1,
            "aiAssessment": ai,
            "officialEdits": [],
            "versions": [
                {
                    "version": 1,
                    "at": now,
                    "byId": current_user["id"],
                    "byName": current_user.get("name", ""),
                    "action": "generated",
                    "reason": "AI assessment generated for officer review.",
                }
            ],
            "approvalHistory": [
                {
                    "at": now,
                    "byId": current_user["id"],
                    "byName": current_user.get("name", ""),
                    "action": "generated",
                    "reason": "AI assessment generated for officer review.",
                    "version": 1,
                }
            ],
            "decision": None,
            "approvedSnapshot": None,
            "reportVersions": [],
            "createdAt": now,
            "createdById": current_user["id"],
            "createdByName": current_user.get("name", ""),
            "updatedAt": now,
        }
        assessment = json_store.set_document(
            ASSESSMENTS_COLLECTION, json_store.generate_id(), record
        )
        return {"success": True, "assessment": _with_current(assessment)}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to generate the assessment")


@router.get("/api/assessments")
def list_assessments(
    current_user: dict = Depends(require_current_user),
    status: Optional[str] = Query(default=None),
    regionKey: Optional[str] = Query(default=None),
    hazardId: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """List assessment summaries. Role 1 oversight and Role 4 ownership."""
    _require_reviewer(current_user)
    try:
        items = json_store.list_documents(ASSESSMENTS_COLLECTION)
        if status:
            items = [a for a in items if str(a.get("status") or "") == status]
        if regionKey:
            wanted = regionKey.strip().lower()
            items = [
                a for a in items
                if str((a.get("aiAssessment") or {}).get("regionKey") or "").strip().lower() == wanted
            ]
        if hazardId:
            items = [
                a for a in items
                if str((a.get("aiAssessment") or {}).get("hazardId") or "") == hazardId
            ]
        items.sort(key=lambda a: str(a.get("createdAt") or ""), reverse=True)
        summaries = [_summary(a) for a in items]
        return {"success": True, "count": len(summaries), "assessments": summaries}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch assessments")


@router.get("/api/assessments/{assessment_id}")
def get_assessment(
    assessment_id: str, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    _require_reviewer(current_user)
    try:
        assessment = json_store.get_document(ASSESSMENTS_COLLECTION, assessment_id)
        if assessment is None:
            raise HTTPException(status_code=404, detail="Assessment not found")
        return {"success": True, "assessment": _with_current(assessment)}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch the assessment")


@router.patch("/api/assessments/{assessment_id}")
def edit_assessment(
    assessment_id: str,
    payload: AssessmentPatch,
    current_user: dict = Depends(require_current_user),
) -> dict[str, Any]:
    """Correct AI figures. Role 4 only; every edit needs a reason.

    The original AI record is never modified; edits are appended with officer
    details and timestamps, and the assessment version is bumped.
    """
    _require_role4(current_user)
    try:
        assessment = json_store.get_document(ASSESSMENTS_COLLECTION, assessment_id)
        if assessment is None:
            raise HTTPException(status_code=404, detail="Assessment not found")
        if assessment.get("status") != "pending_review":
            raise HTTPException(
                status_code=409,
                detail="Only assessments pending review can be edited; decided records are immutable",
            )
        ai = assessment.get("aiAssessment") or {}
        ai_values = {f.get("key"): f.get("value") for f in ai.get("figures") or []}
        now = json_store.utcnow_iso()
        edits = list(assessment.get("officialEdits") or [])
        for edit in payload.edits:
            path = edit.path.strip()
            if not path.startswith("figures."):
                raise HTTPException(status_code=422, detail=f"Invalid edit path: {path}")
            key = path[len("figures."):]
            if key not in assessment_engine.FIGURE_KEYS:
                raise HTTPException(status_code=422, detail=f"Unknown figure: {key}")
            reason = edit.reason.strip()
            if not reason:
                raise HTTPException(status_code=422, detail="Each edit requires a reason")
            current_value = assessment_engine.compute_current(ai, edits)["figures"]
            current_by_key = {f["key"]: f.get("currentValue") for f in current_value}
            edits.append(
                {
                    "at": now,
                    "byId": current_user["id"],
                    "byName": current_user.get("name", ""),
                    "path": f"figures.{key}",
                    "label": _figure_label(ai, key),
                    "aiValue": ai_values.get(key),
                    "oldValue": current_by_key.get(key),
                    "newValue": edit.newValue,
                    "reason": reason,
                }
            )
        new_version = int(assessment.get("version") or 1) + 1
        current = assessment_engine.compute_current(ai, edits)
        versions = list(assessment.get("versions") or [])
        versions.append(
            {
                "version": new_version,
                "at": now,
                "byId": current_user["id"],
                "byName": current_user.get("name", ""),
                "action": "edited",
                "reason": f"{len(payload.edits)} correction(s) by {current_user.get('name', '')}.",
                "figuresSnapshot": current["figures"],
                "totalsSnapshot": current["totals"],
            }
        )
        history = list(assessment.get("approvalHistory") or [])
        history.append(
            {
                "at": now,
                "byId": current_user["id"],
                "byName": current_user.get("name", ""),
                "action": "edited",
                "reason": "; ".join(e.reason.strip() for e in payload.edits)[:1000],
                "version": new_version,
            }
        )
        updated = json_store.update_document(
            ASSESSMENTS_COLLECTION,
            assessment_id,
            {
                "officialEdits": edits,
                "version": new_version,
                "versions": versions,
                "approvalHistory": history,
                "updatedAt": now,
            },
        )
        return {"success": True, "assessment": _with_current(updated)}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to update the assessment")


def _delta_pct(old: Any, new: Any) -> Optional[float]:
    try:
        if old is None or new is None or float(old) == 0:
            return None
        return round((float(new) - float(old)) / float(old) * 100.0, 2)
    except (TypeError, ValueError):
        return None


@router.post("/api/assessments/{assessment_id}/decision")
def decide_assessment(
    assessment_id: str,
    payload: AssessmentDecision,
    current_user: dict = Depends(require_current_user),
) -> dict[str, Any]:
    """Accept or reject an assessment. Role 4 only; reason required.

    Accepting freezes an immutable approved snapshot and stores the
    officer's corrections as *verified* feedback. Rejecting stores them
    as *unverified* so they can never silently become ground truth.
    """
    _require_role4(current_user)
    try:
        assessment = json_store.get_document(ASSESSMENTS_COLLECTION, assessment_id)
        if assessment is None:
            raise HTTPException(status_code=404, detail="Assessment not found")
        if assessment.get("status") != "pending_review":
            raise HTTPException(
                status_code=409,
                detail="This assessment has already been decided and is immutable",
            )
        reason = payload.reason.strip()
        if not reason:
            raise HTTPException(status_code=422, detail="A decision reason is required")
        now = json_store.utcnow_iso()
        ai = assessment.get("aiAssessment") or {}
        current = assessment_engine.compute_current(ai, assessment.get("officialEdits") or [])
        accepted = payload.action == "accept"
        history = list(assessment.get("approvalHistory") or [])
        history.append(
            {
                "at": now,
                "byId": current_user["id"],
                "byName": current_user.get("name", ""),
                "action": "accepted" if accepted else "rejected",
                "reason": reason,
                "version": assessment.get("version"),
            }
        )
        updates: dict[str, Any] = {
            "status": "approved" if accepted else "rejected",
            "decision": {
                "action": "accepted" if accepted else "rejected",
                "byId": current_user["id"],
                "byName": current_user.get("name", ""),
                "at": now,
                "reason": reason,
                "version": assessment.get("version"),
            },
            "approvalHistory": history,
            "updatedAt": now,
        }
        if accepted:
            updates["approvedSnapshot"] = {
                "figures": current["figures"],
                "totals": current["totals"],
                "overridden": current["overridden"],
                "approvedAt": now,
                "version": assessment.get("version"),
            }
        updated = json_store.update_document(ASSESSMENTS_COLLECTION, assessment_id, updates)

        # Structured learning feedback from this officer's corrections.
        for edit in assessment.get("officialEdits") or []:
            key = str(edit.get("path") or "").removeprefix("figures.")
            try:
                json_store.set_document(
                    FEEDBACK_COLLECTION,
                    json_store.generate_id(),
                    {
                        "assessmentId": assessment_id,
                        "assessmentPublicId": assessment.get("publicId"),
                        "regionKey": ai.get("regionKey"),
                        "hazardId": ai.get("hazardId"),
                        "path": edit.get("path"),
                        "label": edit.get("label"),
                        "category": _edit_category(key),
                        "aiValue": edit.get("aiValue"),
                        "correctedValue": edit.get("newValue"),
                        "deltaPct": _delta_pct(edit.get("aiValue"), edit.get("newValue")),
                        "reason": edit.get("reason"),
                        "officerId": edit.get("byId"),
                        "officerName": edit.get("byName"),
                        "at": edit.get("at"),
                        "status": "verified" if accepted else "unverified",
                        "engineVersion": ai.get("engineVersion"),
                    },
                )
            except Exception:
                continue
        return {"success": True, "assessment": _with_current(updated)}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to record the decision")


def _render_and_store(
    assessment: dict[str, Any], current_user: dict, reason: str
) -> tuple[dict[str, Any], bytes]:
    assessment_id = str(assessment.get("id") or "")
    current = assessment_engine.compute_current(
        assessment.get("aiAssessment") or {}, assessment.get("officialEdits") or []
    )
    versions = list(assessment.get("reportVersions") or [])
    next_version = (max((v.get("version", 0) for v in versions), default=0) + 1) if versions else 1
    now = json_store.utcnow_iso()
    pdf = assessment_report.render_approved_report(
        assessment,
        current,
        next_version,
        now,
        {"name": str(current_user.get("name", "")), "roleName": str(current_user.get("roleName", ""))},
    )
    filename, size, digest = assessment_report.write_report_file(
        str(assessment.get("publicId") or assessment_id), next_version, pdf
    )
    versions.append(
        {
            "version": next_version,
            "filename": filename,
            "byteSize": size,
            "sha256": digest,
            "generatedAt": now,
            "generatedById": current_user["id"],
            "generatedByName": current_user.get("name", ""),
            "reason": reason,
            "assessmentVersion": assessment.get("version"),
        }
    )
    history = list(assessment.get("approvalHistory") or [])
    history.append(
        {
            "at": now,
            "byId": current_user["id"],
            "byName": current_user.get("name", ""),
            "action": "report_generated",
            "reason": reason,
            "version": assessment.get("version"),
        }
    )
    updated = json_store.update_document(
        ASSESSMENTS_COLLECTION,
        assessment_id,
        {"reportVersions": versions, "approvalHistory": history, "updatedAt": now},
    )
    return updated, pdf


@router.get("/api/assessments/{assessment_id}/reports")
def list_reports(
    assessment_id: str, current_user: dict = Depends(require_current_user)
) -> dict[str, Any]:
    """List preserved official report versions. Reviewers only."""
    _require_reviewer(current_user)
    try:
        assessment = json_store.get_document(ASSESSMENTS_COLLECTION, assessment_id)
        if assessment is None:
            raise HTTPException(status_code=404, detail="Assessment not found")
        versions = list(assessment.get("reportVersions") or [])
        versions.sort(key=lambda v: v.get("version", 0))
        return {"success": True, "count": len(versions), "reports": versions}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch report versions")


@router.get("/api/assessments/{assessment_id}/report.pdf")
def download_report(
    assessment_id: str,
    current_user: dict = Depends(require_current_user),
    version: Optional[int] = Query(default=None),
) -> Response:
    """Download the official PDF. Only approved assessments, versioned.

    The first download generates and preserves report v1; later downloads
    reuse it unless a newer version was explicitly regenerated.
    """
    _require_reviewer(current_user)
    try:
        assessment = json_store.get_document(ASSESSMENTS_COLLECTION, assessment_id)
        if assessment is None:
            raise HTTPException(status_code=404, detail="Assessment not found")
        if assessment.get("status") != "approved":
            raise HTTPException(
                status_code=409,
                detail="Only government-approved assessments have official reports",
            )
        versions = list(assessment.get("reportVersions") or [])
        target = None
        if version is not None:
            target = next((v for v in versions if v.get("version") == version), None)
            if target is None:
                raise HTTPException(status_code=404, detail="Report version not found")
        elif versions:
            target = max(versions, key=lambda v: v.get("version", 0))
        if target is None:
            _, pdf = _render_and_store(assessment, current_user, "First official report generated on download.")
            filename = assessment_report.report_filename(
                str(assessment.get("publicId") or assessment_id), 1
            )
        else:
            try:
                pdf = assessment_report.read_report_file(str(target["filename"]))
            except FileNotFoundError:
                raise HTTPException(status_code=500, detail="Stored report file is missing")
            filename = str(target["filename"])
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to produce the report")


@router.post("/api/assessments/{assessment_id}/reports/regenerate", status_code=201)
def regenerate_report(
    assessment_id: str,
    payload: ReportRegenerate,
    current_user: dict = Depends(require_current_user),
) -> dict[str, Any]:
    """Create a new preserved report version. Role 4 only; reason required."""
    _require_role4(current_user)
    try:
        assessment = json_store.get_document(ASSESSMENTS_COLLECTION, assessment_id)
        if assessment is None:
            raise HTTPException(status_code=404, detail="Assessment not found")
        if assessment.get("status") != "approved":
            raise HTTPException(
                status_code=409,
                detail="Only government-approved assessments have official reports",
            )
        updated, _ = _render_and_store(
            assessment, current_user, payload.reason.strip() or "Report regenerated."
        )
        versions = list(updated.get("reportVersions") or [])
        versions.sort(key=lambda v: v.get("version", 0))
        return {"success": True, "count": len(versions), "reports": versions}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to regenerate the report")


@router.get("/api/assessment-feedback")
def list_feedback(
    current_user: dict = Depends(require_current_user),
    status: Optional[str] = Query(default=None),
    hazardId: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """List structured officer corrections. Reviewers only."""
    _require_reviewer(current_user)
    try:
        items = json_store.list_documents(FEEDBACK_COLLECTION)
        if status:
            items = [f for f in items if str(f.get("status") or "") == status]
        if hazardId:
            items = [f for f in items if str(f.get("hazardId") or "") == hazardId]
        items.sort(key=lambda f: str(f.get("at") or ""), reverse=True)
        return {"success": True, "count": len(items), "feedback": items}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to fetch feedback")


@router.get("/api/assessment-feedback/analysis")
def analyze_feedback(
    current_user: dict = Depends(require_current_user),
    hazardId: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """Recurring AI-vs-approved differences from verified feedback only."""
    _require_reviewer(current_user)
    try:
        rows = assessment_engine.verified_feedback_stats(hazardId)
        return {"success": True, "count": len(rows), "engineVersion": assessment_engine.ENGINE_VERSION, "rows": rows}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to analyze feedback")

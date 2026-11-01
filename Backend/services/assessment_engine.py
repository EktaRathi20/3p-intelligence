"""Deterministic disaster assessment, cost & compensation engine (Role 4).

Produces an AI-style assessment record in which **every figure carries its
own calculation, assumptions, data sources, confidence, and explanation**.
Narrative text may be drafted by the Meta reasoning client when configured;
all numbers come from transparent deterministic formulas over locally
available data plus officer-observed inputs. Nothing here is an official
approval, eligibility decision, insurance decision, or payment.
"""

from __future__ import annotations

import copy
from statistics import median
from typing import Any, Optional

from services import json_store

ENGINE_VERSION = "assess-engine/1.1"

# Configurable planning defaults. These are NOT official SDRF/NDRF rates;
# every figure that uses them says so in its assumptions.
AVG_HOUSEHOLD_SIZE = 4.4
REPAIR_PER_HOUSE_INR = 150_000
REBUILD_PER_HOUSE_INR = 500_000
CROP_PER_HECTARE_INR = 30_000
LIVESTOCK_PER_HEAD_INR = 20_000
INFRA_PER_SITE_INR = 2_000_000
ROAD_PER_KM_INR = 5_000_000
TASK_DAY_COST_INR = 25_000
RECOVERY_SHARE_OF_DAMAGE = 0.12
RELIEF_SHARE_OF_DAMAGE = 0.25

RATE_DISCLAIMER = (
    "Unit rates are configurable planning defaults, not official SDRF/NDRF "
    "schedules. Verify against current government norms before official use."
)

# Figure keys the engine emits and officers may correct.
DAMAGE_KEYS = (
    "housing_loss_inr",
    "crop_loss_inr",
    "livestock_loss_inr",
    "infrastructure_loss_inr",
)
FIGURE_KEYS = (
    "affected_people",
    *DAMAGE_KEYS,
    "total_damage_inr",
    "preparation_cost_inr",
    "recovery_cost_inr",
    "indicative_relief_inr",
)

MIN_CALIBRATION_POINTS = 3
MAX_CALIBRATION_ABS_DELTA = 0.25


def _inr(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    return f"Rs.{value:,.0f}"


def verified_feedback_stats(hazard_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Aggregate *verified* corrections into recurring-difference statistics.

    Only feedback with status ``verified`` (i.e. approved by a Role 4
    decision) is used. Returns one row per (hazard, figure) with count,
    median/mean delta %, and direction.
    """
    try:
        items = json_store.list_documents("assessment_feedback")
    except Exception:
        return []
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        try:
            if item.get("status") != "verified":
                continue
            hazard = str(item.get("hazardId") or "")
            if hazard_id and hazard != str(hazard_id):
                continue
            path = str(item.get("path") or "")
            delta = item.get("deltaPct")
            if not path or delta is None:
                continue
            groups.setdefault((hazard, path), []).append(item)
        except Exception:
            continue
    rows: list[dict[str, Any]] = []
    for (hazard, path), members in groups.items():
        deltas = [float(m.get("deltaPct") or 0.0) for m in members]
        med = median(deltas)
        rows.append(
            {
                "hazardId": hazard,
                "path": path,
                "label": str(members[0].get("label") or path),
                "count": len(members),
                "medianDeltaPct": round(med, 2),
                "meanDeltaPct": round(sum(deltas) / len(deltas), 2),
                "direction": "under-estimated"
                if med > 0.5
                else ("over-estimated" if med < -0.5 else "aligned"),
                "assessmentIds": sorted(
                    {str(m.get("assessmentPublicId") or "") for m in members if m.get("assessmentPublicId")}
                )[:10],
                "lastAt": max(str(m.get("at") or "") for m in members),
            }
        )
    rows.sort(key=lambda r: (-r["count"], r["hazardId"], r["path"]))
    return rows


def _calibration_for(hazard_id: str, key: str) -> Optional[dict[str, Any]]:
    for row in verified_feedback_stats(hazard_id):
        if row["path"] == f"figures.{key}" and row["count"] >= MIN_CALIBRATION_POINTS:
            return row
    return None


def _apply_calibration(raw: Optional[float], calibration: Optional[dict[str, Any]]) -> tuple[Optional[float], Optional[dict[str, Any]], str]:
    """Apply a bounded median correction; returns (value, record, note)."""
    if raw is None or calibration is None:
        return raw, None, ""
    delta = float(calibration["medianDeltaPct"]) / 100.0
    delta = max(-MAX_CALIBRATION_ABS_DELTA, min(MAX_CALIBRATION_ABS_DELTA, delta))
    adjusted = round(raw * (1.0 + delta), 2)
    record = {
        "feedbackCount": calibration["count"],
        "medianDeltaPct": calibration["medianDeltaPct"],
        "appliedDeltaPct": round(delta * 100.0, 2),
    }
    note = (
        f" Calibrated by {delta * 100:+.1f}% (median of "
        f"{calibration['count']} verified officer corrections for this hazard; "
        f"capped at ±{MAX_CALIBRATION_ABS_DELTA * 100:.0f}%)."
    )
    return adjusted, record, note


def gather_evidence(region_key: str, hazard_id: str) -> dict[str, Any]:
    """Collect locally available evidence. Never raises; gaps are recorded."""
    now = json_store.utcnow_iso()
    evidence: dict[str, Any] = {
        "regionKey": region_key,
        "hazardId": hazard_id,
        "fetchedAt": now,
        "region": None,
        "hazard": None,
        "tasks": [],
        "reports": [],
        "peopleAssistedSum": 0,
        "damageAssessments": [],
        "damageTotals": {},
        "expenses": [],
        "expenseTotals": {
            "preparednessInr": 0.0,
            "recoveryInr": 0.0,
            "preparednessCount": 0,
            "recoveryCount": 0,
        },
        "evidenceAttachments": [],
        "photoCount": 0,
        "geoContext": None,
        "populationContext": None,
        "intelligenceContext": None,
        "historicalContext": None,
        "verifiedFeedbackCount": 0,
        "gaps": [],
    }
    try:
        regions = json_store.list_documents("regions")
        match = next(
            (
                r
                for r in regions
                if str(r.get("code") or "").lower() == region_key.lower()
                or str(r.get("id") or "") == region_key
            ),
            None,
        )
        evidence["region"] = match
        if match is None:
            evidence["gaps"].append(f"No region record found for '{region_key}'.")
    except Exception:
        evidence["gaps"].append("Region data could not be read.")
    try:
        hazards = json_store.list_documents("hazards")
        match = next(
            (
                h
                for h in hazards
                if str(h.get("id") or "") == hazard_id
                or str(h.get("code") or "") == hazard_id
            ),
            None,
        )
        evidence["hazard"] = match
        if match is None:
            evidence["gaps"].append(f"No hazard record found for '{hazard_id}'.")
    except Exception:
        evidence["gaps"].append("Hazard data could not be read.")
    # Tasks, damage submissions, expenses, and evidence store the region key
    # verbatim (often lowercase, e.g. "in-py-ynm") while the Recovery
    # console sends the managed region code (uppercase, e.g. "IN-PY-YNM").
    # Match case-insensitively and also accept the resolved region
    # document's id/code so evidence counts are real instead of zero.
    accepted_keys = {region_key.strip().lower()} - {""}
    _region_doc = evidence.get("region") or {}
    for _candidate in (_region_doc.get("id"), _region_doc.get("code")):
        _text = str(_candidate or "").strip().lower()
        if _text:
            accepted_keys.add(_text)

    def _in_region(doc: dict[str, Any]) -> bool:
        return str(doc.get("regionKey") or "").strip().lower() in accepted_keys

    try:
        tasks = [t for t in json_store.list_documents("tasks") if _in_region(t)]
        evidence["tasks"] = tasks
        reports: list[dict[str, Any]] = []
        assisted = 0
        field_photos = 0
        for task in tasks:
            for report in task.get("reports") or []:
                # Photo bytes stay on the task record; the assessment keeps
                # filename/type/size metadata so it stays small and auditable.
                photo_meta = [
                    {
                        "filename": p.get("filename"),
                        "mimeType": p.get("mimeType"),
                        "size": p.get("size"),
                    }
                    for p in (report.get("photos") or [])
                    if isinstance(p, dict)
                ]
                field_photos += len(photo_meta)
                reports.append(
                    {
                        "at": report.get("at"),
                        "byName": report.get("byName"),
                        "text": str(report.get("text") or "")[:240],
                        "locationNote": report.get("locationNote"),
                        "peopleAssisted": report.get("peopleAssisted"),
                        "photoCount": len(photo_meta),
                        "photos": photo_meta,
                        "taskId": task.get("id"),
                        "taskTitle": task.get("title"),
                    }
                )
                try:
                    assisted += int(report.get("peopleAssisted") or 0)
                except (TypeError, ValueError):
                    pass
        evidence["reports"] = sorted(reports, key=lambda r: str(r.get("at") or ""), reverse=True)
        evidence["peopleAssistedSum"] = assisted
        evidence["photoCount"] = field_photos
        if not tasks:
            evidence["gaps"].append("No operational tasks exist for this region yet.")
        if not reports:
            evidence["gaps"].append("No field reports exist for this region yet.")
    except Exception:
        evidence["gaps"].append("Task and field-report data could not be read.")
    try:
        submissions = [
            d
            for d in json_store.list_documents("damage_assessments")
            if _in_region(d) and str(d.get("hazardId") or "") == hazard_id
        ]
        submissions.sort(key=lambda d: str(d.get("createdAt") or ""), reverse=True)
        evidence["damageAssessments"] = submissions
        totals: dict[str, float] = {}
        for field in (
            "householdsAffected", "housesDamaged", "housesDestroyed",
            "cropHectares", "livestockLost", "infraSites", "roadsKm",
        ):
            values = [d.get(field) for d in submissions if d.get(field) is not None]
            if values:
                totals[field] = round(sum(float(v) for v in values), 2)
        evidence["damageTotals"] = totals
        if not submissions:
            evidence["gaps"].append(
                "No officer damage submissions exist for this region and hazard yet."
            )
    except Exception:
        evidence["gaps"].append("Officer damage submissions could not be read.")
    try:
        # Preparedness spend may predate any hazard, so expenses with no
        # hazard set still count; expenses naming another hazard do not.
        expenses = [
            e
            for e in json_store.list_documents("expenses")
            if _in_region(e)
            and (not str(e.get("hazardId") or "") or str(e.get("hazardId") or "") == hazard_id)
        ]
        expenses.sort(key=lambda e: str(e.get("createdAt") or ""), reverse=True)
        evidence["expenses"] = expenses
        prep = [e for e in expenses if str(e.get("kind") or "") == "preparedness"]
        rec = [e for e in expenses if str(e.get("kind") or "") == "recovery"]
        evidence["expenseTotals"] = {
            "preparednessInr": round(sum(float(e.get("amountInr") or 0.0) for e in prep), 2),
            "recoveryInr": round(sum(float(e.get("amountInr") or 0.0) for e in rec), 2),
            "preparednessCount": len(prep),
            "recoveryCount": len(rec),
        }
        if not expenses:
            evidence["gaps"].append(
                "No expense records exist for this region yet; cost figures "
                "fall back to modelled proxies or Unknown."
            )
    except Exception:
        evidence["gaps"].append("Expense records could not be read.")
    try:
        attachments = [
            a
            for a in json_store.list_documents("evidence_attachments")
            if _in_region(a)
        ]
        attachments.sort(key=lambda a: str(a.get("uploadedAt") or ""), reverse=True)
        evidence["evidenceAttachments"] = attachments
        evidence["photoCount"] = int(evidence["photoCount"] or 0) + sum(
            int(a.get("photoCount") or len(a.get("photos") or [])) for a in attachments
        )
        if not attachments:
            evidence["gaps"].append("No linked evidence attachments exist for this region yet.")
    except Exception:
        evidence["gaps"].append("Evidence attachments could not be read.")
    try:
        region_doc = evidence.get("region") or {}
        sync_meta: dict[str, Any] = {}
        try:
            sync_doc = json_store.get_document("settings", "geoSync") or {}
            sync_meta = {
                "datasetRef": sync_doc.get("datasetRef"),
                "attribution": sync_doc.get("attribution"),
                "syncedAt": sync_doc.get("syncedAt"),
            }
        except Exception:
            sync_meta = {}
        evidence["geoContext"] = {
            "country": region_doc.get("countryName"),
            "countryCode": region_doc.get("countryCode"),
            "state": region_doc.get("stateName"),
            "stateCode": region_doc.get("stateCode"),
            "city": region_doc.get("cityName") or region_doc.get("name"),
            "cityId": region_doc.get("cityId"),
            "sync": sync_meta,
        }
    except Exception:
        evidence["geoContext"] = None
        evidence["gaps"].append("Geographic context could not be read.")
    # Regional population is CONTEXT ONLY: it is quoted alongside figures
    # (e.g. "% of regional population") and NEVER used as affected
    # population. No cached ambient total exists locally, so the value stays
    # None until a live /api/population readout is attached; the note says so.
    evidence["populationContext"] = {
        "regionalPopulation": None,
        "source": None,
        "note": (
            "Ambient regional population (WorldPop, via GET /api/population) is "
            "context only and is never used as affected population. No cached "
            "value is available locally; quote the live readout next to this "
            "assessment when needed."
        ),
    }
    try:
        # Local-only resolution: canonical key + catalog capabilities without
        # any network fetch. Live telemetry, warnings, and historical analogs
        # require the disaster-intelligence/history APIs and are intentionally
        # not fetched during offline assessment generation.
        from services import hazard_intelligence as _hazard_intel

        canonical_key, resolved = _hazard_intel.resolve_region(region_key)
        hazard_doc = _hazard_intel.resolve_hazard(hazard_id)
        capabilities = _hazard_intel.build_hazard_capabilities(canonical_key, resolved)
        hazard_key = _hazard_intel.normalize_key(
            hazard_doc.get("code") or hazard_doc.get("id")
        )
        evidence["intelligenceContext"] = {
            "canonicalRegionKey": canonical_key,
            "hazardImplemented": hazard_key in set(capabilities.get("implemented_hazards", [])),
            "status": "catalog-only",
            "note": (
                "Hazard/region resolved against the local catalog only. Live "
                "telemetry, active systems, and official warnings need GET "
                "/api/disaster-intelligence/{region}?hazard=... and were not "
                "fetched for this offline assessment."
            ),
        }
        evidence["historicalContext"] = {
            "hazardCovered": hazard_key in {
                _hazard_intel.normalize_key(h)
                for h in _hazard_intel.HISTORICAL_HAZARDS
            },
            "status": "catalog-only",
            "note": (
                "Historical analogs (NOAA IBTrACS cyclone tracks) need GET "
                "/api/history and were not fetched for this offline "
                "assessment; non-cyclone history is not integrated."
            ),
        }
    except Exception as exc:
        evidence["intelligenceContext"] = {
            "status": "unavailable",
            "note": f"Local hazard/region resolution failed ({exc}); live disaster "
            "intelligence was not consulted.",
        }
        evidence["historicalContext"] = {
            "status": "unavailable",
            "note": "Historical analogs were not consulted for this assessment.",
        }
        evidence["gaps"].append(
            "Disaster-intelligence and historical context could not be resolved locally."
        )
    try:
        evidence["verifiedFeedbackCount"] = sum(
            1
            for f in json_store.list_documents("assessment_feedback")
            if f.get("status") == "verified"
            and (not hazard_id or str(f.get("hazardId") or "") == hazard_id)
        )
    except Exception:
        evidence["verifiedFeedbackCount"] = 0
    return evidence


def _src(name: str, detail: str, fetched_at: str) -> dict[str, str]:
    return {"name": name, "detail": detail, "fetchedAt": fetched_at}


def build_figures(
    evidence: dict[str, Any], observed: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Compute every estimate with full workings. Returns (figures, reasoning)."""
    now = evidence["fetchedAt"]
    tasks = evidence["tasks"]
    reports = evidence["reports"]
    assisted = evidence["peopleAssistedSum"]
    hazard_id = evidence["hazardId"]
    completed = [t for t in tasks if str(t.get("status") or "") == "Submitted"]
    damage_submissions = evidence.get("damageAssessments") or []
    damage_totals: dict[str, float] = evidence.get("damageTotals") or {}
    expense_totals: dict[str, Any] = evidence.get("expenseTotals") or {}
    attachments = evidence.get("evidenceAttachments") or []
    photo_count = int(evidence.get("photoCount") or 0)
    population_ctx = evidence.get("populationContext") or {}
    regional_population = population_ctx.get("regionalPopulation")
    geo_ctx = evidence.get("geoContext") or {}
    intel_ctx = evidence.get("intelligenceContext") or {}
    hist_ctx = evidence.get("historicalContext") or {}

    def _pop_suffix(raw: Optional[float]) -> str:
        # Regional population is quoted as context only, never as a figure.
        try:
            pop = float(regional_population) if regional_population else 0.0
            val = float(raw) if raw else 0.0
        except (TypeError, ValueError):
            return ""
        if pop > 0 and val > 0:
            return f" ({val / pop * 100:.1f}% of the {pop:,.0f} regional-population context figure)."
        return ""

    def _damage_field(name: str) -> tuple[Optional[float], str, int]:
        """Resolve one damage count: observed wins, else summed submissions.

        Returns (value, origin, submission_count) with origin in
        {"observed", "submitted", "missing"}.
        """
        direct = observed.get(name)
        if direct is not None:
            return float(direct), "observed", 0
        if name in damage_totals:
            count = sum(
                1 for d in damage_submissions if d.get(name) is not None
            )
            return float(damage_totals[name]), "submitted", count
        return None, "missing", 0

    base_sources = [
        _src("regions.json", f"Region record for '{evidence['regionKey']}'", now),
        _src("hazards.json", f"Hazard record for '{hazard_id}'", now),
        _src(
            "tasks.json",
            f"{len(tasks)} task(s) in region, {len(completed)} submitted",
            now,
        ),
        _src(
            "field reports",
            f"{len(reports)} report(s), {assisted} people assisted in total, "
            f"{photo_count} photo(s) across reports and evidence attachments",
            now,
        ),
        _src(
            "damage_assessments.json",
            f"{len(damage_submissions)} officer damage submission(s) for this region and hazard",
            now,
        ),
        _src(
            "expenses.json",
            f"{len(evidence.get('expenses') or [])} expense record(s): "
            f"{int(expense_totals.get('preparednessCount') or 0)} preparedness "
            f"({_inr(expense_totals.get('preparednessInr') or 0)}), "
            f"{int(expense_totals.get('recoveryCount') or 0)} recovery "
            f"({_inr(expense_totals.get('recoveryInr') or 0)})",
            now,
        ),
        _src(
            "evidence_attachments.json",
            f"{len(attachments)} linked evidence attachment(s)",
            now,
        ),
    ]
    if geo_ctx.get("city") or geo_ctx.get("state") or geo_ctx.get("country"):
        base_sources.append(
            _src(
                "geo gazetteer",
                f"{geo_ctx.get('city') or '—'}, {geo_ctx.get('state') or '—'}, "
                f"{geo_ctx.get('country') or '—'} (context only)",
                now,
            )
        )
    base_sources.append(
        _src(
            "disaster intelligence",
            str(intel_ctx.get("note") or "Disaster intelligence not consulted."),
            now,
        )
    )
    base_sources.append(
        _src(
            "historical disasters",
            str(hist_ctx.get("note") or "Historical analogs not consulted."),
            now,
        )
    )
    if evidence["verifiedFeedbackCount"]:
        base_sources.append(
            _src(
                "assessment_feedback",
                f"{evidence['verifiedFeedbackCount']} verified correction(s) for this hazard",
                now,
            )
        )

    reasoning: list[str] = []
    figures: list[dict[str, Any]] = []

    def add_figure(
        key: str,
        label: str,
        raw: Optional[float],
        unit: str,
        calculation: str,
        assumptions: list[str],
        confidence: str,
        explanation: str,
        calibrate: bool = True,
    ) -> None:
        calibration = _calibration_for(hazard_id, key) if calibrate else None
        value, record, note = _apply_calibration(raw, calibration)
        calc = calculation + note
        if record is not None:
            assumptions = assumptions + [
                f"Includes a {record['appliedDeltaPct']:+.1f}% calibration from "
                f"{record['feedbackCount']} verified officer corrections "
                f"(median {record['medianDeltaPct']:+.1f}%)."
            ]
        figures.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "unit": unit,
                "calculation": calc,
                "assumptions": assumptions,
                "sources": base_sources,
                "confidence": confidence,
                "explanation": explanation,
                "calibratedFrom": record,
            }
        )

    # -- Affected people ----------------------------------------------------
    # Regional population is NEVER a source here: it is ambient context, not
    # a headcount of who was affected. See _pop_suffix (context quote only).
    households = observed.get("householdsAffected")
    submitted_households = damage_totals.get("householdsAffected")
    pop_guard = "Regional population is context only and was not used as affected population."
    if households is not None:
        raw_people = round(float(households) * AVG_HOUSEHOLD_SIZE)
        conf = "Medium" if reports else "Low"
        reasoning.append(
            f"Affected people derived from officer-observed {households} households "
            f"x {AVG_HOUSEHOLD_SIZE} average size"
            + (" and corroborated by field reports." if reports else " (no field reports to corroborate).")
        )
        add_figure(
            "affected_people", "Estimated affected people", raw_people, "people",
            f"{households} households x {AVG_HOUSEHOLD_SIZE} people/household = {raw_people:,.0f} people."
            + _pop_suffix(raw_people),
            [
                f"Average household size {AVG_HOUSEHOLD_SIZE} is a planning default; replace with census value.",
                "Assumes every reported household was affected to a similar degree.",
                pop_guard,
            ],
            conf,
            "Household-based headcount is a planning estimate. Field verification is required before relief lists.",
        )
    elif submitted_households is not None:
        sub_count = sum(1 for d in damage_submissions if d.get("householdsAffected") is not None)
        raw_people = round(float(submitted_households) * AVG_HOUSEHOLD_SIZE)
        conf = "Medium" if reports else "Low"
        reasoning.append(
            f"Affected people derived from {submitted_households:,.0f} households summed "
            f"across {sub_count} officer damage submission(s)."
        )
        add_figure(
            "affected_people", "Estimated affected people", raw_people, "people",
            f"{submitted_households:,.0f} households (sum of {sub_count} damage submission(s)) "
            f"x {AVG_HOUSEHOLD_SIZE} people/household = {raw_people:,.0f} people." + _pop_suffix(raw_people),
            [
                f"Average household size {AVG_HOUSEHOLD_SIZE} is a planning default; replace with census value.",
                "Sums officer submissions; overlapping reports of the same households may double-count.",
                pop_guard,
            ],
            conf,
            "Submission-based headcount is a planning estimate. Deduplicate against field verification before relief lists.",
        )
    elif assisted > 0:
        reasoning.append(
            f"No household observation; affected people lower-bounded by {assisted} assisted in field reports."
        )
        add_figure(
            "affected_people", "Estimated affected people", float(assisted), "people",
            f"Sum of peopleAssisted across {len(reports)} field report(s) = {assisted} (lower bound)."
            + _pop_suffix(float(assisted)),
            [
                "Assumes each assisted person was counted once across reports.",
                "Assisted counts measure relief delivered, not the affected headcount.",
                pop_guard,
            ],
            "Low",
            "Only people already assisted are counted — a lower bound — so the true affected "
            "population is unknown and likely higher.",
            calibrate=False,
        )
    else:
        reasoning.append("Affected people unknown: no household observation and no assisted counts.")
        add_figure(
            "affected_people", "Estimated affected people", None, "people",
            "No householdsAffected observation, no officer damage submissions with household counts, "
            "and no field-report assisted counts; cannot compute.",
            [pop_guard],
            "Low",
            "Provide householdsAffected, submit officer damage assessments, or collect field reports "
            "to enable this estimate.",
            calibrate=False,
        )

    # -- Damage lines --------------------------------------------------------
    # Each count resolves observed-first, then summed officer submissions.
    _SUBMITTED_CAVEAT = (
        "Sums officer damage submissions; overlapping reports of the same "
        "damage may double-count — verify before sanction."
    )
    damaged, damaged_origin, damaged_n = _damage_field("housesDamaged")
    destroyed, destroyed_origin, destroyed_n = _damage_field("housesDestroyed")
    if damaged is not None or destroyed is not None:
        d, s = float(damaged or 0), float(destroyed or 0)
        raw = d * REPAIR_PER_HOUSE_INR + s * REBUILD_PER_HOUSE_INR
        origins = {damaged_origin, destroyed_origin} - {"missing"}
        via_submitted = origins == {"submitted"}
        mixed = "observed" in origins and "submitted" in origins
        house_n = sum(
            1 for d in damage_submissions
            if d.get("housesDamaged") is not None or d.get("housesDestroyed") is not None
        )
        if via_submitted:
            basis = f"sums of {house_n} damage submission(s)"
        elif mixed:
            basis = "officer observation plus damage submission sums"
        else:
            basis = "officer observation"
        reasoning.append(f"Housing loss from {d:,.0f} damaged + {s:,.0f} destroyed houses ({basis}).")
        assumptions = [RATE_DISCLAIMER, "Assumes uniform damage severity within each category."]
        if via_submitted or mixed:
            assumptions.append(_SUBMITTED_CAVEAT)
        add_figure(
            "housing_loss_inr", "Housing damage", raw, "INR",
            f"{d:,.0f} x {_inr(REPAIR_PER_HOUSE_INR)} + {s:,.0f} x {_inr(REBUILD_PER_HOUSE_INR)} = {_inr(raw)} "
            f"(counts from {basis}).",
            assumptions,
            "Medium" if reports else "Low",
            "Repair-vs-rebuild split follows officer counts; survey data would raise confidence.",
        )
    else:
        reasoning.append("Housing loss unknown: no house damage observation or submissions.")
        add_figure(
            "housing_loss_inr", "Housing damage", None, "INR",
            "No housesDamaged/housesDestroyed observation and no damage submissions with house counts; "
            "cannot compute.",
            [], "Low", "Provide house damage counts or submit officer damage assessments.", calibrate=False,
        )

    hectares, hectares_origin, hectares_n = _damage_field("cropHectares")
    if hectares is not None:
        raw = float(hectares) * CROP_PER_HECTARE_INR
        basis = f"sum of {hectares_n} damage submission(s)" if hectares_origin == "submitted" else "officer observation"
        reasoning.append(f"Crop loss from {hectares} affected hectares ({basis}).")
        assumptions = [RATE_DISCLAIMER, "Assumes a single average crop value per hectare."]
        if hectares_origin == "submitted":
            assumptions.append(_SUBMITTED_CAVEAT)
        add_figure(
            "crop_loss_inr", "Crop damage", raw, "INR",
            f"{hectares} ha ({basis}) x {_inr(CROP_PER_HECTARE_INR)}/ha = {_inr(raw)}.",
            assumptions,
            "Medium" if reports else "Low",
            "Crop-cutting experiments and mandi prices are needed for a claim-grade figure.",
        )
    else:
        reasoning.append("Crop loss unknown: no crop-hectare observation or submissions.")
        add_figure(
            "crop_loss_inr", "Crop damage", None, "INR",
            "No cropHectares observation and no damage submissions with crop area; cannot compute.",
            [], "Low", "Provide affected crop hectares or submit officer damage assessments.", calibrate=False,
        )

    livestock, livestock_origin, livestock_n = _damage_field("livestockLost")
    if livestock is not None:
        raw = float(livestock) * LIVESTOCK_PER_HEAD_INR
        basis = f"sum of {livestock_n} damage submission(s)" if livestock_origin == "submitted" else "officer observation"
        reasoning.append(f"Livestock loss from {livestock} head lost ({basis}).")
        assumptions = [RATE_DISCLAIMER, "Assumes average value across species; verify with veterinary records."]
        if livestock_origin == "submitted":
            assumptions.append(_SUBMITTED_CAVEAT)
        add_figure(
            "livestock_loss_inr", "Livestock loss", raw, "INR",
            f"{livestock} head ({basis}) x {_inr(LIVESTOCK_PER_HEAD_INR)}/head = {_inr(raw)}.",
            assumptions,
            "Medium" if reports else "Low",
            "Species-wise counts would improve this estimate.",
        )
    else:
        reasoning.append("Livestock loss unknown: no observation or submissions.")
        add_figure(
            "livestock_loss_inr", "Livestock loss", None, "INR",
            "No livestockLost observation and no damage submissions with livestock counts; cannot compute.",
            [], "Low", "Provide livestock losses or submit officer damage assessments.", calibrate=False,
        )

    sites, sites_origin, sites_n = _damage_field("infraSites")
    roads, roads_origin, roads_n = _damage_field("roadsKm")
    if sites is not None or roads is not None:
        s, r = float(sites or 0), float(roads or 0)
        raw = s * INFRA_PER_SITE_INR + r * ROAD_PER_KM_INR
        origins = {sites_origin, roads_origin} - {"missing"}
        via_submitted = origins == {"submitted"}
        mixed = "observed" in origins and "submitted" in origins
        infra_n = sum(
            1 for d in damage_submissions
            if d.get("infraSites") is not None or d.get("roadsKm") is not None
        )
        if via_submitted:
            basis = f"sums of {infra_n} damage submission(s)"
        elif mixed:
            basis = "officer observation plus damage submission sums"
        else:
            basis = "officer observation"
        reasoning.append(f"Infrastructure loss from {s:,.0f} sites + {r} km roads ({basis}).")
        assumptions = [RATE_DISCLAIMER, "Assumes average site/road restoration cost."]
        if via_submitted or mixed:
            assumptions.append(_SUBMITTED_CAVEAT)
        add_figure(
            "infrastructure_loss_inr", "Infrastructure damage", raw, "INR",
            f"{s:,.0f} x {_inr(INFRA_PER_SITE_INR)} + {r} km x {_inr(ROAD_PER_KM_INR)}/km = {_inr(raw)} "
            f"(counts from {basis}).",
            assumptions,
            "Medium" if reports else "Low",
            "Engineering estimates per asset are needed for sanction-grade figures.",
        )
    else:
        reasoning.append("Infrastructure loss unknown: no observation or submissions.")
        add_figure(
            "infrastructure_loss_inr", "Infrastructure damage", None, "INR",
            "No infraSites/roadsKm observation and no damage submissions with infrastructure counts; "
            "cannot compute.",
            [], "Low", "Provide damaged sites/road length or submit officer damage assessments.", calibrate=False,
        )

    # -- Totals ---------------------------------------------------------------
    damage_values = [f["value"] for f in figures if f["key"] in DAMAGE_KEYS and f["value"] is not None]
    total = round(sum(damage_values), 2) if damage_values else None
    missing = [f["label"] for f in figures if f["key"] in DAMAGE_KEYS and f["value"] is None]
    reasoning.append(
        f"Total damage sums {len(damage_values)} of {len(DAMAGE_KEYS)} damage lines."
        + (f" Missing: {', '.join(missing)}." if missing else "")
    )
    add_figure(
        "total_damage_inr", "Total estimated damage", total, "INR",
        " + ".join(
            f"{f['label']} {_inr(f['value'])}" for f in figures if f["key"] in DAMAGE_KEYS
        )
        + (f" = {_inr(total)}." if total is not None else " (nothing to sum)."),
        (["Excludes damage lines with unknown values; true total may be higher."] if missing else [])
        + [RATE_DISCLAIMER],
        "Low" if missing or total is None else "Medium",
        "Arithmetic sum of the damage lines above; inherits their uncertainties.",
        calibrate=False,
    )

    # -- Preparation & recovery -------------------------------------------------
    # Observed spend always beats modelled proxies: direct observation first,
    # then summed expense records, then the planning proxy, else Unknown.
    prep_obs = observed.get("preparationCostInr")
    prep_exp_n = int(expense_totals.get("preparednessCount") or 0)
    prep_exp_sum = float(expense_totals.get("preparednessInr") or 0.0)
    if prep_obs is not None:
        reasoning.append("Preparation cost taken from officer-observed expenditure.")
        add_figure(
            "preparation_cost_inr", "Preparation expenses", float(prep_obs), "INR",
            f"Officer-observed expenditure = {_inr(float(prep_obs))}.",
            ["Assumes observed spend is complete and receipted."],
            "Medium",
            "Observed spend beats modelled spend; vouchers should be attached for audit.",
        )
    elif prep_exp_n > 0:
        reasoning.append(
            f"Preparation cost summed from {prep_exp_n} preparedness expense record(s)."
        )
        add_figure(
            "preparation_cost_inr", "Preparation expenses", prep_exp_sum, "INR",
            f"Sum of {prep_exp_n} preparedness expense record(s) = {_inr(prep_exp_sum)}.",
            [
                "Assumes expense records are complete, receipted, and not duplicated.",
                "Expenses naming another hazard are excluded; unassigned expenses are included.",
            ],
            "Medium",
            "Observed spend from expense records; attach receipts for audit.",
        )
    else:
        raw = float(len(completed)) * TASK_DAY_COST_INR if tasks else None
        reasoning.append(
            f"Preparation cost modelled from {len(completed)} submitted task(s)."
            if tasks else "Preparation cost unknown: no task activity, expense records, or observation."
        )
        add_figure(
            "preparation_cost_inr", "Preparation expenses", raw, "INR",
            f"{len(completed)} submitted task(s) x {_inr(TASK_DAY_COST_INR)}/task-day = {_inr(raw)}."
            if raw is not None else "No observed spend, no expense records, and no task activity; cannot compute.",
            [
                RATE_DISCLAIMER,
                "Assumes one task-day of effort per submitted task.",
                "Task-count proxy is a rough planning fallback, not observed spend.",
            ],
            "Low",
            "A rough activity proxy. Record preparedness expenses to replace it.",
        )

    rec_obs = observed.get("recoveryCostInr")
    rec_exp_n = int(expense_totals.get("recoveryCount") or 0)
    rec_exp_sum = float(expense_totals.get("recoveryInr") or 0.0)
    if rec_obs is not None:
        reasoning.append("Recovery cost taken from officer-observed expenditure.")
        add_figure(
            "recovery_cost_inr", "Recovery expenses", float(rec_obs), "INR",
            f"Officer-observed expenditure = {_inr(float(rec_obs))}.",
            ["Assumes observed spend is complete and receipted."],
            "Medium",
            "Observed spend beats modelled spend; vouchers should be attached for audit.",
        )
    elif rec_exp_n > 0:
        reasoning.append(
            f"Recovery cost summed from {rec_exp_n} recovery expense record(s)."
        )
        add_figure(
            "recovery_cost_inr", "Recovery expenses", rec_exp_sum, "INR",
            f"Sum of {rec_exp_n} recovery expense record(s) = {_inr(rec_exp_sum)}.",
            [
                "Assumes expense records are complete, receipted, and not duplicated.",
                "Expenses naming another hazard are excluded; unassigned expenses are included.",
            ],
            "Medium",
            "Observed spend from expense records; attach receipts for audit.",
        )
    elif total is not None:
        raw = round(total * RECOVERY_SHARE_OF_DAMAGE, 2)
        reasoning.append(f"Recovery cost modelled as {RECOVERY_SHARE_OF_DAMAGE:.0%} of damage.")
        add_figure(
            "recovery_cost_inr", "Recovery expenses", raw, "INR",
            f"{_inr(total)} x {RECOVERY_SHARE_OF_DAMAGE:.0%} = {_inr(raw)}.",
            ["Assumes debris removal + immediate relief scale with damage value."],
            "Low",
            "Planning share only; record recovery expenses as bills arrive.",
        )
    else:
        reasoning.append("Recovery cost unknown: damage total unknown and no observed spend.")
        add_figure(
            "recovery_cost_inr", "Recovery expenses", None, "INR",
            "No observed spend, no recovery expense records, and damage total unknown; cannot compute.",
            [], "Low", "Provide damage inputs, observed spend, or recovery expense records.", calibrate=False,
        )

    # -- Indicative relief envelope (never an eligibility decision) --------------
    if total is not None:
        raw = round(total * RELIEF_SHARE_OF_DAMAGE, 2)
        reasoning.append("Indicative relief envelope computed as a planning share of damage.")
        add_figure(
            "indicative_relief_inr",
            "Indicative relief envelope (planning only)",
            raw, "INR",
            f"{_inr(total)} x {RELIEF_SHARE_OF_DAMAGE:.0%} = {_inr(raw)}.",
            [
                "NOT an eligibility decision, NOT an offer, NOT a sanction. Eligibility is decided solely by the government.",
                "Share is a planning default for budgeting discussion.",
            ],
            "Low",
            "A budgeting envelope for discussion. Only the approved government decision creates obligations.",
        )
    else:
        reasoning.append("Relief envelope unknown: damage total unknown.")
        add_figure(
            "indicative_relief_inr", "Indicative relief envelope (planning only)", None, "INR",
            "Damage total unknown; cannot compute.",
            ["NOT an eligibility decision."],
            "Low", "Provide damage inputs to enable this envelope.", calibrate=False,
        )

    return figures, reasoning


def draft_narrative(
    evidence: dict[str, Any],
    figures: list[dict[str, Any]],
    reasoning: list[str],
    ai_client: Any = None,
) -> tuple[str, str]:
    """Return (narrative, source). AI draft when available, else template."""
    region = evidence.get("region") or {}
    region_name = region.get("name") or evidence["regionKey"]
    hazard = evidence.get("hazard") or {}
    hazard_name = hazard.get("name") or evidence["hazardId"]
    by_key = {f["key"]: f for f in figures}
    total = by_key["total_damage_inr"]["value"]
    people = by_key["affected_people"]["value"]
    template = (
        f"Preliminary assessment for {hazard_name} affecting {region_name} "
        f"(region key {evidence['regionKey']}). "
        f"Estimated affected people: {people if people is not None else 'unknown'}. "
        f"Total estimated damage: {_inr(total)}. "
        f"Evidence: {len(evidence['tasks'])} task(s), {len(evidence['reports'])} field report(s), "
        f"{len(evidence.get('damageAssessments') or [])} damage submission(s), "
        f"{len(evidence.get('expenses') or [])} expense record(s), "
        f"{len(evidence.get('evidenceAttachments') or [])} evidence attachment(s). "
        + ("Gaps: " + " ".join(evidence["gaps"]) if evidence["gaps"] else "No major evidence gaps recorded.")
        + " All figures are planning estimates with stated assumptions; none are official decisions."
    )
    if ai_client is None:
        return template, "deterministic-template"
    try:
        reply = ai_client.generate_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You draft a short preliminary disaster-damage narrative for a government officer. "
                        "Use ONLY the supplied numbers. Never invent measurements, payouts, approvals, or eligibility. "
                        "Reply as JSON: {\"narrative\": string}."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Region: {region_name}. Hazard: {hazard_name}. "
                        f"Affected people: {people}. Total damage: {_inr(total)}. "
                        f"Tasks: {len(evidence['tasks'])}. Reports: {len(evidence['reports'])}. "
                        f"Reasoning: {' | '.join(reasoning[:8])}"
                    ),
                },
            ],
            temperature=0.1,
        )
        text = str(reply.get("narrative") or "").strip()
        if len(text) < 40:
            raise ValueError("AI narrative too short")
        model = ai_client.model() if hasattr(ai_client, "model") else "meta-llama"
        return text[:2000], f"meta-llama:{model}"
    except Exception:
        return template, "deterministic-template (AI unavailable)"


def affected_areas(evidence: dict[str, Any]) -> list[str]:
    areas: list[str] = []
    region = evidence.get("region") or {}
    if region.get("name"):
        label = str(region["name"])
        if region.get("stateName"):
            label += f", {region['stateName']}"
        areas.append(label)
    for task in evidence["tasks"]:
        loc = str(task.get("location") or "").strip()
        if loc and loc not in areas:
            areas.append(loc)
    for report in evidence["reports"]:
        loc = str(report.get("locationNote") or "").strip()
        if loc and loc not in areas:
            areas.append(loc)
    for submission in evidence.get("damageAssessments") or []:
        loc = str(submission.get("locationNote") or "").strip()
        if loc and loc not in areas:
            areas.append(loc)
    return areas[:12]


def overall_confidence(figures: list[dict[str, Any]]) -> str:
    order = {"Low": 0, "Medium": 1, "High": 2}
    known = [f for f in figures if f["value"] is not None and f["key"] != "indicative_relief_inr"]
    if not known:
        return "Low"
    worst = min(order.get(f["confidence"], 0) for f in known)
    return {0: "Low", 1: "Medium", 2: "High"}[worst]


def build_ai_assessment(
    region_key: str,
    hazard_id: str,
    observed: dict[str, Any],
    notes: str,
    ai_client: Any = None,
) -> dict[str, Any]:
    evidence = gather_evidence(region_key, hazard_id)
    figures, reasoning = build_figures(evidence, observed)
    narrative, narrative_source = draft_narrative(evidence, figures, reasoning, ai_client)
    region = evidence.get("region") or {}
    hazard = evidence.get("hazard") or {}
    return {
        "engineVersion": ENGINE_VERSION,
        "generatedAt": json_store.utcnow_iso(),
        "narrative": narrative,
        "narrativeSource": narrative_source,
        "reasoning": reasoning,
        "regionKey": region_key,
        "regionName": region.get("name") or region_key,
        "regionDetail": {
            "country": region.get("countryName"),
            "state": region.get("stateName"),
            "code": region.get("code"),
        },
        "hazardId": hazard_id,
        "hazardName": hazard.get("name") or hazard_id,
        "affectedAreas": affected_areas(evidence),
        "figures": figures,
        "overallConfidence": overall_confidence(figures),
        "evidenceSummary": {
            "taskCount": len(evidence["tasks"]),
            "submittedTaskCount": sum(
                1 for t in evidence["tasks"] if str(t.get("status") or "") == "Submitted"
            ),
            "reportCount": len(evidence["reports"]),
            "peopleAssistedSum": evidence["peopleAssistedSum"],
            "damageAssessmentCount": len(evidence.get("damageAssessments") or []),
            "expenseCount": len(evidence.get("expenses") or []),
            "observedPreparednessInr": (evidence.get("expenseTotals") or {}).get(
                "preparednessInr", 0.0
            ),
            "observedRecoveryInr": (evidence.get("expenseTotals") or {}).get(
                "recoveryInr", 0.0
            ),
            "evidenceAttachmentCount": len(evidence.get("evidenceAttachments") or []),
            "photoCount": int(evidence.get("photoCount") or 0),
            "regionalPopulation": (evidence.get("populationContext") or {}).get(
                "regionalPopulation"
            ),
            "regionalPopulationNote": (evidence.get("populationContext") or {}).get(
                "note"
            ),
            "geoContext": evidence.get("geoContext"),
            "intelligenceStatus": (evidence.get("intelligenceContext") or {}).get(
                "status"
            ),
            "historicalStatus": (evidence.get("historicalContext") or {}).get("status"),
            "verifiedFeedbackCount": evidence["verifiedFeedbackCount"],
            "gaps": evidence["gaps"],
        },
        "evidenceExcerpts": evidence["reports"][:5],
        "observedInputs": observed,
        "officerNotes": notes,
        "insuranceNotes": (
            "No insurance policy, payout, or transaction ledger is connected to this system. "
            "Parametric trigger status must be evaluated separately from disaster intelligence "
            "for this region and hazard, and any claim requires authorized insurer review. "
            "This assessment makes no insurance decision."
        ),
        "disclaimer": (
            "Preliminary planning estimates generated from available local data with stated "
            "assumptions. Not an official approval, eligibility decision, insurance decision, "
            "or payment instruction. A Role 4 officer must review and decide."
        ),
    }


def compute_current(
    ai_assessment: dict[str, Any], edits: list[dict[str, Any]]
) -> dict[str, Any]:
    """Apply official edits over the immutable AI figures.

    Returns {figures: [...with currentValue...], totals: {...}, overridden: [...]}.
    The AI record is never mutated.
    """
    figures = copy.deepcopy(ai_assessment.get("figures") or [])
    by_key = {f["key"]: f for f in figures}
    for figure in figures:
        figure["currentValue"] = figure.get("value")
        figure["edited"] = False
    overridden: list[str] = []
    for edit in edits:
        path = str(edit.get("path") or "")
        if not path.startswith("figures."):
            continue
        key = path[len("figures."):]
        if key in by_key:
            by_key[key]["currentValue"] = edit.get("newValue")
            by_key[key]["edited"] = True
            overridden.append(key)
    damage = [
        by_key[k]["currentValue"] for k in DAMAGE_KEYS if by_key.get(k, {}).get("currentValue") is not None
    ]
    derived_total = round(sum(damage), 2) if damage else None
    total_edited = "total_damage_inr" in overridden
    totals = {
        "damageTotalInr": by_key["total_damage_inr"]["currentValue"]
        if total_edited
        else derived_total,
        "damageTotalDerived": derived_total,
        "damageTotalOverride": total_edited,
        "preparationInr": (by_key.get("preparation_cost_inr") or {}).get("currentValue"),
        "recoveryInr": (by_key.get("recovery_cost_inr") or {}).get("currentValue"),
        "reliefEnvelopeInr": (by_key.get("indicative_relief_inr") or {}).get("currentValue"),
        "affectedPeople": (by_key.get("affected_people") or {}).get("currentValue"),
    }
    grand_parts = [
        totals["damageTotalInr"],
        totals["preparationInr"],
        totals["recoveryInr"],
    ]
    known_parts = [p for p in grand_parts if isinstance(p, (int, float))]
    totals["grandTotalInr"] = round(sum(known_parts), 2) if known_parts else None
    return {"figures": figures, "totals": totals, "overridden": sorted(set(overridden))}

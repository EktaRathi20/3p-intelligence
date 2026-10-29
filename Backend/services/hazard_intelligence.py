"""Resolve configured hazards separately from implemented intelligence handlers."""

import re
from typing import Any

from fastapi import HTTPException

from ingestion_layer.constant import REGION_DATA
from services import json_store


async def run_cyclone_intelligence(region: str, client):
    from ingestion_layer.disaster_intelligence import build_disaster_intelligence

    return await build_disaster_intelligence(region, client)


INTELLIGENCE_HANDLERS = {"cyclone": run_cyclone_intelligence}
IMPLEMENTED_HANDLERS = frozenset(INTELLIGENCE_HANDLERS)
HISTORICAL_HAZARDS = ("cyclone",)


def normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def canonical_hazard_key(hazard: dict[str, Any]) -> str:
    return normalize_key(hazard.get("code") or hazard.get("id"))


def get_hazard_catalog() -> list[dict[str, Any]]:
    return json_store.list_documents("hazards")


def resolve_hazard(value: str) -> dict[str, Any]:
    normalized = normalize_key(value)
    if not normalized:
        raise HTTPException(status_code=422, detail="A hazard type is required.")

    for hazard in get_hazard_catalog():
        if normalized in {
            normalize_key(hazard.get("id")),
            normalize_key(hazard.get("code")),
            normalize_key(hazard.get("name")),
        }:
            return hazard

    raise HTTPException(status_code=422, detail=f"Unknown hazard type: {value}.")


def resolve_region(value: str) -> tuple[str, dict[str, Any] | None]:
    """Resolve a region id, code, or name to its ingestion key."""
    normalized = normalize_key(value)
    if not normalized:
        raise HTTPException(status_code=404, detail="Unknown region.")

    matches = []
    for region in json_store.list_documents("regions"):
        if region.get("active") is False:
            continue
        aliases = (
            region.get("id"),
            region.get("code"),
            region.get("name"),
            region.get("cityName"),
        )
        if normalized in {normalize_key(alias) for alias in aliases if alias}:
            matches.append(region)

    if len(matches) > 1:
        raise HTTPException(
            status_code=422,
            detail=f"Region '{value}' is ambiguous; use its region code or id.",
        )
    if matches:
        record = matches[0]
        region_key = str(record.get("code") or record["id"]).strip().lower()
        return region_key, record

    for region_key in REGION_DATA:
        if normalized == normalize_key(region_key):
            return region_key, None

    raise HTTPException(status_code=404, detail=f"Unknown region: {value}.")


def configured_hazards(region: dict[str, Any] | None) -> list[dict[str, Any]]:
    if region is None:
        return []

    hazard_ids = region.get("hazardIds")
    configured_ids = set(hazard_ids) if isinstance(hazard_ids, list) else set()
    return [
        hazard
        for hazard in get_hazard_catalog()
        if hazard.get("id") in configured_ids
    ]


def build_hazard_capabilities(region_key: str, region: dict[str, Any] | None):
    configured = configured_hazards(region)
    configured_ids = {hazard["id"] for hazard in configured}
    catalog = get_hazard_catalog()

    hazards = []
    for hazard in catalog:
        is_configured = hazard.get("id") in configured_ids
        if hazard.get("active", True) is False and not is_configured:
            continue
        is_implemented = canonical_hazard_key(hazard) in IMPLEMENTED_HANDLERS
        hazards.append({
            "id": hazard["id"],
            "name": hazard.get("name", hazard["id"]),
            "code": hazard.get("code"),
            "configured": is_configured,
            "implemented": is_implemented,
            "intelligence_status": (
                "available"
                if is_configured and is_implemented
                else "not_implemented"
                if is_configured
                else "not_configured"
            ),
        })

    return {
        "region": region_key,
        "hazards": hazards,
        "configured_hazards": [hazard["id"] for hazard in configured],
        "implemented_hazards": sorted(IMPLEMENTED_HANDLERS),
        "not_implemented_hazards": sorted(
            hazard["id"]
            for hazard in configured
            if canonical_hazard_key(hazard) not in IMPLEMENTED_HANDLERS
        ),
        "historical_hazards": list(HISTORICAL_HAZARDS),
        "history_coverage": {
            "complete": False,
            "note": (
                "Historical coverage currently uses NOAA IBTrACS cyclone "
                "tracks only; other hazard history sources are not integrated."
            ),
        },
    }


def unavailable_intelligence(region: str, hazard: str, status: str, message: str):
    return {
        "region": region,
        "hazard": hazard,
        "status": status,
        "supported": False,
        "message": message,
    }

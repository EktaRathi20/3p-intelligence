from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from ingestion_layer.constant import REGION_DATA, register_managed_regions
from schemas.requests import DispatchChatRequest
from services.alert_service import emit_risk_assessment_alert
from services.ai_client import client
from services.dispatch_service import create_dispatch_response
from services.hazard_intelligence import (
    IMPLEMENTED_HANDLERS,
    INTELLIGENCE_HANDLERS,
    build_hazard_capabilities,
    canonical_hazard_key,
    configured_hazards,
    resolve_hazard,
    resolve_region,
    unavailable_intelligence,
)


router = APIRouter()


@router.get("/api/disaster-intelligence/{region}")
async def get_disaster_intelligence(
    region: str,
    request: Request,
    background_tasks: BackgroundTasks,
    hazard: str = Query("cyclone"),
):
    region_key, region_record = resolve_region(region)
    hazard_record = resolve_hazard(hazard)
    hazard_key = canonical_hazard_key(hazard_record)
    configured_ids = {item["id"] for item in configured_hazards(region_record)}

    if hazard_record["id"] not in configured_ids:
        return unavailable_intelligence(
            region_key,
            hazard_key,
            "not_configured",
            f"{hazard_record.get('name', hazard_key)} intelligence is not configured for this region.",
        )

    if hazard_key not in IMPLEMENTED_HANDLERS:
        return unavailable_intelligence(
            region_key,
            hazard_key,
            "not_implemented",
            f"{hazard_record.get('name', hazard_key)} intelligence is configured for this region but is not implemented.",
        )
    if region_key not in REGION_DATA:
        register_managed_regions()
    if region_key not in REGION_DATA:
        raise HTTPException(
            status_code=503,
            detail="Regional intelligence data is unavailable for this region.",
        )

    handler = INTELLIGENCE_HANDLERS[hazard_key]
    try:
        result = await handler(region_key, client)
    except HTTPException:
        raise
    except Exception as error:
        print(f"[DISASTER INTELLIGENCE] {hazard_key} handler failed for '{region_key}': {error}")
        raise HTTPException(
            status_code=500,
            detail="Disaster intelligence processing failed.",
        ) from error

    if result.get("data_quality", {}).get("ingestion_status") == "FAILED":
        raise HTTPException(
            status_code=502,
            detail="Disaster intelligence data sources are temporarily unavailable.",
        )
    if "warnings" in result.get("data_quality", {}).get("source_errors", {}):
        raise HTTPException(
            status_code=502,
            detail="The official-warning source is temporarily unavailable; no risk level can be confirmed.",
        )
    if (
        result.get("data_quality", {}).get("telemetry_status") != "AVAILABLE"
        and not result.get("risk_assessment", {}).get("warning_floor")
    ):
        raise HTTPException(
            status_code=503,
            detail=f"There is not enough current evidence to produce a {hazard_key} assessment.",
        )

    result["hazard"] = hazard_key
    result["supported"] = True
    await emit_risk_assessment_alert(
        result.get("region", region.strip().lower()),
        result,
        background_tasks,
        request.app.state.socket_server,
    )
    return result


@router.get("/api/disaster-intelligence/{region}/capabilities")
def get_disaster_intelligence_capabilities(region: str):
    region_key, region_record = resolve_region(region)
    return build_hazard_capabilities(region_key, region_record)


@router.post("/api/dispatch-chat")
async def process_dispatch_chat(request: DispatchChatRequest):
    try:
        return await create_dispatch_response(request.query, request.region)
    except Exception as error:
        print(f"Chat API Error: {error}")
        raise HTTPException(status_code=500, detail="Failed to generate route clearance")

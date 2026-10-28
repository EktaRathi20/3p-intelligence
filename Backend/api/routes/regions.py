"""Region and hazard-type endpoints backed by the local JSON database."""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import geo_service, json_store
from services.geo_validation import (
    is_valid_region_code,
    normalize_city_id,
    normalize_country_code,
    normalize_region_code,
    normalize_state_code,
)


router = APIRouter()


# --------------------------------------------------
# Collection names
# --------------------------------------------------

REGIONS_COLLECTION = "regions"
HAZARDS_COLLECTION = "hazards"

CONFIG_COLLECTION = "settings"
CONFIG_DOCUMENT = "regionManagement"
COUNTRIES_COLLECTION = "countries"

# --------------------------------------------------
# Models
# --------------------------------------------------

class RegionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    type: str = Field(default="city", min_length=1, max_length=50)
    parentRegionId: Optional[str] = None
    code: Optional[str] = None
    active: bool = True
    hazardIds: list[str] = Field(default_factory=list)
    countryCode: str = Field(min_length=2, max_length=2)
    countryName: Optional[str] = None
    stateCode: Optional[str] = None
    stateName: Optional[str] = None
    cityId: Optional[str] = None
    cityName: Optional[str] = None


class RegionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    parentRegionId: Optional[str] = None
    code: Optional[str] = None
    active: Optional[bool] = None
    hazardIds: Optional[list[str]] = None
    countryCode: Optional[str] = None
    countryName: Optional[str] = None
    stateCode: Optional[str] = None
    stateName: Optional[str] = None
    cityId: Optional[str] = None
    cityName: Optional[str] = None


class RegionConfiguration(BaseModel):
    defaultRegionId: Optional[str] = None


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def resolve_country(country_code: Optional[str]) -> Optional[dict[str, Any]]:
    """Normalize a country code and return its stored record.

    Raises HTTP 400 when the code is missing/blank or unknown. The stored
    country name is always taken from this record, never from the client.
    """
    normalized_code = normalize_country_code(country_code)
    if not normalized_code:
        raise HTTPException(
            status_code=400,
            detail="Country is required.",
        )

    record = json_store.get_document(COUNTRIES_COLLECTION, normalized_code)

    if record is None:
        raise HTTPException(
            status_code=400,
            detail=f"Country '{normalized_code}' does not exist.",
        )

    record["code"] = normalized_code
    return record


def resolve_geography(
    country_code: Optional[str],
    state_code: Optional[str],
    city_id: Optional[str],
) -> dict[str, Any]:
    """Validate the country/state/city triple and resolve display names.

    Returns the geography fields to persist. State and city names always
    come from the provider data, ignoring client-submitted labels.
    """
    country = resolve_country(country_code)
    normalized_country = country["code"]

    try:
        has_subdivisions = geo_service.country_has_subdivisions(
            normalized_country
        )
    except geo_service.GeoDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    normalized_state = normalize_state_code(state_code)
    normalized_city = normalize_city_id(city_id)

    state: Optional[dict[str, Any]] = None
    if has_subdivisions:
        if not normalized_state:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"State/province is required for "
                    f"{country.get('name', normalized_country)}."
                ),
            )
        state = geo_service.get_state(normalized_country, normalized_state)
        if state is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"State '{normalized_state}' does not belong to "
                    f"country '{normalized_country}'."
                ),
            )
    elif normalized_state:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Country '{normalized_country}' has no state/province "
                "subdivisions; omit the state selection."
            ),
        )

    city: Optional[dict[str, Any]] = None
    if normalized_city:
        city = geo_service.get_city(normalized_city)
        if city is None:
            raise HTTPException(
                status_code=400,
                detail=f"City '{normalized_city}' does not exist.",
            )
        if city["countryCode"] != normalized_country:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"City '{city['name']}' does not belong to country "
                    f"'{normalized_country}'."
                ),
            )
        if state is not None and city.get("stateCode") != state["code"]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"City '{city['name']}' does not belong to "
                    f"'{state['name']}'."
                ),
            )

    return {
        "countryCode": normalized_country,
        "countryName": country.get("name"),
        "stateCode": state["code"] if state else None,
        "stateName": state["name"] if state else None,
        "cityId": city["id"] if city else None,
        "cityName": city["name"] if city else None,
    }


def validate_hazard_ids(hazard_ids: list[str]) -> list[str]:
    """Ensure every attached hazard id refers to a valid hazard type."""
    cleaned = [str(hazard_id).strip() for hazard_id in hazard_ids]
    cleaned = [hazard_id for hazard_id in cleaned if hazard_id]
    if not cleaned:
        return []

    hazards = json_store.list_documents(HAZARDS_COLLECTION)
    valid_ids = {hazard["id"] for hazard in hazards}
    invalid_ids = [hazard_id for hazard_id in cleaned if hazard_id not in valid_ids]
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown hazard id(s): {', '.join(sorted(set(invalid_ids)))}.",
        )
    # Deduplicate while preserving order.
    return list(dict.fromkeys(cleaned))


def ensure_region_code_unique(code: str, exclude_id: Optional[str] = None) -> None:
    """Enforce case-insensitive region-code uniqueness (HTTP 409)."""
    for region in json_store.list_documents(REGIONS_COLLECTION):
        if region.get("code") == code and region["id"] != exclude_id:
            raise HTTPException(
                status_code=409,
                detail=f"Region code '{code}' is already in use.",
            )


def normalize_region_code_or_400(code: Optional[str]) -> Optional[str]:
    """Normalize an optional region code, enforcing format when present."""
    normalized = normalize_region_code(code)
    if normalized is None:
        return None
    if not is_valid_region_code(normalized):
        raise HTTPException(
            status_code=400,
            detail=(
                "Region code must be 2-24 characters: letters, digits, "
                "hyphens or underscores, starting and ending with a "
                "letter or digit."
            ),
        )
    return normalized


def validate_parent_region(parent_id: Optional[str], region_id: Optional[str]) -> None:
    """Validate an optional parent region reference."""
    if not parent_id:
        return
    if region_id is not None and parent_id == region_id:
        raise HTTPException(
            status_code=400,
            detail="A region cannot be its own parent.",
        )
    parent = json_store.get_document(REGIONS_COLLECTION, parent_id)
    if parent is None:
        raise HTTPException(
            status_code=400,
            detail="Parent region does not exist.",
        )
    if parent.get("active") is False:
        raise HTTPException(
            status_code=400,
            detail="Parent region is inactive.",
        )


def get_configuration_data() -> dict[str, Any]:
    record = json_store.get_document(CONFIG_COLLECTION, CONFIG_DOCUMENT)

    if record is None:
        return {
            "defaultRegionId": None,
        }

    return {
        "defaultRegionId": record.get("defaultRegionId"),
    }


def validate_configuration(config: RegionConfiguration) -> None:
    if config.defaultRegionId:
        region = json_store.get_document(
            REGIONS_COLLECTION, config.defaultRegionId
        )

        if region is None:
            raise HTTPException(
                status_code=400,
                detail="Selected default region does not exist.",
            )

        if region.get("active") is False:
            raise HTTPException(
                status_code=400,
                detail="Inactive region cannot be selected as default.",
            )



def save_configuration_data(
    config: RegionConfiguration,
    merge: bool = True,
) -> dict[str, Any]:
    validate_configuration(config)

    payload = {
        "defaultRegionId": config.defaultRegionId,
        "updatedAt": json_store.utcnow_iso(),
    }

    json_store.set_document(
        CONFIG_COLLECTION, CONFIG_DOCUMENT, payload, merge=merge
    )

    return get_configuration_data()


# --------------------------------------------------
# GET: Hazard list
# GET /api/hazard-types
# --------------------------------------------------

@router.get("/api/hazard-types")
def get_hazard_types(
    activeOnly: bool = Query(default=True),
):
    try:
        hazards = json_store.list_documents(HAZARDS_COLLECTION)

        if activeOnly:
            hazards = [
                hazard for hazard in hazards
                if hazard.get("active", True) is not False
            ]

        hazards.sort(key=lambda item: item.get("name", "").lower())

        return {
            "success": True,
            "count": len(hazards),
            "hazards": hazards,
            "items": hazards,
        }

    except Exception as exc:
        print(f"Error loading hazard types: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load hazard types.",
        )


# --------------------------------------------------
# GET: Region list
# GET /api/regions
# --------------------------------------------------

@router.get("/api/regions")
def get_regions(
    activeOnly: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=1000),
):
    try:
        regions = json_store.list_documents(
            REGIONS_COLLECTION, limit=limit
        )

        if activeOnly:
            regions = [
                region for region in regions
                if region.get("active", True) is not False
            ]

        regions.sort(key=lambda item: item.get("name", "").lower())

        return {
            "success": True,
            "count": len(regions),
            "regions": regions,
            "items": regions,
        }

    except Exception as exc:
        print(f"Error loading regions: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load regions.",
        )


# --------------------------------------------------
# GET: Single region (for editing)
# GET /api/regions/{region_id}
# --------------------------------------------------

@router.get("/api/regions/{region_id}")
def get_region(region_id: str):
    try:
        region = json_store.get_document(REGIONS_COLLECTION, region_id)

        if region is None:
            raise HTTPException(
                status_code=404,
                detail="Region not found.",
            )

        return {
            "success": True,
            "region": region,
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error loading region {region_id}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load region.",
        )


# --------------------------------------------------
# POST: Create region
# POST /api/regions
# --------------------------------------------------

@router.post("/api/regions", status_code=201)
def create_region(payload: RegionCreate):
    try:
        name = payload.name.strip()

        if not name:
            raise HTTPException(
                status_code=400,
                detail="Region name is required.",
            )

        validate_parent_region(payload.parentRegionId, None)
        geography = resolve_geography(
            payload.countryCode, payload.stateCode, payload.cityId
        )
        hazard_ids = validate_hazard_ids(payload.hazardIds)
        code = normalize_region_code_or_400(payload.code)
        if code is not None:
            ensure_region_code_unique(code)

        region_data = {
            "name": name,
            "type": payload.type.strip(),
            "parentRegionId": payload.parentRegionId,
            "code": code,
            "active": payload.active,
            "hazardIds": hazard_ids,
            "createdAt": json_store.utcnow_iso(),
            "updatedAt": json_store.utcnow_iso(),
            **geography,
        }

        region_id = json_store.generate_id()
        region = json_store.set_document(
            REGIONS_COLLECTION, region_id, region_data
        )

        return {
            "success": True,
            "message": "Region created successfully.",
            "region": region,
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error creating region: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create region.",
        )


# --------------------------------------------------
# PUT: Update region
# PUT /api/regions/{region_id}
# --------------------------------------------------

@router.put("/api/regions/{region_id}")
def update_region(region_id: str, payload: RegionUpdate):
    try:
        existing = json_store.get_document(REGIONS_COLLECTION, region_id)

        if existing is None:
            raise HTTPException(
                status_code=404,
                detail="Region not found.",
            )

        updates = payload.model_dump(exclude_unset=True)

        if "name" in updates and updates["name"] is not None:
            updates["name"] = updates["name"].strip()

            if not updates["name"]:
                raise HTTPException(
                    status_code=400,
                    detail="Region name cannot be empty.",
                )

        if "type" in updates and updates["type"] is not None:
            updates["type"] = updates["type"].strip()

        if "code" in updates:
            updates["code"] = normalize_region_code_or_400(updates["code"])
            if updates["code"] is not None:
                ensure_region_code_unique(updates["code"], exclude_id=region_id)

        if "hazardIds" in updates and updates["hazardIds"] is not None:
            updates["hazardIds"] = validate_hazard_ids(updates["hazardIds"])

        if "parentRegionId" in updates:
            validate_parent_region(updates["parentRegionId"], region_id)

        geo_ids_touched = any(
            key in updates for key in ("countryCode", "stateCode", "cityId")
        )
        if geo_ids_touched:
            merged_country = updates.get(
                "countryCode", existing.get("countryCode")
            )
            if normalize_country_code(merged_country) is None:
                raise HTTPException(
                    status_code=400,
                    detail="Country is required when setting geography.",
                )
            geography = resolve_geography(
                merged_country,
                updates.get("stateCode", existing.get("stateCode")),
                updates.get("cityId", existing.get("cityId")),
            )
            updates.update(geography)
        else:
            # Client-submitted display labels are never trusted on their own.
            updates.pop("countryName", None)
            updates.pop("stateName", None)
            updates.pop("cityName", None)

        updates["updatedAt"] = json_store.utcnow_iso()
        region = json_store.update_document(
            REGIONS_COLLECTION, region_id, updates
        )

        return {
            "success": True,
            "message": "Region updated successfully.",
            "region": region,
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error updating region: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to update region.",
        )


# --------------------------------------------------
# DELETE: Delete region
# DELETE /api/regions/{region_id}
# --------------------------------------------------

@router.delete("/api/regions/{region_id}")
def delete_region(region_id: str):
    try:
        region = json_store.get_document(REGIONS_COLLECTION, region_id)

        if region is None:
            raise HTTPException(
                status_code=404,
                detail="Region not found.",
            )

        # Do not delete a region that has child regions.
        has_children = any(
            child.get("parentRegionId") == region_id
            for child in json_store.list_documents(REGIONS_COLLECTION)
        )

        if has_children:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a region that has child regions.",
            )

        config = get_configuration_data()

        if config["defaultRegionId"] == region_id:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete the default region. Change the default first.",
            )

        json_store.delete_document(REGIONS_COLLECTION, region_id)

        return {
            "success": True,
            "message": "Region deleted successfully.",
            "id": region_id,
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error deleting region: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete region.",
        )


# --------------------------------------------------
# GET: Read saved configuration
# GET /api/region-configuration
# --------------------------------------------------

@router.get("/api/region-configuration")
def get_region_configuration():
    try:
        record = json_store.get_document(CONFIG_COLLECTION, CONFIG_DOCUMENT)

        exists = record is not None
        if not exists:
            config = {
                "defaultRegionId": None,
            }
        else:
            config = {
                "defaultRegionId": record.get("defaultRegionId"),
            }

        return {
            "success": True,
            "exists": exists,
            "configuration": config,
            **config,
        }

    except Exception as exc:
        print(f"Error reading region configuration: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load region configuration.",
        )


# --------------------------------------------------
# POST: Create configuration
# POST /api/region-configuration
# --------------------------------------------------

@router.post("/api/region-configuration", status_code=201)
def create_region_configuration(payload: RegionConfiguration):
    try:
        if json_store.document_exists(CONFIG_COLLECTION, CONFIG_DOCUMENT):
            raise HTTPException(
                status_code=409,
                detail="Configuration already exists. Use PUT to update it.",
            )

        config = save_configuration_data(payload, merge=False)

        return {
            "success": True,
            "message": "Region configuration created successfully.",
            "configuration": config,
            **config,
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error creating region configuration: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create region configuration.",
        )


# --------------------------------------------------
# PUT: Update or save configuration
# PUT /api/region-configuration
# --------------------------------------------------

@router.put("/api/region-configuration")
def update_region_configuration(payload: RegionConfiguration):
    try:
        if not json_store.document_exists(CONFIG_COLLECTION, CONFIG_DOCUMENT):
            raise HTTPException(
                status_code=404,
                detail="Configuration does not exist. Use POST to create it.",
            )

        config = save_configuration_data(payload, merge=True)

        return {
            "success": True,
            "message": "Region configuration updated successfully.",
            "configuration": config,
            **config,
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error updating region configuration: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to update region configuration.",
        )


# --------------------------------------------------
# DELETE: Delete/reset configuration
# DELETE /api/region-configuration
# --------------------------------------------------

@router.delete("/api/region-configuration")
def delete_region_configuration():
    try:
        if not json_store.document_exists(CONFIG_COLLECTION, CONFIG_DOCUMENT):
            raise HTTPException(
                status_code=404,
                detail="Configuration not found.",
            )

        json_store.delete_document(CONFIG_COLLECTION, CONFIG_DOCUMENT)

        return {
            "success": True,
            "message": "Region configuration deleted successfully.",
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error deleting region configuration: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete region configuration.",
        )

# NOTE: GET /api/countries now lives in api/routes/geo.py alongside the
# state/city lookup endpoints. The response shape is unchanged.

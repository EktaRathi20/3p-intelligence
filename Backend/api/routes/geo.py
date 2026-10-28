"""Geographic lookup endpoints (countries, states, cities).

Response shapes follow the existing region-route conventions
(``{success, count, <plural>, items}``) so current frontend callers keep
working. All geographic data is served from the local JSON database (see
``services/geo_service.py``) with server-side search and pagination.
"""

from fastapi import APIRouter, HTTPException, Query

from services import geo_service

router = APIRouter()


# --------------------------------------------------
# GET: Country list
# GET /api/countries
# --------------------------------------------------
@router.get("/api/countries")
def get_countries(
    search: str = Query(default="", max_length=120),
    limit: int = Query(default=500, ge=1, le=1000),
):
    try:
        countries = geo_service.list_countries(search=search, limit=limit)
    except Exception as exc:
        print(f"Error loading countries: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load countries.",
        )

    return {
        "success": True,
        "count": len(countries),
        "countries": countries,
        "items": countries,
    }


# --------------------------------------------------
# GET: State/province list for a country
# GET /api/states?countryCode=IN
# --------------------------------------------------
@router.get("/api/states")
def get_states(
    countryCode: str = Query(min_length=2, max_length=2),
    search: str = Query(default="", max_length=120),
):
    normalized_country = countryCode.strip().upper()
    try:
        states = geo_service.list_states(normalized_country, search=search)
    except geo_service.GeoDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        print(f"Error loading states for {normalized_country}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load states.",
        )

    return {
        "success": True,
        "count": len(states),
        "countryCode": normalized_country,
        "hasSubdivisions": len(states) > 0,
        "states": states,
        "items": states,
    }


# --------------------------------------------------
# GET: City list for a state/province (paginated)
# GET /api/cities?countryCode=IN&stateCode=RJ&search=&page=1&limit=20
# --------------------------------------------------
@router.get("/api/cities")
def get_cities(
    countryCode: str = Query(min_length=2, max_length=2),
    stateCode: str | None = Query(default=None, max_length=10),
    search: str = Query(default="", max_length=120),
    page: int = Query(default=1, ge=1, le=10000),
    limit: int = Query(default=20, ge=1, le=100),
):
    normalized_country = countryCode.strip().upper()
    normalized_state = stateCode.strip().upper() if stateCode else None
    try:
        result = geo_service.search_cities(
            normalized_country,
            state_code=normalized_state,
            search=search,
            page=page,
            limit=limit,
        )
    except geo_service.GeoDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        print(
            f"Error loading cities for {normalized_country}/"
            f"{normalized_state}: {exc}"
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to load cities.",
        )

    return {
        "success": True,
        "countryCode": normalized_country,
        "stateCode": normalized_state,
        "cities": result["items"],
        "items": result["items"],
        "page": result["page"],
        "limit": result["limit"],
        "total": result["total"],
        "totalPages": result["totalPages"],
    }


# --------------------------------------------------
# GET: Geo dataset status/coverage
# GET /api/geo/status
# --------------------------------------------------
@router.get("/api/geo/status")
def get_geo_status():
    # Single cached metadata read; never raises (see geo_service).
    status = geo_service.get_status()

    return {
        "success": True,
        "synced": status.get("synced", False),
        "countries": status.get("countries"),
        "states": status.get("states", 0),
        "cities": status.get("cities", 0),
        "dataset": status.get("dataset"),
        "datasetUrl": status.get("datasetUrl"),
        "license": status.get("license"),
        "attribution": status.get("attribution"),
        "meta": status.get("meta", {}),
        "error": status.get("error"),
    }

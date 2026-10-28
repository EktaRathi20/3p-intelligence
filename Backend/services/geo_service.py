"""Geographic data service backed by the local JSON database.

Data source: the dr5hn/countries-states-cities-database dataset
(https://github.com/dr5hn/countries-states-cities-database, ODbL v1.0,
attribution required), synchronized into ``database/*.json`` by
``Backend/scripts/sync_geo_data.py``.

Storage layout (stable, unique document ids):

- ``countries.json`` -- one record per country, id is the uppercase
  ISO alpha-2 code.
- ``states.json`` -- one record per state/province, id is the
  dataset's numeric provider id rendered as a string.
- ``cities.json`` -- one record per city, id is the dataset's
  numeric provider id rendered as a string.
- ``settings.json`` / ``geoSync`` -- sync metadata written by the sync
  script (per-collection counts, dataset ref, timestamp).

Read strategy (keep file parsing low):

- Countries (250 records), per-country state lists, and the city index
  are cached in memory with a TTL, sorted/filtered in Python.
- ``country_has_subdivisions`` and ``get_state`` reuse the cached
  per-country state list, so region validation adds no extra reads.
- City search filters the cached city index in Python (equality on
  ``countryCode``/``stateCode``, prefix match on ``nameLower``) with
  ``limit``/``offset`` pagination; see ``Backend/docs/GEO_DATA_SETUP.md``.
"""

from __future__ import annotations

import time
from typing import Any

from services import json_store

COUNTRIES_COLLECTION = "countries"
STATES_COLLECTION = "states"
CITIES_COLLECTION = "cities"
SETTINGS_COLLECTION = "settings"
GEO_SYNC_DOCUMENT = "geoSync"

DATASET_NAME = "dr5hn/countries-states-cities-database"
DATASET_URL = "https://github.com/dr5hn/countries-states-cities-database"
DATASET_LICENSE = "ODbL v1.0"
ATTRIBUTION = (
    "Geographic data by Countries States Cities Database "
    f"({DATASET_URL}) | {DATASET_LICENSE}"
)

MAX_CITY_LIMIT = 100
MAX_STATE_RESULTS = 2000

# In-memory TTL caches keep hot geo reads off disk. The dataset only
# changes when the sync script runs, so multi-minute TTLs are safe.
COUNTRIES_CACHE_TTL = 600.0
STATES_CACHE_TTL = 600.0
CITIES_CACHE_TTL = 600.0
SYNC_META_CACHE_TTL = 300.0

_CACHE: dict[str, tuple[float, Any]] = {}


class GeoDataUnavailable(RuntimeError):
    """Raised when geographic data has not been synchronized yet."""

    def __init__(self) -> None:
        super().__init__(
            "Geographic data is not synchronized yet. "
            "Run: python Backend/scripts/sync_geo_data.py "
            "(see Backend/docs/GEO_DATA_SETUP.md)."
        )


def _cache_get(key: str) -> Any | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() >= expires_at:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any, ttl: float) -> None:
    _CACHE[key] = (time.monotonic() + ttl, value)


def clear_cache() -> None:
    """Clear in-memory geo caches (used after a re-sync and in tests)."""
    _CACHE.clear()
    json_store.clear_cache()


def _doc_to_state(doc_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc_id,
        "code": data.get("code"),
        "name": data.get("name"),
        "countryCode": data.get("countryCode"),
        "type": data.get("type"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
    }


def _doc_to_city(doc_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc_id,
        "name": data.get("name"),
        "stateCode": data.get("stateCode"),
        "stateName": data.get("stateName"),
        "countryCode": data.get("countryCode"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
    }


def get_sync_meta() -> dict[str, Any] | None:
    """Return the cached ``geoSync`` settings record (None when missing)."""
    cached = _cache_get("sync-meta")
    if cached is not None:
        return cached
    record = json_store.get_document(SETTINGS_COLLECTION, GEO_SYNC_DOCUMENT)
    meta = None
    if record is not None:
        meta = {key: value for key, value in record.items() if key != "id"}
    if meta is not None:
        _cache_set("sync-meta", meta, SYNC_META_CACHE_TTL)
    return meta


def ensure_synced() -> dict[str, Any]:
    """Return sync metadata, or raise when geo data was never synced."""
    meta = get_sync_meta()
    if meta is None:
        raise GeoDataUnavailable()
    return meta


def list_countries(search: str = "", limit: int = 500) -> list[dict[str, Any]]:
    """List countries (cached), optionally filtered by name/code substring."""
    cached = _cache_get("countries")
    if cached is None:
        cached = []
        for doc_id, data in json_store.read_collection(
            COUNTRIES_COLLECTION
        ).items():
            record = dict(data)
            record["id"] = doc_id
            cached.append(record)
        cached.sort(key=lambda item: str(item.get("name", "")).lower())
        _cache_set("countries", cached, COUNTRIES_CACHE_TTL)

    normalized_search = (search or "").strip().casefold()
    if normalized_search:
        cached = [
            country
            for country in cached
            if normalized_search in str(country.get("name", "")).casefold()
            or normalized_search
            in str(country.get("code", country.get("id", ""))).casefold()
        ]
    return list(cached[: max(1, limit)])


def _fetch_states(country_code: str) -> list[dict[str, Any]]:
    """Fetch and cache the full state list for one country (no filtering)."""
    cache_key = f"states:{country_code}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    states = [
        _doc_to_state(doc_id, data)
        for doc_id, data in json_store.read_collection(
            STATES_COLLECTION
        ).items()
        if data.get("countryCode") == country_code
    ]
    states.sort(key=lambda item: str(item.get("name", "")).lower())
    states = states[:MAX_STATE_RESULTS]
    _cache_set(cache_key, states, STATES_CACHE_TTL)
    return states


def list_states(country_code: str, search: str = "") -> list[dict[str, Any]]:
    """List states/provinces for a country, optionally filtered by name."""
    ensure_synced()
    normalized_country = (country_code or "").strip().upper()
    normalized_search = (search or "").strip().casefold()
    states = list(_fetch_states(normalized_country))
    if normalized_search:
        states = [
            state
            for state in states
            if normalized_search in str(state.get("name", "")).casefold()
            or normalized_search in str(state.get("code") or "").casefold()
        ]
    return states


def country_has_subdivisions(country_code: str) -> bool:
    """Check whether a country has any state/province subdivisions."""
    ensure_synced()
    normalized_country = (country_code or "").strip().upper()
    return len(_fetch_states(normalized_country)) > 0


def get_state(country_code: str, state_code: str) -> dict[str, Any] | None:
    """Return one state by country + state code, or None when not found."""
    ensure_synced()
    normalized_country = (country_code or "").strip().upper()
    normalized_state = (state_code or "").strip().upper()
    for state in _fetch_states(normalized_country):
        if str(state.get("code") or "").upper() == normalized_state:
            return dict(state)
    return None


def _fetch_cities() -> list[tuple[str, dict[str, Any]]]:
    """Fetch and cache the full city index (no filtering)."""
    cached = _cache_get("cities-index")
    if cached is not None:
        return cached
    cities = list(json_store.read_collection(CITIES_COLLECTION).items())
    _cache_set("cities-index", cities, CITIES_CACHE_TTL)
    return cities


def search_cities(
    country_code: str,
    state_code: str | None = None,
    search: str = "",
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """Search cities with pagination.

    ``state_code`` may be omitted for countries without subdivisions (or to
    search across a whole country). ``search`` is prefix-matched against the
    lowercased city name; results are ordered alphabetically with stable ids
    so duplicate city names stay distinguishable via their parent geography.
    """
    ensure_synced()
    normalized_country = (country_code or "").strip().upper()
    normalized_state = (state_code or "").strip().upper() or None
    prefix = (search or "").strip().casefold()
    page = max(1, int(page or 1))
    limit = max(1, min(MAX_CITY_LIMIT, int(limit or 20)))

    index = _fetch_cities()
    matches: list[tuple[str, str]] = []
    for doc_id, data in index:
        if data.get("countryCode") != normalized_country:
            continue
        if normalized_state and data.get("stateCode") != normalized_state:
            continue
        name_lower = str(data.get("nameLower") or "")
        if prefix and not name_lower.startswith(prefix):
            continue
        matches.append((name_lower, doc_id))
    matches.sort()

    total = len(matches)
    total_pages = max(1, (total + limit - 1) // limit) if total else 0
    offset = (page - 1) * limit

    by_id = dict(index)
    items = [
        _doc_to_city(doc_id, by_id[doc_id])
        for _, doc_id in matches[offset : offset + limit]
        if doc_id in by_id
    ]

    return {
        "items": items,
        "page": page,
        "limit": limit,
        "total": total,
        "totalPages": total_pages,
    }


def get_city(city_id: str | int) -> dict[str, Any] | None:
    """Return one city by provider id, or None when not found."""
    if isinstance(city_id, bool):
        return None
    normalized_id = str(city_id or "").strip()
    if not normalized_id or "/" in normalized_id:
        return None
    ensure_synced()
    record = json_store.get_document(CITIES_COLLECTION, normalized_id)
    if record is None:
        return None
    return _doc_to_city(record["id"], record)


def get_status() -> dict[str, Any]:
    """Report geo dataset availability and coverage (never raises)."""
    status: dict[str, Any] = {
        "synced": False,
        "dataset": DATASET_NAME,
        "datasetUrl": DATASET_URL,
        "license": DATASET_LICENSE,
        "attribution": ATTRIBUTION,
        "countries": None,
        "states": 0,
        "cities": 0,
        "meta": {},
    }
    try:
        meta = get_sync_meta()
    except Exception as exc:  # noqa: BLE001 - status must never raise
        status["error"] = f"Geo status is unavailable: {exc}"
        return status
    if meta is None:
        status["error"] = str(GeoDataUnavailable())
        return status
    status["synced"] = True
    status["countries"] = meta.get("countries")
    status["states"] = meta.get("states", 0)
    status["cities"] = meta.get("cities", 0)
    status["meta"] = {
        "dataset_ref": meta.get("datasetRef"),
        "synced_at": meta.get("syncedAt"),
    }
    return status

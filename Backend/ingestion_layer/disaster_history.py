import codecs
import csv
from datetime import datetime, timedelta, timezone
import math
import threading
import time

import requests

from ingestion_layer.cache import load_json_cache, save_json_cache
from ingestion_layer.constant import (
    ACTIVE_SYSTEM_WINDOW_DAYS,
    DATASET_STALE_DAYS,
    HISTORY_SEARCH_RADIUS_KM,
    REGION_COORDS,
    get_region_coords,
)

IBTRACS_CSV_URL = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.NI.list.v04r01.csv"
CACHE_TTL_SECONDS = 6 * 60 * 60
CACHE_FILENAME = "historical_tracks_cache.json"
CACHE_PAYLOAD_KEY = "events_by_region"
_cache_lock = threading.Lock()
_cache_loaded_at = 0.0
_cache_events_by_region = None

LATENCY_NOTE = (
    "IBTrACS best-tracks are provisional with weeks-scale latency. Recent "
    "fixes corroborate ongoing activity but absence of recent fixes does "
    "not prove no active storm; always corroborate with live telemetry."
)


def _distance_km(latitude_a, longitude_a, latitude_b, longitude_b):
    earth_radius_km = 6371.0
    latitude_delta = math.radians(latitude_b - latitude_a)
    longitude_delta = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(math.radians(latitude_a))
        * math.cos(math.radians(latitude_b))
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(haversine))


def _number(value):
    try:
        parsed = float(value)
        return parsed if parsed >= 0 else None
    except (TypeError, ValueError):
        return None


def _parse_observed_at(value):
    """Parse an IBTrACS ISO_TIME value to an aware datetime (None if bad)."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "").replace("T", " ")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text[:19], pattern)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _download_tracks_by_region():
    events_by_region = {region_key: {} for region_key in REGION_COORDS}
    recent_fixes_by_region = {region_key: [] for region_key in REGION_COORDS}
    now = datetime.now(timezone.utc)
    first_season = now.year - 30
    recent_cutoff = now - timedelta(days=ACTIVE_SYSTEM_WINDOW_DAYS)
    max_observed_at = None
    # Hoisted out of the row loop: region geometry never changes mid-parse.
    region_items = list(REGION_COORDS.items())
    region_radii = {
        region_key: HISTORY_SEARCH_RADIUS_KM.get(region_key, 250)
        for region_key in REGION_COORDS
    }

    try:
        with requests.get(IBTRACS_CSV_URL, stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            lines = codecs.iterdecode(response.iter_lines(), "utf-8-sig")
            reader = csv.DictReader(lines)
            next(reader, None)

            for row in reader:
                try:
                    season = int(row.get("SEASON", ""))
                except (TypeError, ValueError):
                    continue
                observed_at = _parse_observed_at(row.get("ISO_TIME", ""))
                if observed_at is None:
                    continue
                if max_observed_at is None or observed_at > max_observed_at:
                    max_observed_at = observed_at

                if season < first_season:
                    continue

                try:
                    latitude = float(row.get("LAT", ""))
                    longitude = float(row.get("LON", ""))
                except (TypeError, ValueError):
                    continue

                name = (row.get("NAME") or "UNNAMED").strip()
                storm_id = row.get("SID") or f"{season}:{name}"
                wind_knots = _number(row.get("WMO_WIND"))
                if wind_knots is None:
                    wind_knots = _number(row.get("USA_WIND"))
                wind_kmh = round(wind_knots * 1.852) if wind_knots is not None else None
                observed_date = observed_at.date().isoformat()
                is_recent = observed_at >= recent_cutoff

                for region_key, coordinates in region_items:
                    distance = _distance_km(
                        coordinates["lat"], coordinates["lon"], latitude, longitude
                    )
                    if distance > region_radii[region_key]:
                        continue

                    storm = events_by_region[region_key].setdefault(storm_id, {
                        "matched_cyclone": f"{name} ({season})",
                        "historical_peak_wind_kmh": None,
                        "historical_surge_meters": None,
                        "closest_approach_km": round(distance, 1),
                        "reference_period": {
                            "start_date": observed_date,
                            "end_date": observed_date,
                        },
                        "source": "NOAA IBTrACS v04r01",
                    })
                    storm["reference_period"]["start_date"] = min(
                        storm["reference_period"]["start_date"], observed_date
                    )
                    storm["reference_period"]["end_date"] = max(
                        storm["reference_period"]["end_date"], observed_date
                    )
                    storm["closest_approach_km"] = min(storm["closest_approach_km"], round(distance, 1))
                    if wind_kmh is not None and (
                        storm["historical_peak_wind_kmh"] is None
                        or wind_kmh > storm["historical_peak_wind_kmh"]
                    ):
                        storm["historical_peak_wind_kmh"] = wind_kmh

                    if is_recent:
                        recent_fixes_by_region[region_key].append({
                            "storm_id": storm_id,
                            "matched_cyclone": f"{name} ({season})",
                            "observed_at": observed_at.isoformat(),
                            "latitude": latitude,
                            "longitude": longitude,
                            "wind_kmh": wind_kmh,
                            "distance_km": round(distance, 1),
                        })
    except requests.RequestException as error:
        raise RuntimeError(f"Could not retrieve NOAA IBTrACS history: {error}") from error

    return {
        "dataset_max_observed_at": max_observed_at.isoformat() if max_observed_at else None,
        "storms_by_region": {
            region_key: sorted(
                region_events.values(),
                key=lambda event: event["reference_period"]["start_date"],
                reverse=True,
            )
            for region_key, region_events in events_by_region.items()
        },
        "recent_fixes_by_region": {
            region_key: sorted(
                fixes,
                key=lambda fix: fix["observed_at"],
                reverse=True,
            )
            for region_key, fixes in recent_fixes_by_region.items()
        },
    }


def _get_cached_tracks():
    global _cache_loaded_at, _cache_events_by_region
    has_all_regions = (
        _cache_events_by_region is not None
        and all(
            region_key in _cache_events_by_region["storms_by_region"]
            and region_key in _cache_events_by_region["recent_fixes_by_region"]
            for region_key in REGION_COORDS
        )
    )
    if has_all_regions and time.monotonic() - _cache_loaded_at < CACHE_TTL_SECONDS:
        return _cache_events_by_region

    with _cache_lock:
        has_all_regions = (
            _cache_events_by_region is not None
            and all(
                region_key in _cache_events_by_region["storms_by_region"]
                and region_key in _cache_events_by_region["recent_fixes_by_region"]
                for region_key in REGION_COORDS
            )
        )
        if not has_all_regions or time.monotonic() - _cache_loaded_at >= CACHE_TTL_SECONDS:
            cached_tracks = load_json_cache(
                CACHE_FILENAME,
                timedelta(seconds=CACHE_TTL_SECONDS),
                payload_key=CACHE_PAYLOAD_KEY,
                validator=lambda payload: (
                    isinstance(payload, dict)
                    and isinstance(payload.get("storms_by_region"), dict)
                    and isinstance(payload.get("recent_fixes_by_region"), dict)
                    and isinstance(payload.get("dataset_max_observed_at"), str)
                    and all(
                        isinstance(payload["storms_by_region"].get(region_key), list)
                        and isinstance(payload["recent_fixes_by_region"].get(region_key), list)
                        for region_key in REGION_COORDS
                    )
                ),
            )

            if cached_tracks is not None:
                _cache_events_by_region = cached_tracks
            else:
                _cache_events_by_region = _download_tracks_by_region()
                save_json_cache(
                    CACHE_FILENAME,
                    _cache_events_by_region,
                    payload_key=CACHE_PAYLOAD_KEY,
                )
            _cache_loaded_at = time.monotonic()
    return _cache_events_by_region


def _freshness_info(tracks):
    """Dataset freshness: newest fix timestamp, age, and staleness flag."""
    max_observed = _parse_observed_at(tracks.get("dataset_max_observed_at", ""))
    if max_observed is None:
        return {
            "dataset_max_observed_at": None,
            "dataset_age_days": None,
            "dataset_stale_for_active_detection": True,
        }
    age_days = (datetime.now(timezone.utc) - max_observed).days
    return {
        "dataset_max_observed_at": max_observed.isoformat(),
        "dataset_age_days": age_days,
        "dataset_stale_for_active_detection": age_days > DATASET_STALE_DAYS,
    }


def fetch_historical_disasters(region_key="vizag"):
    get_region_coords(region_key)
    tracks = _get_cached_tracks()
    events = [
        {**event, "hazard_type": "cyclone"}
        for event in tracks["storms_by_region"][region_key]
    ]
    hazards_with_records = sorted({
        event["hazard_type"]
        for event in events
        if event.get("hazard_type")
    })
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "region_target": region_key,
        "source": "NOAA IBTrACS North Indian Ocean v04r01",
        "source_url": IBTRACS_CSV_URL,
        "total_historical_events_analyzed": len(events),
        "historical_analogs": events,
        "available_hazards": ["cyclone"],
        "hazards_with_records": hazards_with_records,
        "history_coverage": {
            "complete": False,
            "note": (
                "Historical coverage currently uses NOAA IBTrACS cyclone "
                "tracks only; other hazard history sources are not integrated."
            ),
        },
        **_freshness_info(tracks),
    }


def fetch_active_systems(region_key="vizag", within_days=ACTIVE_SYSTEM_WINDOW_DAYS,
                         radius_km=None):
    """Detect recently-observed tropical systems near a region.

    Uses the same real IBTrACS download as the historical fetch: fixes
    observed within ``within_days`` inside the region radius are grouped
    per storm. See ``LATENCY_NOTE`` — this is corroborating evidence of
    current occurrence, not a real-time warning feed.
    """
    get_region_coords(region_key)
    if radius_km is None:
        radius_km = HISTORY_SEARCH_RADIUS_KM.get(region_key, 250)
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    tracks = _get_cached_tracks()
    fixes = tracks["recent_fixes_by_region"][region_key]

    systems = {}
    for fix in fixes:
        observed_at = _parse_observed_at(fix.get("observed_at", ""))
        if observed_at is None or observed_at < cutoff:
            continue
        if (fix.get("distance_km") or float("inf")) > radius_km:
            continue
        storm = systems.setdefault(fix["storm_id"], {
            "storm_id": fix["storm_id"],
            "matched_cyclone": fix["matched_cyclone"],
            "fixes_count": 0,
            "latest_observed_at": None,
            "latest_wind_kmh": None,
            "latest_latitude": None,
            "latest_longitude": None,
            "closest_approach_km": None,
        })
        storm["fixes_count"] += 1
        if (storm["latest_observed_at"] is None
                or observed_at.isoformat() > storm["latest_observed_at"]):
            storm["latest_observed_at"] = observed_at.isoformat()
            storm["latest_wind_kmh"] = fix.get("wind_kmh")
            storm["latest_latitude"] = fix.get("latitude")
            storm["latest_longitude"] = fix.get("longitude")
        distance = fix.get("distance_km")
        if distance is not None and (
                storm["closest_approach_km"] is None
                or distance < storm["closest_approach_km"]):
            storm["closest_approach_km"] = distance

    ordered = sorted(
        systems.values(),
        key=lambda storm: storm["latest_observed_at"] or "",
        reverse=True,
    )
    freshness = _freshness_info(tracks)
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "region_target": region_key,
        "source": "NOAA IBTrACS North Indian Ocean v04r01 recent fixes",
        "source_url": IBTRACS_CSV_URL,
        "within_days": within_days,
        "radius_km": radius_km,
        "latency_note": LATENCY_NOTE,
        "systems": ordered,
        **freshness,
    }
    if freshness["dataset_stale_for_active_detection"]:
        result["stale_note"] = (
            "The downloaded IBTrACS file predates the detection window, so "
            "an empty systems list reflects dataset blindness, not proof of "
            "no active storm. Official warnings take precedence."
        )
    return result

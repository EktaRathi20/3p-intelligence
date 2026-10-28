REGION_DATA = {
    "vizag": {"min_lon": 83.15, "min_lat": 17.65, "max_lon": 83.35, "max_lat": 17.75, "name": "Visakhapatnam"},
    "odisha": {"min_lon": 85.75, "min_lat": 19.75, "max_lon": 85.95, "max_lat": 19.85, "name": "Puri, Odisha"},
    "chennai": {"min_lon": 80.20, "min_lat": 12.90, "max_lon": 80.40, "max_lat": 13.10, "name": "Chennai"},
    "bengal": {"min_lon": 88.75, "min_lat": 21.50, "max_lon": 88.95, "max_lat": 21.70, "name": "Sundarbans"},
    "gujarat": {"min_lon": 69.50, "min_lat": 22.30, "max_lon": 69.70, "max_lat": 22.50, "name": "Saurashtra"},
    "paradip": {"min_lon": 86.52, "min_lat": 20.20, "max_lon": 86.72, "max_lat": 20.40, "name": "Paradip, Odisha"},
    "gopalpur": {"min_lon": 84.82, "min_lat": 19.20, "max_lon": 85.02, "max_lat": 19.40, "name": "Gopalpur, Odisha"},
    "kakinada": {"min_lon": 82.15, "min_lat": 16.90, "max_lon": 82.35, "max_lat": 17.10, "name": "Kakinada, Andhra Pradesh"},
    "mumbai": {"min_lon": 72.75, "min_lat": 18.95, "max_lon": 73.05, "max_lat": 19.20, "name": "Mumbai"},
    "bay_of_bengal": {"min_lon": 86.00, "min_lat": 15.00, "max_lon": 89.00, "max_lat": 18.00, "name": "Bay of Bengal Cyclone Zone"},
}

REGION_COORDS = {
    "vizag": {"lat": 17.6868, "lon": 83.2185},
    "odisha": {"lat": 19.8135, "lon": 85.8312},
    "chennai": {"lat": 13.0827, "lon": 80.2707},
    "bengal": {"lat": 21.8380, "lon": 88.8920},
    "gujarat": {"lat": 22.3000, "lon": 69.7000},
    "paradip": {"lat": 20.2644, "lon": 86.6085},
    "gopalpur": {"lat": 19.2584, "lon": 84.9052},
    "kakinada": {"lat": 16.9891, "lon": 82.2475},
    "mumbai": {"lat": 19.0760, "lon": 72.8777},
    "bay_of_bengal": {"lat": 16.5000, "lon": 87.5000},
}

HISTORY_SEARCH_RADIUS_KM = {
    # City-scale anchors: fixes within typical district warning range.
    "vizag": 250,
    "kakinada": 250,
    "chennai": 250,
    "mumbai": 250,
    "paradip": 200,
    "gopalpur": 200,
    # State-scale anchors: wider net for state-level exposure.
    "odisha": 400,
    "gujarat": 500,
    "bengal": 500,
    # Basin-scale watch zone: must see cyclones anywhere in the Bay,
    # including systems whose landfall is 500+ km from the anchor.
    "bay_of_bengal": 1500,
}


def get_region_coords(region_key):
    if region_key not in REGION_COORDS:
        register_managed_regions()
    try:
        return REGION_COORDS[region_key]
    except KeyError as error:
        raise ValueError(f"Unsupported region: {region_key}") from error


def register_managed_regions():
    """Expose managed city/state regions to the ingestion endpoints."""
    from services import geo_service, json_store

    for region in json_store.list_documents("regions"):
        if region.get("active") is False:
            continue

        region_key = str(region.get("code") or region.get("id") or "").lower()
        if not region_key or region_key in REGION_COORDS:
            continue

        geography = None
        city_id = region.get("cityId")
        if city_id:
            geography = geo_service.get_city(city_id)
        if geography is None and region.get("stateCode"):
            geography = geo_service.get_state(
                region.get("countryCode", ""),
                region["stateCode"],
            )
        if geography is None:
            continue

        try:
            latitude = float(geography["latitude"])
            longitude = float(geography["longitude"])
        except (KeyError, TypeError, ValueError):
            continue

        REGION_COORDS[region_key] = {"lat": latitude, "lon": longitude}
        REGION_DATA[region_key] = {
            "min_lon": longitude - 0.1,
            "min_lat": latitude - 0.1,
            "max_lon": longitude + 0.1,
            "max_lat": latitude + 0.1,
            "name": region.get("name") or geography.get("name") or region_key,
        }


# -----------------------------------------------------------
# Deterministic screening thresholds (documented, citable)
# -----------------------------------------------------------
# Wind boundaries follow the India Meteorological Department (IMD)
# tropical-cyclone intensity scale for the North Indian Ocean
# (3-minute sustained winds):
#   Cyclonic Storm >= 62 km/h, Severe Cyclonic Storm >= 88 km/h,
#   Very Severe Cyclonic Storm >= 118 km/h.
# Pressure bands are screening heuristics for unusually low mean
# sea-level pressure near a coastal region, not IMD categories.
IMD_CYCLONIC_STORM_KMH = 62.0
IMD_SEVERE_CYCLONIC_STORM_KMH = 88.0
IMD_VERY_SEVERE_CYCLONIC_STORM_KMH = 118.0

PRESSURE_LOW_HPA = 995.0
PRESSURE_VERY_LOW_HPA = 980.0

# Wave-height screening bands follow the WMO Douglas sea-state scale
# (significant wave height): >= 2.5 m "rough", >= 4 m "very rough",
# >= 6 m "high". Used only as an observed-marine-signal screen.
WMO_WAVE_ROUGH_M = 2.5
WMO_WAVE_VERY_ROUGH_M = 4.0
WMO_WAVE_HIGH_M = 6.0

# Active-system detection: a recent IBTrACS fix within this window and
# the per-region history radius counts as current-occurrence evidence.
# IBTrACS best-tracks are provisional with weeks-scale latency, so this
# is corroborating evidence, never a real-time warning feed.
ACTIVE_SYSTEM_WINDOW_DAYS = 7

# Risk-score bands mapping the deterministic screening score to levels.
RISK_SCORE_RED = 75
RISK_SCORE_ORANGE = 50
RISK_SCORE_YELLOW = 25
RISK_SCORE_MAX = 100

# IBTrACS dataset freshness: active-system detection is blind when the
# newest fix in the downloaded file predates the detection window.
DATASET_STALE_DAYS = ACTIVE_SYSTEM_WINDOW_DAYS

# Official warnings (GDACS): only current episodes whose end date falls
# inside this recency window can raise the risk level.
WARNING_RECENCY_DAYS = 3

# Official-warning severity floor: a verified warning at/above YELLOW
# raises the reported level to at least the mapped floor. Screening can
# only raise the level further, never lower it below the floor.
WARNING_LEVEL_FLOOR = {
    "RED": "RED",
    "ORANGE": "ORANGE",
    "YELLOW": "YELLOW",
}
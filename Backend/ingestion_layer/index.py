import json
from datetime import timedelta
from pathlib import Path
from ingestion_layer.cache import INGESTED_DIR, load_json_cache, save_json_cache
from ingestion_layer.gee import init_gee, fetch_sar_imagery, REGION_DATA
from ingestion_layer.weather import fetch_meteorological_telemetry
from ingestion_layer.weather import fetch_7_day_forecast, fetch_marine_conditions
from ingestion_layer.population import fetch_population
from ingestion_layer.disaster_history import fetch_historical_disasters
from ingestion_layer.disaster_history import fetch_active_systems
from ingestion_layer.places import fetch_critical_infrastructure
from ingestion_layer.official_warnings import fetch_warnings_for_region
from ingestion_layer.constant import register_managed_regions

RUN_INGESTION_CACHE_TTL = timedelta(hours=6)


def _load_recent_ingestion(region):
    region_metadata = REGION_DATA.get(region)
    if region_metadata is None:
        return None

    image_path = INGESTED_DIR / f"scan_{region}.png"
    return load_json_cache(
        f"unified_payload_{region}.json",
        RUN_INGESTION_CACHE_TTL,
        use_file_mtime=True,
        validator=lambda payload: (
            isinstance(payload, dict)
            and payload.get("region_metadata") == region_metadata
            # Payload schema version: payloads cached before the
            # marine/active-systems/warnings sections existed must be
            # refetched instead of served stale.
            and isinstance(payload.get("marine"), dict)
            and isinstance(payload.get("active_systems"), dict)
            and isinstance(payload.get("warnings"), dict)
            and isinstance(payload.get("warnings", {}).get("local_impact"), dict)
            and (
                image_path.is_file()
                or payload.get("satellite_frame_path") is None
            )
        ),
    )


def run_ingestion(region="vizag"):
    register_managed_regions()
    cached_payload = _load_recent_ingestion(region)
    if cached_payload is not None:
        return cached_payload

    # GEE (guarded: a satellite outage must not fail all of ingestion)
    region_meta = REGION_DATA.get(region, {})
    image_bytes = None
    try:
        init_gee()
        image_bytes, region_meta = fetch_sar_imagery(region)
    except Exception as error:
        print(f"[INGESTION] Satellite imagery unavailable for '{region}': {error}")

    # IMD
    weather_data = fetch_meteorological_telemetry(region)

    #7 days
    forcast = fetch_7_day_forecast(region)

    # MARINE (individually guarded: a marine outage must not fail ingestion)
    try:
        marine_data = fetch_marine_conditions(region)
    except Exception as error:
        print(f"[INGESTION] Marine conditions unavailable for '{region}': {error}")
        marine_data = {
            "region_target": region,
            "source": "Open-Meteo Marine API",
            "source_errors": {"ingestion": str(error)},
        }

    # POPULATION
    population = fetch_population(region)

    #PLACES
    places = fetch_critical_infrastructure(region)

    # Disaster History
    disaster_history_data = fetch_historical_disasters(region)

    # Active tropical systems (same IBTrACS download; guarded likewise)
    try:
        active_systems_data = fetch_active_systems(region)
    except Exception as error:
        print(f"[INGESTION] Active-system detection unavailable for '{region}': {error}")
        active_systems_data = {
            "region_target": region,
            "source": "NOAA IBTrACS North Indian Ocean v04r01 recent fixes",
            "systems": [],
            "source_error": str(error),
        }

    # Official warnings (GDACS; guarded likewise)
    try:
        warnings_data = fetch_warnings_for_region(region)
    except Exception as error:
        print(f"[INGESTION] Official warnings unavailable for '{region}': {error}")
        warnings_data = {
            "region_target": region,
            "source": "GDACS (UN Global Disaster Alert and Coordination System)",
            "warnings": [],
            "source_error": str(error),
        }

    # Output Directory
    output_dir = INGESTED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save Image (when the satellite fetch succeeded)
    image_filepath = output_dir / f"scan_{region}.png"
    if image_bytes is not None:
        image_filepath.write_bytes(image_bytes)

    # Telemetry JSON
    telemetry_filepath = output_dir / f"telemetry_{region}.json"
    with open(telemetry_filepath, "w") as f:
        json.dump(weather_data, f, indent=2)

    # Population JSON
    pop_history_filepath = output_dir / f"population_{region}.json"
    with open(pop_history_filepath, "w") as f:
        json.dump(population, f, indent=2)

    # Disaster JSON
    with open(output_dir / f"history_{region}.json", "w") as f:
        json.dump(disaster_history_data, f, indent=2)

    compiled_payload = {
        "region_metadata": region_meta,
        "satellite_frame_path": (
            str(Path("data/ingested") / image_filepath.name)
            if image_bytes is not None
            else None
        ),
        "meteorological_telemetry": weather_data,
        "forcast":forcast,
        "marine": marine_data,
        "demography": population,
        "places":places,
        "history": disaster_history_data,
        "active_systems": active_systems_data,
        "warnings": warnings_data,
    }

    compiled_filepath = output_dir / f"unified_payload_{region}.json"
    save_json_cache(compiled_filepath.name, compiled_payload)

    return compiled_payload

if __name__ == "__main__":
    result = run_ingestion("odisha")
    print(result)

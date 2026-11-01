import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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

# Independent ingestion units run concurrently (each is network-bound).
INGESTION_MAX_WORKERS = 9

# Serializes artifact writes and same-region pipeline runs so concurrent
# requests share one cold run instead of stampeding external providers.
_artifact_lock = threading.Lock()
_region_locks_guard = threading.Lock()
_region_locks: dict[str, threading.Lock] = {}


def _region_lock(region):
    with _region_locks_guard:
        lock = _region_locks.get(region)
        if lock is None:
            lock = threading.Lock()
            _region_locks[region] = lock
        return lock


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


def _fetch_satellite(region, region_meta, gee_ready):
    """GEE SAR imagery (guarded: an outage must not fail ingestion)."""
    if not gee_ready:
        return None, region_meta
    try:
        return fetch_sar_imagery(region)
    except Exception as error:
        print(f"[INGESTION] Satellite imagery unavailable for '{region}': {error}")
        return None, region_meta


def _fetch_marine_guarded(region):
    """Marine conditions (guarded: an outage must not fail ingestion)."""
    try:
        return fetch_marine_conditions(region)
    except Exception as error:
        print(f"[INGESTION] Marine conditions unavailable for '{region}': {error}")
        return {
            "region_target": region,
            "source": "Open-Meteo Marine API",
            "source_errors": {"ingestion": str(error)},
        }


def _fetch_active_systems_guarded(region):
    """Active tropical systems (same IBTrACS download; guarded likewise)."""
    try:
        return fetch_active_systems(region)
    except Exception as error:
        print(f"[INGESTION] Active-system detection unavailable for '{region}': {error}")
        return {
            "region_target": region,
            "source": "NOAA IBTrACS North Indian Ocean v04r01 recent fixes",
            "systems": [],
            "source_error": str(error),
        }


def _fetch_warnings_guarded(region):
    """Official warnings (GDACS; guarded likewise)."""
    try:
        return fetch_warnings_for_region(region)
    except Exception as error:
        print(f"[INGESTION] Official warnings unavailable for '{region}': {error}")
        return {
            "region_target": region,
            "source": "GDACS (UN Global Disaster Alert and Coordination System)",
            "warnings": [],
            "source_error": str(error),
        }


def _run_pipeline(region):
    """Execute every ingestion unit concurrently and compile the payload.

    Failure semantics match the previous sequential implementation:
    telemetry, forecast, population, places, and history failures
    propagate (failing the run), while satellite, marine, active-system,
    and warning failures degrade to guarded fallbacks. Results are
    collected in the original order so the same failure surfaces first.
    """
    base_meta = REGION_DATA.get(region, {})

    # GEE initialization stays up-front: the SAR and population units both
    # need an initialized client, exactly as in the sequential version.
    gee_ready = True
    try:
        init_gee()
    except Exception as error:
        gee_ready = False
        print(f"[INGESTION] Satellite imagery unavailable for '{region}': {error}")

    durations: dict[str, float] = {}

    def timed(name, func, *args):
        def _run():
            started = time.monotonic()
            try:
                return func(*args)
            finally:
                durations[name] = time.monotonic() - started

        return _run

    fan_out_started = time.monotonic()
    with ThreadPoolExecutor(max_workers=INGESTION_MAX_WORKERS) as pool:
        satellite_future = pool.submit(timed("satellite", _fetch_satellite, region, base_meta, gee_ready))
        telemetry_future = pool.submit(timed("telemetry", fetch_meteorological_telemetry, region))
        forecast_future = pool.submit(timed("forecast", fetch_7_day_forecast, region))
        marine_future = pool.submit(timed("marine", _fetch_marine_guarded, region))
        population_future = pool.submit(timed("population", fetch_population, region))
        places_future = pool.submit(timed("places", fetch_critical_infrastructure, region))
        history_future = pool.submit(timed("history", fetch_historical_disasters, region))
        active_future = pool.submit(timed("active", _fetch_active_systems_guarded, region))
        warnings_future = pool.submit(timed("warnings", _fetch_warnings_guarded, region))

        image_bytes, region_meta = satellite_future.result()
        weather_data = telemetry_future.result()
        forcast = forecast_future.result()
        marine_data = marine_future.result()
        population = population_future.result()
        places = places_future.result()
        disaster_history_data = history_future.result()
        active_systems_data = active_future.result()
        warnings_data = warnings_future.result()

    unit_order = (
        "satellite", "telemetry", "forecast", "marine", "population",
        "places", "history", "active", "warnings",
    )
    breakdown = " ".join(f"{name}={durations.get(name, 0.0):.1f}s" for name in unit_order)
    print(
        f"[INGESTION] region={region} wall={time.monotonic() - fan_out_started:.1f}s "
        f"({breakdown})"
    )

    with _artifact_lock:
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


def run_ingestion(region="vizag"):
    register_managed_regions()
    cached_payload = _load_recent_ingestion(region)
    if cached_payload is not None:
        return cached_payload

    # Stampede guard: concurrent cold requests for one region share a
    # single pipeline run instead of duplicating every external call.
    with _region_lock(region):
        cached_payload = _load_recent_ingestion(region)
        if cached_payload is not None:
            return cached_payload
        return _run_pipeline(region)

if __name__ == "__main__":
    result = run_ingestion("odisha")
    print(result)

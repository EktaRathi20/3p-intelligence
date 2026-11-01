"""Throwaway concurrency verification for the latency fix (NOT committed).

Measures, with stubbed network fetchers (each sleeps SLEEP seconds):
  1. run_ingestion pipeline: old sequential order vs new _run_pipeline fan-out.
  2. Failure semantics preserved (propagating vs guarded units).
  3. Stampede guard: concurrent cold run_ingestion calls share one pipeline run.
  4. Marine / Places / GDACS-CAP parallelism: sequential vs concurrent.

Run from Backend/: python .tmp/p3verify/measure_concurrency.py
"""

import sys
import threading
import time
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[2] / "Backend"
sys.path.insert(0, str(BACKEND))

SLEEP = 1.0
WORK = Path(__file__).resolve().parent / "work"
WORK.mkdir(parents=True, exist_ok=True)

from ingestion_layer import index as ingestion_index  # noqa: E402
from ingestion_layer import cache as cache_module  # noqa: E402
from ingestion_layer import weather as weather_module  # noqa: E402
from ingestion_layer import places as places_module  # noqa: E402
from ingestion_layer import official_warnings as warnings_module  # noqa: E402

RESULTS = []


def sleeper(name, result=None, error=None):
    def _fn(*args, **kwargs):
        time.sleep(SLEEP)
        if error is not None:
            raise error
        return result() if callable(result) else result

    _fn.__name__ = name
    return _fn


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print(f"[{'PASS' if condition else 'FAIL'}] {name} {detail}")


# ---------------------------------------------------------------- pipeline
def test_pipeline_parallelism():
    units = {
        "init_gee": sleeper("init_gee", result=None),
        "fetch_sar_imagery": sleeper("sar", result=(b"img", {"name": "Vizag"})),
        "fetch_meteorological_telemetry": sleeper("telemetry", result={"t": 1}),
        "fetch_7_day_forecast": sleeper("forecast", result={"f": 1}),
        "fetch_marine_conditions": sleeper("marine", result={"m": 1}),
        "fetch_population": sleeper("population", result={"p": 1}),
        "fetch_critical_infrastructure": sleeper("places", result={"pl": 1}),
        "fetch_historical_disasters": sleeper("history", result={"h": 1}),
        "fetch_active_systems": sleeper("active", result={"a": 1}),
        "fetch_warnings_for_region": sleeper("warnings", result={"w": 1}),
    }
    with (
        mock.patch.object(ingestion_index, "INGESTED_DIR", WORK),
        mock.patch.object(cache_module, "INGESTED_DIR", WORK),
        mock.patch.object(ingestion_index, "init_gee", units["init_gee"]),
        mock.patch.object(ingestion_index, "fetch_sar_imagery", units["fetch_sar_imagery"]),
        mock.patch.object(ingestion_index, "fetch_meteorological_telemetry", units["fetch_meteorological_telemetry"]),
        mock.patch.object(ingestion_index, "fetch_7_day_forecast", units["fetch_7_day_forecast"]),
        mock.patch.object(ingestion_index, "fetch_marine_conditions", units["fetch_marine_conditions"]),
        mock.patch.object(ingestion_index, "fetch_population", units["fetch_population"]),
        mock.patch.object(ingestion_index, "fetch_critical_infrastructure", units["fetch_critical_infrastructure"]),
        mock.patch.object(ingestion_index, "fetch_historical_disasters", units["fetch_historical_disasters"]),
        mock.patch.object(ingestion_index, "fetch_active_systems", units["fetch_active_systems"]),
        mock.patch.object(ingestion_index, "fetch_warnings_for_region", units["fetch_warnings_for_region"]),
    ):
        # BEFORE: the old sequential order (init + 9 fetchers, one by one).
        started = time.monotonic()
        for key in (
            "init_gee", "fetch_sar_imagery", "fetch_meteorological_telemetry",
            "fetch_7_day_forecast", "fetch_marine_conditions", "fetch_population",
            "fetch_critical_infrastructure", "fetch_historical_disasters",
            "fetch_active_systems", "fetch_warnings_for_region",
        ):
            units[key]("vizag")
        before = time.monotonic() - started

        # AFTER: the new fanned-out pipeline (init, then 9 units at once).
        started = time.monotonic()
        payload = ingestion_index._run_pipeline("vizag")
        after = time.monotonic() - started

    expected_keys = {
        "region_metadata", "satellite_frame_path", "meteorological_telemetry",
        "forcast", "marine", "demography", "places", "history",
        "active_systems", "warnings",
    }
    print(f"  pipeline sequential(before)={before:.1f}s  fanned-out(after)={after:.1f}s")
    check("pipeline wall time collapses (10xSLEEP -> ~2xSLEEP)", after < before / 3,
          f"before={before:.1f}s after={after:.1f}s")
    check("payload shape preserved", expected_keys <= set(payload), f"keys={sorted(payload)}")
    check("satellite artifact path set", payload["satellite_frame_path"] is not None)
    return before, after


def test_pipeline_failure_semantics():
    ok = sleeper("ok", result={"ok": 1})
    sar_ok = sleeper("sar-ok", result=(b"img", {"name": "Vizag"}))
    boom = sleeper("boom", error=RuntimeError("provider down"))
    patches = {
        "init_gee": sleeper("init", result=None),
        "fetch_sar_imagery": sar_ok, "fetch_meteorological_telemetry": ok,
        "fetch_7_day_forecast": ok, "fetch_marine_conditions": ok,
        "fetch_population": ok, "fetch_critical_infrastructure": ok,
        "fetch_historical_disasters": ok, "fetch_active_systems": ok,
        "fetch_warnings_for_region": ok,
    }

    def run_with(overrides):
        applied = dict(patches)
        applied.update(overrides)
        stack = [
            mock.patch.object(ingestion_index, "INGESTED_DIR", WORK),
            mock.patch.object(cache_module, "INGESTED_DIR", WORK),
        ]
        stack += [mock.patch.object(ingestion_index, name, fn) for name, fn in applied.items()]
        with stack[0]:
            with stack[1]:
                for ctx in stack[2:]:
                    ctx.__enter__()
                try:
                    return ingestion_index._run_pipeline("vizag")
                finally:
                    for ctx in reversed(stack[2:]):
                        ctx.__exit__(None, None, None)

    # Propagating unit (telemetry) must still fail the run.
    try:
        run_with({"fetch_meteorological_telemetry": boom})
        check("telemetry failure propagates", False, "no exception raised")
    except RuntimeError as error:
        check("telemetry failure propagates", str(error) == "provider down", str(error))

    # Guarded units must degrade to fallbacks, not fail the run.
    payload = run_with({
        "fetch_marine_conditions": boom,
        "fetch_active_systems": boom,
        "fetch_warnings_for_region": boom,
        "fetch_sar_imagery": boom,
    })
    check("marine guarded fallback", payload["marine"].get("source_errors"),
          str(payload["marine"].get("source_errors")))
    check("active-systems guarded fallback", payload["active_systems"].get("source_error") is not None)
    check("warnings guarded fallback", payload["warnings"].get("source_error") is not None)
    check("satellite guarded fallback", payload["satellite_frame_path"] is None)


def test_stampede_guard():
    calls = {"n": 0}
    real_run = ingestion_index._run_pipeline
    populated = threading.Event()

    def counting_run(region):
        calls["n"] += 1
        try:
            return real_run(region)
        finally:
            populated.set()

    def fake_cache(region):
        # Miss until the first pipeline run completes, then hit —
        # mirroring the real file cache the winner populates.
        return {"cached": True} if populated.is_set() else None

    ok = sleeper("ok", result={"ok": 1})
    patches = {name: ok for name in (
        "fetch_meteorological_telemetry", "fetch_7_day_forecast",
        "fetch_marine_conditions", "fetch_population", "fetch_critical_infrastructure",
        "fetch_historical_disasters", "fetch_active_systems", "fetch_warnings_for_region",
    )}
    patches["fetch_sar_imagery"] = sleeper("sar-ok", result=(b"img", {"name": "Vizag"}))
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(mock.patch.object(ingestion_index, "INGESTED_DIR", WORK))
    stack.enter_context(mock.patch.object(cache_module, "INGESTED_DIR", WORK))
    stack.enter_context(mock.patch.object(ingestion_index, "init_gee", sleeper("init", result=None)))
    stack.enter_context(mock.patch.object(ingestion_index, "_load_recent_ingestion", side_effect=fake_cache))
    stack.enter_context(mock.patch.object(ingestion_index, "_run_pipeline", side_effect=counting_run))
    for name, fn in patches.items():
        stack.enter_context(mock.patch.object(ingestion_index, name, fn))
    # Bypass register_managed_regions file reads for speed determinism.
    stack.enter_context(mock.patch.object(ingestion_index, "register_managed_regions", return_value=None))
    with stack:
        threads = [threading.Thread(target=lambda: ingestion_index.run_ingestion("vizag"))
                   for _ in range(5)]
        started = time.monotonic()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        elapsed = time.monotonic() - started
    print(f"  5 concurrent cold calls took {elapsed:.1f}s with {calls['n']} pipeline run(s)")
    check("concurrent cold calls share one pipeline run", calls["n"] == 1, f"runs={calls['n']}")


# ------------------------------------------------------- marine/places/CAP
def test_marine_parallelism():
    def fake_request(latitude, longitude, **params):
        time.sleep(SLEEP)
        if "daily" in params:
            return {"daily": {"time": ["2024-01-01"], "wave_height_max": [3.1]}}
        if "wave_direction" in params.get("current", ""):
            return {"current": {"wave_direction": 180, "wave_period": 9.5,
                               "ocean_current_velocity": 0.4, "sea_level_height_msl": 0.12}}
        return {"current": {"wave_height": 2.8, "sea_surface_temperature": 29.1}}

    with (
        mock.patch.object(weather_module, "_marine_request", side_effect=fake_request),
        mock.patch.object(weather_module, "load_json_cache", return_value=None),
        mock.patch.object(weather_module, "save_json_cache"),
    ):
        started = time.monotonic()
        result = weather_module.fetch_marine_conditions("vizag")
        elapsed = time.monotonic() - started
    print(f"  marine 3 groups: sequential would be {3 * SLEEP:.1f}s, measured {elapsed:.1f}s")
    check("marine groups fetched concurrently", elapsed < 2 * SLEEP, f"{elapsed:.1f}s")
    check("marine merge intact", result["wave_height_m"] == 2.8 and result["wave_direction_deg"] == 180.0
          and len(result["forecast_wave_height_max_7d"]) == 1 and result["source_errors"] == {})


def test_places_parallelism():
    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        time.sleep(SLEEP)
        response = mock.Mock()
        response.ok = True
        if "searchNearby" in url:
            response.json.return_value = {"places": [{
                "displayName": {"text": "City Hospital"},
                "formattedAddress": "1 Main St",
                "location": {"latitude": 17.6868, "longitude": 83.2185},
            }]}
        else:
            response.json.return_value = {"places": [{
                "displayName": {"text": "Relief Shelter"},
                "formattedAddress": "2 Main St",
                "location": {"latitude": 17.6868, "longitude": 83.2185},
            }]}
        return response

    with (
        mock.patch.object(places_module.requests, "post", side_effect=fake_post),
        mock.patch.object(places_module, "load_json_cache", return_value=None),
        mock.patch.object(places_module, "save_json_cache"),
        mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}),
    ):
        started = time.monotonic()
        result = places_module.fetch_critical_infrastructure("vizag")
        elapsed = time.monotonic() - started
    print(f"  places 2 queries: sequential would be {2 * SLEEP:.1f}s, measured {elapsed:.1f}s")
    check("places queries run concurrently", elapsed < 2 * SLEEP, f"{elapsed:.1f}s")
    check("places merge intact", [h["name"] for h in result["hospitals"]] == ["City Hospital"]
          and [s["name"] for s in result["shelters"]] == ["Relief Shelter"]
          and result["source_errors"] == {})


def test_cap_parallelism():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    events = []
    for index in range(3):
        events.append({
            "event_id": f"SYNTH-{index}", "episode_id": f"EP-{index}",
            "event_name": f"SYNTH-{index}", "event_type": "TC",
            "alert_level": "RED", "episode_alert_level": "RED",
            "iso3": "IND", "country": "India",
            "latitude": 16.4, "longitude": 81.8,
            "bbox": {"lonmin": 71.0, "lonmax": 97.0, "latmin": 3.8, "latmax": 29.8},
            "fromdate": (now - timedelta(days=1)).isoformat(),
            "todate": (now + timedelta(days=1)).isoformat(),
            "datemodified": now.isoformat(), "is_current": True,
            "link": "https://www.gdacs.org/report.aspx?eventid=1",
            "cap_url": f"https://www.gdacs.org/cap_{index}.xml",
            "glide": f"TC-2026-00000{index}-IND",
        })

    def fake_footprint(event):
        time.sleep(SLEEP)
        return {"polygons": [], "circles": []}

    with (
        mock.patch.object(warnings_module, "_get_cached_events", return_value=events),
        mock.patch.object(warnings_module, "fetch_footprint_for_event", side_effect=fake_footprint),
    ):
        started = time.monotonic()
        result = warnings_module.fetch_warnings_for_region("odisha")
        elapsed = time.monotonic() - started
    print(f"  CAP 3 footprints: sequential would be {3 * SLEEP:.1f}s, measured {elapsed:.1f}s")
    check("CAP footprints fetched concurrently", elapsed < 2 * SLEEP, f"{elapsed:.1f}s")
    check("warnings carry footprints in order",
          [w["event_name"] for w in result["warnings"]] == ["SYNTH-0", "SYNTH-1", "SYNTH-2"]
          and all(w["footprint"] == {"polygons": [], "circles": []} for w in result["warnings"]))


if __name__ == "__main__":
    print("=== pipeline ===")
    test_pipeline_parallelism()
    test_pipeline_failure_semantics()
    test_stampede_guard()
    print("=== sub-fetchers ===")
    test_marine_parallelism()
    test_places_parallelism()
    test_cap_parallelism()
    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)

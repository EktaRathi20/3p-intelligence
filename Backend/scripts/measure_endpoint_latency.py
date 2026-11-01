"""Measure dashboard endpoint latency the way the frontend loads it.

Fires the six dashboard requests concurrently (mirroring the frontend's
Promise.allSettled on region change) and reports each endpoint's
time-to-last-byte plus the total wall time. Run against a live backend:

    python Backend/scripts/measure_endpoint_latency.py [BASE_URL] [REGION]

Example:
    python Backend/scripts/measure_endpoint_latency.py http://localhost:8000 vizag

Stdlib only (urllib + threads) so it runs anywhere.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ENDPOINTS = [
    ("population", "/api/population?region={region}"),
    ("forecast", "/api/forecast?region={region}"),
    ("shelter", "/api/shelter?region={region}"),
    ("current-conditions", "/api/current-conditions?region={region}"),
    ("cyclone-intelligence", "/api/disaster-intelligence/{region}?hazard=cyclone"),
    ("capabilities", "/api/disaster-intelligence/{region}/capabilities"),
]

REQUEST_TIMEOUT = 300


def fetch(base_url, name, path):
    url = base_url + path
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            body = response.read()
        elapsed = time.monotonic() - started
        return name, response.status, elapsed, len(body), None
    except Exception as error:  # noqa: BLE001 - report, don't crash
        elapsed = time.monotonic() - started
        return name, None, elapsed, 0, f"{type(error).__name__}: {error}"


def main():
    base_url = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
    region = sys.argv[2] if len(sys.argv) > 2 else "vizag"
    region = urllib.parse.quote(region, safe="")

    print(f"GET {base_url} region={region} ({len(ENDPOINTS)} concurrent requests)")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(ENDPOINTS)) as pool:
        results = list(
            pool.map(
                lambda item: fetch(base_url, item[0], item[1].format(region=region)),
                ENDPOINTS,
            )
        )
    wall = time.monotonic() - started

    print(f"{'endpoint':<22}{'status':<8}{'seconds':<10}{'bytes':<10}error")
    for name, status, elapsed, size, error in sorted(results, key=lambda row: row[2]):
        print(f"{name:<22}{str(status):<8}{elapsed:<10.1f}{size:<10}{error or ''}")
    print(f"total wall time: {wall:.1f}s")
    print(json.dumps({"wall_seconds": round(wall, 1)}))


if __name__ == "__main__":
    main()

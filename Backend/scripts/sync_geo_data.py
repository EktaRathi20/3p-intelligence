"""Synchronize global geographic data into the local JSON database.

Dataset: dr5hn/countries-states-cities-database
(https://github.com/dr5hn/countries-states-cities-database, ODbL v1.0,
attribution required). Coverage at time of writing: 250 countries,
~5,300 states/provinces, ~153,000 cities.

What this script does (all writes are upserts, so reruns are safe and
unrelated fields on existing records are preserved):

1. Downloads ``countries.json`` and ``states.json`` from the versioned
   dataset and upserts countries into ``database/countries.json``
   (stable record id = ISO alpha-2 code) and states into
   ``database/states.json`` (stable record id = dataset provider id).
2. Downloads the versioned ``json-cities.json.gz`` release asset,
   streaming it object-by-object (the export is ~199MB uncompressed), and
   upserts each city into ``database/cities.json`` (stable record id =
   dataset provider id).
3. Records per-collection counts and the dataset ref in the ``geoSync``
   record of ``database/settings.json`` so the backend status endpoint
   stays a single cached read.

Writes are merged per collection and saved atomically, with progress
reporting. For the full import expect ~160k records over a few minutes
(mostly download time).

Examples:
    python Backend/scripts/sync_geo_data.py
    python Backend/scripts/sync_geo_data.py --collections countries,states
    python Backend/scripts/sync_geo_data.py --skip-cities   # countries+states only
    python Backend/scripts/sync_geo_data.py --dry-run --max-cities 1000
    python Backend/scripts/sync_geo_data.py --check         # verify, no downloads
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

# Allow running as ``python Backend/scripts/sync_geo_data.py`` from repo root
# as well as from inside ``Backend/``.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import json_store  # noqa: E402
from services.json_stream import iter_json_array  # noqa: E402

COUNTRIES_COLLECTION = "countries"
STATES_COLLECTION = "states"
CITIES_COLLECTION = "cities"
SETTINGS_COLLECTION = "settings"
GEO_SYNC_DOCUMENT = "geoSync"

RAW_BASE_URL = (
    "https://raw.githubusercontent.com"
    "/dr5hn/countries-states-cities-database"
)
RELEASE_BASE_URL = (
    "https://github.com/dr5hn/countries-states-cities-database"
    "/releases"
)

DEFAULT_DATASET_REF = "master"
DEFAULT_TIMEOUT = 300

ATTRIBUTION = (
    "Geographic data by Countries States Cities Database "
    "(https://github.com/dr5hn/countries-states-cities-database) | ODbL v1.0"
)


# --------------------------------------------------
# Document builders (pure: no database access)
# --------------------------------------------------

def _to_float(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _clean_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_country_doc(country: dict) -> tuple[str, dict] | None:
    """Build a (record_id, data) pair for a country, or None to skip."""
    code = _clean_str(country.get("iso2")).upper()
    name = _clean_str(country.get("name"))
    if len(code) != 2 or not code.isalpha() or not name:
        return None
    return code, {
        "code": code,
        "name": name,
        "nameLower": name.casefold(),
        "flag": country.get("emoji"),
        "region": country.get("region"),
        "subregion": country.get("subregion"),
        "iso3": country.get("iso3"),
        "capital": country.get("capital"),
        "currency": country.get("currency"),
        "phonecode": country.get("phonecode"),
        "updatedAt": json_store.utcnow_iso(),
    }


def build_state_doc(state: dict) -> tuple[str, dict] | None:
    """Build a (record_id, data) pair for a state/province, or None to skip."""
    provider_id = _to_int(state.get("id"))
    country_code = _clean_str(state.get("country_code")).upper()
    name = _clean_str(state.get("name"))
    if provider_id is None or len(country_code) != 2 or not name:
        return None
    state_code = _clean_str(state.get("iso2")).upper() or None
    return str(provider_id), {
        "providerId": provider_id,
        "countryCode": country_code,
        "code": state_code,
        "name": name,
        "nameLower": name.casefold(),
        "type": state.get("type"),
        "latitude": _to_float(state.get("latitude")),
        "longitude": _to_float(state.get("longitude")),
        "updatedAt": json_store.utcnow_iso(),
    }


def build_city_doc(city: dict) -> tuple[str, dict] | None:
    """Build a (record_id, data) pair for a city, or None to skip."""
    provider_id = _to_int(city.get("id"))
    country_code = _clean_str(city.get("country_code")).upper()
    name = _clean_str(city.get("name"))
    if provider_id is None or len(country_code) != 2 or not name:
        return None
    return str(provider_id), {
        "providerId": provider_id,
        "countryCode": country_code,
        "stateCode": _clean_str(city.get("state_code")).upper() or None,
        "stateName": _clean_str(city.get("state_name")) or None,
        "name": name,
        "nameLower": name.casefold(),
        "latitude": _to_float(city.get("latitude")),
        "longitude": _to_float(city.get("longitude")),
        "updatedAt": json_store.utcnow_iso(),
    }


# --------------------------------------------------
# Download helpers
# --------------------------------------------------

def download_file(url: str, dest: Path, timeout: int, retries: int = 3) -> Path:
    """Stream-download a URL to ``dest`` with retries and basic checks."""
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                # NOTE: content-length is only authoritative when the server
                # sends no content-encoding; requests transparently decodes
                # gzip/deflate, in which case iter_content yields MORE bytes
                # than the (compressed) content-length advertises.
                encoded = bool(response.headers.get("content-encoding"))
                total = int(response.headers.get("content-length") or 0)
                dest.parent.mkdir(parents=True, exist_ok=True)
                downloaded = 0
                with open(dest, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded += len(chunk)
                if not encoded and total and downloaded != total:
                    raise ValueError(
                        f"Incomplete download: got {downloaded} of {total} bytes."
                    )
                if downloaded == 0:
                    raise ValueError("Downloaded file is empty.")
                return dest
        except Exception as exc:  # noqa: BLE001 - retried, then reported
            last_error = exc
            print(f"  attempt {attempt}/{retries} failed for {url}: {exc}")
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Failed to download {url}: {last_error}")


# NOTE: top-level JSON arrays are parsed incrementally with
# services.json_stream.iter_json_array (the cities export is ~199MB
# uncompressed, too large for json.load on small machines).


# --------------------------------------------------
# Progress reporting
# --------------------------------------------------

ProgressFn = Callable[[int, int], None]


class SyncProgress:
    """Rate/ETA progress printer for one collection sync."""

    def __init__(self, label: str, total: int | None = None) -> None:
        self._label = label
        self._total = total
        self._start = time.monotonic()

    def __call__(self, written: int, _batch_size: int) -> None:
        elapsed = max(time.monotonic() - self._start, 0.001)
        rate = written / elapsed
        if self._total:
            pct = 100.0 * written / self._total
            print(
                f"  [{self._label}] {written:,}/{self._total:,} ({pct:.1f}%) "
                f"| {rate:,.0f} docs/s | elapsed {elapsed:,.0f}s",
                flush=True,
            )
        else:
            print(
                f"  [{self._label}] {written:,} docs "
                f"| {rate:,.0f} docs/s | elapsed {elapsed:,.0f}s",
                flush=True,
            )


# --------------------------------------------------
# JSON database sync: countries / states / cities
# --------------------------------------------------

# Progress is reported every N parsed records so large imports stay lively.
PROGRESS_EVERY = 5000


def _upsert_records(
    collection: str,
    records: dict[str, dict],
    dry_run: bool,
) -> int:
    """Merge records into a collection file; return the upserted count."""
    if dry_run:
        return len(records)
    existing = json_store.read_collection(collection)
    for record_id, data in records.items():
        if record_id in existing:
            merged = dict(existing[record_id])
            merged.update(data)
            existing[record_id] = merged
        else:
            existing[record_id] = data
    json_store.write_collection(collection, existing)
    return len(records)


def sync_countries(
    countries_path: Path,
    *,
    dry_run: bool = False,
    max_records: int | None = None,
) -> dict[str, int]:
    """Upsert countries into the JSON database. Returns written/skipped."""
    with open(countries_path, encoding="utf-8") as handle:
        countries = json.load(handle)
    if not isinstance(countries, list):
        raise ValueError("Expected countries.json to contain a JSON list.")

    progress = SyncProgress(
        "countries",
        total=len(countries) if max_records is None else max_records,
    )
    records: dict[str, dict] = {}
    skipped = 0
    for country in countries:
        if max_records is not None and len(records) >= max_records:
            break
        if not isinstance(country, dict):
            skipped += 1
            continue
        built = build_country_doc(country)
        if built is None:
            skipped += 1
            continue
        doc_id, data = built
        records[doc_id] = data
        if len(records) % PROGRESS_EVERY == 0:
            progress(len(records), PROGRESS_EVERY)
    progress(len(records), 0)
    written = _upsert_records(COUNTRIES_COLLECTION, records, dry_run)
    return {"written": written, "skipped": skipped}


def sync_states(
    states_path: Path,
    *,
    dry_run: bool = False,
    max_records: int | None = None,
) -> dict[str, int]:
    """Upsert states/provinces into the JSON database. Returns written/skipped."""
    with open(states_path, encoding="utf-8") as handle:
        states = json.load(handle)
    if not isinstance(states, list):
        raise ValueError("Expected states.json to contain a JSON list.")

    progress = SyncProgress(
        "states",
        total=len(states) if max_records is None else max_records,
    )
    records: dict[str, dict] = {}
    skipped = 0
    for state in states:
        if max_records is not None and len(records) >= max_records:
            break
        if not isinstance(state, dict):
            skipped += 1
            continue
        built = build_state_doc(state)
        if built is None:
            skipped += 1
            continue
        doc_id, data = built
        records[doc_id] = data
        if len(records) % PROGRESS_EVERY == 0:
            progress(len(records), PROGRESS_EVERY)
    progress(len(records), 0)
    written = _upsert_records(STATES_COLLECTION, records, dry_run)
    return {"written": written, "skipped": skipped}


def sync_cities(
    cities_path: Path,
    *,
    dry_run: bool = False,
    max_records: int | None = None,
) -> dict[str, int]:
    """Stream cities from ``json-cities.json.gz`` into the JSON database."""
    progress = SyncProgress("cities", total=max_records)
    records: dict[str, dict] = {}
    skipped = 0
    for city in iter_json_array(cities_path, gzipped=True):
        if max_records is not None and len(records) >= max_records:
            break
        if not isinstance(city, dict):
            skipped += 1
            continue
        built = build_city_doc(city)
        if built is None:
            skipped += 1
            continue
        doc_id, data = built
        records[doc_id] = data
        if len(records) % PROGRESS_EVERY == 0:
            progress(len(records), PROGRESS_EVERY)
    progress(len(records), 0)
    written = _upsert_records(CITIES_COLLECTION, records, dry_run)
    return {"written": written, "skipped": skipped}


def write_sync_meta(
    dataset_ref: str,
    counts: dict[str, int],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Merge per-collection counts into the ``geoSync`` settings record.

    Only collections present in ``counts`` are updated, so partial syncs
    (e.g. ``--countries-only``) never zero out other collections' counts.
    Returns the merged metadata dict.
    """
    try:
        existing = json_store.get_document(
            SETTINGS_COLLECTION, GEO_SYNC_DOCUMENT
        ) or {}
    except Exception:  # noqa: BLE001 - missing/corrupt file: start fresh
        existing = {}
    meta: dict[str, Any] = {
        "datasetRef": dataset_ref,
        "attribution": ATTRIBUTION,
        "syncedAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": json_store.utcnow_iso(),
    }
    for key in ("countries", "states", "cities"):
        if key in counts:
            meta[key] = counts[key]
        elif key in existing:
            meta[key] = existing[key]
    if not dry_run:
        json_store.set_document(
            SETTINGS_COLLECTION, GEO_SYNC_DOCUMENT, meta, merge=True
        )
    return meta


# --------------------------------------------------
# Check mode
# --------------------------------------------------

def check_status(verify_counts: bool = False) -> int:
    """Report sync status without downloading. Returns exit code."""
    ok = True
    try:
        meta = json_store.get_document(SETTINGS_COLLECTION, GEO_SYNC_DOCUMENT)
    except Exception as exc:  # noqa: BLE001 - reported, exit 1
        print(f"  sync metadata unreadable: {exc}")
        print(ATTRIBUTION)
        return 1

    if not meta:
        print("Sync metadata (settings/geoSync): MISSING")
        print("  Run the sync to import geographic data.")
        ok = False
    else:
        print("Sync metadata (settings/geoSync):")
        print(f"  datasetRef: {meta.get('datasetRef', 'unknown')}")
        print(f"  syncedAt: {meta.get('syncedAt', 'unknown')}")
        print(
            "  counts: countries={} states={} cities={}".format(
                meta.get("countries", "?"),
                meta.get("states", "?"),
                meta.get("cities", "?"),
            )
        )

    for collection_name in (
        COUNTRIES_COLLECTION,
        STATES_COLLECTION,
        CITIES_COLLECTION,
    ):
        try:
            count = json_store.count_documents(collection_name)
            if verify_counts:
                print(f"Database '{collection_name}': {count} records")
                if count == 0:
                    print("  WARNING: collection is empty; re-run the sync.")
                    ok = False
            elif count > 0:
                print(f"Database '{collection_name}': OK (non-empty)")
            else:
                print(f"Database '{collection_name}': EMPTY")
                print("  WARNING: collection is empty; re-run the sync.")
                ok = False
        except Exception as exc:  # noqa: BLE001 - reported, exit 1
            print(f"Database '{collection_name}' unreadable: {exc}")
            ok = False

    print(ATTRIBUTION)
    return 0 if ok else 1


# --------------------------------------------------
# CLI
# --------------------------------------------------

COLLECTION_CHOICES = ("countries", "states", "cities")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Synchronize global country/state/city data to the "
        "local JSON database (database/)."
    )
    parser.add_argument(
        "--dataset-ref",
        default=DEFAULT_DATASET_REF,
        help=(
            "Dataset git ref for countries/states JSON (default: %(default)s). "
            "Use a release tag for a pinned cities snapshot."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Download timeout in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--collections",
        default=",".join(COLLECTION_CHOICES),
        help=(
            "Comma-separated collections to sync "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--skip-cities",
        action="store_true",
        help="Sync countries and states only (faster; cities untouched).",
    )
    parser.add_argument(
        "--countries-only",
        action="store_true",
        help="Only upsert countries; skip states and cities.",
    )
    parser.add_argument(
        "--max-states",
        type=int,
        default=None,
        help="Cap state upserts (smoke testing only).",
    )
    parser.add_argument(
        "--max-cities",
        type=int,
        default=None,
        help="Cap city upserts (smoke testing only).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and count records without writing to the database.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report sync status without downloading anything.",
    )
    parser.add_argument(
        "--verify-counts",
        action="store_true",
        help="With --check, report live record counts per collection.",
    )
    return parser.parse_args(argv)


def resolve_collections(args) -> set[str]:
    """Resolve the requested collection set from CLI flags."""
    if args.countries_only:
        return {"countries"}
    requested = {
        part.strip().lower()
        for part in str(args.collections).split(",")
        if part.strip()
    }
    unknown = requested - set(COLLECTION_CHOICES)
    if unknown:
        raise ValueError(
            f"Unknown collection(s): {sorted(unknown)}. "
            f"Choose from: {', '.join(COLLECTION_CHOICES)}."
        )
    if not requested:
        raise ValueError("No collections selected.")
    if args.skip_cities:
        requested.discard("cities")
    if not requested:
        raise ValueError("No collections selected.")
    return requested


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.check:
        return check_status(verify_counts=args.verify_counts)

    try:
        collections = resolve_collections(args)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    dataset_ref = args.dataset_ref
    countries_url = f"{RAW_BASE_URL}/{dataset_ref}/json/countries.json"
    states_url = f"{RAW_BASE_URL}/{dataset_ref}/json/states.json"
    if dataset_ref in ("master", "main"):
        cities_url = f"{RELEASE_BASE_URL}/latest/download/json-cities.json.gz"
    else:
        cities_url = (
            f"{RELEASE_BASE_URL}/download/{dataset_ref}/json-cities.json.gz"
        )

    work_dir = Path(tempfile.mkdtemp(prefix="geo_sync_"))
    failures: list[str] = []
    counts: dict[str, int] = {}
    try:
        want_countries = "countries" in collections
        want_states = "states" in collections
        want_cities = "cities" in collections

        countries_path = work_dir / "countries.json"
        states_path = work_dir / "states.json"
        cities_path = work_dir / "json-cities.json.gz"

        if want_countries:
            print(f"Downloading countries: {countries_url}")
            try:
                download_file(countries_url, countries_path, args.timeout)
            except Exception as exc:
                failures.append(f"countries download: {exc}")
                want_countries = False

        if want_states:
            print(f"Downloading states: {states_url}")
            try:
                download_file(states_url, states_path, args.timeout)
            except Exception as exc:
                failures.append(f"states download: {exc}")
                want_states = False

        if want_cities:
            print(f"Downloading cities: {cities_url}")
            try:
                download_file(cities_url, cities_path, args.timeout)
            except Exception as exc:
                failures.append(f"cities download: {exc}")
                want_cities = False

        if want_countries:
            print("Upserting database countries...")
            try:
                result = sync_countries(
                    countries_path,
                    dry_run=args.dry_run,
                )
                counts["countries"] = result["written"]
                print(
                    f"  countries written: {result['written']}, "
                    f"skipped: {result['skipped']}"
                )
            except Exception as exc:
                failures.append(f"countries sync: {exc}")

        if want_states:
            print("Upserting database states...")
            try:
                result = sync_states(
                    states_path,
                    dry_run=args.dry_run,
                    max_records=args.max_states,
                )
                counts["states"] = result["written"]
                print(
                    f"  states written: {result['written']}, "
                    f"skipped: {result['skipped']}"
                )
            except Exception as exc:
                failures.append(f"states sync: {exc}")

        if want_cities:
            print("Upserting database cities...")
            try:
                result = sync_cities(
                    cities_path,
                    dry_run=args.dry_run,
                    max_records=args.max_cities,
                )
                counts["cities"] = result["written"]
                print(
                    f"  cities written: {result['written']}, "
                    f"skipped: {result['skipped']}"
                )
            except Exception as exc:
                failures.append(f"cities sync: {exc}")

        if counts and not args.dry_run:
            meta = write_sync_meta(dataset_ref, counts)
            print(
                "Sync metadata: countries={} states={} cities={}".format(
                    meta.get("countries", "?"),
                    meta.get("states", "?"),
                    meta.get("cities", "?"),
                )
            )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    print(ATTRIBUTION)
    if failures:
        print("COMPLETED WITH FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    if args.dry_run:
        print("Dry run completed successfully (no writes made).")
    else:
        print("Geo sync completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

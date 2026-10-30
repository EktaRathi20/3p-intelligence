"""Official disaster-alert evidence from GDACS (UN).

Source: the GDACS near-real-time RSS feed
(https://www.gdacs.org/xml/rss.xml, EC-JRC, CC BY 4.0), which carries
tropical-cyclone episodes with alert level, footprint bbox, maximum
winds, affected population, and per-episode timestamps. Each item links
to a CAP 1.2 alert carrying the verified affected-area polygon, which
is fetched for candidate events to support precise local assessment.

Two-tier model (kept separate everywhere downstream):

- Regional relevance: current + recent + country match + footprint bbox
  intersects the region box. A matching warning raises the REGION risk
  level via the severity floor.
- Local impact: the region anchor tested against verified CAP polygons.
  Inside/outside/uncertain is reported per location and gates precise
  map zones; it never lowers the regional floor.

IMD district warnings have no reliable machine-readable feed
(RSMC/IMD publish PHP pages and PDFs), so they remain a manual
cross-check until such a feed exists — never scraped or guessed here.
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
import xml.etree.ElementTree as ET

import requests

from ingestion_layer.cache import load_json_cache, save_json_cache
from ingestion_layer.constant import (
    REGION_DATA,
    WARNING_RECENCY_DAYS,
    get_region_coords,
)
from ingestion_layer.signals import assess_local_impact

GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"
PROVIDER_NAME = "GDACS (UN Global Disaster Alert and Coordination System)"
CACHE_FILENAME = "gdacs_tc_events.json"
CACHE_TTL = timedelta(minutes=30)
CAP_CACHE_TTL = timedelta(minutes=30)
REQUEST_TIMEOUT = 30

# GDACS event types relevant to cyclone-risk exposure.
RELEVANT_EVENT_TYPES = ("TC",)

# Guard against pathological CAP payloads; larger polygons are
# stride-sampled with an explicit "simplified" flag.
MAX_POLYGON_POINTS = 2000

GDACS_NAMESPACES = {
    "gdacs": "http://www.gdacs.org",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
}
CAP_NAMESPACE = "urn:oasis:names:tc:emergency:cap:1.2"

_cache_lock = threading.Lock()
_cache_loaded_at = 0.0
_cache_events: list[dict[str, Any]] | None = None


def _text(item: ET.Element, path: str) -> str:
    return (item.findtext(path, default="", namespaces=GDACS_NAMESPACES) or "").strip()


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed
    except (TypeError, ValueError):
        return None


def _parse_rss_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_bbox(value: str) -> dict[str, float] | None:
    """Parse a GDACS bbox (lonmin lonmax latmin latmax) or return None."""
    try:
        lonmin, lonmax, latmin, latmax = (float(part) for part in value.split())
    except (TypeError, ValueError):
        return None
    if lonmin > lonmax or latmin > latmax:
        return None
    return {"lonmin": lonmin, "lonmax": lonmax, "latmin": latmin, "latmax": latmax}


def _bbox_intersects(region_box: dict[str, Any], event_box: dict[str, float]) -> bool:
    try:
        min_lon = float(region_box["min_lon"])
        max_lon = float(region_box["max_lon"])
        min_lat = float(region_box["min_lat"])
        max_lat = float(region_box["max_lat"])
    except (KeyError, TypeError, ValueError):
        return False
    return not (
        event_box["lonmax"] < min_lon
        or event_box["lonmin"] > max_lon
        or event_box["latmax"] < min_lat
        or event_box["latmin"] > max_lat
    )


def parse_tc_events(rss_bytes: bytes) -> list[dict[str, Any]]:
    """Parse GDACS RSS bytes into normalized tropical-cyclone events.

    Pure function (no I/O): raises ValueError on malformed XML.
    """
    try:
        root = ET.fromstring(rss_bytes)
    except ET.ParseError as error:
        raise ValueError(f"GDACS RSS is not valid XML: {error}") from error

    events: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        event_type = _text(item, "gdacs:eventtype").upper()
        if event_type not in RELEVANT_EVENT_TYPES:
            continue
        point = item.find("geo:Point", namespaces=GDACS_NAMESPACES)
        latitude = _number(point.findtext("geo:lat", namespaces=GDACS_NAMESPACES)) if point is not None else None
        longitude = _number(point.findtext("geo:long", namespaces=GDACS_NAMESPACES)) if point is not None else None
        severity_el = item.find("gdacs:severity", namespaces=GDACS_NAMESPACES)
        population_el = item.find("gdacs:population", namespaces=GDACS_NAMESPACES)
        events.append({
            "event_id": _text(item, "gdacs:eventid") or None,
            "episode_id": _text(item, "gdacs:episodeid") or None,
            "event_name": _text(item, "gdacs:eventname") or None,
            "event_type": event_type,
            "title": _text(item, "title") or None,
            "description": _text(item, "description") or None,
            "alert_level": _text(item, "gdacs:alertlevel").upper() or None,
            "episode_alert_level": _text(item, "gdacs:episodealertlevel").upper() or None,
            "severity_text": (severity_el.text or "").strip() if severity_el is not None else None,
            "max_wind_kmh": _number(severity_el.get("value")) if severity_el is not None else None,
            "population_affected": None
            if population_el is None
            else _coerce_population(population_el.get("value")),
            "vulnerability": _text(item, "gdacs:vulnerability") or None,
            "iso3": _text(item, "gdacs:iso3").upper() or None,
            "country": _text(item, "gdacs:country") or None,
            "latitude": latitude,
            "longitude": longitude,
            "bbox": _parse_bbox(_text(item, "gdacs:bbox")),
            "fromdate": _iso_or_none(_parse_rss_date(_text(item, "gdacs:fromdate"))),
            "todate": _iso_or_none(_parse_rss_date(_text(item, "gdacs:todate"))),
            "datemodified": _iso_or_none(_parse_rss_date(_text(item, "gdacs:datemodified"))),
            "is_current": _text(item, "gdacs:iscurrent").lower() == "true",
            "link": _text(item, "link") or None,
            "cap_url": _text(item, "gdacs:cap") or None,
            "glide": _text(item, "gdacs:glide") or None,
        })
    return events


def _coerce_population(value: Any) -> int | None:
    try:
        parsed = int(float(value))
        return parsed if parsed >= 0 else None
    except (TypeError, ValueError):
        return None


def _iso_or_none(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def parse_cap_footprint(cap_bytes: bytes, source_url: str) -> dict[str, Any]:
    """Parse a CAP 1.2 alert into affected-area geometry.

    Pure function (no I/O): raises ValueError on malformed XML. Returns
    {"polygons", "circles", "cap_severity", "cap_urgency",
    "cap_certainty", "cap_headline", "cap_sent", "simplified",
    "source_url"}. Polygons are lists of [lat, lon] pairs in CAP order.
    """
    try:
        root = ET.fromstring(cap_bytes)
    except ET.ParseError as error:
        raise ValueError(f"CAP alert is not valid XML: {error}") from error

    ns = {"cap": CAP_NAMESPACE}
    if root.tag != f"{{{CAP_NAMESPACE}}}alert":
        raise ValueError("CAP payload is not a cap:alert document.")

    infos = root.findall("cap:info", ns)
    first = infos[0] if infos else None

    def _info_text(name: str) -> str | None:
        if first is None:
            return None
        value = first.findtext(f"cap:{name}", namespaces=ns)
        return (value or "").strip() or None

    polygons: list[list[list[float]]] = []
    circles: list[dict[str, Any]] = []
    simplified = False
    for info in infos:
        for area in info.findall("cap:area", ns):
            for polygon_el in area.findall("cap:polygon", ns):
                points = _parse_cap_polygon(polygon_el.text or "")
                if len(points) >= 3:
                    if len(points) > MAX_POLYGON_POINTS:
                        stride = (len(points) + MAX_POLYGON_POINTS - 1) // MAX_POLYGON_POINTS
                        points = points[::stride]
                        simplified = True
                    polygons.append(points)
            for circle_el in area.findall("cap:circle", ns):
                circle = _parse_cap_circle(circle_el.text or "")
                if circle is not None:
                    circles.append(circle)

    return {
        "polygons": polygons,
        "circles": circles,
        "cap_severity": _info_text("severity"),
        "cap_urgency": _info_text("urgency"),
        "cap_certainty": _info_text("certainty"),
        "cap_headline": _info_text("headline"),
        "cap_sent": _info_text("sent"),
        "simplified": simplified,
        "source_url": source_url,
    }


def _parse_cap_polygon(text: str) -> list[list[float]]:
    """Parse CAP "lat,lon lat,lon ..." pairs (drops malformed pairs)."""
    points: list[list[float]] = []
    for pair in text.split():
        parts = pair.split(",")
        if len(parts) != 2:
            continue
        try:
            latitude = float(parts[0])
            longitude = float(parts[1])
        except ValueError:
            continue
        points.append([latitude, longitude])
    return points


def _parse_cap_circle(text: str) -> dict[str, Any] | None:
    """Parse a CAP circle ("lat,lon radius_km") or return None.

    Per CAP 1.2, the center pair is comma-separated and the radius in
    kilometres follows after a space.
    """
    parts = text.split()
    if len(parts) != 2:
        return None
    coords = parts[0].split(",")
    if len(coords) != 2:
        return None
    try:
        latitude = float(coords[0])
        longitude = float(coords[1])
        radius_km = float(parts[1])
    except ValueError:
        return None
    if radius_km <= 0:
        return None
    return {"center": [latitude, longitude], "radius_km": radius_km}


def _download_events() -> list[dict[str, Any]]:
    try:
        response = requests.get(GDACS_RSS_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(f"Could not retrieve GDACS alerts: {error}") from error
    return parse_tc_events(response.content)


def _get_cached_events() -> list[dict[str, Any]]:
    global _cache_loaded_at, _cache_events
    if _cache_events is not None and time.monotonic() - _cache_loaded_at < CACHE_TTL.total_seconds():
        return _cache_events
    with _cache_lock:
        if _cache_events is None or time.monotonic() - _cache_loaded_at >= CACHE_TTL.total_seconds():
            cached = load_json_cache(
                CACHE_FILENAME,
                CACHE_TTL,
                payload_key="events",
                # Schema version: events cached before cap_url existed
                # must be refetched instead of served stale.
                validator=lambda payload: isinstance(payload, list)
                and all(
                    isinstance(event, dict) and "cap_url" in event
                    for event in payload
                ),
            )
            if cached is not None:
                _cache_events = cached
            else:
                _cache_events = _download_events()
                save_json_cache(CACHE_FILENAME, _cache_events, payload_key="events")
            _cache_loaded_at = time.monotonic()
    assert _cache_events is not None
    return _cache_events


def _cap_cache_filename(event: dict[str, Any]) -> str:
    stable_id = event.get("event_id") or event.get("cap_url") or "unknown"
    digest = hashlib.sha256(str(stable_id).encode("utf-8")).hexdigest()[:16]
    return f"gdacs_cap_{digest}.json"


def fetch_footprint_for_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch and parse the CAP footprint for one event (None on failure).

    Cached per event id. Any failure (network, malformed CAP, missing
    URL) yields None so callers report uncertainty, never fake geometry.
    """
    cap_url = (event.get("cap_url") or "").strip()
    if not cap_url:
        return None
    cache_filename = _cap_cache_filename(event)
    cached = load_json_cache(
        cache_filename,
        CAP_CACHE_TTL,
        payload_key="footprint",
        validator=lambda payload: isinstance(payload, dict)
        and isinstance(payload.get("polygons"), list),
    )
    if cached is not None:
        return cached
    try:
        response = requests.get(cap_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        footprint = parse_cap_footprint(response.content, cap_url)
    except Exception as error:  # noqa: BLE001 - uncertainty, not fatal
        print(f"[WARNINGS] CAP footprint unavailable for {event.get('event_name')}: {error}")
        return None
    save_json_cache(cache_filename, footprint, payload_key="footprint")
    return footprint


def _event_is_fresh(event: dict[str, Any], now: datetime) -> bool:
    """A warning counts only when current and recently active."""
    if not event.get("is_current"):
        return False
    todate = event.get("todate")
    if not todate:
        return False
    try:
        end = datetime.fromisoformat(todate)
    except ValueError:
        return False
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return end >= now - timedelta(days=WARNING_RECENCY_DAYS)


def _event_matches_country(event: dict[str, Any], country_hint: str) -> bool:
    hint = (country_hint or "").upper()
    if (event.get("iso3") or "").upper() == hint:
        return True
    return hint.capitalize() in (event.get("country") or "")


def fetch_warnings_for_region(region_key: str = "vizag",
                              country_hint: str = "IND") -> dict[str, Any]:
    """Return applicable official TC warnings for a region.

    An event applies at REGION level when it is a current, recent
    tropical cyclone whose country matches and whose footprint bbox
    intersects the region box. Each warning carries its verified CAP
    footprint (when retrievable), and ``local_impact`` judges the
    region anchor against that precise geometry. Geographically
    relevant but stale or non-current events are preserved in
    ``inactive_warnings`` with an ``exclusion_reason`` ("expired" or
    "not_current") instead of being silently dropped.
    """
    coords = get_region_coords(region_key)
    region_box = REGION_DATA.get(region_key, {})
    now = datetime.now(timezone.utc)
    try:
        events = _get_cached_events()
    except Exception as error:  # noqa: BLE001 - honest unavailable state
        return {
            "timestamp": now.isoformat(),
            "region_target": region_key,
            "source": PROVIDER_NAME,
            "source_url": GDACS_RSS_URL,
            "warnings": [],
            "inactive_warnings": [],
            "local_impact": assess_local_impact(None, None, []),
            "source_error": str(error),
        }

    warnings: list[dict[str, Any]] = []
    inactive_warnings: list[dict[str, Any]] = []
    for event in events:
        if not _event_matches_country(event, country_hint):
            continue
        bbox = event.get("bbox")
        if not bbox or not _bbox_intersects(region_box, bbox):
            continue
        if not _event_is_fresh(event, now):
            # Geographically relevant but no longer valid: preserved with
            # its original severity so callers can report "expired"
            # instead of silently dropping it. No CAP fetch — stale
            # geometry must not drive local assessment.
            exclusion = (
                "not_current" if not event.get("is_current") else "expired"
            )
            inactive_warnings.append({
                **event,
                "matched_region": region_key,
                "exclusion_reason": exclusion,
            })
            continue
        warning = {**event, "matched_region": region_key}
        warning["footprint"] = fetch_footprint_for_event(event)
        warnings.append(warning)

    warnings.sort(
        key=lambda warning: warning.get("datemodified") or "",
        reverse=True,
    )
    inactive_warnings.sort(
        key=lambda warning: warning.get("datemodified") or "",
        reverse=True,
    )
    footprints = [
        warning["footprint"]
        for warning in warnings
        if isinstance(warning.get("footprint"), dict)
    ]
    local_impact = assess_local_impact(
        coords.get("lat"), coords.get("lon"), footprints
    )
    if not warnings:
        local_impact = assess_local_impact(None, None, [])
    return {
        "timestamp": now.isoformat(),
        "region_target": region_key,
        "source": PROVIDER_NAME,
        "source_url": GDACS_RSS_URL,
        "warnings": warnings,
        "inactive_warnings": inactive_warnings,
        "local_impact": local_impact,
    }

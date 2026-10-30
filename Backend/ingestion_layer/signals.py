"""Pure hazard-screening and model-feature helpers (no I/O).

These functions hold the deterministic screening math so it can be unit
tested without network access or credentials. Conventions:

- Wind bands follow the IMD North Indian Ocean intensity scale.
- Wave bands follow the WMO Douglas sea-state scale.
- Missing data contributes no points and no factors (never zero-filled).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ingestion_layer.constant import (
    IMD_CYCLONIC_STORM_KMH,
    IMD_SEVERE_CYCLONIC_STORM_KMH,
    IMD_VERY_SEVERE_CYCLONIC_STORM_KMH,
    PRESSURE_LOW_HPA,
    PRESSURE_VERY_LOW_HPA,
    RISK_SCORE_MAX,
    RISK_SCORE_ORANGE,
    RISK_SCORE_RED,
    RISK_SCORE_YELLOW,
    WMO_WAVE_HIGH_M,
    WMO_WAVE_ROUGH_M,
    WMO_WAVE_VERY_ROUGH_M,
)

# H2O model feature contract. The training script
# (Backend/scripts/train_risk_model.py) and inference MUST use exactly
# these snapshot fields so training and serving distributions match.
# Wave height is deliberately excluded: IBTrACS has no wave observations,
# so a model trained with it could not be served honestly.
MODEL_FEATURES = (
    "latitude",
    "longitude",
    "month",
    "wind_speed_kmh",
    "pressure_hpa",
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def classify_wind_kmh(wind: Any) -> tuple[int, str | None]:
    """Score an observed sustained wind (IMD scale bands)."""
    if not _is_number(wind):
        return 0, None
    if wind >= IMD_VERY_SEVERE_CYCLONIC_STORM_KMH:
        return 45, f"Very high wind observation: {wind:.1f} km/h"
    if wind >= IMD_SEVERE_CYCLONIC_STORM_KMH:
        return 35, f"High wind observation: {wind:.1f} km/h"
    if wind >= IMD_CYCLONIC_STORM_KMH:
        return 20, f"Strong wind observation: {wind:.1f} km/h"
    return 0, None


def classify_pressure_hpa(pressure: Any) -> tuple[int, str | None]:
    """Score an observed mean sea-level pressure (screening bands)."""
    if not _is_number(pressure):
        return 0, None
    if pressure <= PRESSURE_VERY_LOW_HPA:
        return 30, f"Very low atmospheric pressure: {pressure:.1f} hPa"
    if pressure <= PRESSURE_LOW_HPA:
        return 20, f"Low atmospheric pressure: {pressure:.1f} hPa"
    return 0, None


def classify_wave_height_m(wave_height: Any) -> tuple[int, str | None]:
    """Score an observed significant wave height (WMO sea-state bands)."""
    if not _is_number(wave_height):
        return 0, None
    if wave_height >= WMO_WAVE_HIGH_M:
        return 30, f"High sea state observed: {wave_height:.1f} m waves"
    if wave_height >= WMO_WAVE_VERY_ROUGH_M:
        return 20, f"Very rough sea state observed: {wave_height:.1f} m waves"
    if wave_height >= WMO_WAVE_ROUGH_M:
        return 10, f"Rough sea state observed: {wave_height:.1f} m waves"
    return 0, None


def score_to_level(score: int) -> str:
    """Map a screening score to a risk level."""
    if score >= RISK_SCORE_RED:
        return "RED"
    if score >= RISK_SCORE_ORANGE:
        return "ORANGE"
    if score >= RISK_SCORE_YELLOW:
        return "YELLOW"
    return "GREEN"


def screen_risk(
    wind: Any = None,
    pressure: Any = None,
    wave_height_m: Any = None,
) -> tuple[int, list[str]]:
    """Deterministic screening score + evidence factors (capped at 100)."""
    score = 0
    factors: list[str] = []
    for points, factor in (
        classify_wind_kmh(wind),
        classify_pressure_hpa(pressure),
        classify_wave_height_m(wave_height_m),
    ):
        score += points
        if factor:
            factors.append(factor)
    return min(score, RISK_SCORE_MAX), factors


def summarize_active_systems(
    systems: Any, *, limit: int = 3
) -> list[str]:
    """Build evidence lines for recently-observed tropical systems."""
    if not isinstance(systems, list):
        return []
    lines: list[str] = []
    for system in systems[: max(0, limit)]:
        if not isinstance(system, dict):
            continue
        name = system.get("matched_cyclone") or system.get("storm_id") or "Unnamed system"
        wind = system.get("latest_wind_kmh")
        distance = system.get("closest_approach_km")
        observed = str(system.get("latest_observed_at") or "")[:10]
        parts = [f"Recently observed tropical system {name}"]
        if _is_number(wind):
            parts.append(f"latest winds {wind:.0f} km/h")
        if _is_number(distance):
            parts.append(f"closest approach {distance:.0f} km")
        if observed:
            parts.append(f"observed {observed}")
        parts.append("(IBTrACS provisional)")
        lines.append(": ".join([parts[0], ", ".join(parts[1:])]))
    return lines


def build_model_features(
    *,
    latitude: Any,
    longitude: Any,
    month: Any = None,
    observed_at: datetime | None = None,
    wind_speed_kmh: Any = None,
    pressure_hpa: Any = None,
) -> dict[str, float] | None:
    """Build the H2O feature row, or None when any feature is missing.

    ``month`` defaults to the current UTC month unless ``observed_at`` or
    an explicit month is given. Non-numeric or missing values return None:
    the model layer must report "unavailable", never zero-fill.
    """
    if month is None:
        moment = observed_at or datetime.now(timezone.utc)
        month = moment.month
    features = {
        "latitude": latitude,
        "longitude": longitude,
        "month": month,
        "wind_speed_kmh": wind_speed_kmh,
        "pressure_hpa": pressure_hpa,
    }
    if not all(_is_number(value) for value in features.values()):
        return None
    if not 1 <= int(features["month"]) <= 12:
        return None
    return {key: float(value) for key, value in features.items()}


_LEVEL_RANK = {"GREEN": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}


def warning_floor_level(warnings: Any) -> str | None:
    """Highest official-warning floor across warnings (None when no floor).

    Each warning contributes the stronger of its overall and episode
    alert levels; levels outside the floor map (e.g. GREEN) add nothing.
    """
    from ingestion_layer.constant import WARNING_LEVEL_FLOOR

    if not isinstance(warnings, list):
        return None
    best: str | None = None
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        for key in ("alert_level", "episode_alert_level"):
            level = str(warning.get(key) or "").upper()
            floor = WARNING_LEVEL_FLOOR.get(level)
            if floor is None:
                continue
            if best is None or _LEVEL_RANK[floor] > _LEVEL_RANK[best]:
                best = floor
    return best


def combine_levels(screening_level: Any, warning_floor: Any) -> tuple[str, str]:
    """Combine deterministic screening with the official-warning floor.

    Returns (level, basis) where basis is "screening",
    "official_warning", or "both". The floor can only raise the level,
    never lower it; an UNKNOWN screening defers to a verified warning.
    """
    screening = str(screening_level or "").upper()
    if screening not in _LEVEL_RANK and screening != "UNKNOWN":
        screening = "UNKNOWN"
    floor = str(warning_floor or "").upper()
    if floor not in _LEVEL_RANK:
        floor = ""

    if not floor:
        return screening, "screening"
    if screening == "UNKNOWN":
        return floor, "official_warning"
    if _LEVEL_RANK[floor] > _LEVEL_RANK[screening]:
        return floor, "official_warning"
    if _LEVEL_RANK[screening] > _LEVEL_RANK[floor]:
        return screening, "screening"
    if screening == "GREEN":
        return "GREEN", "screening"
    return screening, "both"


def summarize_warning_lines(warnings: Any, *, limit: int = 3) -> list[str]:
    """Build evidence lines for applicable official warnings."""
    if not isinstance(warnings, list):
        return []
    lines: list[str] = []
    for warning in warnings[: max(0, limit)]:
        if not isinstance(warning, dict):
            continue
        level = str(warning.get("alert_level") or "").capitalize() or "Unrated"
        name = warning.get("event_name") or "Unnamed system"
        parts = [f"Official {level} warning: {name}"]
        details: list[str] = []
        wind = warning.get("max_wind_kmh")
        if _is_number(wind):
            details.append(f"max winds {wind:.0f} km/h")
        population = warning.get("population_affected")
        if isinstance(population, int) and population > 0:
            if population >= 1_000_000:
                details.append(f"{population / 1_000_000:.1f}M people in impact zone")
            elif population >= 1_000:
                details.append(f"{population / 1_000:.0f}k people in impact zone")
            else:
                details.append(f"{population} people in impact zone")
        modified = str(warning.get("datemodified") or "")[:10]
        if modified:
            details.append(f"updated {modified}")
        details.append("GDACS/UN")
        lines.append(": ".join([parts[0], ", ".join(details)]))
    return lines


def haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance between two points in kilometres."""
    import math

    radius_km = 6371.0
    lat_delta = math.radians(lat_b - lat_a)
    lon_delta = math.radians(lon_b - lon_a)
    haversine = (
        math.sin(lat_delta / 2) ** 2
        + math.cos(math.radians(lat_a))
        * math.cos(math.radians(lat_b))
        * math.sin(lon_delta / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(haversine))


def point_in_polygon(latitude: Any, longitude: Any, polygon: Any) -> bool:
    """Ray-casting point-in-polygon test (lon=x, lat=y plane).

    ``polygon`` is a list of [lat, lon] pairs. Returns False for any
    malformed input rather than raising.
    """
    if not _is_number(latitude) or not _is_number(longitude):
        return False
    if not isinstance(polygon, list) or len(polygon) < 3:
        return False
    points: list[tuple[float, float]] = []
    for pair in polygon:
        if (
            not isinstance(pair, (list, tuple))
            or len(pair) != 2
            or not _is_number(pair[0])
            or not _is_number(pair[1])
        ):
            return False
        points.append((float(pair[0]), float(pair[1])))
    lat = float(latitude)
    lon = float(longitude)
    inside = False
    count = len(points)
    for index in range(count):
        lat_a, lon_a = points[index]
        lat_b, lon_b = points[(index + 1) % count]
        if (lon_a > lon) != (lon_b > lon):
            intersect_lat = lat_a + (lat_b - lat_a) * (lon - lon_a) / (lon_b - lon_a)
            if lat < intersect_lat:
                inside = not inside
    return inside


def polygon_bbox(polygon: Any) -> dict[str, float] | None:
    """Bounding box of a polygon as lon/lat mins and maxes (None if bad)."""
    if not isinstance(polygon, list) or not polygon:
        return None
    lats: list[float] = []
    lons: list[float] = []
    for pair in polygon:
        if (
            not isinstance(pair, (list, tuple))
            or len(pair) != 2
            or not _is_number(pair[0])
            or not _is_number(pair[1])
        ):
            return None
        lats.append(float(pair[0]))
        lons.append(float(pair[1]))
    return {
        "lonmin": min(lons),
        "lonmax": max(lons),
        "latmin": min(lats),
        "latmax": max(lats),
    }


def approx_distance_to_polygon_km(
    latitude: Any, longitude: Any, polygon: Any
) -> float | None:
    """Approximate distance from a point to a polygon's vertices.

    This is a vertex-distance approximation (not true edge distance);
    callers must label it as approximate. None for malformed input.
    """
    if not _is_number(latitude) or not _is_number(longitude):
        return None
    if not isinstance(polygon, list) or not polygon:
        return None
    import math

    best: float | None = None
    for pair in polygon:
        if (
            not isinstance(pair, (list, tuple))
            or len(pair) != 2
            or not _is_number(pair[0])
            or not _is_number(pair[1])
            or not math.isfinite(float(pair[0]))
            or not math.isfinite(float(pair[1]))
        ):
            return None
        distance = haversine_km(
            float(latitude), float(longitude), float(pair[0]), float(pair[1])
        )
        if best is None or distance < best:
            best = distance
    return best


def assess_local_impact(
    latitude: Any,
    longitude: Any,
    footprints: Any,
) -> dict[str, Any]:
    """Assess a location against verified warning footprints.

    Returns {"verdict", "basis", "distance_to_footprint_km",
    "geometry_source"} where verdict is "inside_footprint",
    "outside_footprint", or "uncertain". Uncertain covers missing
    geometry, malformed geometry, and malformed coordinates — never
    silently GREEN. Only footprints with at least one VALID circle or
    polygon count as evaluated geometry.
    """
    no_geometry = {
        "verdict": "uncertain",
        "basis": ["No verified footprint geometry available for precise local assessment."],
        "distance_to_footprint_km": None,
        "geometry_source": None,
    }
    if not _is_number(latitude) or not _is_number(longitude):
        return no_geometry
    import math

    if not math.isfinite(float(latitude)) or not math.isfinite(float(longitude)):
        return no_geometry
    if not isinstance(footprints, list) or not footprints:
        return no_geometry

    any_geometry = False
    best_distance: float | None = None
    for footprint in footprints:
        if not isinstance(footprint, dict):
            continue
        polygons = footprint.get("polygons")
        circles = footprint.get("circles")
        has_polygons = isinstance(polygons, list) and len(polygons) > 0
        has_circles = isinstance(circles, list) and len(circles) > 0
        if not has_polygons and not has_circles:
            continue
        for circle in circles if has_circles else []:
            if not isinstance(circle, dict):
                continue
            center = circle.get("center")
            radius = circle.get("radius_km")
            if (
                not isinstance(center, (list, tuple))
                or len(center) != 2
                or not _is_number(center[0])
                or not _is_number(center[1])
                or not _is_number(radius)
                or not math.isfinite(float(center[0]))
                or not math.isfinite(float(center[1]))
                or not math.isfinite(float(radius))
            ):
                continue
            any_geometry = True
            center_distance = haversine_km(
                float(latitude), float(longitude),
                float(center[0]), float(center[1]),
            )
            if center_distance <= float(radius):
                return {
                    "verdict": "inside_footprint",
                    "basis": [
                        "Location lies inside a verified warning footprint circle."
                    ],
                    "distance_to_footprint_km": 0.0,
                    "geometry_source": footprint.get("source_url"),
                }
            outside = center_distance - float(radius)
            if best_distance is None or outside < best_distance:
                best_distance = outside
        for polygon in polygons if has_polygons else []:
            # approx distance is None only for malformed polygons here
            # (the anchor coordinates were validated above), while
            # point_in_polygon is False for both malformed and outside
            # inputs — so malformed polygons must be skipped first.
            distance = approx_distance_to_polygon_km(latitude, longitude, polygon)
            if distance is None:
                continue
            any_geometry = True
            if point_in_polygon(latitude, longitude, polygon):
                return {
                    "verdict": "inside_footprint",
                    "basis": [
                        "Location lies inside a verified warning footprint polygon."
                    ],
                    "distance_to_footprint_km": 0.0,
                    "geometry_source": footprint.get("source_url"),
                }
            if best_distance is None or distance < best_distance:
                best_distance = distance

    if not any_geometry:
        return no_geometry
    return {
        "verdict": "outside_footprint",
        "basis": [
            "Location lies outside all verified warning footprint polygons; "
            "the regional warning still applies at region level."
        ],
        "distance_to_footprint_km": (
            round(best_distance, 1) if best_distance is not None else None
        ),
        "geometry_source": "GDACS CAP polygon",
    }


def classify_local_cyclone_impact(
    *,
    warnings=None,
    inactive_warnings=None,
    warnings_source=None,
    warnings_timestamp=None,
    warnings_error=None,
    verdict=None,
    distance_km=None,
    geometry_source=None,
    screening_level=None,
    screening_score=None,
    telemetry_status=None,
) -> dict[str, Any]:
    """Classify LOCAL cyclone impact separately from the regional warning.

    Pure function (no I/O). The official regional warning severity is
    preserved untouched in ``regional_warning_level``; the local zone is
    derived only from documented evidence and never invents distance
    thresholds (distance is reported, never classified on).

    Evidence rules for ``local_impact_zone``:

    1. No active warning and no source error: the zone follows local
       screening (GREEN when calm, elevated when observed); UNKNOWN
       without telemetry. An inside verdict with no valid warning
       behind it is conflicting (stale) geometry and yields UNKNOWN
       unless screening itself is elevated.
    2. Warning source failed: elevated screening still stands on its own
       observations, otherwise UNKNOWN (an unfetched warning cannot be
       ruled out, so calm screening alone must not claim GREEN).
    3. Active warning: the zone is the stronger of footprint evidence
       (inside a verified footprint takes the warning severity) and
       screening evidence (elevated screening always counts; GREEN
       screening counts only when the location is verified outside).
       Anything else is UNKNOWN.

    In particular, an outside-footprint location is never assigned RED
    merely because the regional event is RED, and an uncertain location
    with calm screening is UNKNOWN rather than GREEN. Bounding-box
    overlap alone is never treated as footprint intersection (callers
    must pass a verdict computed against verified geometry).

    Returns the local-assessment contract: ``regional_warning_level``,
    ``regional_warning_status`` ("active", "expired", "unavailable", or
    "none"), ``local_impact_status``, ``local_impact_zone``,
    ``distance_to_footprint_km``, ``reason``, ``source``, ``updated_at``.
    """
    active = list(warnings) if isinstance(warnings, list) else []
    active = [warning for warning in active if isinstance(warning, dict)]
    inactive = (
        list(inactive_warnings) if isinstance(inactive_warnings, list) else []
    )
    floor = warning_floor_level(active)
    screening = str(screening_level or "").upper()
    if screening not in _LEVEL_RANK:
        screening = "UNKNOWN" if screening == "UNKNOWN" else ""
    telemetry_ok = telemetry_status == "AVAILABLE"
    status = str(verdict or "")
    if status not in ("inside_footprint", "outside_footprint", "uncertain"):
        status = "uncertain"

    if warnings_error and not active:
        regional_status = "unavailable"
    elif active:
        regional_status = "active"
    elif inactive:
        regional_status = "expired"
    else:
        regional_status = "none"

    first_name = active[0].get("event_name") if active else None
    warning_name = str(first_name) if first_name else "the active warning"
    distance_text = (
        f"approx. {float(distance_km):.0f} km"
        if isinstance(distance_km, (int, float))
        and not isinstance(distance_km, bool)
        else None
    )
    score_text = (
        f"{int(screening_score)}/100"
        if isinstance(screening_score, (int, float))
        and not isinstance(screening_score, bool)
        else "unavailable"
    )
    regional_caveat = (
        f" Regional {floor} warning {warning_name} still applies at "
        "region level."
        if floor
        else " No regional warning floor is active."
    )

    zone: str
    reason: str
    if not active:
        if warnings_error:
            if telemetry_ok and screening in ("RED", "ORANGE", "YELLOW"):
                zone = screening
                reason = (
                    f"Local observations show {screening}-level screening "
                    f"signals (score {score_text}); the warning source is "
                    "unavailable so regional status cannot be confirmed."
                )
            else:
                zone = "UNKNOWN"
                reason = (
                    "The warning source is unavailable, so an active "
                    "warning cannot be ruled out; direct impact cannot "
                    "be confirmed."
                )
        elif status == "inside_footprint":
            # Conflicting evidence: an inside verdict with no valid
            # warning behind it (stale geometry). Direct observations
            # still count on their own.
            if telemetry_ok and screening in ("RED", "ORANGE", "YELLOW"):
                zone = screening
                reason = (
                    f"Local observations show {screening}-level screening "
                    f"signals (score {score_text}); no valid warning "
                    "backs the inside-footprint verdict."
                )
            else:
                zone = "UNKNOWN"
                reason = (
                    "Footprint verdict conflicts with warning validity "
                    "(inside, but no active warning); direct impact "
                    "cannot be confirmed."
                )
        elif telemetry_ok:
            zone = screening if screening else "UNKNOWN"
            if zone == "UNKNOWN":
                reason = (
                    "No active warning and no usable screening level; "
                    "direct impact cannot be confirmed."
                )
            else:
                reason = (
                    f"No active warning; local observations show "
                    f"{zone} screening (score {score_text})."
                )
        else:
            zone = "UNKNOWN"
            if inactive:
                reason = (
                    "Only expired warnings apply to this region and no "
                    "current local observations exist; direct impact "
                    "cannot be confirmed."
                )
            else:
                reason = (
                    "No active warning and no current local observations; "
                    "direct impact cannot be confirmed."
                )
    else:
        footprint_zone = (floor or "GREEN") if status == "inside_footprint" else None
        screening_zone = None
        if telemetry_ok and screening in ("RED", "ORANGE", "YELLOW"):
            screening_zone = screening
        elif telemetry_ok and screening == "GREEN" and status == "outside_footprint":
            screening_zone = "GREEN"
        candidates = [
            candidate
            for candidate in (footprint_zone, screening_zone)
            if candidate is not None
        ]
        if not candidates:
            zone = "UNKNOWN"
            if status == "outside_footprint":
                reason = (
                    "Outside the verified footprint, but local telemetry "
                    "is unavailable, so direct impact cannot be confirmed "
                    "or ruled out." + regional_caveat
                )
            else:
                reason = (
                    "Cannot determine footprint intersection (no verified "
                    "geometry); direct impact cannot be confirmed or ruled "
                    "out." + regional_caveat
                )
        else:
            zone = max(candidates, key=lambda level: _LEVEL_RANK[level])
            if footprint_zone is not None and _LEVEL_RANK[zone] <= _LEVEL_RANK[footprint_zone]:
                zone = footprint_zone
                origin = geometry_source or "warning"
                reason = (
                    f"Inside the verified {origin} footprint of active "
                    f"{footprint_zone} warning {warning_name}."
                )
            elif screening_zone == "GREEN":
                distance_clause = (
                    f" (nearest verified vertex {distance_text} away)"
                    if distance_text
                    else ""
                )
                reason = (
                    "Outside all verified footprints"
                    f"{distance_clause} with calm local observations "
                    f"(screening {score_text} GREEN)." + regional_caveat
                )
            else:
                reason = (
                    f"Local observations show {screening}-level screening "
                    f"signals (score {score_text})." + regional_caveat
                )

    return {
        "regional_warning_level": floor,
        "regional_warning_status": regional_status,
        "local_impact_status": status,
        "local_impact_zone": zone,
        "distance_to_footprint_km": distance_km,
        "reason": reason,
        "source": warnings_source,
        "updated_at": warnings_timestamp,
    }

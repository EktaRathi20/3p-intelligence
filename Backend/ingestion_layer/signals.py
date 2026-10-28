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
    best: float | None = None
    for pair in polygon:
        if (
            not isinstance(pair, (list, tuple))
            or len(pair) != 2
            or not _is_number(pair[0])
            or not _is_number(pair[1])
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
    "outside_footprint", or "uncertain". Uncertain covers both missing
    geometry and malformed coordinates — never silently GREEN.
    """
    no_geometry = {
        "verdict": "uncertain",
        "basis": ["No verified footprint geometry available for precise local assessment."],
        "distance_to_footprint_km": None,
        "geometry_source": None,
    }
    if not _is_number(latitude) or not _is_number(longitude):
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
        any_geometry = True
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
            ):
                continue
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
            if point_in_polygon(latitude, longitude, polygon):
                return {
                    "verdict": "inside_footprint",
                    "basis": [
                        "Location lies inside a verified warning footprint polygon."
                    ],
                    "distance_to_footprint_km": 0.0,
                    "geometry_source": footprint.get("source_url"),
                }
            distance = approx_distance_to_polygon_km(latitude, longitude, polygon)
            if distance is not None and (
                best_distance is None or distance < best_distance
            ):
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

"""Pure geographic/region-code helpers (no database or network access).

These helpers are intentionally dependency-free so they can be unit tested
standalone. Route modules import them for validation and
default generation; the frontend mirrors the default code/name behaviour.
"""

from __future__ import annotations

import re
import unicodedata

# Region codes: 2-24 chars, uppercase letters/digits with interior - or _.
# Stored normalized (uppercased, trimmed). Uniqueness is enforced
# by the region routes using the normalized value.
REGION_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9\-_]{0,22}[A-Z0-9]$")
REGION_CODE_MIN_LENGTH = 2
REGION_CODE_MAX_LENGTH = 24

# ISO 3166-1 alpha-2 country codes.
COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")


def normalize_country_code(value: object) -> str | None:
    """Normalize a country code to uppercase ISO alpha-2, or None if blank."""
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def normalize_state_code(value: object) -> str | None:
    """Normalize a subdivision code (uppercased, trimmed), or None if blank."""
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def normalize_city_id(value: object) -> str | None:
    """Normalize a city id to its stripped string form, or None if blank."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    normalized = str(value).strip()
    return normalized or None


def normalize_region_code(value: object) -> str | None:
    """Normalize a region code (uppercased, trimmed), or None if blank."""
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def is_valid_region_code(value: object) -> bool:
    """Check the documented region-code format (after normalization)."""
    normalized = normalize_region_code(value)
    if normalized is None:
        return False
    if not (
        REGION_CODE_MIN_LENGTH <= len(normalized) <= REGION_CODE_MAX_LENGTH
    ):
        return False
    return REGION_CODE_PATTERN.match(normalized) is not None


def region_code_error(value: object) -> str | None:
    """Return a user-facing error message, or None when the code is valid."""
    normalized = normalize_region_code(value)
    if normalized is None:
        return "Region code is required."
    if not (
        REGION_CODE_MIN_LENGTH <= len(normalized) <= REGION_CODE_MAX_LENGTH
    ):
        return (
            "Region code must be between "
            f"{REGION_CODE_MIN_LENGTH} and {REGION_CODE_MAX_LENGTH} characters."
        )
    if REGION_CODE_PATTERN.match(normalized) is None:
        return (
            "Region code may only contain letters, digits, hyphens and "
            "underscores, and must start and end with a letter or digit."
        )
    return None


def _ascii_fold(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text)
    return folded.encode("ascii", "ignore").decode("ascii")


def slug_token(name: str, length: int = 3) -> str:
    """Build an uppercase alpha token from a place name (e.g. Jodhpur->JOD)."""
    cleaned = re.sub(r"[^A-Za-z]", "", _ascii_fold(name or "")).upper()
    if not cleaned:
        return "X" * length
    if len(cleaned) <= length:
        return cleaned
    # Prefer consonant skeleton for readability (Jodhpur -> JDH).
    consonants = "".join(ch for ch in cleaned if ch not in "AEIOU")
    if len(consonants) >= length:
        return consonants[:length]
    return cleaned[:length]


def build_default_region_code(
    country_code: str,
    state_code: str | None = None,
    city_name: str | None = None,
) -> str:
    """Generate a default region code such as ``IN-RJ-JOD``.

    The suggestion is deterministic but not guaranteed unique; the backend
    enforces uniqueness and returns HTTP 409 on conflict.
    """
    parts = [normalize_country_code(country_code) or "XX"]
    normalized_state = normalize_state_code(state_code)
    if normalized_state:
        parts.append(normalized_state)
    if city_name and city_name.strip():
        parts.append(slug_token(city_name))
    return "-".join(parts)


def suggest_region_name(city_name: str | None, fallback: str = "") -> str:
    """Default the region name to the selected city name."""
    if city_name and city_name.strip():
        return city_name.strip()
    return fallback

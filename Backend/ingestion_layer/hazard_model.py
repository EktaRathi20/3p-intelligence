"""H2O AutoML scoring for cyclone severity probability.

The model is trained offline by ``Backend/scripts/train_risk_model.py`` on
real IBTrACS North Indian basin fixes and loaded here from the file named
by ``H2O_MODEL_PATH``. Key honesty rules:

- Features must ALL be present and numeric (see
  ``ingestion_layer.signals.MODEL_FEATURES``); anything missing means the
  probability is reported unavailable — values are never zero-filled.
- A missing ``h2o`` install, missing model file, or prediction failure
  also yields "unavailable", never a fabricated number.
- ``h2o`` is imported lazily so the backend (and unit tests) run without
  it or a Java runtime until scoring is actually requested.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from ingestion_layer.signals import MODEL_FEATURES

# Label contract shared with the training script: probability that the
# same storm reaches IMD very-severe strength (>= 118 km/h sustained
# winds) within the next 24 hours of fixes.
SEVERE_WIND_KMH = 118.0
POSITIVE_WINDOW_HOURS = 24
LABEL_DESCRIPTION = (
    "P(same-storm max wind >= 118 km/h within next 24h of fixes), "
    "trained on IBTrACS North Indian basin tracks"
)

_lock = threading.Lock()
_model: Any = None
_model_path: str | None = None


def get_model_path() -> str | None:
    """Return the configured model path, or None when unset/blank."""
    configured = (os.getenv("H2O_MODEL_PATH") or "").strip()
    return configured or None


def get_model_status() -> dict[str, Any]:
    """Report whether H2O scoring is available and why (never raises)."""
    try:
        import h2o  # noqa: F401
    except Exception as error:  # noqa: BLE001 - reported as status
        return {
            "available": False,
            "reason": f"h2o package unavailable: {error}",
        }
    path = get_model_path()
    if not path:
        return {
            "available": False,
            "reason": "H2O_MODEL_PATH is not configured.",
        }
    if not os.path.exists(path):
        return {
            "available": False,
            "reason": f"H2O model path not found: {path}",
        }
    return {"available": True, "model_path": path}


def _load_model_unlocked(path: str) -> Any:
    """Import h2o, start the cluster, and load the model (caller locks)."""
    import h2o

    h2o.init()
    return h2o.load_model(path)


def _validate_features(features: dict[str, Any]) -> dict[str, float] | None:
    cleaned: dict[str, float] = {}
    for name in MODEL_FEATURES:
        value = features.get(name)
        if isinstance(value, bool):
            return None
        try:
            cleaned[name] = float(value)
        except (TypeError, ValueError):
            return None
    return cleaned


def score(features: dict[str, Any]) -> dict[str, Any] | None:
    """Score severe-weather probability, or None when unavailable.

    Returns ``{"probability", "model_id", "features_used", "label"}``.
    """
    cleaned = _validate_features(features or {})
    if cleaned is None:
        print("[H2O] Scoring skipped: incomplete model features.")
        return None

    path = get_model_path()
    if not path or not os.path.exists(path):
        print("[H2O] Scoring skipped: no trained model path configured.")
        return None

    global _model, _model_path
    try:
        import h2o

        with _lock:
            if _model is None or _model_path != path:
                _model = _load_model_unlocked(path)
                _model_path = path
            frame = h2o.H2OFrame(
                {name: [value] for name, value in cleaned.items()}
            )
            result = _model.predict(frame)
            # Pandas-free extraction: raw rows + column names.
            columns = list(result.columns)
            data_rows = result.as_data_frame(use_pandas=False) or []
            if data_rows and list(data_rows[0]) == columns:
                data_rows = data_rows[1:]  # tolerate a header row
            if not data_rows:
                raise ValueError("prediction returned no rows")
            row = dict(zip(columns, data_rows[0]))
    except Exception as error:  # noqa: BLE001 - unavailable, not fatal
        print(f"[H2O] Scoring failed: {error}")
        return None

    try:
        probability = float(row["p1"])
    except (KeyError, TypeError, ValueError):
        print("[H2O] Scoring failed: prediction had no p1 probability.")
        return None
    if not 0.0 <= probability <= 1.0:
        print("[H2O] Scoring failed: probability outside [0, 1].")
        return None

    model_id = None
    try:
        model_id = getattr(_model, "model_id", None) or getattr(
            _model, "_id", None
        )
    except Exception:  # noqa: BLE001 - id is best-effort only
        model_id = None

    return {
        "probability": probability,
        "model_id": str(model_id) if model_id else None,
        "features_used": cleaned,
        "label": LABEL_DESCRIPTION,
    }


def reset_for_tests() -> None:
    """Drop the cached model (unit tests only)."""
    global _model, _model_path
    with _lock:
        _model = None
        _model_path = None

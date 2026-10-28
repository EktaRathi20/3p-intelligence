"""Train the cyclone severity model with H2O AutoML (free, open source).

Dataset: real NOAA IBTrACS North Indian basin fixes (same source as the
ingestion layer). Each row is one 6-hourly storm fix; the label is 1 when
the SAME storm reaches IMD very-severe strength (>= 118 km/h sustained
winds) within the following 24 hours of fixes. Features are exactly
``ingestion_layer.signals.MODEL_FEATURES`` so training and serving match.

Rows missing any required field are dropped and counted (never imputed),
so every training row is a fully-observed real fix.

Requirements: ``pip install h2o`` plus a Java runtime for the H2O
cluster. Training needs network access for the IBTrACS download.

Examples:
    python Backend/scripts/train_risk_model.py --dry-run
    python Backend/scripts/train_risk_model.py --max-runtime 600
    python Backend/scripts/train_risk_model.py --check
"""

from __future__ import annotations

import argparse
import codecs
import csv
import json
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ingestion_layer.disaster_history import IBTRACS_CSV_URL  # noqa: E402
from ingestion_layer.hazard_model import (  # noqa: E402
    LABEL_DESCRIPTION,
    POSITIVE_WINDOW_HOURS,
    SEVERE_WIND_KMH,
)
from ingestion_layer.signals import MODEL_FEATURES  # noqa: E402

DEFAULT_MODELS_DIR = BACKEND_DIR / "models"
DEFAULT_DATASET_NAME = "ibtracs_training.csv"
DEFAULT_MAX_RUNTIME = 600
DEFAULT_MAX_MODELS = 20
DEFAULT_NFOLDS = 5
FIRST_SEASON_YEARS_BACK = 30


def _number(value):
    try:
        parsed = float(value)
        return parsed if parsed >= 0 else None
    except (TypeError, ValueError):
        return None


def _parse_time(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip()[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def download_dataset(url: str, dest: Path, timeout: int = 300) -> Path:
    """Stream-download the IBTrACS CSV with basic completeness checks."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with open(dest, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                if not chunk:
                    continue
                handle.write(chunk)
                downloaded += len(chunk)
    if downloaded == 0:
        raise ValueError("Downloaded dataset is empty.")
    return dest


def build_rows(csv_path: Path) -> tuple[list[dict], dict[str, int]]:
    """Parse per-fix training rows with 24h look-ahead labels.

    Returns (rows, stats). A row is kept only when latitude, longitude,
    month, wind, and pressure are all observed; fixes with fewer than
    one subsequent fix inside the label window are still kept (their
    label reflects only observed follow-ups, documented in the card).
    """
    now = datetime.now(timezone.utc)
    first_season = now.year - FIRST_SEASON_YEARS_BACK
    storms: dict[str, list[dict]] = defaultdict(list)
    stats = {"raw_rows": 0, "storms": 0, "kept": 0, "dropped": 0, "positive": 0}

    with open(csv_path, encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        next(reader, None)  # units row
        for row in reader:
            stats["raw_rows"] += 1
            try:
                season = int(row.get("SEASON", ""))
                latitude = float(row.get("LAT", ""))
                longitude = float(row.get("LON", ""))
            except (TypeError, ValueError):
                stats["dropped"] += 1
                continue
            if season < first_season:
                continue
            observed_at = _parse_time(row.get("ISO_TIME", ""))
            if observed_at is None:
                stats["dropped"] += 1
                continue
            wind_knots = _number(row.get("WMO_WIND"))
            if wind_knots is None:
                wind_knots = _number(row.get("USA_WIND"))
            pressure = _number(row.get("WMO_PRES"))
            if pressure is None:
                pressure = _number(row.get("USA_PRES"))
            if wind_knots is None or pressure is None:
                stats["dropped"] += 1
                continue
            storm_id = row.get("SID") or f"{season}:{row.get('NAME') or 'UNNAMED'}"
            storms[storm_id].append({
                "latitude": latitude,
                "longitude": longitude,
                "month": observed_at.month,
                "wind_speed_kmh": wind_knots * 1.852,
                "pressure_hpa": pressure,
                "observed_at": observed_at,
            })

    window = timedelta(hours=POSITIVE_WINDOW_HOURS)
    rows: list[dict] = []
    for fixes in storms.values():
        fixes.sort(key=lambda fix: fix["observed_at"])
        for index, fix in enumerate(fixes):
            horizon = fix["observed_at"] + window
            peak = fix["wind_speed_kmh"]
            for later in fixes[index + 1:]:
                if later["observed_at"] > horizon:
                    break
                peak = max(peak, later["wind_speed_kmh"])
            label = 1 if peak >= SEVERE_WIND_KMH else 0
            stats["positive"] += label
            stats["kept"] += 1
            rows.append({
                "latitude": round(fix["latitude"], 4),
                "longitude": round(fix["longitude"], 4),
                "month": fix["month"],
                "wind_speed_kmh": round(fix["wind_speed_kmh"], 2),
                "pressure_hpa": round(fix["pressure_hpa"], 2),
                "severe_next24h": label,
            })
    stats["storms"] = len(storms)
    return rows, stats


def write_dataset(rows: list[dict], dest: Path) -> Path:
    """Write the auditable training CSV."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[*MODEL_FEATURES, "severe_next24h"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return dest


def run_automl(dataset_path: Path, models_dir: Path, *, max_runtime: int,
               max_models: int, nfolds: int, seed: int) -> dict:
    """Run H2O AutoML and save the leader plus a model card."""
    try:
        import h2o
        from h2o.automl import H2OAutoML
    except Exception as error:  # noqa: BLE001 - actionable message
        raise RuntimeError(
            "H2O is required for training: pip install h2o (plus a Java "
            f"runtime). Import failed: {error}"
        ) from error

    h2o.init()
    try:
        frame = h2o.import_file(str(dataset_path))
        frame["severe_next24h"] = frame["severe_next24h"].asfactor()
        aml = H2OAutoML(
            max_runtime_secs=max_runtime,
            max_models=max_models,
            nfolds=nfolds,
            balance_classes=True,
            seed=seed,
            sort_metric="AUC",
        )
        aml.train(x=list(MODEL_FEATURES), y="severe_next24h", training_frame=frame)
        leader = aml.leader
        models_dir.mkdir(parents=True, exist_ok=True)
        model_path = h2o.save_model(leader, path=str(models_dir), force=True)

        # Pandas-free leaderboard extraction: raw rows + column names.
        board_columns = list(aml.leaderboard.columns)
        board_rows = aml.leaderboard.as_data_frame(use_pandas=False) or []
        if board_rows and list(board_rows[0]) == board_columns:
            board_rows = board_rows[1:]  # tolerate a header row
        board = [dict(zip(board_columns, row)) for row in board_rows]
        metrics: dict[str, object] = {}
        try:
            perf = leader.model_performance(xval=nfolds > 0)
            metrics = {
                "auc": perf.auc(),
                "logloss": perf.logloss(),
                "mean_per_class_error": perf.mean_per_class_error(),
            }
        except Exception as error:  # noqa: BLE001 - metrics best effort
            metrics = {"error": str(error)}

        card = {
            "model_id": leader.model_id,
            "algorithm": leader.algo,
            "model_path": model_path,
            "label": LABEL_DESCRIPTION,
            "features": list(MODEL_FEATURES),
            "metrics": metrics,
            "leaderboard_top5": board[:5],
            "dataset_url": IBTRACS_CSV_URL,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "h2o_version": h2o.__version__,
            "automl_settings": {
                "max_runtime_secs": max_runtime,
                "max_models": max_models,
                "nfolds": nfolds,
                "balance_classes": True,
                "seed": seed,
            },
        }
        card_path = Path(model_path).parent / "model_card.json"
        card_path.write_text(json.dumps(card, indent=2), encoding="utf-8")
        return {"model_path": model_path, "card_path": str(card_path), "card": card}
    finally:
        try:
            h2o.cluster().shutdown(prompt=False)
        except Exception:  # noqa: BLE001 - shutdown best effort
            pass


def check_status(models_dir: Path) -> int:
    """Report training artifacts without training. Returns exit code."""
    card_path = models_dir / "model_card.json"
    if card_path.exists():
        card = json.loads(card_path.read_text(encoding="utf-8"))
        print(f"Model card: {card_path}")
        print(f"  model_id: {card.get('model_id', 'unknown')}")
        print(f"  trained_at: {card.get('trained_at', 'unknown')}")
        print(f"  metrics: {card.get('metrics', {})}")
        model_path = card.get("model_path")
        if model_path and Path(model_path).exists():
            size_mb = Path(model_path).stat().st_size / (1 << 20)
            print(f"  model file: OK ({size_mb:.1f} MB)")
            print("Set H2O_MODEL_PATH to the model file to enable scoring.")
            return 0
        print("  WARNING: model file from the card is missing; retrain.")
        return 1
    print(f"No model card at {card_path}; train with this script first.")
    return 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Train the H2O AutoML cyclone severity model on IBTrACS."
    )
    parser.add_argument("--dataset-url", default=IBTRACS_CSV_URL)
    parser.add_argument("--models-dir", default=str(DEFAULT_MODELS_DIR))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-runtime", type=int, default=DEFAULT_MAX_RUNTIME)
    parser.add_argument("--max-models", type=int, default=DEFAULT_MAX_MODELS)
    parser.add_argument("--nfolds", type=int, default=DEFAULT_NFOLDS)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build the dataset and report stats without training.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Report training artifacts without downloading/training.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    models_dir = Path(args.models_dir)

    if args.check:
        return check_status(models_dir)

    work_dir = Path(tempfile.mkdtemp(prefix="risk_train_"))
    try:
        csv_path = work_dir / "ibtracs.csv"
        print(f"Downloading IBTrACS: {args.dataset_url}")
        download_dataset(args.dataset_url, csv_path, args.timeout)

        print("Building labeled rows (this parses the full basin history)...")
        rows, stats = build_rows(csv_path)
        print(
            "Rows: kept={kept} dropped={dropped} storms={storms} "
            "positive_rate={rate:.3f}".format(
                rate=(stats["positive"] / stats["kept"]) if stats["kept"] else 0.0,
                **stats,
            )
        )
        if not rows:
            print("ERROR: no usable training rows; aborting.")
            return 1

        dataset_path = models_dir / DEFAULT_DATASET_NAME
        write_dataset(rows, dataset_path)
        print(f"Training dataset: {dataset_path} ({len(rows):,} rows)")

        if args.dry_run:
            print("Dry run completed (no training performed).")
            return 0

        result = run_automl(
            dataset_path,
            models_dir,
            max_runtime=args.max_runtime,
            max_models=args.max_models,
            nfolds=args.nfolds,
            seed=args.seed,
        )
        print(f"Leader model: {result['model_path']}")
        print(f"Model card: {result['card_path']}")
        print("Set H2O_MODEL_PATH to the model file to enable scoring.")
        return 0
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

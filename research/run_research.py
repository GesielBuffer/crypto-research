"""Run a registered, reproducible historical research experiment by ID."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research.backtest import CostModel, FixedHorizonConfig
from research.config import BASE_DIR, DATA_DIR, RESULTS_DIR
from research.metrics import summarize_returns
from research.regression import replay_frozen_trades


REGISTRY_PATH = BASE_DIR / "experiments" / "registry.toml"
COMPARISON_FIELDS = (
    "samples", "mean_return", "median_return", "win_rate", "profit_factor"
)


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    return document.get("experiments", {})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_commit() -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={BASE_DIR.as_posix()}", "rev-parse", "HEAD"],
        cwd=BASE_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def expected_summary(path: Path, cost: float) -> dict[str, float | int]:
    table = pd.read_csv(path)
    row = table.loc[table["cost"].sub(cost).abs().idxmin()]
    return {field: row[field].item() for field in COMPARISON_FIELDS}


def used_cache_files(frozen: pd.DataFrame, spec: dict) -> list[Path]:
    signal_column = spec["signal_time_column"]
    times = pd.to_datetime(frozen[signal_column], utc=True)
    keys = pd.DataFrame({
        "symbol": frozen["symbol"],
        "period": times.dt.strftime("%Y-%m"),
    }).drop_duplicates()
    paths = []
    for row in keys.itertuples(index=False):
        start = pd.Timestamp(f"{row.period}-01", tz="UTC")
        end = start + pd.offsets.MonthBegin(1)
        paths.append(DATA_DIR / (
            f"{row.symbol}_{spec['interval']}_{start:%Y-%m-%d}_{end:%Y-%m-%d}.csv"
        ))
    return sorted(paths)


def run_experiment(experiment_id: str, *, write_report: bool = True) -> dict:
    registry = load_registry()
    if experiment_id not in registry:
        choices = ", ".join(sorted(registry))
        raise ValueError(f"unknown experiment '{experiment_id}'; choose: {choices}")
    spec = registry[experiment_id]
    trades_path = BASE_DIR / spec["trades_file"]
    summary_path = BASE_DIR / spec["summary_file"]
    frozen = pd.read_csv(trades_path)
    config = FixedHorizonConfig(
        side=spec["side"],
        entry_delay_bars=spec["entry_delay_bars"],
        hold_bars=spec["hold_bars"],
        overlap=spec["overlap"],
        costs=CostModel(fees=spec["cost"]),
    )
    replayed = replay_frozen_trades(
        frozen,
        DATA_DIR,
        config,
        interval=spec["interval"],
        signal_time_column=spec["signal_time_column"],
    )
    actual = summarize_returns(replayed["net_return"])
    expected = expected_summary(summary_path, spec["cost"])
    mismatches = {
        field: {"actual": actual[field], "expected": expected[field]}
        for field in COMPARISON_FIELDS
        if not math.isclose(
            actual[field], expected[field], rel_tol=1e-12, abs_tol=1e-12
        )
    }
    cache_files = used_cache_files(frozen, spec)
    missing = [str(path) for path in cache_files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing cache files: {missing}")

    report = {
        "experiment_id": experiment_id,
        "description": spec["description"],
        "strategy_version": spec["strategy_version"],
        "split": spec["split"],
        "expected_decision": spec["expected_decision"],
        "status": "PASS_REGRESSION" if not mismatches else "FAIL_REGRESSION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_commit(),
        "parameters": {
            key: spec[key] for key in (
                "interval", "side", "entry_delay_bars", "hold_bars", "overlap", "cost"
            )
        },
        "metrics": {field: actual[field] for field in COMPARISON_FIELDS},
        "mismatches": mismatches,
        "inputs": {
            "trades": {"path": spec["trades_file"], "sha256": sha256(trades_path)},
            "summary": {"path": spec["summary_file"], "sha256": sha256(summary_path)},
            "candles": [
                {"path": path.relative_to(BASE_DIR).as_posix(), "sha256": sha256(path)}
                for path in cache_files
            ],
        },
    }
    if write_report:
        output = RESULTS_DIR / "runs" / f"{experiment_id}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if mismatches:
        raise AssertionError(f"regression mismatch: {mismatches}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment_id", nargs="?")
    parser.add_argument("--list", action="store_true", help="list registered experiments")
    args = parser.parse_args()
    registry = load_registry()
    if args.list:
        for experiment_id in sorted(registry):
            print(experiment_id)
        return 0
    if not args.experiment_id:
        parser.error("experiment_id is required unless --list is used")
    report = run_experiment(args.experiment_id)
    print(json.dumps({
        "experiment_id": report["experiment_id"],
        "status": report["status"],
        "expected_decision": report["expected_decision"],
        "metrics": report["metrics"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

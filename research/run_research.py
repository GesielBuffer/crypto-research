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
import numpy as np

from research.backtest import CostModel, FixedHorizonConfig
from research.backtest import simulate_fixed_horizon
from research.binance_data import load_csv
from research.config import BASE_DIR, DATA_DIR, RESULTS_DIR
from research.data_manifest import verify_manifest
from research.experiments.cost_sensitivity import (
    cache_files as cost_sensitivity_cache_files,
    reproduce as reproduce_cost_sensitivity,
)
from research.metrics import summarize_returns
from research.signals import build_c2_signals


REGISTRY_PATH = BASE_DIR / "experiments" / "registry.toml"
COMPARISON_FIELDS = (
    "samples", "mean_return", "median_return", "win_rate", "profit_factor"
)
COMMON_SPEC_FIELDS = {
    "kind",
    "description",
    "strategy_version",
    "split",
    "data_manifest",
    "interval",
    "expected_decision",
    "data_start",
    "data_end",
    "evaluation_start",
    "evaluation_end",
}
C2_SPEC_FIELDS = {
    "trades_file", "summary_file", "signal_time_column", "side",
    "entry_delay_bars", "hold_bars", "overlap", "cost",
}
COST_SENSITIVITY_SPEC_FIELDS = {
    "detailed_file", "summary_file", "symbols", "entry_delay_bars",
    "hold_bars", "overlap", "costs",
}


def validate_experiment_spec(experiment_id: str, spec: dict) -> None:
    """Reject incomplete or unsafe experiment definitions before execution."""

    if not isinstance(spec, dict):
        raise ValueError(f"experiment '{experiment_id}' must be a TOML table")
    kind = spec.get("kind")
    kind_fields = {
        "c2_replay": C2_SPEC_FIELDS,
        "trend_short_cost_sensitivity": COST_SENSITIVITY_SPEC_FIELDS,
    }.get(kind)
    if kind_fields is None:
        raise ValueError(f"experiment '{experiment_id}' has unsupported kind: {kind}")
    missing = (COMMON_SPEC_FIELDS | kind_fields).difference(spec)
    if missing:
        raise ValueError(
            f"experiment '{experiment_id}' missing fields: {sorted(missing)}"
        )

    path_fields = ["summary_file", "data_manifest"]
    path_fields.append("trades_file" if kind == "c2_replay" else "detailed_file")
    for field in path_fields:
        path = Path(spec[field])
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(
                f"experiment '{experiment_id}' field '{field}' must stay inside the repository"
            )
    if kind == "c2_replay" and spec["side"] not in {"long", "short"}:
        raise ValueError(f"experiment '{experiment_id}' has invalid side")
    if spec["overlap"] not in {"allow", "single_position"}:
        raise ValueError(f"experiment '{experiment_id}' has invalid overlap policy")
    if not isinstance(spec["entry_delay_bars"], int) or spec["entry_delay_bars"] < 1:
        raise ValueError(f"experiment '{experiment_id}' must enter at t+1 or later")
    if not isinstance(spec["hold_bars"], int) or spec["hold_bars"] < spec["entry_delay_bars"]:
        raise ValueError(f"experiment '{experiment_id}' has invalid hold_bars")
    costs = [spec["cost"]] if kind == "c2_replay" else spec["costs"]
    if (
        not isinstance(costs, list)
        or not costs
        or any(not isinstance(cost, (int, float)) or cost < 0 for cost in costs)
    ):
        raise ValueError(f"experiment '{experiment_id}' has invalid costs")
    if kind == "trend_short_cost_sensitivity" and (
        not isinstance(spec["symbols"], list) or not spec["symbols"]
    ):
        raise ValueError(f"experiment '{experiment_id}' must define symbols")

    dates = {
        field: pd.Timestamp(spec[field], tz="UTC")
        for field in ("data_start", "data_end", "evaluation_start", "evaluation_end")
    }
    if dates["data_start"] >= dates["data_end"]:
        raise ValueError(f"experiment '{experiment_id}' has an empty data period")
    if dates["evaluation_start"] >= dates["evaluation_end"]:
        raise ValueError(f"experiment '{experiment_id}' has an empty evaluation period")
    if (
        dates["evaluation_start"] < dates["data_start"]
        or dates["evaluation_end"] > dates["data_end"]
    ):
        raise ValueError(
            f"experiment '{experiment_id}' evaluation period must be inside the data period"
        )


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    experiments = document.get("experiments", {})
    if not isinstance(experiments, dict) or not experiments:
        raise ValueError("registry must contain at least one experiment")
    for experiment_id, spec in experiments.items():
        validate_experiment_spec(experiment_id, spec)
    return experiments


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


def used_cache_files(symbols: list[str], spec: dict) -> list[Path]:
    starts = pd.date_range(spec["data_start"], spec["data_end"], freq="MS", inclusive="left")
    return [
        DATA_DIR / (
            f"{symbol}_{spec['interval']}_{start:%Y-%m-%d}_"
            f"{start + pd.offsets.MonthBegin(1):%Y-%m-%d}.csv"
        )
        for symbol in sorted(symbols)
        for start in starts
    ]


def generate_trades(frozen: pd.DataFrame, spec: dict, config: FixedHorizonConfig) -> pd.DataFrame:
    frames = []
    cache_files = used_cache_files(frozen["symbol"].unique().tolist(), spec)
    for symbol in sorted(frozen["symbol"].unique()):
        symbol_paths = [path for path in cache_files if path.name.startswith(f"{symbol}_")]
        bars = pd.concat([load_csv(path) for path in symbol_paths], ignore_index=True)
        bars = bars.drop_duplicates("open_time").sort_values("open_time", ignore_index=True)
        features = build_c2_signals(bars)
        trades = simulate_fixed_horizon(bars, features["signal"], config)
        trades.insert(0, "symbol", symbol)
        frames.append(trades)
    generated = pd.concat(frames, ignore_index=True)
    evaluation_start = pd.Timestamp(spec["evaluation_start"], tz="UTC")
    evaluation_end = pd.Timestamp(spec["evaluation_end"], tz="UTC")
    return generated[
        (generated["entry_time"] >= evaluation_start)
        & (generated["exit_time"] < evaluation_end)
    ].sort_values(["signal_time", "symbol"], ignore_index=True)


def compare_frozen_frame(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
    *,
    sort_by: list[str],
) -> dict:
    """Compare a regenerated result table with a committed small artifact."""

    if set(actual.columns) != set(expected.columns):
        return {
            "columns": {
                "actual": actual.columns.tolist(),
                "expected": expected.columns.tolist(),
            }
        }
    actual = actual[expected.columns].sort_values(sort_by, ignore_index=True)
    expected = expected.sort_values(sort_by, ignore_index=True)
    if len(actual) != len(expected):
        return {"rows": {"actual": len(actual), "expected": len(expected)}}

    mismatches = {}
    for column in expected.columns:
        if pd.api.types.is_numeric_dtype(expected[column]):
            matches = np.allclose(
                actual[column].to_numpy(dtype=float),
                expected[column].to_numpy(dtype=float),
                rtol=1e-12,
                atol=1e-12,
                equal_nan=True,
            )
        else:
            matches = actual[column].astype(str).equals(expected[column].astype(str))
        if not matches:
            mismatches[column] = "values differ"
    return mismatches


def run_cost_sensitivity_experiment(
    experiment_id: str,
    spec: dict,
    *,
    write_report: bool,
) -> dict:
    detailed_path = BASE_DIR / spec["detailed_file"]
    summary_path = BASE_DIR / spec["summary_file"]
    manifest_path = BASE_DIR / spec["data_manifest"]
    paths = cost_sensitivity_cache_files(spec)
    verified = verify_manifest(manifest_path, paths)
    detailed, summary, _ = reproduce_cost_sensitivity(spec)
    expected_detailed = pd.read_csv(detailed_path)
    expected_summary = pd.read_csv(summary_path)
    mismatches = {
        "detailed": compare_frozen_frame(
            detailed, expected_detailed, sort_by=["symbol", "period", "cost"]
        ),
        "summary": compare_frozen_frame(
            summary, expected_summary, sort_by=["cost"]
        ),
    }
    mismatches = {key: value for key, value in mismatches.items() if value}
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
                "interval", "symbols", "entry_delay_bars", "hold_bars",
                "overlap", "costs", "data_start", "data_end",
                "evaluation_start", "evaluation_end",
            )
        },
        "metrics": summary.to_dict(orient="records"),
        "mismatches": mismatches,
        "inputs": {
            "data_manifest": {
                "path": spec["data_manifest"],
                "sha256": sha256(manifest_path),
                "verified_files": len(verified),
            },
            "detailed": {
                "path": spec["detailed_file"], "sha256": sha256(detailed_path)
            },
            "summary": {
                "path": spec["summary_file"], "sha256": sha256(summary_path)
            },
        },
    }
    if write_report:
        output = RESULTS_DIR / "runs" / f"{experiment_id}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if mismatches:
        raise AssertionError(f"regression mismatch: {mismatches}")
    return report


def run_experiment(experiment_id: str, *, write_report: bool = True) -> dict:
    registry = load_registry()
    if experiment_id not in registry:
        choices = ", ".join(sorted(registry))
        raise ValueError(f"unknown experiment '{experiment_id}'; choose: {choices}")
    spec = registry[experiment_id]
    if spec["kind"] == "trend_short_cost_sensitivity":
        return run_cost_sensitivity_experiment(
            experiment_id, spec, write_report=write_report
        )
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
    cache_files = used_cache_files(frozen["symbol"].unique().tolist(), spec)
    missing = [str(path) for path in cache_files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing cache files: {missing}")
    manifest_path = BASE_DIR / spec["data_manifest"]
    verified_manifest_entries = verify_manifest(manifest_path, cache_files)
    generated = generate_trades(frozen, spec, config)
    signal_column = spec["signal_time_column"]
    expected_trades = frozen.copy()
    expected_trades[signal_column] = pd.to_datetime(expected_trades[signal_column], utc=True)
    expected_trades = expected_trades.sort_values(
        [signal_column, "symbol"], ignore_index=True
    )
    trade_mismatch = (
        len(generated) != len(expected_trades)
        or generated["symbol"].tolist() != expected_trades["symbol"].tolist()
        or not generated["signal_time"].reset_index(drop=True).equals(
            expected_trades[signal_column].reset_index(drop=True)
        )
        or not np.allclose(
            generated["gross_return"].to_numpy(),
            expected_trades["gross_return"].to_numpy(),
            rtol=1e-12,
            atol=1e-12,
        )
    )
    actual = summarize_returns(generated["net_return"])
    expected = expected_summary(summary_path, spec["cost"])
    mismatches = {
        field: {"actual": actual[field], "expected": expected[field]}
        for field in COMPARISON_FIELDS
        if not math.isclose(
            actual[field], expected[field], rel_tol=1e-12, abs_tol=1e-12
        )
    }
    if trade_mismatch:
        mismatches["trades"] = {
            "actual_count": len(generated),
            "expected_count": len(expected_trades),
        }

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
                "interval", "side", "entry_delay_bars", "hold_bars", "overlap", "cost",
                "data_start", "data_end", "evaluation_start", "evaluation_end",
            )
        },
        "metrics": {field: actual[field] for field in COMPARISON_FIELDS},
        "mismatches": mismatches,
        "inputs": {
            "data_manifest": {
                "path": spec["data_manifest"],
                "sha256": sha256(manifest_path),
                "verified_files": len(verified_manifest_entries),
            },
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

"""Evaluate preregistered intrabar exit policies on frozen C2 development signals."""

from __future__ import annotations

import argparse
import json
import math
import tomllib
from itertools import product
from pathlib import Path

import pandas as pd

from research.backtest import CostModel, IntrabarExitConfig, simulate_intrabar_exits
from research.binance_data import load_csv
from research.config import BASE_DIR, DATA_DIR, RESULTS_DIR
from research.data_manifest import verify_manifest
from research.metrics import summarize_returns
from research.run_research import used_cache_files


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "c2_exit_policy_v1.toml"


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        protocol = tomllib.load(handle)
    for section in ("experiment", "data", "splits", "execution", "grid", "selection"):
        if section not in protocol:
            raise ValueError(f"protocol missing section: {section}")
    execution = protocol["execution"]
    if execution["entry_delay_bars"] < 1:
        raise ValueError("entry_delay_bars must be at least one")
    if execution["same_bar_policy"] != "adverse_first":
        raise ValueError("exit-policy research must use adverse_first")
    if execution["break_even_effective"] != "next_bar":
        raise ValueError("break-even must become effective on the next bar")
    if execution["overlap"] != "allow":
        raise ValueError("frozen non-overlapping signals must use allow")
    return protocol


def split_bounds(protocol: dict) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    values = protocol["splits"]
    return {
        name: (
            pd.Timestamp(values[f"{name}_start"], tz="UTC"),
            pd.Timestamp(values[f"{name}_end"], tz="UTC"),
        )
        for name in ("development", "validation", "confirmation")
    }


def load_bars_and_signals(protocol: dict) -> dict[str, tuple[pd.DataFrame, pd.Series]]:
    data = protocol["data"]
    manifest_path = BASE_DIR / data["manifest"]
    spec = {
        "data_start": data["start"],
        "data_end": data["end"],
        "interval": data["interval"],
    }
    paths = used_cache_files(data["symbols"], spec)
    verify_manifest(manifest_path, paths)
    frozen = pd.read_csv(BASE_DIR / data["frozen_signals"])
    frozen["signal_time"] = pd.to_datetime(frozen["signal_time"], utc=True)
    loaded = {}
    for symbol in data["symbols"]:
        symbol_paths = [path for path in paths if path.name.startswith(f"{symbol}_")]
        bars = pd.concat([load_csv(path) for path in symbol_paths], ignore_index=True)
        bars = bars.drop_duplicates("open_time").sort_values("open_time", ignore_index=True)
        signal_times = set(
            frozen.loc[frozen["symbol"] == symbol, "signal_time"]
        )
        signals = bars["open_time"].isin(signal_times)
        missing = signal_times.difference(set(bars.loc[signals, "open_time"]))
        if missing:
            raise ValueError(f"frozen signals missing for {symbol}: {len(missing)}")
        loaded[symbol] = (bars, signals)
    return loaded


def _policy_name(activation_r: float | None) -> str:
    return "no_break_even" if activation_r is None else f"break_even_{activation_r:g}r"


def evaluate(protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    loaded = load_bars_and_signals(protocol)
    grid = protocol["grid"]
    execution = protocol["execution"]
    summary_rows = []
    asset_rows = []
    activations = [None, *grid["break_even_activation_r_multiples"]]
    for stop_fraction, target_r, activation_r in product(
        grid["stop_loss_fractions"],
        grid["take_profit_r_multiples"],
        activations,
    ):
        target_fraction = stop_fraction * target_r
        frames = []
        for symbol, (bars, signals) in loaded.items():
            trades = simulate_intrabar_exits(
                bars,
                signals,
                IntrabarExitConfig(
                    side="long",
                    entry_delay_bars=execution["entry_delay_bars"],
                    hold_bars=execution["hold_bars"],
                    overlap=execution["overlap"],
                    stop_loss_fraction=stop_fraction,
                    take_profit_fraction=target_fraction,
                    break_even_activation_r_multiple=activation_r,
                    break_even_cost_buffer=execution["break_even_cost_buffer"],
                    same_bar_policy=execution["same_bar_policy"],
                    costs=CostModel(fees=0),
                ),
            )
            trades.insert(0, "symbol", symbol)
            frames.append(trades)
        combined = pd.concat(frames, ignore_index=True)
        for split, (start, end) in split_bounds(protocol).items():
            split_trades = combined[
                (combined["signal_time"] >= start)
                & (combined["signal_time"] < end)
            ]
            for cost in execution["costs"]:
                common = {
                    "stop_loss_fraction": stop_fraction,
                    "take_profit_r_multiple": target_r,
                    "policy": _policy_name(activation_r),
                    "activation_r_multiple": activation_r,
                    "split": split,
                    "cost": cost,
                }
                metrics = summarize_returns(split_trades["gross_return"] - cost)
                summary_rows.append({
                    **common,
                    **metrics,
                    "break_even_exit_share": float(
                        (split_trades["exit_reason"] == "break_even").mean()
                    ),
                })
                for symbol in protocol["data"]["symbols"]:
                    symbol_trades = split_trades[split_trades["symbol"] == symbol]
                    asset_rows.append({
                        **common,
                        "symbol": symbol,
                        **summarize_returns(symbol_trades["gross_return"] - cost),
                    })
    return pd.DataFrame(summary_rows), pd.DataFrame(asset_rows)


def decide(protocol: dict, summary: pd.DataFrame, assets: pd.DataFrame) -> dict:
    selection = protocol["selection"]
    keys = ["stop_loss_fraction", "take_profit_r_multiple", "activation_r_multiple"]
    candidates = []
    candidate_rows = summary[summary["policy"] != "no_break_even"]
    for values, rows in candidate_rows.groupby(keys, dropna=False, sort=True):
        candidate = dict(zip(keys, values))
        reasons = []
        for split in selection["gated_splits"]:
            for cost in protocol["execution"]["costs"]:
                row = rows[(rows["split"] == split) & (rows["cost"] == cost)].iloc[0]
                baseline = summary[
                    (summary["stop_loss_fraction"] == candidate["stop_loss_fraction"])
                    & (summary["take_profit_r_multiple"] == candidate["take_profit_r_multiple"])
                    & (summary["policy"] == "no_break_even")
                    & (summary["split"] == split)
                    & (summary["cost"] == cost)
                ].iloc[0]
                prefix = f"{split}_{cost:g}"
                if (
                    not math.isfinite(row["profit_factor"])
                    or row["profit_factor"] < selection["min_candidate_profit_factor"]
                ):
                    reasons.append(f"{prefix}_absolute_pf")
                for required, field in (
                    (selection["require_mean_not_lower_than_baseline"], "mean_return"),
                    (
                        selection["require_profit_factor_not_lower_than_baseline"],
                        "profit_factor",
                    ),
                    (selection["require_q10_not_lower_than_baseline"], "q10"),
                ):
                    if required and (
                        not math.isfinite(row[field]) or row[field] < baseline[field]
                    ):
                        reasons.append(f"{prefix}_{field}")

                candidate_assets = assets[
                    (assets["stop_loss_fraction"] == candidate["stop_loss_fraction"])
                    & (assets["take_profit_r_multiple"] == candidate["take_profit_r_multiple"])
                    & (assets["policy"] == row["policy"])
                    & (assets["split"] == split)
                    & (assets["cost"] == cost)
                ].set_index("symbol")
                baseline_assets = assets[
                    (assets["stop_loss_fraction"] == candidate["stop_loss_fraction"])
                    & (assets["take_profit_r_multiple"] == candidate["take_profit_r_multiple"])
                    & (assets["policy"] == "no_break_even")
                    & (assets["split"] == split)
                    & (assets["cost"] == cost)
                ].set_index("symbol")
                paired = candidate_assets[["profit_factor"]].join(
                    baseline_assets[["profit_factor"]],
                    lsuffix="_candidate",
                    rsuffix="_baseline",
                )
                non_degraded = int(
                    (
                        paired["profit_factor_candidate"]
                        >= paired["profit_factor_baseline"]
                    ).sum()
                )
                if non_degraded < selection["min_non_degraded_assets"]:
                    reasons.append(f"{prefix}_asset_breadth")
        confirmation = rows[
            (rows["split"] == "confirmation")
            & (rows["cost"] == protocol["execution"]["costs"][0])
        ].iloc[0]
        candidates.append({
            **candidate,
            "policy": confirmation["policy"],
            "pass": not reasons,
            "confirmation_profit_factor": confirmation["profit_factor"],
            "reasons": sorted(set(reasons)),
        })
    passing = [row for row in candidates if row["pass"]]
    passing.sort(key=lambda row: row["confirmation_profit_factor"], reverse=True)
    return {
        "strategy_version": protocol["experiment"]["strategy_version"],
        "decision": "PASS_EXPLORATORY" if passing else "FAIL",
        "production_effect": "NONE",
        "tested_break_even_rules": len(candidates),
        "passing_break_even_rules": len(passing),
        "selected": passing[0] if passing else None,
        "candidates": candidates,
    }


def run(protocol_path: Path = DEFAULT_PROTOCOL) -> dict:
    protocol = load_protocol(protocol_path)
    summary, assets = evaluate(protocol)
    decision = decide(protocol, summary, assets)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(RESULTS_DIR / "c2_exit_policy_v1_summary.csv", index=False)
    assets.to_csv(RESULTS_DIR / "c2_exit_policy_v1_by_asset.csv", index=False)
    (RESULTS_DIR / "c2_exit_policy_v1_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args()
    decision = run(args.protocol)
    print(json.dumps({
        key: decision[key]
        for key in (
            "strategy_version",
            "decision",
            "production_effect",
            "tested_break_even_rules",
            "passing_break_even_rules",
            "selected",
        )
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

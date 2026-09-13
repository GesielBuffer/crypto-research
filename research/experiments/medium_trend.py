"""Preregistered event-driven medium-trend research family."""

from __future__ import annotations

import argparse
import json
import math
import tomllib
from itertools import product
from pathlib import Path

import pandas as pd

from research.backtest import CostModel, FixedHorizonConfig, simulate_fixed_horizon
from research.binance_data import load_csv
from research.config import BASE_DIR, DATA_DIR, RESULTS_DIR
from research.data_manifest import verify_manifest
from research.indicators import add_adx, add_atr
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "medium_trend_v1.toml"


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    required = {"experiment", "data", "splits", "execution", "grid", "selection"}
    missing = required.difference(document)
    if missing:
        raise ValueError(f"protocol missing sections: {sorted(missing)}")
    if document["experiment"].get("status") != "PREREGISTERED":
        raise ValueError("experiment must be preregistered before execution")
    return document


def cache_files(protocol: dict) -> list[Path]:
    data = protocol["data"]
    months = pd.date_range(data["start"], data["end"], freq="MS", inclusive="left")
    return [
        DATA_DIR / (
            f"{symbol}_{data['interval']}_{month:%Y-%m-%d}_"
            f"{month + pd.offsets.MonthBegin(1):%Y-%m-%d}.csv"
        )
        for symbol in sorted(data["symbols"])
        for month in months
    ]


def load_feature_bars(protocol: dict) -> dict[str, pd.DataFrame]:
    paths = cache_files(protocol)
    verify_manifest(BASE_DIR / protocol["data"]["manifest"], paths)
    by_symbol = {}
    spans = sorted(set(protocol["grid"]["fast_spans"] + protocol["grid"]["slow_spans"]))
    for symbol in sorted(protocol["data"]["symbols"]):
        symbol_paths = [path for path in paths if path.name.startswith(f"{symbol}_")]
        bars = pd.concat([load_csv(path) for path in symbol_paths], ignore_index=True)
        bars = bars.drop_duplicates("open_time").sort_values("open_time", ignore_index=True)
        bars = add_atr(bars)
        bars = add_adx(bars)
        for span in spans:
            bars[f"ema_{span}"] = bars["close"].ewm(span=span, adjust=False).mean()
        by_symbol[symbol] = bars
    return by_symbol


def build_event_signal(
    bars: pd.DataFrame,
    *,
    fast_span: int,
    slow_span: int,
    adx_threshold: int,
    side: str,
) -> pd.Series:
    fast = bars[f"ema_{fast_span}"]
    slow = bars[f"ema_{slow_span}"]
    slow_rising = slow.diff(12) > 0
    if side == "long":
        regime = (
            (fast > slow)
            & slow_rising
            & (bars["adx"] >= adx_threshold)
            & (bars["plus_di"] > bars["minus_di"])
        )
    elif side == "short":
        regime = (
            (fast < slow)
            & ~slow_rising
            & (bars["adx"] >= adx_threshold)
            & (bars["minus_di"] > bars["plus_di"])
        )
    else:
        raise ValueError("side must be long or short")
    warm = pd.Series(range(len(bars)), index=bars.index) >= slow_span * 3
    regime = regime.fillna(False) & warm
    return regime & ~regime.shift(1, fill_value=False)


def _remove_cross_side_overlap(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    selected = []
    next_allowed = None
    for index, row in trades.sort_values(["signal_time", "side"]).iterrows():
        if next_allowed is not None and row["signal_time"] < next_allowed:
            continue
        selected.append(index)
        next_allowed = row["exit_time"]
    return trades.loc[selected].sort_values("signal_time", ignore_index=True)


def generate_gross_trades(
    bars_by_symbol: dict[str, pd.DataFrame],
    *,
    fast_span: int,
    slow_span: int,
    adx_threshold: int,
    hold_bars: int,
) -> pd.DataFrame:
    frames = []
    for symbol, bars in bars_by_symbol.items():
        side_frames = []
        for side in ("long", "short"):
            signal = build_event_signal(
                bars,
                fast_span=fast_span,
                slow_span=slow_span,
                adx_threshold=adx_threshold,
                side=side,
            )
            trades = simulate_fixed_horizon(
                bars,
                signal,
                FixedHorizonConfig(
                    side=side,
                    entry_delay_bars=1,
                    hold_bars=hold_bars,
                    overlap="single_position",
                    costs=CostModel(fees=0),
                ),
            )
            side_frames.append(trades)
        combined = _remove_cross_side_overlap(pd.concat(side_frames, ignore_index=True))
        combined.insert(0, "symbol", symbol)
        frames.append(combined)
    return pd.concat(frames, ignore_index=True)


def split_bounds(protocol: dict) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    values = protocol["splits"]
    return {
        name: (
            pd.Timestamp(values[f"{name}_start"], tz="UTC"),
            pd.Timestamp(values[f"{name}_end"], tz="UTC"),
        )
        for name in ("development", "validation", "confirmation")
    }


def evaluate(protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars_by_symbol = load_feature_bars(protocol)
    grid = protocol["grid"]
    rows = []
    asset_rows = []
    combinations = product(
        grid["fast_spans"],
        grid["slow_spans"],
        grid["adx_thresholds"],
        grid["hold_bars"],
    )
    for fast_span, slow_span, adx_threshold, hold_bars in combinations:
        if fast_span >= slow_span:
            continue
        trades = generate_gross_trades(
            bars_by_symbol,
            fast_span=fast_span,
            slow_span=slow_span,
            adx_threshold=adx_threshold,
            hold_bars=hold_bars,
        )
        for split, (start, end) in split_bounds(protocol).items():
            split_trades = trades[
                (trades["entry_time"] >= start) & (trades["exit_time"] < end)
            ]
            for cost in protocol["execution"]["costs"]:
                metrics = summarize_returns(split_trades["gross_return"] - cost)
                rows.append({
                    "fast_span": fast_span,
                    "slow_span": slow_span,
                    "adx_threshold": adx_threshold,
                    "hold_bars": hold_bars,
                    "split": split,
                    "cost": cost,
                    **metrics,
                })
            base_cost = protocol["execution"]["costs"][0]
            for symbol in sorted(protocol["data"]["symbols"]):
                returns = split_trades.loc[
                    split_trades["symbol"] == symbol, "gross_return"
                ] - base_cost
                asset_rows.append({
                    "fast_span": fast_span,
                    "slow_span": slow_span,
                    "adx_threshold": adx_threshold,
                    "hold_bars": hold_bars,
                    "split": split,
                    "symbol": symbol,
                    **summarize_returns(returns),
                })
    return pd.DataFrame(rows), pd.DataFrame(asset_rows)


def decide(protocol: dict, summary: pd.DataFrame, assets: pd.DataFrame) -> dict:
    limits = protocol["selection"]
    keys = ["fast_span", "slow_span", "adx_threshold", "hold_bars"]
    decisions = []
    for values, rows in summary.groupby(keys, sort=True):
        candidate = dict(zip(keys, values))
        passed = True
        reasons = []
        for split in ("development", "validation", "confirmation"):
            base = rows[(rows["split"] == split) & (rows["cost"] == 0.0006)].iloc[0]
            min_samples = limits[f"{split}_min_samples"]
            min_pf = limits[f"{split}_min_profit_factor"]
            if base["samples"] < min_samples or not math.isfinite(base["profit_factor"]) or base["profit_factor"] < min_pf:
                passed = False
                reasons.append(f"{split}_base")
            stress = rows[(rows["split"] == split) & (rows["cost"] == 0.001)].iloc[0]
            if not math.isfinite(stress["profit_factor"]) or stress["profit_factor"] < limits["stress_cost_min_profit_factor"]:
                passed = False
                reasons.append(f"{split}_stress")
            mask = pd.Series(True, index=assets.index)
            for key, value in candidate.items():
                mask &= assets[key] == value
            split_assets = assets[mask & (assets["split"] == split)]
            profitable_assets = int((split_assets["profit_factor"] > 1).sum())
            if profitable_assets < limits["min_profitable_assets_per_split"]:
                passed = False
                reasons.append(f"{split}_breadth")
        confirmation = rows[
            (rows["split"] == "confirmation") & (rows["cost"] == 0.0006)
        ].iloc[0]
        decisions.append({
            **candidate,
            "pass": passed,
            "confirmation_profit_factor": confirmation["profit_factor"],
            "reasons": sorted(set(reasons)),
        })
    passing = [row for row in decisions if row["pass"]]
    passing.sort(key=lambda row: row["confirmation_profit_factor"], reverse=True)
    return {
        "strategy_version": protocol["experiment"]["strategy_version"],
        "decision": "PASS" if passing else "FAIL",
        "tested_parameter_sets": len(decisions),
        "passing_parameter_sets": len(passing),
        "selected": passing[0] if passing else None,
        "candidates": decisions,
    }


def run(protocol_path: Path = DEFAULT_PROTOCOL) -> dict:
    protocol = load_protocol(protocol_path)
    summary, assets = evaluate(protocol)
    decision = decide(protocol, summary, assets)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(RESULTS_DIR / "medium_trend_v1_summary.csv", index=False)
    assets.to_csv(RESULTS_DIR / "medium_trend_v1_by_asset.csv", index=False)
    (RESULTS_DIR / "medium_trend_v1_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args()
    decision = run(args.protocol)
    print(json.dumps({
        "strategy_version": decision["strategy_version"],
        "decision": decision["decision"],
        "tested_parameter_sets": decision["tested_parameter_sets"],
        "passing_parameter_sets": decision["passing_parameter_sets"],
        "selected": decision["selected"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

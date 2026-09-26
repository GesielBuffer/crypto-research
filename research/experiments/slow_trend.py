"""Preregistered slow multi-speed time-series trend discovery."""

from __future__ import annotations

import argparse
import json
import math
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from research.config import BASE_DIR, RESULTS_DIR
from research.experiments.cross_sectional_momentum import build_panels, load_inputs
from research.experiments.delta_neutral_carry import max_compounded_drawdown
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "slow_trend_v1.toml"


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        protocol = tomllib.load(handle)
    required = {"experiment", "data", "signal", "portfolio", "splits", "selection", "fresh_holdout"}
    missing = required.difference(protocol)
    if missing:
        raise ValueError(f"protocol missing sections: {sorted(missing)}")
    if protocol["experiment"].get("status") != "PREREGISTERED":
        raise ValueError("experiment must be preregistered")
    if protocol["fresh_holdout"].get("status") != "UNOPENED":
        raise ValueError("discovery refuses an opened holdout")
    return protocol


def _capped_signed_weights(raw: pd.Series, gross: float, cap: float) -> pd.Series:
    raw = raw.replace([np.inf, -np.inf], np.nan).dropna()
    raw = raw[raw != 0]
    if raw.empty or len(raw) * cap + 1e-12 < gross:
        raise ValueError("insufficient active signals for the weight cap")
    weights = pd.Series(0.0, index=raw.index)
    remaining = list(raw.index)
    residual = gross
    magnitude = raw.abs()
    while remaining:
        allocation = magnitude.loc[remaining] / magnitude.loc[remaining].sum() * residual
        capped = allocation[allocation > cap]
        if capped.empty:
            weights.loc[remaining] = allocation * np.sign(raw.loc[remaining])
            break
        for symbol in capped.index:
            weights.loc[symbol] = cap * np.sign(raw[symbol])
            remaining.remove(symbol)
            residual -= cap
    return weights


def simulate(
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    *,
    speeds: list[int],
    rebalance_days: int,
    weight_cap: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = pd.Timestamp("2024-04-01", tz="UTC")
    end = pd.Timestamp("2026-08-01", tz="UTC")
    rebalances = pd.date_range(start, end, freq=f"{rebalance_days}D", inclusive="left")
    previous = pd.Series(0.0, index=closes.columns)
    rows, details = [], []
    for timestamp in rebalances:
        next_timestamp = timestamp + pd.Timedelta(days=rebalance_days)
        if next_timestamp > end:
            break
        entry_time = timestamp + pd.Timedelta(hours=4)
        exit_time = next_timestamp + pd.Timedelta(hours=4)
        if entry_time not in opens.index or exit_time not in opens.index:
            continue
        current = closes.loc[:timestamp].iloc[-2]
        components = []
        for speed in speeds:
            past = closes.loc[:timestamp - pd.Timedelta(days=speed)].iloc[-1]
            components.append(np.sign(current / past - 1.0))
        trend_score = pd.concat(components, axis=1).mean(axis=1)
        history = closes.loc[timestamp - pd.Timedelta(days=28):timestamp].pct_change().iloc[:-1]
        volatility = history.std(ddof=1) * math.sqrt(6 * 365)
        raw = trend_score / volatility
        active = raw.replace([np.inf, -np.inf], np.nan).dropna()
        weights = pd.Series(0.0, index=closes.columns)
        signed = _capped_signed_weights(active, 1.0, weight_cap)
        weights.loc[signed.index] = signed
        asset_returns = opens.loc[exit_time] / opens.loc[entry_time] - 1.0
        contribution = weights * asset_returns
        turnover = (weights - previous).abs()
        rows.append({
            "rebalance_time": timestamp,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "gross_return": float(contribution.sum()),
            "turnover": float(turnover.sum()),
            "net_exposure": float(weights.sum()),
            "active_assets": int((weights != 0).sum()),
        })
        for symbol in closes.columns:
            details.append({
                "rebalance_time": timestamp,
                "symbol": symbol,
                "gross_contribution": float(contribution[symbol]),
                "turnover": float(turnover[symbol]),
                "weight": float(weights[symbol]),
            })
        previous = weights
    periods = pd.DataFrame(rows)
    detail = pd.DataFrame(details)
    if not periods.empty:
        periods.loc[periods.index[-1], "turnover"] += float(previous.abs().sum())
        mask = detail["rebalance_time"] == periods.iloc[-1]["rebalance_time"]
        detail.loc[mask, "turnover"] += detail.loc[mask, "weight"].abs()
    return periods, detail


def evaluate(protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    source_protocol = {
        "data": {
            "candidate_symbols": pd.read_csv(BASE_DIR / protocol["data"]["universe_source"])["symbol"].tolist(),
            "interval": protocol["data"]["interval"],
            "start": protocol["data"]["start"],
            "discovery_end": protocol["data"]["discovery_end"],
        }
    }
    all_frames = load_inputs(source_protocol)
    universe_table = pd.read_csv(BASE_DIR / protocol["data"]["universe_source"])
    universe = universe_table.loc[universe_table["selected"].astype(str).str.lower() == "true", "symbol"].tolist()
    if len(universe) != 16:
        raise ValueError("frozen universe must contain exactly 16 symbols")
    closes, opens = build_panels(all_frames, universe)
    summaries, period_frames, detail_frames = [], [], []
    costs = protocol["portfolio"]["round_trip_costs"]
    for speed_set in protocol["signal"]["speed_sets"]:
        speed_id = "_".join(map(str, speed_set))
        periods, detail = simulate(
            closes,
            opens,
            speeds=speed_set,
            rebalance_days=protocol["signal"]["rebalance_days"],
            weight_cap=protocol["portfolio"]["weight_cap"],
        )
        periods.insert(0, "speed_set", speed_id)
        detail.insert(0, "speed_set", speed_id)
        period_frames.append(periods)
        detail_frames.append(detail)
        for split, bounds in protocol["splits"].items():
            start, end = (pd.Timestamp(value, tz="UTC") for value in bounds)
            selected = periods[(periods["entry_time"] >= start) & (periods["entry_time"] < end)]
            for cost in costs:
                net = selected["gross_return"] - selected["turnover"] * cost / 2
                summaries.append({
                    "speed_set": speed_id,
                    "split": split,
                    "cost": cost,
                    **summarize_returns(net),
                    "max_compounded_drawdown": max_compounded_drawdown(net),
                    "mean_turnover": float(selected["turnover"].mean()),
                    "mean_abs_net_exposure": float(selected["net_exposure"].abs().mean()),
                })
    return pd.DataFrame(summaries), pd.concat(period_frames, ignore_index=True), pd.concat(detail_frames, ignore_index=True)


def decide(protocol: dict, summary: pd.DataFrame, periods: pd.DataFrame, details: pd.DataFrame) -> dict:
    limits = protocol["selection"]
    costs = protocol["portfolio"]["round_trip_costs"]
    decisions = []
    for speed_set, rows in summary.groupby("speed_set", sort=True):
        reasons, base_pfs = [], []
        for split in protocol["splits"]:
            base = rows[(rows["split"] == split) & (rows["cost"] == costs[0])].iloc[0]
            stress = rows[(rows["split"] == split) & (rows["cost"] == costs[-1])].iloc[0]
            minimum = limits["minimum_rebalances_confirmation"] if split == "confirmation" else limits["minimum_rebalances_each_full_split"]
            base_pfs.append(float(base["profit_factor"]))
            if base["samples"] < minimum or base["profit_factor"] < limits["base_cost_min_profit_factor_each_split"]:
                reasons.append(f"{split}_base")
            if stress["profit_factor"] < limits["stress_cost_min_profit_factor_each_split"]:
                reasons.append(f"{split}_stress")
        p = periods[periods["speed_set"] == speed_set]
        net = p["gross_return"] - p["turnover"] * costs[0] / 2
        drawdown = max_compounded_drawdown(net)
        if drawdown > limits["max_pooled_drawdown"]:
            reasons.append("drawdown")
        d = details[details["speed_set"] == speed_set].copy()
        d["net_contribution"] = d["gross_contribution"] - d["turnover"] * costs[0] / 2
        positive = int((d.groupby("symbol")["net_contribution"].sum() > 0).sum())
        if positive < limits["minimum_positive_symbols"]:
            reasons.append("symbol_breadth")
        decisions.append({
            "speed_set": speed_set,
            "pass": not reasons,
            "minimum_split_profit_factor": min(base_pfs),
            "pooled_drawdown": drawdown,
            "positive_symbols": positive,
            "reasons": sorted(set(reasons)),
        })
    passing = [row for row in decisions if row["pass"]]
    passing.sort(key=lambda row: (-row["minimum_split_profit_factor"], len(row["speed_set"].split("_"))))
    return {
        "strategy_version": protocol["experiment"]["strategy_version"],
        "stage": "DISCOVERY",
        "decision": "FREEZE" if passing else "FAIL_DISCOVERY",
        "tested_parameter_sets": len(decisions),
        "passing_parameter_sets": len(passing),
        "selected": passing[0] if passing else None,
        "holdout_status": "UNOPENED",
        "candidates": decisions,
    }


def run(protocol: dict) -> dict:
    summary, periods, details = evaluate(protocol)
    decision = decide(protocol, summary, periods, details)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(RESULTS_DIR / "slow_trend_v1_discovery_summary.csv", index=False)
    periods.to_csv(RESULTS_DIR / "slow_trend_v1_periods.csv", index=False)
    details.to_csv(RESULTS_DIR / "slow_trend_v1_contributions.csv", index=False)
    (RESULTS_DIR / "slow_trend_v1_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args()
    decision = run(load_protocol(args.protocol))
    print(json.dumps({key: decision[key] for key in (
        "strategy_version", "stage", "decision", "tested_parameter_sets",
        "passing_parameter_sets", "selected", "holdout_status",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

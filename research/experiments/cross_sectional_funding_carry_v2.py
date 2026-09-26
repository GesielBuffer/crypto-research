"""Hysteresis follow-up for the cross-sectional funding carry candidate."""

from __future__ import annotations

import argparse
import json
import math
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from research.config import BASE_DIR, RESULTS_DIR
from research.experiments.cross_sectional_funding_carry import (
    _universe,
    funding_between,
    load_funding,
    period_return,
    trailing_funding_matrix,
)
from research.experiments.cross_sectional_momentum import build_panels, load_inputs
from research.experiments.delta_neutral_carry import max_compounded_drawdown
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "cross_sectional_funding_carry_v2.toml"


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        protocol = tomllib.load(handle)
    required = {
        "experiment", "data", "signal", "portfolio", "splits", "bootstrap",
        "research_continuation", "holdout_selection", "fresh_holdout",
    }
    missing = required.difference(protocol)
    if missing:
        raise ValueError(f"protocol missing sections: {sorted(missing)}")
    if protocol["experiment"].get("status") != "PREREGISTERED":
        raise ValueError("experiment must be preregistered")
    if protocol["fresh_holdout"].get("status") != "UNOPENED":
        raise ValueError("discovery refuses an opened holdout")
    return protocol


def block_bootstrap_mean(
    returns: pd.Series,
    *,
    resamples: int,
    block_periods: int,
    seed: int,
) -> dict[str, float]:
    values = pd.to_numeric(returns, errors="raise").dropna().to_numpy(dtype=float)
    if len(values) < block_periods:
        return {"probability_positive": math.nan, "mean_ci_low": math.nan, "mean_ci_high": math.nan}
    rng = np.random.default_rng(seed)
    block_count = math.ceil(len(values) / block_periods)
    means = np.empty(resamples)
    offsets = np.arange(block_periods)
    for index in range(resamples):
        starts = rng.integers(0, len(values), size=block_count)
        sample_indices = ((starts[:, None] + offsets) % len(values)).reshape(-1)[:len(values)]
        means[index] = values[sample_indices].mean()
    return {
        "probability_positive": float((means > 0).mean()),
        "mean_ci_low": float(np.quantile(means, 0.025)),
        "mean_ci_high": float(np.quantile(means, 0.975)),
    }


def hysteresis_membership(
    ranking: pd.Series,
    previous_longs: set[str],
    previous_shorts: set[str],
    *,
    entry_fraction: float,
    exit_boundary: float,
) -> tuple[set[str], set[str]]:
    ordered = ranking.sort_values()
    entry_count = max(1, math.floor(len(ordered) * entry_fraction))
    boundary = math.floor(len(ordered) * exit_boundary)
    lower_half = set(ordered.head(boundary).index)
    upper_half = set(ordered.tail(len(ordered) - boundary).index)
    longs = (previous_longs & lower_half) | set(ordered.head(entry_count).index)
    shorts = (previous_shorts & upper_half) | set(ordered.tail(entry_count).index)
    if longs & shorts:
        raise ValueError("hysteresis produced overlapping sides")
    return longs, shorts


def simulate(
    opens: pd.DataFrame,
    funding: dict[str, pd.DataFrame],
    protocol: dict,
    *,
    start: str = "2024-04-01",
    end: str = "2026-08-01",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    signal = protocol["signal"]
    matrix = trailing_funding_matrix(funding, signal["trailing_funding_records"])
    matrix = matrix[(matrix.index >= pd.Timestamp(start, tz="UTC")) & (matrix.index < pd.Timestamp(end, tz="UTC"))]
    timestamps = matrix.index
    step = signal["rebalance_funding_periods"]
    previous_weights = pd.Series(0.0, index=matrix.columns)
    previous_longs: set[str] = set()
    previous_shorts: set[str] = set()
    rows, details = [], []
    for position in range(0, len(timestamps) - step, step):
        observation, exit_observation = timestamps[position], timestamps[position + step]
        entry_index = int(opens.index.searchsorted(observation, side="right"))
        exit_index = int(opens.index.searchsorted(exit_observation, side="right"))
        if entry_index >= len(opens) or exit_index >= len(opens):
            break
        entry_time, exit_time = opens.index[entry_index], opens.index[exit_index]
        longs, shorts = hysteresis_membership(
            matrix.loc[observation], previous_longs, previous_shorts,
            entry_fraction=signal["entry_fraction"], exit_boundary=signal["exit_boundary"],
        )
        weights = pd.Series(0.0, index=matrix.columns)
        weights.loc[list(longs)] = 0.5 / len(longs)
        weights.loc[list(shorts)] = -0.5 / len(shorts)
        paid = pd.Series({symbol: funding_between(funding[symbol], observation, exit_observation) for symbol in matrix.columns})
        gross, price_component, funding_component = period_return(
            weights, opens.loc[entry_time, matrix.columns], opens.loc[exit_time, matrix.columns], paid
        )
        turnover = (weights - previous_weights).abs()
        rows.append({
            "observation_time": observation,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "gross_return": gross,
            "price_component": price_component,
            "funding_component": funding_component,
            "turnover": float(turnover.sum()),
            "long_count": len(longs),
            "short_count": len(shorts),
        })
        price_returns = opens.loc[exit_time, matrix.columns] / opens.loc[entry_time, matrix.columns] - 1.0
        for symbol in matrix.columns:
            details.append({
                "observation_time": observation,
                "symbol": symbol,
                "gross_contribution": float(weights[symbol] * price_returns[symbol] - weights[symbol] * paid[symbol]),
                "funding_contribution": float(-weights[symbol] * paid[symbol]),
                "turnover": float(turnover[symbol]),
                "weight": float(weights[symbol]),
            })
        previous_weights = weights
        previous_longs, previous_shorts = longs, shorts
    periods = pd.DataFrame(rows)
    detail = pd.DataFrame(details)
    if not periods.empty:
        periods.loc[periods.index[-1], "turnover"] += float(previous_weights.abs().sum())
        mask = detail["observation_time"] == periods.iloc[-1]["observation_time"]
        detail.loc[mask, "turnover"] += detail.loc[mask, "weight"].abs()
    return periods, detail


def evaluate(protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    symbols = _universe(protocol)
    source_protocol = {"data": {
        "candidate_symbols": symbols,
        "interval": protocol["data"]["interval"],
        "start": protocol["data"]["start"],
        "discovery_end": protocol["data"]["discovery_end"],
    }}
    _, opens = build_panels(load_inputs(source_protocol), symbols)
    periods, details = simulate(opens, load_funding(protocol), protocol)
    rows = []
    bootstrap = protocol["bootstrap"]
    for split, bounds in protocol["splits"].items():
        start, end = (pd.Timestamp(value, tz="UTC") for value in bounds)
        selected = periods[(periods["entry_time"] >= start) & (periods["exit_time"] < end)]
        for cost_index, cost in enumerate(protocol["portfolio"]["round_trip_costs"]):
            net = selected["gross_return"] - selected["turnover"] * cost / 2
            uncertainty = block_bootstrap_mean(
                net,
                resamples=bootstrap["resamples"],
                block_periods=bootstrap["block_periods"],
                seed=bootstrap["seed"] + cost_index,
            )
            rows.append({
                "split": split,
                "cost": cost,
                **summarize_returns(net),
                **uncertainty,
                "max_compounded_drawdown": max_compounded_drawdown(net),
                "mean_turnover": float(selected["turnover"].mean()),
                "mean_price_component": float(selected["price_component"].mean()),
                "mean_funding_component": float(selected["funding_component"].mean()),
                "mean_long_count": float(selected["long_count"].mean()),
                "mean_short_count": float(selected["short_count"].mean()),
            })
    return pd.DataFrame(rows), periods, details


def _minimum(limits: dict, split: str) -> int:
    return limits["minimum_periods_confirmation"] if split == "confirmation" else limits["minimum_periods_each_full_split"]


def decide(protocol: dict, summary: pd.DataFrame, periods: pd.DataFrame, details: pd.DataFrame) -> dict:
    research = protocol["research_continuation"]
    promotion = protocol["holdout_selection"]
    bootstrap = protocol["bootstrap"]
    costs = protocol["portfolio"]["round_trip_costs"]
    research_reasons, promotion_reasons, base_pfs = [], [], []
    for split in protocol["splits"]:
        base = summary[(summary["split"] == split) & (summary["cost"] == costs[0])].iloc[0]
        stress = summary[(summary["split"] == split) & (summary["cost"] == costs[-1])].iloc[0]
        base_pfs.append(float(base["profit_factor"]))
        if base["samples"] < _minimum(research, split) or base["profit_factor"] < research["minimum_base_profit_factor_each_split"]:
            research_reasons.append(f"{split}_base")
        if base["samples"] < _minimum(promotion, split) or base["profit_factor"] < promotion["base_cost_min_profit_factor_each_split"]:
            promotion_reasons.append(f"{split}_base")
        if stress["profit_factor"] < promotion["stress_cost_min_profit_factor_each_split"]:
            promotion_reasons.append(f"{split}_stress")
        if base["probability_positive"] < bootstrap["holdout_min_probability_positive_each_split"]:
            promotion_reasons.append(f"{split}_bootstrap")
    base_net = periods["gross_return"] - periods["turnover"] * costs[0] / 2
    pooled = summarize_returns(base_net)
    pooled_bootstrap = block_bootstrap_mean(
        base_net,
        resamples=bootstrap["resamples"],
        block_periods=bootstrap["block_periods"],
        seed=bootstrap["seed"],
    )
    drawdown = max_compounded_drawdown(base_net)
    if pooled["profit_factor"] < research["minimum_pooled_profit_factor"]:
        research_reasons.append("pooled_profit_factor")
    if pooled_bootstrap["probability_positive"] < bootstrap["research_min_probability_positive"]:
        research_reasons.append("pooled_bootstrap")
    if drawdown > research["max_pooled_drawdown"]:
        research_reasons.append("drawdown")
    if drawdown > promotion["max_pooled_drawdown"]:
        promotion_reasons.append("drawdown")
    detail = details.copy()
    detail["net_contribution"] = detail["gross_contribution"] - detail["turnover"] * costs[0] / 2
    positive = int((detail.groupby("symbol")["net_contribution"].sum() > 0).sum())
    if positive < research["minimum_positive_symbols"]:
        research_reasons.append("symbol_breadth")
    if positive < promotion["minimum_positive_symbols"]:
        promotion_reasons.append("symbol_breadth")
    level = "HOLDOUT_READY" if not promotion_reasons else ("RESEARCH_CANDIDATE" if not research_reasons else "REJECT")
    return {
        "strategy_version": protocol["experiment"]["strategy_version"],
        "stage": "DISCOVERY",
        "decision": level,
        "holdout_status": "UNOPENED",
        "minimum_split_profit_factor": min(base_pfs),
        "pooled_profit_factor": float(pooled["profit_factor"]),
        "pooled_drawdown": drawdown,
        "pooled_probability_positive": pooled_bootstrap["probability_positive"],
        "pooled_mean_ci_low": pooled_bootstrap["mean_ci_low"],
        "pooled_mean_ci_high": pooled_bootstrap["mean_ci_high"],
        "positive_symbols": positive,
        "research_reasons": sorted(set(research_reasons)),
        "promotion_reasons": sorted(set(promotion_reasons)),
    }


def run(protocol: dict) -> dict:
    summary, periods, details = evaluate(protocol)
    decision = decide(protocol, summary, periods, details)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(RESULTS_DIR / "cross_sectional_funding_carry_v2_summary.csv", index=False)
    periods.to_csv(RESULTS_DIR / "cross_sectional_funding_carry_v2_periods.csv", index=False)
    details.to_csv(RESULTS_DIR / "cross_sectional_funding_carry_v2_contributions.csv", index=False)
    (RESULTS_DIR / "cross_sectional_funding_carry_v2_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args()
    decision = run(load_protocol(args.protocol))
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

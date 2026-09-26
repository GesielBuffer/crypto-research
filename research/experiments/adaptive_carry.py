"""Discovery stage for the preregistered adaptive delta-neutral carry family."""

from __future__ import annotations

import argparse
import json
import math
import tomllib
from itertools import product
from pathlib import Path

import pandas as pd

from research.config import BASE_DIR, RESULTS_DIR
from research.experiments.delta_neutral_carry import (
    load_inputs,
    max_compounded_drawdown,
)
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "adaptive_carry_v2.toml"
TRADE_COLUMNS = [
    "observation_time",
    "entry_time",
    "exit_time",
    "trailing_funding",
    "historical_threshold",
    "entry_basis",
    "spot_return",
    "perp_short_return",
    "realized_funding",
    "gross_return",
]


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    required = {
        "experiment",
        "discovery_data",
        "signal",
        "execution",
        "discovery_selection",
        "fresh_holdout",
    }
    missing = required.difference(document)
    if missing:
        raise ValueError(f"protocol missing sections: {sorted(missing)}")
    if document["experiment"].get("status") != "PREREGISTERED":
        raise ValueError("experiment must be preregistered")
    if document["fresh_holdout"].get("status") != "UNOPENED":
        raise ValueError("discovery refuses an already opened holdout")
    return document


def _input_protocol(protocol: dict) -> dict:
    data = protocol["discovery_data"]
    return {
        "data": {
            "symbols": data["symbols"],
            "start": data["start"],
            "end": data["end"],
            "perpetual_interval": data["perpetual_interval"],
            "spot_interval": data["spot_interval"],
            "perpetual_manifest": data["perpetual_manifest"],
            "structural_manifest": data["structural_manifest"],
        }
    }


def simulate_adaptive_symbol(
    prices: pd.DataFrame,
    funding: pd.DataFrame,
    *,
    trailing_records: int,
    percentile_history_records: int,
    entry_percentile: float,
    hold_funding_periods: int,
    max_entry_basis: float,
) -> pd.DataFrame:
    """Compare current trailing carry with an exclusively historical percentile."""
    rates = funding["fundingRate"].astype(float)
    trailing = rates.rolling(trailing_records, min_periods=trailing_records).mean()
    thresholds = trailing.shift(1).rolling(
        percentile_history_records,
        min_periods=percentile_history_records,
    ).quantile(entry_percentile)
    price_times = prices["open_time"]
    rows = []
    index = trailing_records - 1 + percentile_history_records
    last_entry = len(funding) - hold_funding_periods - 1
    while index <= last_entry:
        observation = funding.iloc[index]
        current_trailing = float(trailing.iloc[index])
        threshold = float(thresholds.iloc[index])
        if (
            not math.isfinite(threshold)
            or float(observation["fundingRate"]) <= 0
            or current_trailing < threshold
        ):
            index += 1
            continue
        exit_funding_index = index + hold_funding_periods
        entry_position = int(
            price_times.searchsorted(observation["fundingTime"], side="right")
        )
        exit_position = int(
            price_times.searchsorted(
                funding.iloc[exit_funding_index]["fundingTime"], side="right"
            )
        )
        if entry_position >= len(prices) or exit_position >= len(prices):
            break
        entry = prices.iloc[entry_position]
        exit_row = prices.iloc[exit_position]
        basis = float(entry["perp_open"] / entry["spot_open"] - 1.0)
        if basis < 0 or basis > max_entry_basis:
            index += 1
            continue
        spot_return = float(exit_row["spot_open"] / entry["spot_open"] - 1.0)
        perp_short_return = float(1.0 - exit_row["perp_open"] / entry["perp_open"])
        realized_funding = float(
            rates.iloc[index + 1 : exit_funding_index + 1].sum()
        )
        rows.append({
            "observation_time": observation["fundingTime"],
            "entry_time": entry["open_time"],
            "exit_time": exit_row["open_time"],
            "trailing_funding": current_trailing,
            "historical_threshold": threshold,
            "entry_basis": basis,
            "spot_return": spot_return,
            "perp_short_return": perp_short_return,
            "realized_funding": realized_funding,
            "gross_return": 0.5 * (
                spot_return + perp_short_return + realized_funding
            ),
        })
        index = exit_funding_index
    return pd.DataFrame(rows, columns=TRADE_COLUMNS)


def evaluate(protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    inputs = load_inputs(_input_protocol(protocol))
    signal = protocol["signal"]
    execution = protocol["execution"]
    summary_rows = []
    asset_rows = []
    trade_frames = []
    for hold, percentile in product(
        execution["hold_funding_periods"], signal["entry_percentiles"]
    ):
        frames = []
        for symbol, (prices, funding) in inputs.items():
            trades = simulate_adaptive_symbol(
                prices,
                funding,
                trailing_records=signal["trailing_funding_records"],
                percentile_history_records=signal["percentile_history_records"],
                entry_percentile=percentile,
                hold_funding_periods=hold,
                max_entry_basis=signal["max_entry_basis"],
            )
            trades.insert(0, "symbol", symbol)
            frames.append(trades)
        combined = pd.concat(frames, ignore_index=True)
        combined.insert(0, "hold_funding_periods", hold)
        combined.insert(1, "entry_percentile", percentile)
        trade_frames.append(combined)
        for year in protocol["discovery_selection"]["calendar_segments"]:
            selected = combined[
                (combined["entry_time"].dt.year == year)
                & (combined["exit_time"].dt.year == year)
            ].sort_values(["entry_time", "symbol"])
            for cost in execution["portfolio_round_trip_costs"]:
                returns = selected["gross_return"] - cost
                summary_rows.append({
                    "hold_funding_periods": hold,
                    "entry_percentile": percentile,
                    "year": year,
                    "cost": cost,
                    **summarize_returns(returns),
                    "max_compounded_drawdown": max_compounded_drawdown(returns),
                })
        base_cost = execution["portfolio_round_trip_costs"][0]
        for symbol in sorted(protocol["discovery_data"]["symbols"]):
            returns = combined.loc[combined["symbol"] == symbol, "gross_return"] - base_cost
            asset_rows.append({
                "hold_funding_periods": hold,
                "entry_percentile": percentile,
                "symbol": symbol,
                **summarize_returns(returns),
            })
    return (
        pd.DataFrame(summary_rows),
        pd.DataFrame(asset_rows),
        pd.concat(trade_frames, ignore_index=True),
    )


def decide(
    protocol: dict,
    summary: pd.DataFrame,
    assets: pd.DataFrame,
    trades: pd.DataFrame,
) -> dict:
    limits = protocol["discovery_selection"]
    costs = protocol["execution"]["portfolio_round_trip_costs"]
    keys = ["hold_funding_periods", "entry_percentile"]
    decisions = []
    for values, rows in summary.groupby(keys, sort=True):
        candidate = dict(zip(keys, values))
        reasons = []
        base_pfs = []
        for year in limits["calendar_segments"]:
            base = rows[(rows["year"] == year) & (rows["cost"] == costs[0])].iloc[0]
            base_pfs.append(float(base["profit_factor"]))
            minimum_samples = (
                limits["min_samples_2026_partial"]
                if year == 2026
                else limits["min_samples_per_full_year"]
            )
            if (
                base["samples"] < minimum_samples
                or not math.isfinite(base["profit_factor"])
                or base["profit_factor"] < limits["min_profit_factor_each_segment"]
            ):
                reasons.append(f"year_{year}_base")
            stress = rows[(rows["year"] == year) & (rows["cost"] == costs[-1])].iloc[0]
            if (
                not math.isfinite(stress["profit_factor"])
                or stress["profit_factor"] < limits["stress_cost_min_profit_factor"]
            ):
                reasons.append(f"year_{year}_stress")
        mask = pd.Series(True, index=assets.index)
        for key, value in candidate.items():
            mask &= assets[key] == value
        selected_assets = assets[mask]
        if int((selected_assets["profit_factor"] > 1).sum()) < limits["min_profitable_assets_pooled"]:
            reasons.append("asset_breadth")
        trade_mask = pd.Series(True, index=trades.index)
        for key, value in candidate.items():
            trade_mask &= trades[key] == value
        pooled_drawdown = max_compounded_drawdown(
            trades.loc[trade_mask, "gross_return"] - costs[0]
        )
        if not math.isfinite(pooled_drawdown) or pooled_drawdown > limits["max_pooled_drawdown"]:
            reasons.append("drawdown")
        decisions.append({
            **candidate,
            "pass": not reasons,
            "minimum_segment_profit_factor": min(base_pfs),
            "pooled_drawdown": pooled_drawdown,
            "reasons": sorted(set(reasons)),
        })
    passing = [row for row in decisions if row["pass"]]
    passing.sort(key=lambda row: (
        -row["minimum_segment_profit_factor"],
        row["hold_funding_periods"],
        -row["entry_percentile"],
    ))
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


def run(protocol_path: Path = DEFAULT_PROTOCOL) -> dict:
    protocol = load_protocol(protocol_path)
    summary, assets, trades = evaluate(protocol)
    decision = decide(protocol, summary, assets, trades)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(RESULTS_DIR / "adaptive_carry_v2_discovery_summary.csv", index=False)
    assets.to_csv(RESULTS_DIR / "adaptive_carry_v2_discovery_by_asset.csv", index=False)
    trades.to_csv(RESULTS_DIR / "adaptive_carry_v2_discovery_trades.csv", index=False)
    (RESULTS_DIR / "adaptive_carry_v2_discovery_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args()
    decision = run(args.protocol)
    print(json.dumps({key: decision[key] for key in (
        "strategy_version", "stage", "decision", "tested_parameter_sets",
        "passing_parameter_sets", "selected", "holdout_status"
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

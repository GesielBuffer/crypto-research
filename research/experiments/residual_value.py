"""Preregistered residual relative-value discovery."""

from __future__ import annotations

import argparse
import json
import math
import tomllib
from pathlib import Path

import pandas as pd

from research.config import BASE_DIR, RESULTS_DIR
from research.experiments.cross_sectional_momentum import build_panels, load_inputs
from research.experiments.delta_neutral_carry import max_compounded_drawdown
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "residual_value_v1.toml"


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


def residual_scores(
    closes: pd.DataFrame,
    timestamp: pd.Timestamp,
    *,
    market_factor: str,
    beta_window_days: int,
    residual_lookback_days: int,
) -> tuple[pd.Series, pd.Series]:
    """Estimate trailing beta and residuals using completed candles only."""
    returns = closes.pct_change()
    completed = returns.loc[:timestamp].iloc[:-1]
    beta_rows = beta_window_days * 6
    residual_rows = residual_lookback_days * 6
    window = completed.tail(beta_rows).dropna(how="any")
    if len(window) < beta_rows:
        raise ValueError("insufficient completed history for beta")
    factor = window[market_factor]
    denominator = float((factor * factor).sum())
    if denominator <= 0:
        raise ValueError("market factor has zero variance")
    betas = window.mul(factor, axis=0).sum() / denominator
    recent = window.tail(residual_rows)
    residual = recent.subtract(recent[market_factor].to_numpy()[:, None] * betas.to_numpy()[None, :])
    return residual.sum(), betas


def simulate(
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    *,
    market_factor: str,
    beta_window_days: int,
    residual_lookback_days: int,
    rebalance_days: int,
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
        scores, betas = residual_scores(
            closes,
            timestamp,
            market_factor=market_factor,
            beta_window_days=beta_window_days,
            residual_lookback_days=residual_lookback_days,
        )
        ranked = scores.dropna().sort_values()
        count = max(1, math.floor(len(ranked) * 0.25))
        longs = ranked.head(count).index
        shorts = ranked.tail(count).index
        weights = pd.Series(0.0, index=closes.columns)
        weights.loc[longs] = 0.5 / count
        weights.loc[shorts] = -0.5 / count
        asset_returns = opens.loc[exit_time] / opens.loc[entry_time] - 1.0
        contribution = weights * asset_returns
        turnover = (weights - previous).abs()
        rows.append({
            "rebalance_time": timestamp,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "gross_return": float(contribution.sum()),
            "turnover": float(turnover.sum()),
            "estimated_market_beta": float((weights * betas).sum()),
            "long_count": len(longs),
            "short_count": len(shorts),
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
    universe_table = pd.read_csv(BASE_DIR / protocol["data"]["universe_source"])
    universe = universe_table.loc[universe_table["selected"].astype(str).str.lower() == "true", "symbol"].tolist()
    source_protocol = {
        "data": {
            "candidate_symbols": universe,
            "interval": protocol["data"]["interval"],
            "start": protocol["data"]["start"],
            "discovery_end": protocol["data"]["discovery_end"],
        }
    }
    frames = load_inputs(source_protocol)
    closes, opens = build_panels(frames, universe)
    costs = protocol["portfolio"]["round_trip_costs"]
    summaries, period_frames, detail_frames = [], [], []
    for beta_window in protocol["signal"]["beta_window_days"]:
        for residual_lookback in protocol["signal"]["residual_lookback_days"]:
            periods, detail = simulate(
                closes,
                opens,
                market_factor=protocol["data"]["market_factor"],
                beta_window_days=beta_window,
                residual_lookback_days=residual_lookback,
                rebalance_days=protocol["signal"]["rebalance_days"],
            )
            periods.insert(0, "beta_window_days", beta_window)
            periods.insert(1, "residual_lookback_days", residual_lookback)
            detail.insert(0, "beta_window_days", beta_window)
            detail.insert(1, "residual_lookback_days", residual_lookback)
            period_frames.append(periods)
            detail_frames.append(detail)
            for split, bounds in protocol["splits"].items():
                start, end = (pd.Timestamp(value, tz="UTC") for value in bounds)
                selected = periods[(periods["entry_time"] >= start) & (periods["entry_time"] < end)]
                for cost in costs:
                    net = selected["gross_return"] - selected["turnover"] * cost / 2
                    summaries.append({
                        "beta_window_days": beta_window,
                        "residual_lookback_days": residual_lookback,
                        "split": split,
                        "cost": cost,
                        **summarize_returns(net),
                        "max_compounded_drawdown": max_compounded_drawdown(net),
                        "mean_turnover": float(selected["turnover"].mean()),
                        "mean_abs_market_beta": float(selected["estimated_market_beta"].abs().mean()),
                    })
    return pd.DataFrame(summaries), pd.concat(period_frames, ignore_index=True), pd.concat(detail_frames, ignore_index=True)


def decide(protocol: dict, summary: pd.DataFrame, periods: pd.DataFrame, details: pd.DataFrame) -> dict:
    limits = protocol["selection"]
    costs = protocol["portfolio"]["round_trip_costs"]
    decisions = []
    keys = ["beta_window_days", "residual_lookback_days"]
    for values, rows in summary.groupby(keys, sort=True):
        beta_window, residual_lookback = values
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
        mask = (periods["beta_window_days"] == beta_window) & (periods["residual_lookback_days"] == residual_lookback)
        p = periods[mask]
        net = p["gross_return"] - p["turnover"] * costs[0] / 2
        drawdown = max_compounded_drawdown(net)
        if drawdown > limits["max_pooled_drawdown"]:
            reasons.append("drawdown")
        dmask = (details["beta_window_days"] == beta_window) & (details["residual_lookback_days"] == residual_lookback)
        d = details[dmask].copy()
        d["net_contribution"] = d["gross_contribution"] - d["turnover"] * costs[0] / 2
        positive = int((d.groupby("symbol")["net_contribution"].sum() > 0).sum())
        if positive < limits["minimum_positive_symbols"]:
            reasons.append("symbol_breadth")
        decisions.append({
            "beta_window_days": int(beta_window),
            "residual_lookback_days": int(residual_lookback),
            "pass": not reasons,
            "minimum_split_profit_factor": min(base_pfs),
            "pooled_drawdown": drawdown,
            "positive_symbols": positive,
            "reasons": sorted(set(reasons)),
        })
    passing = [row for row in decisions if row["pass"]]
    passing.sort(key=lambda row: (-row["minimum_split_profit_factor"], row["residual_lookback_days"], -row["beta_window_days"]))
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
    summary.to_csv(RESULTS_DIR / "residual_value_v1_discovery_summary.csv", index=False)
    periods.to_csv(RESULTS_DIR / "residual_value_v1_periods.csv", index=False)
    details.to_csv(RESULTS_DIR / "residual_value_v1_contributions.csv", index=False)
    (RESULTS_DIR / "residual_value_v1_decision.json").write_text(
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

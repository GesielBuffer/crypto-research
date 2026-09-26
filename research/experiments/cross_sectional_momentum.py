"""Preregistered cross-sectional momentum discovery and public-data acquisition."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import fetch_klines, load_csv, save_csv
from research.config import BASE_DIR, RESULTS_DIR
from research.experiments.delta_neutral_carry import max_compounded_drawdown
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "cross_sectional_momentum_v1.toml"
DATA_DIR = BASE_DIR / "data" / "cross_sectional_momentum_v1"
MANIFEST_PATH = BASE_DIR / "manifests" / "cross_sectional_momentum_v1.json"


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        protocol = tomllib.load(handle)
    required = {"experiment", "data", "universe", "signal", "portfolio", "splits", "selection", "fresh_holdout"}
    missing = required.difference(protocol)
    if missing:
        raise ValueError(f"protocol missing sections: {sorted(missing)}")
    if protocol["experiment"].get("status") != "PREREGISTERED":
        raise ValueError("experiment must be preregistered")
    if protocol["fresh_holdout"].get("status") != "UNOPENED":
        raise ValueError("discovery refuses an opened holdout")
    return protocol


def cache_path(symbol: str, protocol: dict) -> Path:
    data = protocol["data"]
    return DATA_DIR / f"{symbol}_{data['interval']}_{data['start']}_{data['discovery_end']}.csv"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def acquire(protocol: dict, *, refresh: bool = False) -> dict:
    """Download only public discovery data and write an auditable local manifest."""
    entries = []
    for symbol in protocol["data"]["candidate_symbols"]:
        path = cache_path(symbol, protocol)
        if refresh or not path.exists():
            frame = fetch_klines(
                symbol,
                protocol["data"]["interval"],
                protocol["data"]["start"],
                protocol["data"]["discovery_end"],
            )
            if frame.empty:
                raise RuntimeError(f"no public klines returned for {symbol}")
            save_csv(frame, path)
        frame = load_csv(path)
        entries.append({
            "symbol": symbol,
            "path": path.relative_to(BASE_DIR).as_posix(),
            "rows": len(frame),
            "first_open_time": frame["open_time"].min().isoformat(),
            "last_open_time": frame["open_time"].max().isoformat(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })
    manifest = {
        "dataset_id": "cross-sectional-momentum-v1-public-usdm-4h",
        "source": "https://fapi.binance.com/fapi/v1/klines",
        "interval": protocol["data"]["interval"],
        "requested_start": protocol["data"]["start"],
        "requested_end_exclusive": protocol["data"]["discovery_end"],
        "holdout_included": False,
        "files": entries,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_inputs(protocol: dict) -> dict[str, pd.DataFrame]:
    frames = {}
    for symbol in protocol["data"]["candidate_symbols"]:
        path = cache_path(symbol, protocol)
        if not path.exists():
            raise FileNotFoundError(f"missing {path}; run with --download")
        frames[symbol] = load_csv(path)
    return frames


def select_universe(frames: dict[str, pd.DataFrame], protocol: dict) -> tuple[list[str], pd.DataFrame]:
    rules = protocol["universe"]
    start = pd.Timestamp(rules["formation_start"], tz="UTC")
    end = pd.Timestamp(rules["formation_end"], tz="UTC")
    expected_days = (end - start).days
    rows = []
    for symbol, frame in frames.items():
        formation = frame[(frame["open_time"] >= start) & (frame["open_time"] < end)].copy()
        daily = formation.set_index("open_time")["quote_volume"].resample("1D").agg(["sum", "count"])
        complete = daily[daily["count"] == 6]
        coverage = len(complete) / expected_days
        rows.append({
            "symbol": symbol,
            "complete_days": len(complete),
            "coverage": coverage,
            "median_daily_quote_volume": float(complete["sum"].median()) if len(complete) else math.nan,
        })
    ranking = pd.DataFrame(rows).sort_values(
        ["median_daily_quote_volume", "symbol"], ascending=[False, True]
    ).reset_index(drop=True)
    eligible = ranking[ranking["coverage"] >= rules["minimum_daily_coverage"]]
    selected = eligible.head(16)["symbol"].tolist()
    if len(selected) != 16:
        raise ValueError(f"universe formation produced {len(selected)} eligible symbols, expected 16")
    ranking["selected"] = ranking["symbol"].isin(selected)
    return selected, ranking


def _capped_inverse_vol(volatility: pd.Series, gross: float, cap: float) -> pd.Series:
    if volatility.empty or (volatility <= 0).any() or not np.isfinite(volatility).all():
        raise ValueError("volatility must be finite and positive")
    if len(volatility) * cap + 1e-12 < gross:
        raise ValueError("weight cap is infeasible")
    raw = 1.0 / volatility
    weights = pd.Series(0.0, index=volatility.index)
    remaining = list(volatility.index)
    residual = gross
    while remaining:
        allocation = raw.loc[remaining] / raw.loc[remaining].sum() * residual
        capped = allocation[allocation > cap]
        if capped.empty:
            weights.loc[remaining] = allocation
            break
        for symbol in capped.index:
            weights.loc[symbol] = cap
            remaining.remove(symbol)
            residual -= cap
    return weights


def build_panels(frames: dict[str, pd.DataFrame], symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    closes = pd.concat(
        [frames[s].set_index("open_time")["close"].rename(s) for s in symbols], axis=1
    ).sort_index()
    opens = pd.concat(
        [frames[s].set_index("open_time")["open"].rename(s) for s in symbols], axis=1
    ).sort_index()
    return closes, opens


def simulate(
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    *,
    lookback_days: int,
    rebalance_days: int,
    skip_hours: int,
    long_fraction: float,
    short_fraction: float,
    weight_cap: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build positions from completed data and enter at the next 4h open."""
    start = pd.Timestamp("2024-04-01", tz="UTC")
    end = pd.Timestamp("2026-08-01", tz="UTC")
    rebalances = pd.date_range(start, end, freq=f"{rebalance_days}D", inclusive="left")
    rows = []
    contributions = []
    previous = pd.Series(0.0, index=closes.columns)
    for i, timestamp in enumerate(rebalances):
        next_timestamp = timestamp + pd.Timedelta(days=rebalance_days)
        if next_timestamp > end:
            break
        score_end = timestamp - pd.Timedelta(hours=skip_hours)
        score_start = score_end - pd.Timedelta(days=lookback_days)
        entry_time = timestamp + pd.Timedelta(hours=4)
        exit_time = next_timestamp + pd.Timedelta(hours=4)
        if entry_time not in opens.index or exit_time not in opens.index:
            continue
        end_prices = closes.loc[:score_end].iloc[-1]
        start_prices = closes.loc[:score_start].iloc[-1]
        returns_4h = closes.loc[timestamp - pd.Timedelta(days=28):timestamp].pct_change().iloc[:-1]
        vol = returns_4h.std(ddof=1) * math.sqrt(6 * 365)
        score = (end_prices / start_prices - 1.0) / vol
        valid = score.replace([np.inf, -np.inf], np.nan).dropna().index.intersection(vol.dropna().index)
        count = max(1, math.floor(len(valid) * long_fraction))
        ranked = score.loc[valid].sort_values()
        shorts = ranked.head(count).index
        longs = ranked.tail(count).index
        weights = pd.Series(0.0, index=closes.columns)
        weights.loc[longs] = _capped_inverse_vol(vol.loc[longs], 0.5, weight_cap)
        weights.loc[shorts] = -_capped_inverse_vol(vol.loc[shorts], 0.5, weight_cap)
        asset_returns = opens.loc[exit_time] / opens.loc[entry_time] - 1.0
        asset_contribution = weights * asset_returns
        turnover_by_asset = (weights - previous).abs()
        rows.append({
            "rebalance_time": timestamp,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "gross_return": float(asset_contribution.sum()),
            "turnover": float(turnover_by_asset.sum()),
            "long_count": len(longs),
            "short_count": len(shorts),
        })
        for symbol in closes.columns:
            contributions.append({
                "rebalance_time": timestamp,
                "symbol": symbol,
                "gross_contribution": float(asset_contribution[symbol]),
                "turnover": float(turnover_by_asset[symbol]),
                "weight": float(weights[symbol]),
            })
        previous = weights
    periods = pd.DataFrame(rows)
    detail = pd.DataFrame(contributions)
    if not periods.empty:
        closing_turnover = float(previous.abs().sum())
        periods.loc[periods.index[-1], "turnover"] += closing_turnover
        mask = detail["rebalance_time"] == periods.iloc[-1]["rebalance_time"]
        detail.loc[mask, "turnover"] += detail.loc[mask, "weight"].abs()
    return periods, detail


def evaluate(protocol: dict, frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    universe, ranking = select_universe(frames, protocol)
    closes, opens = build_panels(frames, universe)
    costs = protocol["portfolio"]["round_trip_costs"]
    summaries, period_frames, contribution_frames = [], [], []
    for lookback in protocol["signal"]["lookback_days"]:
        for rebalance in protocol["signal"]["rebalance_days"]:
            periods, contributions = simulate(
                closes, opens,
                lookback_days=lookback,
                rebalance_days=rebalance,
                skip_hours=protocol["signal"]["skip_hours"],
                long_fraction=protocol["signal"]["long_fraction"],
                short_fraction=protocol["signal"]["short_fraction"],
            )
            periods.insert(0, "lookback_days", lookback)
            periods.insert(1, "rebalance_days", rebalance)
            contributions.insert(0, "lookback_days", lookback)
            contributions.insert(1, "rebalance_days", rebalance)
            period_frames.append(periods)
            contribution_frames.append(contributions)
            for split, bounds in protocol["splits"].items():
                start, end = (pd.Timestamp(value, tz="UTC") for value in bounds)
                selected = periods[(periods["entry_time"] >= start) & (periods["entry_time"] < end)]
                for cost in costs:
                    net = selected["gross_return"] - selected["turnover"] * cost / 2
                    summaries.append({
                        "lookback_days": lookback,
                        "rebalance_days": rebalance,
                        "split": split,
                        "cost": cost,
                        **summarize_returns(net),
                        "max_compounded_drawdown": max_compounded_drawdown(net),
                        "mean_turnover": float(selected["turnover"].mean()),
                    })
    return ranking, pd.DataFrame(summaries), pd.concat(period_frames, ignore_index=True), pd.concat(contribution_frames, ignore_index=True)


def decide(protocol: dict, summary: pd.DataFrame, periods: pd.DataFrame, contributions: pd.DataFrame) -> dict:
    limits = protocol["selection"]
    costs = protocol["portfolio"]["round_trip_costs"]
    decisions = []
    for (lookback, rebalance), rows in summary.groupby(["lookback_days", "rebalance_days"], sort=True):
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
        mask = (periods["lookback_days"] == lookback) & (periods["rebalance_days"] == rebalance)
        selected_periods = periods[mask]
        base_net = selected_periods["gross_return"] - selected_periods["turnover"] * costs[0] / 2
        drawdown = max_compounded_drawdown(base_net)
        if drawdown > limits["max_pooled_drawdown"]:
            reasons.append("drawdown")
        cmask = (contributions["lookback_days"] == lookback) & (contributions["rebalance_days"] == rebalance)
        asset = contributions[cmask].copy()
        asset["net_contribution"] = asset["gross_contribution"] - asset["turnover"] * costs[0] / 2
        positive_symbols = int((asset.groupby("symbol")["net_contribution"].sum() > 0).sum())
        if positive_symbols < limits["minimum_positive_symbols"]:
            reasons.append("symbol_breadth")
        decisions.append({
            "lookback_days": int(lookback),
            "rebalance_days": int(rebalance),
            "pass": not reasons,
            "minimum_split_profit_factor": min(base_pfs),
            "pooled_drawdown": drawdown,
            "positive_symbols": positive_symbols,
            "reasons": sorted(set(reasons)),
        })
    passing = [row for row in decisions if row["pass"]]
    passing.sort(key=lambda row: (-row["minimum_split_profit_factor"], row["rebalance_days"], -row["lookback_days"]))
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
    frames = load_inputs(protocol)
    ranking, summary, periods, contributions = evaluate(protocol, frames)
    decision = decide(protocol, summary, periods, contributions)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ranking.to_csv(RESULTS_DIR / "cross_sectional_momentum_v1_universe.csv", index=False)
    summary.to_csv(RESULTS_DIR / "cross_sectional_momentum_v1_discovery_summary.csv", index=False)
    periods.to_csv(RESULTS_DIR / "cross_sectional_momentum_v1_periods.csv", index=False)
    contributions.to_csv(RESULTS_DIR / "cross_sectional_momentum_v1_contributions.csv", index=False)
    (RESULTS_DIR / "cross_sectional_momentum_v1_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    if args.download or args.refresh:
        manifest = acquire(protocol, refresh=args.refresh)
        print(f"downloaded_or_verified={len(manifest['files'])}")
    decision = run(protocol)
    print(json.dumps({key: decision[key] for key in (
        "strategy_version", "stage", "decision", "tested_parameter_sets",
        "passing_parameter_sets", "selected", "holdout_status",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

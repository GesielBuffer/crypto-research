"""Frozen V2 strategy evaluated once on August stress and fresh September holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tomllib
from pathlib import Path

import pandas as pd

from research.binance_data import fetch_klines, load_csv, save_csv
from research.config import BASE_DIR, RESULTS_DIR
from research.experiments.cross_sectional_funding_carry import (
    _universe,
    fetch_funding,
    load_funding,
)
from research.experiments.cross_sectional_funding_carry_v2 import (
    block_bootstrap_mean,
    simulate,
)
from research.experiments.cross_sectional_momentum import build_panels, load_inputs
from research.experiments.delta_neutral_carry import max_compounded_drawdown
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "cross_sectional_funding_carry_v3.toml"
EXTENSION_DIR = BASE_DIR / "data" / "cross_sectional_funding_carry_v3"
MANIFEST_PATH = BASE_DIR / "manifests" / "cross_sectional_funding_carry_v3.json"


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        protocol = tomllib.load(handle)
    required = {"experiment", "data", "strategy", "discovery_gate", "opened_stress", "fresh_holdout"}
    missing = required.difference(protocol)
    if missing:
        raise ValueError(f"protocol missing sections: {sorted(missing)}")
    if protocol["experiment"].get("status") != "FROZEN_CANDIDATE":
        raise ValueError("V3 must be frozen before extension acquisition")
    if protocol["fresh_holdout"].get("status") != "UNOPENED":
        raise ValueError("holdout runner refuses a previously opened holdout")
    return protocol


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def price_path(symbol: str, protocol: dict) -> Path:
    data = protocol["data"]
    return EXTENSION_DIR / f"{symbol}_{data['interval']}_{data['extension_start']}_{data['extension_end']}.csv"


def funding_path(symbol: str, protocol: dict) -> Path:
    data = protocol["data"]
    return EXTENSION_DIR / f"{symbol}_funding_{data['extension_start']}_{data['extension_end']}.csv"


def acquire(protocol: dict, *, refresh: bool = False) -> dict:
    EXTENSION_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    funding_protocol = {"data": {
        "start": protocol["data"]["extension_start"],
        "discovery_end": protocol["data"]["extension_end"],
        "funding_endpoint": "https://fapi.binance.com/fapi/v1/fundingRate",
    }}
    for symbol in _universe(protocol):
        p_path = price_path(symbol, protocol)
        f_path = funding_path(symbol, protocol)
        if refresh or not p_path.exists():
            prices = fetch_klines(
                symbol,
                protocol["data"]["interval"],
                protocol["data"]["extension_start"],
                protocol["data"]["extension_end"],
            )
            if prices.empty:
                raise RuntimeError(f"no extension prices returned for {symbol}")
            save_csv(prices, p_path)
        if refresh or not f_path.exists():
            fetch_funding(symbol, funding_protocol).to_csv(f_path, index=False)
        for kind, path, time_column in (("price", p_path, "open_time"), ("funding", f_path, "fundingTime")):
            frame = pd.read_csv(path)
            times = pd.to_datetime(frame[time_column], utc=True, format="mixed")
            entries.append({
                "symbol": symbol,
                "kind": kind,
                "path": path.relative_to(BASE_DIR).as_posix(),
                "rows": len(frame),
                "first_time": times.min().isoformat(),
                "last_time": times.max().isoformat(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            })
    manifest = {
        "dataset_id": "cross-sectional-funding-carry-v3-extension",
        "requested_start": protocol["data"]["extension_start"],
        "requested_end_exclusive": protocol["data"]["extension_end"],
        "contains_fresh_holdout": True,
        "files": entries,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def combined_inputs(protocol: dict) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    symbols = _universe(protocol)
    source_protocol = {"data": {
        "candidate_symbols": symbols,
        "interval": protocol["data"]["interval"],
        "start": protocol["data"]["discovery_start"],
        "discovery_end": protocol["data"]["discovery_end"],
    }}
    discovery_prices = load_inputs(source_protocol)
    combined_prices = {}
    for symbol in symbols:
        extension = load_csv(price_path(symbol, protocol))
        combined_prices[symbol] = pd.concat([discovery_prices[symbol], extension], ignore_index=True).drop_duplicates("open_time").sort_values("open_time")
    _, opens = build_panels(combined_prices, symbols)
    funding_source_protocol = {"data": {
        "universe_source": protocol["data"]["universe_source"],
        "start": protocol["data"]["discovery_start"],
        "discovery_end": protocol["data"]["discovery_end"],
    }}
    discovery_funding = load_funding(funding_source_protocol)
    combined_funding = {}
    for symbol in symbols:
        extension = pd.read_csv(funding_path(symbol, protocol))
        extension["fundingTime"] = pd.to_datetime(extension["fundingTime"], utc=True, format="mixed")
        extension["fundingRate"] = pd.to_numeric(extension["fundingRate"], errors="raise")
        combined_funding[symbol] = pd.concat([discovery_funding[symbol], extension], ignore_index=True).drop_duplicates("fundingTime").sort_values("fundingTime")
    return opens, combined_funding


def v2_protocol(protocol: dict) -> dict:
    strategy = protocol["strategy"]
    return {"signal": {
        "trailing_funding_records": strategy["trailing_funding_records"],
        "rebalance_funding_periods": strategy["rebalance_funding_periods"],
        "entry_fraction": strategy["entry_fraction"],
        "exit_boundary": strategy["exit_boundary"],
    }}


def summarize_window(periods: pd.DataFrame, start: str, end: str, costs: list[float]) -> list[dict]:
    lower, upper = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    selected = periods[(periods["entry_time"] >= lower) & (periods["exit_time"] < upper)]
    rows = []
    for cost in costs:
        net = selected["gross_return"] - selected["turnover"] * cost / 2
        rows.append({
            "cost": cost,
            **summarize_returns(net),
            "max_compounded_drawdown": max_compounded_drawdown(net),
            "mean_turnover": float(selected["turnover"].mean()),
            "mean_price_component": float(selected["price_component"].mean()),
            "mean_funding_component": float(selected["funding_component"].mean()),
        })
    return rows


def leave_one_out(periods: pd.DataFrame, details: pd.DataFrame, cost: float, end: str) -> pd.DataFrame:
    cutoff = pd.Timestamp(end, tz="UTC")
    selected = periods[periods["exit_time"] < cutoff].set_index("observation_time")
    total = selected["gross_return"] - selected["turnover"] * cost / 2
    detail = details[details["observation_time"].isin(selected.index)].copy()
    detail["net"] = detail["gross_contribution"] - detail["turnover"] * cost / 2
    rows = []
    for symbol, values in detail.groupby("symbol"):
        excluded = total - values.set_index("observation_time")["net"].reindex(total.index, fill_value=0)
        metrics = summarize_returns(excluded)
        rows.append({"excluded_symbol": symbol, "profit_factor": metrics["profit_factor"], "max_drawdown": max_compounded_drawdown(excluded)})
    return pd.DataFrame(rows)


def discovery_ready(protocol: dict, periods: pd.DataFrame, details: pd.DataFrame) -> tuple[bool, dict]:
    gate = protocol["discovery_gate"]
    costs = protocol["strategy"]["round_trip_costs"]
    splits = {
        "development": ("2024-04-01", "2025-01-01"),
        "validation": ("2025-01-01", "2026-01-01"),
        "confirmation": ("2026-01-01", "2026-08-01"),
    }
    reasons, split_rows = [], []
    probabilities = []
    for index, (name, (start, end)) in enumerate(splits.items()):
        rows = summarize_window(periods, start, end, costs)
        base, stress = rows[0], rows[-1]
        window = periods[(periods["entry_time"] >= pd.Timestamp(start, tz="UTC")) & (periods["exit_time"] < pd.Timestamp(end, tz="UTC"))]
        net = window["gross_return"] - window["turnover"] * costs[0] / 2
        probability = block_bootstrap_mean(net, resamples=2000, block_periods=7, seed=20260926 + index)["probability_positive"]
        probabilities.append(probability)
        split_rows.append({"split": name, "base_pf": base["profit_factor"], "stress_pf": stress["profit_factor"], "bootstrap_probability_positive": probability})
        if base["profit_factor"] < gate["base_cost_min_profit_factor_each_split"]:
            reasons.append(f"{name}_base")
        if stress["profit_factor"] < gate["stress_cost_min_profit_factor_each_split"]:
            reasons.append(f"{name}_stress")
        if probability < gate["minimum_split_bootstrap_probability_positive"]:
            reasons.append(f"{name}_bootstrap")
    discovery = periods[periods["exit_time"] < pd.Timestamp(protocol["data"]["discovery_end"], tz="UTC")]
    net = discovery["gross_return"] - discovery["turnover"] * costs[0] / 2
    pooled_probability = block_bootstrap_mean(net, resamples=2000, block_periods=7, seed=20260926)["probability_positive"]
    drawdown = max_compounded_drawdown(net)
    loo = leave_one_out(periods, details, costs[0], protocol["data"]["discovery_end"])
    if drawdown > gate["max_pooled_drawdown"]:
        reasons.append("drawdown")
    if pooled_probability < gate["pooled_bootstrap_probability_positive"]:
        reasons.append("pooled_bootstrap")
    if loo["profit_factor"].min() < gate["leave_one_asset_out_min_profit_factor"]:
        reasons.append("leave_one_out_pf")
    if loo["max_drawdown"].max() > gate["leave_one_asset_out_max_drawdown"]:
        reasons.append("leave_one_out_drawdown")
    evidence = {
        "splits": split_rows,
        "pooled_drawdown": drawdown,
        "pooled_bootstrap_probability_positive": pooled_probability,
        "leave_one_out_min_profit_factor": float(loo["profit_factor"].min()),
        "leave_one_out_max_drawdown": float(loo["max_drawdown"].max()),
        "reasons": reasons,
    }
    return not reasons, evidence


def run(protocol: dict) -> dict:
    opens, funding = combined_inputs(protocol)
    periods, details = simulate(
        opens,
        funding,
        v2_protocol(protocol),
        start="2024-04-01",
        end=protocol["data"]["extension_end"],
    )
    costs = protocol["strategy"]["round_trip_costs"]
    ready, discovery = discovery_ready(protocol, periods, details)
    august = summarize_window(periods, protocol["opened_stress"]["start"], protocol["opened_stress"]["end"], costs)
    september = summarize_window(periods, protocol["fresh_holdout"]["start"], protocol["fresh_holdout"]["end"], costs)
    base, stress = september[0], september[-1]
    gate = protocol["fresh_holdout"]
    holdout_reasons = []
    if not ready:
        holdout_reasons.append("discovery_not_ready")
    if base["samples"] < gate["minimum_periods"]:
        holdout_reasons.append("minimum_periods")
    if not math.isfinite(base["profit_factor"]) or base["profit_factor"] < gate["base_cost_min_profit_factor"]:
        holdout_reasons.append("base_profit_factor")
    if not math.isfinite(stress["profit_factor"]) or stress["profit_factor"] < gate["stress_cost_min_profit_factor"]:
        holdout_reasons.append("stress_profit_factor")
    if base["max_compounded_drawdown"] > gate["max_drawdown"]:
        holdout_reasons.append("drawdown")
    if gate["mean_return_must_be_positive"] and base["mean_return"] <= 0:
        holdout_reasons.append("mean_return")
    decision = "PASS" if not holdout_reasons else ("INSUFFICIENT" if holdout_reasons == ["minimum_periods"] else "FAIL")
    report = {
        "strategy_version": protocol["experiment"]["strategy_version"],
        "strategy_changed_from_v2": False,
        "discovery_ready": ready,
        "discovery_evidence": discovery,
        "august_role": "OPENED_STRESS_ONLY",
        "august": august,
        "holdout_period": [gate["start"], gate["end"]],
        "holdout_status": "OPENED_ONCE",
        "holdout": september,
        "decision": decision,
        "reasons": holdout_reasons,
        "promotion_effect": "SHADOW_PAPER_ONLY" if decision == "PASS" else "NONE",
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    periods.to_csv(RESULTS_DIR / "cross_sectional_funding_carry_v3_periods.csv", index=False)
    leave_one_out(periods, details, costs[0], protocol["data"]["discovery_end"]).to_csv(
        RESULTS_DIR / "cross_sectional_funding_carry_v3_leave_one_out.csv", index=False
    )
    (RESULTS_DIR / "cross_sectional_funding_carry_v3_decision.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    if args.download or args.refresh:
        manifest = acquire(protocol, refresh=args.refresh)
        print(f"extension_files={len(manifest['files'])}")
    report = run(protocol)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

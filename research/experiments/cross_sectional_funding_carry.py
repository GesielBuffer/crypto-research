"""Cross-sectional funding carry with tiered research and promotion gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import tomllib
from pathlib import Path

import pandas as pd
import requests

from research.config import BASE_DIR, RESULTS_DIR
from research.experiments.cross_sectional_momentum import build_panels, load_inputs
from research.experiments.delta_neutral_carry import max_compounded_drawdown
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "cross_sectional_funding_carry_v1.toml"
FUNDING_DIR = BASE_DIR / "data" / "cross_sectional_funding_carry_v1"
FUNDING_MANIFEST = BASE_DIR / "manifests" / "cross_sectional_funding_carry_v1.json"


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        protocol = tomllib.load(handle)
    required = {
        "experiment", "data", "signal", "portfolio", "splits",
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


def _universe(protocol: dict) -> list[str]:
    table = pd.read_csv(BASE_DIR / protocol["data"]["universe_source"])
    symbols = table.loc[table["selected"].astype(str).str.lower() == "true", "symbol"].tolist()
    if len(symbols) != 16:
        raise ValueError("frozen universe must contain exactly 16 symbols")
    return symbols


def funding_path(symbol: str, protocol: dict) -> Path:
    data = protocol["data"]
    return FUNDING_DIR / f"{symbol}_funding_{data['start']}_{data['discovery_end']}.csv"


def fetch_funding(symbol: str, protocol: dict) -> pd.DataFrame:
    start = int(pd.Timestamp(protocol["data"]["start"], tz="UTC").timestamp() * 1000)
    end = int(pd.Timestamp(protocol["data"]["discovery_end"], tz="UTC").timestamp() * 1000)
    rows, cursor = [], start
    while cursor < end:
        response = requests.get(
            protocol["data"]["funding_endpoint"],
            params={"symbol": symbol, "startTime": cursor, "endTime": end - 1, "limit": 1000},
            timeout=20,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        next_cursor = int(batch[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError(f"funding pagination stalled for {symbol}")
        cursor = next_cursor
        if len(batch) < 1000:
            break
        time.sleep(0.10)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"no public funding returned for {symbol}")
    frame["fundingTime"] = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
    frame["fundingRate"] = pd.to_numeric(frame["fundingRate"], errors="raise")
    frame["symbol"] = symbol
    return frame[["symbol", "fundingTime", "fundingRate"]].drop_duplicates("fundingTime").sort_values("fundingTime")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def acquire(protocol: dict, *, refresh: bool = False) -> dict:
    entries = []
    FUNDING_DIR.mkdir(parents=True, exist_ok=True)
    for symbol in _universe(protocol):
        path = funding_path(symbol, protocol)
        if refresh or not path.exists():
            fetch_funding(symbol, protocol).to_csv(path, index=False)
        frame = pd.read_csv(path, parse_dates=["fundingTime"])
        entries.append({
            "symbol": symbol,
            "path": path.relative_to(BASE_DIR).as_posix(),
            "rows": len(frame),
            "first_funding_time": pd.to_datetime(frame["fundingTime"], utc=True, format="mixed").min().isoformat(),
            "last_funding_time": pd.to_datetime(frame["fundingTime"], utc=True, format="mixed").max().isoformat(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })
    manifest = {
        "dataset_id": "cross-sectional-funding-carry-v1-public-usdm",
        "source": protocol["data"]["funding_endpoint"],
        "requested_start": protocol["data"]["start"],
        "requested_end_exclusive": protocol["data"]["discovery_end"],
        "holdout_included": False,
        "files": entries,
    }
    FUNDING_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    FUNDING_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_funding(protocol: dict) -> dict[str, pd.DataFrame]:
    result = {}
    for symbol in _universe(protocol):
        path = funding_path(symbol, protocol)
        if not path.exists():
            raise FileNotFoundError(f"missing {path}; run with --download")
        frame = pd.read_csv(path)
        frame["fundingTime"] = pd.to_datetime(frame["fundingTime"], utc=True, format="mixed")
        frame["fundingRate"] = pd.to_numeric(frame["fundingRate"], errors="raise")
        result[symbol] = frame.sort_values("fundingTime").drop_duplicates("fundingTime")
    return result


def trailing_funding_matrix(funding: dict[str, pd.DataFrame], records: int) -> pd.DataFrame:
    series = []
    for symbol, frame in funding.items():
        indexed = frame.set_index("fundingTime")["fundingRate"].astype(float)
        series.append(indexed.rolling(records, min_periods=records).mean().rename(symbol))
    return pd.concat(series, axis=1, join="inner").dropna().sort_index()


def funding_between(frame: pd.DataFrame, after: pd.Timestamp, through: pd.Timestamp) -> float:
    mask = (frame["fundingTime"] > after) & (frame["fundingTime"] <= through)
    return float(frame.loc[mask, "fundingRate"].sum())


def period_return(
    weights: pd.Series,
    entry_prices: pd.Series,
    exit_prices: pd.Series,
    funding_paid: pd.Series,
) -> tuple[float, float, float]:
    price_component = float((weights * (exit_prices / entry_prices - 1.0)).sum())
    funding_component = float(-(weights * funding_paid).sum())
    return price_component + funding_component, price_component, funding_component


def simulate(
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    funding: dict[str, pd.DataFrame],
    *,
    trailing_records: int,
    rebalance_periods: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    matrix = trailing_funding_matrix(funding, trailing_records)
    matrix = matrix[(matrix.index >= pd.Timestamp("2024-04-01", tz="UTC")) & (matrix.index < pd.Timestamp("2026-08-01", tz="UTC"))]
    timestamps = matrix.index
    previous = pd.Series(0.0, index=matrix.columns)
    rows, details = [], []
    for position in range(0, len(timestamps) - rebalance_periods, rebalance_periods):
        observation = timestamps[position]
        exit_observation = timestamps[position + rebalance_periods]
        entry_index = int(opens.index.searchsorted(observation, side="right"))
        exit_index = int(opens.index.searchsorted(exit_observation, side="right"))
        if entry_index >= len(opens) or exit_index >= len(opens):
            break
        entry_time, exit_time = opens.index[entry_index], opens.index[exit_index]
        ranking = matrix.loc[observation].sort_values()
        count = max(1, math.floor(len(ranking) * 0.25))
        longs, shorts = ranking.head(count).index, ranking.tail(count).index
        weights = pd.Series(0.0, index=matrix.columns)
        weights.loc[longs] = 0.5 / count
        weights.loc[shorts] = -0.5 / count
        paid = pd.Series({symbol: funding_between(funding[symbol], observation, exit_observation) for symbol in matrix.columns})
        gross, price_component, funding_component = period_return(
            weights, opens.loc[entry_time, matrix.columns], opens.loc[exit_time, matrix.columns], paid
        )
        turnover = (weights - previous).abs()
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
        previous = weights
    periods = pd.DataFrame(rows)
    detail = pd.DataFrame(details)
    if not periods.empty:
        periods.loc[periods.index[-1], "turnover"] += float(previous.abs().sum())
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
    price_frames = load_inputs(source_protocol)
    closes, opens = build_panels(price_frames, symbols)
    funding = load_funding(protocol)
    costs = protocol["portfolio"]["round_trip_costs"]
    summaries, period_frames, detail_frames = [], [], []
    for trailing in protocol["signal"]["trailing_funding_records"]:
        for rebalance in protocol["signal"]["rebalance_funding_periods"]:
            periods, detail = simulate(closes, opens, funding, trailing_records=trailing, rebalance_periods=rebalance)
            periods.insert(0, "trailing_funding_records", trailing)
            periods.insert(1, "rebalance_funding_periods", rebalance)
            detail.insert(0, "trailing_funding_records", trailing)
            detail.insert(1, "rebalance_funding_periods", rebalance)
            period_frames.append(periods)
            detail_frames.append(detail)
            for split, bounds in protocol["splits"].items():
                start, end = (pd.Timestamp(value, tz="UTC") for value in bounds)
                selected = periods[(periods["entry_time"] >= start) & (periods["exit_time"] < end)]
                for cost in costs:
                    net = selected["gross_return"] - selected["turnover"] * cost / 2
                    summaries.append({
                        "trailing_funding_records": trailing,
                        "rebalance_funding_periods": rebalance,
                        "split": split,
                        "cost": cost,
                        **summarize_returns(net),
                        "max_compounded_drawdown": max_compounded_drawdown(net),
                        "mean_turnover": float(selected["turnover"].mean()),
                        "mean_price_component": float(selected["price_component"].mean()),
                        "mean_funding_component": float(selected["funding_component"].mean()),
                    })
    return pd.DataFrame(summaries), pd.concat(period_frames, ignore_index=True), pd.concat(detail_frames, ignore_index=True)


def _sample_minimum(limits: dict, split: str) -> int:
    return limits["minimum_periods_confirmation"] if split == "confirmation" else limits["minimum_periods_each_full_split"]


def decide(protocol: dict, summary: pd.DataFrame, periods: pd.DataFrame, details: pd.DataFrame) -> dict:
    research = protocol["research_continuation"]
    promotion = protocol["holdout_selection"]
    costs = protocol["portfolio"]["round_trip_costs"]
    keys = ["trailing_funding_records", "rebalance_funding_periods"]
    candidates = []
    for values, rows in summary.groupby(keys, sort=True):
        trailing, rebalance = values
        research_reasons, promotion_reasons, base_pfs = [], [], []
        for split in protocol["splits"]:
            base = rows[(rows["split"] == split) & (rows["cost"] == costs[0])].iloc[0]
            stress = rows[(rows["split"] == split) & (rows["cost"] == costs[-1])].iloc[0]
            base_pfs.append(float(base["profit_factor"]))
            if base["samples"] < _sample_minimum(research, split) or base["profit_factor"] < research["minimum_base_profit_factor_each_split"]:
                research_reasons.append(f"{split}_base")
            if base["samples"] < _sample_minimum(promotion, split) or base["profit_factor"] < promotion["base_cost_min_profit_factor_each_split"]:
                promotion_reasons.append(f"{split}_base")
            if stress["profit_factor"] < promotion["stress_cost_min_profit_factor_each_split"]:
                promotion_reasons.append(f"{split}_stress")
        mask = (periods["trailing_funding_records"] == trailing) & (periods["rebalance_funding_periods"] == rebalance)
        p = periods[mask]
        base_net = p["gross_return"] - p["turnover"] * costs[0] / 2
        pooled = summarize_returns(base_net)
        drawdown = max_compounded_drawdown(base_net)
        if pooled["profit_factor"] < research["minimum_pooled_profit_factor"]:
            research_reasons.append("pooled_profit_factor")
        if drawdown > research["max_pooled_drawdown"]:
            research_reasons.append("drawdown")
        if drawdown > promotion["max_pooled_drawdown"]:
            promotion_reasons.append("drawdown")
        dmask = (details["trailing_funding_records"] == trailing) & (details["rebalance_funding_periods"] == rebalance)
        d = details[dmask].copy()
        d["net_contribution"] = d["gross_contribution"] - d["turnover"] * costs[0] / 2
        positive = int((d.groupby("symbol")["net_contribution"].sum() > 0).sum())
        if positive < research["minimum_positive_symbols"]:
            research_reasons.append("symbol_breadth")
        if positive < promotion["minimum_positive_symbols"]:
            promotion_reasons.append("symbol_breadth")
        level = "HOLDOUT_READY" if not promotion_reasons else ("RESEARCH_CANDIDATE" if not research_reasons else "REJECT")
        candidates.append({
            "trailing_funding_records": int(trailing),
            "rebalance_funding_periods": int(rebalance),
            "level": level,
            "minimum_split_profit_factor": min(base_pfs),
            "pooled_profit_factor": float(pooled["profit_factor"]),
            "pooled_drawdown": drawdown,
            "positive_symbols": positive,
            "research_reasons": sorted(set(research_reasons)),
            "promotion_reasons": sorted(set(promotion_reasons)),
        })
    ready = [row for row in candidates if row["level"] == "HOLDOUT_READY"]
    watch = [row for row in candidates if row["level"] == "RESEARCH_CANDIDATE"]
    ranking = lambda row: (-row["minimum_split_profit_factor"], row["rebalance_funding_periods"], -row["trailing_funding_records"])
    ready.sort(key=ranking)
    watch.sort(key=ranking)
    decision = "HOLDOUT_READY" if ready else ("RESEARCH_CANDIDATE" if watch else "REJECT")
    selected = ready[0] if ready else (watch[0] if watch else None)
    return {
        "strategy_version": protocol["experiment"]["strategy_version"],
        "stage": "DISCOVERY",
        "decision": decision,
        "tested_parameter_sets": len(candidates),
        "holdout_ready_parameter_sets": len(ready),
        "research_candidate_parameter_sets": len(watch),
        "selected": selected,
        "holdout_status": "UNOPENED",
        "candidates": candidates,
    }


def run(protocol: dict) -> dict:
    summary, periods, details = evaluate(protocol)
    decision = decide(protocol, summary, periods, details)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(RESULTS_DIR / "cross_sectional_funding_carry_v1_summary.csv", index=False)
    periods.to_csv(RESULTS_DIR / "cross_sectional_funding_carry_v1_periods.csv", index=False)
    details.to_csv(RESULTS_DIR / "cross_sectional_funding_carry_v1_contributions.csv", index=False)
    (RESULTS_DIR / "cross_sectional_funding_carry_v1_decision.json").write_text(
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
        print(f"funding_downloaded_or_verified={len(manifest['files'])}")
    decision = run(protocol)
    print(json.dumps({key: decision[key] for key in (
        "strategy_version", "stage", "decision", "tested_parameter_sets",
        "holdout_ready_parameter_sets", "research_candidate_parameter_sets",
        "selected", "holdout_status",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

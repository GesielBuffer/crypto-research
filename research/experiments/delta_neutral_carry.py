"""Preregistered delta-neutral spot/perpetual funding-carry experiment."""

from __future__ import annotations

import argparse
import json
import math
import tomllib
from itertools import product
from pathlib import Path

import pandas as pd

from research.binance_data import load_csv
from research.config import BASE_DIR, DATA_DIR, RESULTS_DIR
from research.data_manifest import verify_manifest
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "delta_neutral_carry_v1.toml"


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    required = {"experiment", "data", "splits", "signal", "execution", "selection"}
    missing = required.difference(document)
    if missing:
        raise ValueError(f"protocol missing sections: {sorted(missing)}")
    if document["experiment"].get("status") != "PREREGISTERED":
        raise ValueError("experiment must be preregistered before execution")
    if document["signal"].get("negative_funding_trade"):
        raise ValueError("V1 must not assume spot shorting or borrow")
    return document


def perpetual_files(protocol: dict) -> list[Path]:
    data = protocol["data"]
    months = pd.date_range(data["start"], data["end"], freq="MS", inclusive="left")
    return [
        DATA_DIR / (
            f"{symbol}_{data['perpetual_interval']}_{month:%Y-%m-%d}_"
            f"{month + pd.offsets.MonthBegin(1):%Y-%m-%d}.csv"
        )
        for symbol in sorted(data["symbols"])
        for month in months
    ]


def structural_files(protocol: dict) -> list[Path]:
    data = protocol["data"]
    return sorted(
        [
            DATA_DIR / f"{symbol}_funding_{data['start']}_{data['end']}.csv"
            for symbol in data["symbols"]
        ]
        + [
            DATA_DIR / (
                f"{symbol}_spot_{data['spot_interval']}_"
                f"{data['start']}_{data['end']}.csv"
            )
            for symbol in data["symbols"]
        ]
    )


def _numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    values = frame.copy()
    for column in columns:
        values[column] = pd.to_numeric(values[column], errors="raise")
    return values


def load_inputs(protocol: dict) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    perps = perpetual_files(protocol)
    structural = structural_files(protocol)
    verify_manifest(BASE_DIR / protocol["data"]["perpetual_manifest"], perps)
    verify_manifest(BASE_DIR / protocol["data"]["structural_manifest"], structural)
    end = pd.Timestamp(protocol["data"]["end"], tz="UTC")
    result = {}
    for symbol in sorted(protocol["data"]["symbols"]):
        symbol_perps = [path for path in perps if path.name.startswith(f"{symbol}_")]
        perp = pd.concat([load_csv(path) for path in symbol_perps], ignore_index=True)
        perp["open_time"] = pd.to_datetime(perp["open_time"], utc=True, format="mixed")
        perp = _numeric(perp, ["open"])
        perp = perp[perp["open_time"] < end].drop_duplicates("open_time")
        spot_path = DATA_DIR / (
            f"{symbol}_spot_{protocol['data']['spot_interval']}_"
            f"{protocol['data']['start']}_{protocol['data']['end']}.csv"
        )
        spot = pd.read_csv(spot_path)
        spot["open_time"] = pd.to_datetime(spot["open_time"], utc=True, format="mixed")
        spot = _numeric(spot, ["spot_open"])
        spot = spot[spot["open_time"] < end].drop_duplicates("open_time")
        prices = perp[["open_time", "open"]].rename(columns={"open": "perp_open"}).merge(
            spot[["open_time", "spot_open"]], on="open_time", how="inner", validate="one_to_one"
        ).sort_values("open_time", ignore_index=True)
        funding_path = DATA_DIR / (
            f"{symbol}_funding_{protocol['data']['start']}_"
            f"{protocol['data']['end']}.csv"
        )
        funding = pd.read_csv(funding_path)
        funding["fundingTime"] = pd.to_datetime(
            funding["fundingTime"], utc=True, format="mixed"
        )
        funding = _numeric(funding, ["fundingRate"])
        funding = funding[funding["fundingTime"] < end]
        funding = funding.drop_duplicates("fundingTime").sort_values(
            "fundingTime", ignore_index=True
        )
        result[symbol] = (prices, funding)
    return result


def simulate_symbol(
    prices: pd.DataFrame,
    funding: pd.DataFrame,
    *,
    trailing_records: int,
    annualization_periods: int,
    min_annualized_funding: float,
    hold_funding_periods: int,
    max_entry_basis: float,
) -> pd.DataFrame:
    """Use settled funding only; enter at the first common price strictly after it."""
    rates = funding["fundingRate"].astype(float)
    trailing = rates.rolling(trailing_records, min_periods=trailing_records).mean()
    price_times = prices["open_time"]
    rows = []
    index = trailing_records - 1
    last_entry = len(funding) - hold_funding_periods - 1
    while index <= last_entry:
        observation = funding.iloc[index]
        annualized = float(trailing.iloc[index]) * annualization_periods
        if float(observation["fundingRate"]) <= 0 or annualized < min_annualized_funding:
            index += 1
            continue
        exit_funding_index = index + hold_funding_periods
        entry_position = int(price_times.searchsorted(observation["fundingTime"], side="right"))
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
        gross_return = 0.5 * (spot_return + perp_short_return + realized_funding)
        rows.append({
            "observation_time": observation["fundingTime"],
            "entry_time": entry["open_time"],
            "exit_time": exit_row["open_time"],
            "trailing_annualized_funding": annualized,
            "entry_basis": basis,
            "spot_return": spot_return,
            "perp_short_return": perp_short_return,
            "realized_funding": realized_funding,
            "gross_return": gross_return,
        })
        index = exit_funding_index
    return pd.DataFrame(rows)


def split_bounds(protocol: dict) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    values = protocol["splits"]
    return {
        name: (
            pd.Timestamp(values[f"{name}_start"], tz="UTC"),
            pd.Timestamp(values[f"{name}_end"], tz="UTC"),
        )
        for name in ("development", "validation", "confirmation")
    }


def max_compounded_drawdown(returns: pd.Series) -> float:
    values = pd.to_numeric(returns, errors="raise").dropna().astype(float)
    if values.empty:
        return math.nan
    equity = (1.0 + values).cumprod()
    peak = equity.cummax().clip(lower=1.0)
    return float((1.0 - equity / peak).max())


def evaluate(protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    inputs = load_inputs(protocol)
    execution = protocol["execution"]
    signal = protocol["signal"]
    summary_rows = []
    asset_rows = []
    for hold, threshold in product(
        execution["hold_funding_periods"],
        execution["min_trailing_annualized_funding"],
    ):
        frames = []
        for symbol, (prices, funding) in inputs.items():
            trades = simulate_symbol(
                prices,
                funding,
                trailing_records=signal["trailing_funding_records"],
                annualization_periods=signal["annualization_periods"],
                min_annualized_funding=threshold,
                hold_funding_periods=hold,
                max_entry_basis=signal["max_entry_basis"],
            )
            trades.insert(0, "symbol", symbol)
            frames.append(trades)
        all_trades = pd.concat(frames, ignore_index=True)
        for split, (start, end) in split_bounds(protocol).items():
            selected = all_trades[
                (all_trades["entry_time"] >= start) & (all_trades["exit_time"] < end)
            ].sort_values(["entry_time", "symbol"])
            for cost in execution["portfolio_round_trip_costs"]:
                returns = selected["gross_return"] - cost
                summary_rows.append({
                    "hold_funding_periods": hold,
                    "min_trailing_annualized_funding": threshold,
                    "split": split,
                    "cost": cost,
                    **summarize_returns(returns),
                    "max_compounded_drawdown": max_compounded_drawdown(returns),
                    "mean_spot_return": float(selected["spot_return"].mean()),
                    "mean_perp_short_return": float(selected["perp_short_return"].mean()),
                    "mean_realized_funding": float(selected["realized_funding"].mean()),
                })
            base_cost = execution["portfolio_round_trip_costs"][0]
            for symbol in sorted(protocol["data"]["symbols"]):
                symbol_returns = selected.loc[
                    selected["symbol"] == symbol, "gross_return"
                ] - base_cost
                asset_rows.append({
                    "hold_funding_periods": hold,
                    "min_trailing_annualized_funding": threshold,
                    "split": split,
                    "symbol": symbol,
                    **summarize_returns(symbol_returns),
                })
    return pd.DataFrame(summary_rows), pd.DataFrame(asset_rows)


def decide(protocol: dict, summary: pd.DataFrame, assets: pd.DataFrame) -> dict:
    limits = protocol["selection"]
    keys = ["hold_funding_periods", "min_trailing_annualized_funding"]
    costs = protocol["execution"]["portfolio_round_trip_costs"]
    decisions = []
    for values, rows in summary.groupby(keys, sort=True):
        candidate = dict(zip(keys, values))
        reasons = []
        base_pfs = []
        for split in ("development", "validation", "confirmation"):
            base = rows[(rows["split"] == split) & (rows["cost"] == costs[0])].iloc[0]
            base_pfs.append(float(base["profit_factor"]))
            if (
                base["samples"] < limits[f"{split}_min_samples"]
                or not math.isfinite(base["profit_factor"])
                or base["profit_factor"] < limits[f"{split}_min_profit_factor"]
            ):
                reasons.append(f"{split}_base")
            if (
                not math.isfinite(base["max_compounded_drawdown"])
                or base["max_compounded_drawdown"] > limits["max_split_drawdown"]
            ):
                reasons.append(f"{split}_drawdown")
            stress = rows[(rows["split"] == split) & (rows["cost"] == costs[-1])].iloc[0]
            if (
                not math.isfinite(stress["profit_factor"])
                or stress["profit_factor"] < limits["stress_cost_min_profit_factor"]
            ):
                reasons.append(f"{split}_stress")
            mask = pd.Series(True, index=assets.index)
            for key, value in candidate.items():
                mask &= assets[key] == value
            split_assets = assets[mask & (assets["split"] == split)]
            if int((split_assets["profit_factor"] > 1).sum()) < limits["min_profitable_assets_per_split"]:
                reasons.append(f"{split}_breadth")
        decisions.append({
            **candidate,
            "pass": not reasons,
            "minimum_base_profit_factor": min(base_pfs),
            "reasons": sorted(set(reasons)),
        })
    passing = [row for row in decisions if row["pass"]]
    passing.sort(key=lambda row: (
        -row["minimum_base_profit_factor"],
        row["hold_funding_periods"],
        -row["min_trailing_annualized_funding"],
    ))
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
    summary.to_csv(RESULTS_DIR / "delta_neutral_carry_v1_summary.csv", index=False)
    assets.to_csv(RESULTS_DIR / "delta_neutral_carry_v1_by_asset.csv", index=False)
    (RESULTS_DIR / "delta_neutral_carry_v1_decision.json").write_text(
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

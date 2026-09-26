"""Preregistered low-turnover hourly breakout research family."""

from __future__ import annotations

import argparse
import json
import math
import tomllib
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv
from research.config import BASE_DIR, DATA_DIR, RESULTS_DIR
from research.data_manifest import verify_manifest
from research.indicators import add_atr
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "hourly_breakout_v1.toml"


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    required = {"experiment", "data", "splits", "execution", "grid", "selection"}
    missing = required.difference(document)
    if missing:
        raise ValueError(f"protocol missing sections: {sorted(missing)}")
    if document["experiment"].get("status") != "PREREGISTERED":
        raise ValueError("experiment must be preregistered before execution")
    execution = document["execution"]
    if execution.get("entry_delay_bars") != 1:
        raise ValueError("entry must occur exactly one bar after the signal")
    if execution.get("same_bar_policy") != "adverse_first":
        raise ValueError("same-bar policy must be adverse_first")
    if execution.get("short_return_convention") != "linear_usdm":
        raise ValueError("short returns must use the linear USD-M convention")
    return document


def cache_files(protocol: dict) -> list[Path]:
    data = protocol["data"]
    months = pd.date_range(data["start"], data["end"], freq="MS", inclusive="left")
    return [
        DATA_DIR / (
            f"{symbol}_{data['source_interval']}_{month:%Y-%m-%d}_"
            f"{month + pd.offsets.MonthBegin(1):%Y-%m-%d}.csv"
        )
        for symbol in sorted(data["symbols"])
        for month in months
    ]


def resample_hourly(bars: pd.DataFrame) -> pd.DataFrame:
    """Build complete UTC hours from 5-minute candles."""
    values = bars.copy()
    values["open_time"] = pd.to_datetime(values["open_time"], utc=True)
    values = values.drop_duplicates("open_time").sort_values("open_time")
    indexed = values.set_index("open_time")
    hourly = indexed.resample("1h", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        source_bars=("close", "count"),
    )
    hourly = hourly[hourly["source_bars"] == 12].drop(columns="source_bars")
    return hourly.reset_index()


def load_feature_bars(protocol: dict) -> dict[str, pd.DataFrame]:
    paths = cache_files(protocol)
    verify_manifest(BASE_DIR / protocol["data"]["manifest"], paths)
    execution = protocol["execution"]
    ema_spans = protocol["grid"]["trend_ema_spans"]
    end = pd.Timestamp(protocol["data"]["end"], tz="UTC")
    by_symbol = {}
    for symbol in sorted(protocol["data"]["symbols"]):
        symbol_paths = [path for path in paths if path.name.startswith(f"{symbol}_")]
        source = pd.concat([load_csv(path) for path in symbol_paths], ignore_index=True)
        source = source[pd.to_datetime(source["open_time"], utc=True) < end]
        bars = resample_hourly(source)
        bars = add_atr(bars, period=execution["atr_period"])
        for span in ema_spans:
            bars[f"ema_{span}"] = bars["close"].ewm(span=span, adjust=False).mean()
        by_symbol[symbol] = bars
    return by_symbol


def build_signal(
    bars: pd.DataFrame,
    *,
    breakout_window: int,
    trend_ema_span: int,
    side: str,
    min_atr_fraction: float,
    max_atr_fraction: float,
) -> pd.Series:
    """Create a close-confirmed signal using only information through bar t."""
    prior_high = bars["high"].rolling(breakout_window).max().shift(1)
    prior_low = bars["low"].rolling(breakout_window).min().shift(1)
    ema = bars[f"ema_{trend_ema_span}"]
    atr_fraction = bars["atr"] / bars["close"]
    volatility_ok = atr_fraction.between(min_atr_fraction, max_atr_fraction)
    warm = pd.Series(np.arange(len(bars)), index=bars.index) >= max(
        breakout_window, trend_ema_span * 3
    )
    if side == "long":
        signal = (bars["close"] > prior_high) & (bars["close"] > ema)
    elif side == "short":
        signal = (bars["close"] < prior_low) & (bars["close"] < ema)
    else:
        raise ValueError("side must be long or short")
    return (signal & volatility_ok & warm).fillna(False)


def simulate_atr_exits(
    bars: pd.DataFrame,
    signals: pd.Series,
    *,
    side: str,
    stop_atr_multiple: float,
    reward_r_multiple: float,
    max_hold_bars: int,
) -> pd.DataFrame:
    """Enter next open and apply variable ATR barriers with adverse-first ties."""
    if side not in {"long", "short"}:
        raise ValueError("side must be long or short")
    if len(signals) != len(bars) or not signals.index.equals(bars.index):
        raise ValueError("signals must align with bars")
    columns = [
        "signal_time",
        "entry_time",
        "exit_time",
        "side",
        "entry_price",
        "initial_stop_price",
        "take_profit_price",
        "exit_price",
        "exit_reason",
        "gross_return",
    ]
    candidates = np.flatnonzero(signals.fillna(False).to_numpy(dtype=bool))
    candidates = candidates[candidates + max_hold_bars < len(bars)]
    rows = []
    next_allowed_signal = 0
    for signal_position in candidates:
        signal_position = int(signal_position)
        if signal_position < next_allowed_signal:
            continue
        entry_position = signal_position + 1
        horizon_position = signal_position + max_hold_bars
        entry_price = float(bars.iloc[entry_position]["open"])
        risk_distance = float(bars.iloc[signal_position]["atr"]) * stop_atr_multiple
        if not math.isfinite(risk_distance) or risk_distance <= 0:
            continue
        direction = 1.0 if side == "long" else -1.0
        stop_price = entry_price - direction * risk_distance
        target_price = entry_price + direction * reward_r_multiple * risk_distance
        exit_position = horizon_position
        exit_price = float(bars.iloc[horizon_position]["close"])
        exit_reason = "horizon"
        for position in range(entry_position, horizon_position + 1):
            row = bars.iloc[position]
            open_price = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            if side == "long":
                if open_price <= stop_price:
                    exit_price, exit_reason = open_price, "stop_loss"
                elif open_price >= target_price:
                    exit_price, exit_reason = open_price, "take_profit"
                elif low <= stop_price:
                    exit_price, exit_reason = stop_price, "stop_loss"
                elif high >= target_price:
                    exit_price, exit_reason = target_price, "take_profit"
                else:
                    continue
            else:
                if open_price >= stop_price:
                    exit_price, exit_reason = open_price, "stop_loss"
                elif open_price <= target_price:
                    exit_price, exit_reason = open_price, "take_profit"
                elif high >= stop_price:
                    exit_price, exit_reason = stop_price, "stop_loss"
                elif low <= target_price:
                    exit_price, exit_reason = target_price, "take_profit"
                else:
                    continue
            exit_position = position
            break
        gross_return = (
            exit_price / entry_price - 1.0
            if side == "long"
            else 1.0 - exit_price / entry_price
        )
        rows.append({
            "signal_time": bars.iloc[signal_position]["open_time"],
            "entry_time": bars.iloc[entry_position]["open_time"],
            "exit_time": bars.iloc[exit_position]["open_time"],
            "side": side,
            "entry_price": entry_price,
            "initial_stop_price": stop_price,
            "take_profit_price": target_price,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "gross_return": gross_return,
        })
        next_allowed_signal = exit_position
    return pd.DataFrame(rows, columns=columns)


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
    protocol: dict,
    *,
    breakout_window: int,
    trend_ema_span: int,
    stop_atr_multiple: float,
) -> pd.DataFrame:
    execution = protocol["execution"]
    frames = []
    for symbol, bars in bars_by_symbol.items():
        sides = []
        for side in protocol["grid"]["sides"]:
            signals = build_signal(
                bars,
                breakout_window=breakout_window,
                trend_ema_span=trend_ema_span,
                side=side,
                min_atr_fraction=execution["min_atr_fraction"],
                max_atr_fraction=execution["max_atr_fraction"],
            )
            sides.append(simulate_atr_exits(
                bars,
                signals,
                side=side,
                stop_atr_multiple=stop_atr_multiple,
                reward_r_multiple=execution["reward_r_multiple"],
                max_hold_bars=execution["max_hold_bars"],
            ))
        combined = _remove_cross_side_overlap(pd.concat(sides, ignore_index=True))
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


def max_compounded_drawdown(returns: pd.Series) -> float:
    values = pd.to_numeric(returns, errors="raise").dropna().astype(float)
    if values.empty:
        return math.nan
    equity = (1.0 + values).cumprod()
    peak = equity.cummax().clip(lower=1.0)
    return float((1.0 - equity / peak).max())


def evaluate(protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars_by_symbol = load_feature_bars(protocol)
    grid = protocol["grid"]
    summary_rows = []
    asset_rows = []
    for breakout_window, trend_ema_span, stop_atr_multiple in product(
        grid["breakout_windows"],
        grid["trend_ema_spans"],
        grid["stop_atr_multiples"],
    ):
        trades = generate_gross_trades(
            bars_by_symbol,
            protocol,
            breakout_window=breakout_window,
            trend_ema_span=trend_ema_span,
            stop_atr_multiple=stop_atr_multiple,
        )
        for split, (start, end) in split_bounds(protocol).items():
            split_trades = trades[
                (trades["entry_time"] >= start) & (trades["exit_time"] < end)
            ].sort_values(["entry_time", "symbol"])
            for cost in protocol["execution"]["costs"]:
                returns = split_trades["gross_return"] - cost
                summary_rows.append({
                    "breakout_window": breakout_window,
                    "trend_ema_span": trend_ema_span,
                    "stop_atr_multiple": stop_atr_multiple,
                    "split": split,
                    "cost": cost,
                    **summarize_returns(returns),
                    "max_compounded_drawdown": max_compounded_drawdown(returns),
                })
            base_cost = protocol["execution"]["costs"][0]
            for symbol in sorted(protocol["data"]["symbols"]):
                returns = split_trades.loc[
                    split_trades["symbol"] == symbol, "gross_return"
                ] - base_cost
                asset_rows.append({
                    "breakout_window": breakout_window,
                    "trend_ema_span": trend_ema_span,
                    "stop_atr_multiple": stop_atr_multiple,
                    "split": split,
                    "symbol": symbol,
                    **summarize_returns(returns),
                    "max_compounded_drawdown": max_compounded_drawdown(returns),
                })
    return pd.DataFrame(summary_rows), pd.DataFrame(asset_rows)


def decide(protocol: dict, summary: pd.DataFrame, assets: pd.DataFrame) -> dict:
    limits = protocol["selection"]
    keys = ["breakout_window", "trend_ema_span", "stop_atr_multiple"]
    base_cost = protocol["execution"]["costs"][0]
    stress_cost = protocol["execution"]["costs"][-1]
    decisions = []
    for values, rows in summary.groupby(keys, sort=True):
        candidate = dict(zip(keys, values))
        reasons = []
        base_pfs = []
        for split in ("development", "validation", "confirmation"):
            base = rows[(rows["split"] == split) & (rows["cost"] == base_cost)].iloc[0]
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
            stress = rows[
                (rows["split"] == split) & (rows["cost"] == stress_cost)
            ].iloc[0]
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
        row["breakout_window"],
        row["trend_ema_span"],
        row["stop_atr_multiple"],
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
    summary.to_csv(RESULTS_DIR / "hourly_breakout_v1_summary.csv", index=False)
    assets.to_csv(RESULTS_DIR / "hourly_breakout_v1_by_asset.csv", index=False)
    (RESULTS_DIR / "hourly_breakout_v1_decision.json").write_text(
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

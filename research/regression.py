"""Regression helpers that replay frozen signals against cached public data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.backtest import FixedHorizonConfig, simulate_fixed_horizon
from research.binance_data import load_csv


def replay_frozen_trades(
    frozen: pd.DataFrame,
    data_dir: Path,
    config: FixedHorizonConfig,
    *,
    interval: str = "5m",
    signal_time_column: str | None = None,
) -> pd.DataFrame:
    """Replay frozen signal timestamps from the project's monthly cache files."""

    signal_column = signal_time_column or (
        "signal_time" if "signal_time" in frozen.columns else "open_time"
    )
    required = {"symbol", signal_column}
    missing = required.difference(frozen.columns)
    if missing:
        raise ValueError(f"frozen trades missing columns: {sorted(missing)}")

    source = frozen.copy()
    source[signal_column] = pd.to_datetime(source[signal_column], utc=True)
    source["period"] = source[signal_column].dt.strftime("%Y-%m")
    replayed = []

    for (symbol, period), expected in source.groupby(["symbol", "period"]):
        start = pd.Timestamp(f"{period}-01", tz="UTC")
        end = start + pd.offsets.MonthBegin(1)
        path = data_dir / (
            f"{symbol}_{interval}_{start:%Y-%m-%d}_{end:%Y-%m-%d}.csv"
        )
        if not path.exists():
            raise FileNotFoundError(f"missing candle cache: {path}")

        bars = load_csv(path)
        signal_times = set(expected[signal_column])
        signals = bars["open_time"].isin(signal_times)
        missing_times = signal_times.difference(set(bars.loc[signals, "open_time"]))
        if missing_times:
            raise ValueError(f"signals absent from candle cache: {sorted(missing_times)}")

        actual = simulate_fixed_horizon(bars, signals, config)
        actual.insert(0, "symbol", symbol)
        replayed.append(actual)

    if not replayed:
        return pd.DataFrame()
    return pd.concat(replayed, ignore_index=True).sort_values(
        ["signal_time", "symbol"], ignore_index=True
    )

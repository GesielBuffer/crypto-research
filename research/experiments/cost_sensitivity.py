"""Canonical reproduction of the legacy trend-short cost sensitivity study."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.backtest import CostModel, FixedHorizonConfig, simulate_fixed_horizon
from research.binance_data import load_csv
from research.config import DATA_DIR
from research.features import add_all_features
from research.indicators import add_all_indicators
from research.metrics import summarize_returns
from research.signals import build_trend_short_signal


DETAIL_FIELDS = (
    "samples",
    "win_rate",
    "mean_return",
    "median_return",
    "profit_factor",
    "best_trade",
    "worst_trade",
)


def cache_files(spec: dict) -> list[Path]:
    starts = pd.date_range(
        spec["data_start"], spec["data_end"], freq="MS", inclusive="left"
    )
    return [
        DATA_DIR / (
            f"{symbol}_{spec['interval']}_{start:%Y-%m-%d}_"
            f"{start + pd.offsets.MonthBegin(1):%Y-%m-%d}.csv"
        )
        for symbol in spec["symbols"]
        for start in starts
    ]


def reproduce(spec: dict) -> tuple[pd.DataFrame, pd.DataFrame, list[Path]]:
    """Recreate detailed and aggregate legacy outputs through the core engine."""

    rows = []
    paths = cache_files(spec)
    for path in paths:
        parts = path.stem.split("_")
        symbol = parts[0]
        period = parts[2][:7]
        bars = add_all_features(add_all_indicators(load_csv(path)))
        signals = build_trend_short_signal(bars)

        for cost in spec["costs"]:
            trades = simulate_fixed_horizon(
                bars,
                signals,
                FixedHorizonConfig(
                    side="short",
                    entry_delay_bars=spec["entry_delay_bars"],
                    hold_bars=spec["hold_bars"],
                    overlap=spec["overlap"],
                    short_return_convention="inverse",
                    costs=CostModel(fees=cost),
                ),
            )
            metrics = summarize_returns(trades["net_return"])
            rows.append({
                "symbol": symbol,
                "period": period,
                "cost": cost,
                **{field: metrics[field] for field in DETAIL_FIELDS},
            })

    detailed = pd.DataFrame(rows)
    summary = (
        detailed.groupby("cost", as_index=False)
        .agg(
            windows=("period", "count"),
            total_samples=("samples", "sum"),
            positive_windows=("mean_return", lambda values: int((values > 0).sum())),
            positive_window_rate=("mean_return", lambda values: (values > 0).mean()),
            median_mean_return=("mean_return", "median"),
            median_profit_factor=("profit_factor", "median"),
            median_win_rate=("win_rate", "median"),
        )
    )
    return detailed, summary, paths

"""Canonical metrics shared by research experiments."""

from __future__ import annotations

import math

import pandas as pd

from research.statistics import calculate_profit_factor


def max_losing_streak(returns: pd.Series) -> int:
    maximum = current = 0
    for value in returns.dropna():
        if value < 0:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def summarize_returns(returns: pd.Series) -> dict[str, float | int]:
    """Summarize independent trade returns using the project's conventions."""

    values = pd.to_numeric(returns, errors="raise").dropna().astype(float)
    if values.empty:
        return {
            "samples": 0,
            "mean_return": math.nan,
            "median_return": math.nan,
            "win_rate": math.nan,
            "profit_factor": math.nan,
            "max_losing_streak": 0,
            "q10": math.nan,
            "q90": math.nan,
            "worst_trade": math.nan,
            "best_trade": math.nan,
        }

    return {
        "samples": len(values),
        "mean_return": float(values.mean()),
        "median_return": float(values.median()),
        "win_rate": float((values > 0).mean()),
        "profit_factor": calculate_profit_factor(values),
        "max_losing_streak": max_losing_streak(values),
        "q10": float(values.quantile(0.10)),
        "q90": float(values.quantile(0.90)),
        "worst_trade": float(values.min()),
        "best_trade": float(values.max()),
    }

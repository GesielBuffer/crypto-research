"""Core, strategy-agnostic primitives for historical backtests.

This module deliberately has no exchange integration.  It operates on returns
that were already produced with information available at the signal candle and
an entry at a later candle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


Side = Literal["long", "short"]
OverlapPolicy = Literal["allow", "single_position"]
ShortReturnConvention = Literal["linear", "inverse"]


@dataclass(frozen=True)
class CostModel:
    """Additive costs expressed as fractions of notional per round trip."""

    fees: float = 0.0006
    slippage: float = 0.0
    funding: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("fees", self.fees),
            ("slippage", self.slippage),
            ("funding", self.funding),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")

    @property
    def round_trip(self) -> float:
        return self.fees + self.slippage + self.funding


def apply_costs(
    gross_returns: pd.Series,
    cost_model: CostModel | None = None,
) -> pd.Series:
    """Return net trade returns without mutating the caller's series."""

    costs = cost_model or CostModel()
    gross = pd.to_numeric(gross_returns, errors="raise").astype(float)
    net = gross - costs.round_trip
    net.name = "net_return"
    return net


@dataclass(frozen=True)
class FixedHorizonConfig:
    """Execution convention for a fixed-horizon bar backtest."""

    side: Side = "long"
    entry_delay_bars: int = 1
    hold_bars: int = 1
    overlap: OverlapPolicy = "single_position"
    short_return_convention: ShortReturnConvention = "linear"
    costs: CostModel = CostModel()

    def __post_init__(self) -> None:
        if self.side not in ("long", "short"):
            raise ValueError("side must be 'long' or 'short'")
        if self.entry_delay_bars < 1:
            raise ValueError("entry_delay_bars must be at least 1")
        if self.hold_bars < self.entry_delay_bars:
            raise ValueError("hold_bars must be >= entry_delay_bars")
        if self.overlap not in ("allow", "single_position"):
            raise ValueError("overlap must be 'allow' or 'single_position'")
        if self.short_return_convention not in ("linear", "inverse"):
            raise ValueError("short_return_convention must be 'linear' or 'inverse'")


def simulate_fixed_horizon(
    bars: pd.DataFrame,
    signals: pd.Series,
    config: FixedHorizonConfig | None = None,
    *,
    time_column: str = "open_time",
) -> pd.DataFrame:
    """Simulate signals using open at ``t+delay`` and close at ``t+hold``.

    The signal series is interpreted only at candle ``t``.  Requiring a delay
    of at least one bar makes same-candle fills impossible by construction.
    With ``single_position``, a signal at the existing position's exit bar is
    allowed, matching the project's historical non-overlap convention.
    """

    cfg = config or FixedHorizonConfig()
    required = {"open", "close", time_column}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"bars missing required columns: {sorted(missing)}")
    if len(signals) != len(bars) or not signals.index.equals(bars.index):
        raise ValueError("signals must have the same length and index as bars")

    candidates = np.flatnonzero(signals.fillna(False).to_numpy(dtype=bool))
    candidates = candidates[candidates + cfg.hold_bars < len(bars)]
    if cfg.overlap == "single_position":
        selected = []
        next_allowed = 0
        for position in candidates:
            if position >= next_allowed:
                selected.append(int(position))
                next_allowed = int(position) + cfg.hold_bars
        selected = np.asarray(selected, dtype=int)
    else:
        selected = candidates.astype(int, copy=False)

    columns = [
        "signal_time", "entry_time", "exit_time", "side", "signal_position",
        "entry_position", "exit_position", "entry_price", "exit_price",
        "gross_return", "cost", "net_return",
    ]
    if selected.size == 0:
        return pd.DataFrame(columns=columns)

    entry_positions = selected + cfg.entry_delay_bars
    exit_positions = selected + cfg.hold_bars
    entry_prices = bars["open"].iloc[entry_positions].to_numpy(dtype=float)
    exit_prices = bars["close"].iloc[exit_positions].to_numpy(dtype=float)
    if (entry_prices <= 0).any() or (exit_prices <= 0).any():
        raise ValueError("entry and exit prices must be positive")
    if cfg.side == "long":
        gross_returns = exit_prices / entry_prices - 1.0
    elif cfg.short_return_convention == "inverse":
        gross_returns = entry_prices / exit_prices - 1.0
    else:
        gross_returns = 1.0 - exit_prices / entry_prices
    return pd.DataFrame({
        "signal_time": bars[time_column].iloc[selected].to_numpy(),
        "entry_time": bars[time_column].iloc[entry_positions].to_numpy(),
        "exit_time": bars[time_column].iloc[exit_positions].to_numpy(),
        "side": cfg.side,
        "signal_position": selected,
        "entry_position": entry_positions,
        "exit_position": exit_positions,
        "entry_price": entry_prices,
        "exit_price": exit_prices,
        "gross_return": gross_returns,
        "cost": cfg.costs.round_trip,
        "net_return": gross_returns - cfg.costs.round_trip,
    }, columns=columns)

"""Core, strategy-agnostic primitives for historical backtests.

This module deliberately has no exchange integration.  It operates on returns
that were already produced with information available at the signal candle and
an entry at a later candle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


Side = Literal["long", "short"]
OverlapPolicy = Literal["allow", "single_position"]


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

    selected: list[int] = []
    next_allowed = 0
    for position, is_signal in enumerate(signals.fillna(False).astype(bool)):
        if not is_signal or position + cfg.hold_bars >= len(bars):
            continue
        if cfg.overlap == "single_position" and position < next_allowed:
            continue
        selected.append(position)
        if cfg.overlap == "single_position":
            next_allowed = position + cfg.hold_bars

    columns = [
        "signal_time", "entry_time", "exit_time", "side", "signal_position",
        "entry_position", "exit_position", "entry_price", "exit_price",
        "gross_return", "cost", "net_return",
    ]
    if not selected:
        return pd.DataFrame(columns=columns)

    records = []
    for signal_position in selected:
        entry_position = signal_position + cfg.entry_delay_bars
        exit_position = signal_position + cfg.hold_bars
        entry_price = float(bars["open"].iloc[entry_position])
        exit_price = float(bars["close"].iloc[exit_position])
        if entry_price <= 0 or exit_price <= 0:
            raise ValueError("entry and exit prices must be positive")
        direction = 1.0 if cfg.side == "long" else -1.0
        gross_return = direction * (exit_price / entry_price - 1.0)
        records.append({
            "signal_time": bars[time_column].iloc[signal_position],
            "entry_time": bars[time_column].iloc[entry_position],
            "exit_time": bars[time_column].iloc[exit_position],
            "side": cfg.side,
            "signal_position": signal_position,
            "entry_position": entry_position,
            "exit_position": exit_position,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "gross_return": gross_return,
            "cost": cfg.costs.round_trip,
            "net_return": gross_return - cfg.costs.round_trip,
        })
    return pd.DataFrame.from_records(records, columns=columns)

"""Core, strategy-agnostic primitives for historical backtests.

This module deliberately has no exchange integration.  It operates on returns
that were already produced with information available at the signal candle and
an entry at a later candle.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


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

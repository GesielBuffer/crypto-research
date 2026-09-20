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
SameBarPolicy = Literal["adverse_first"]


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


@dataclass(frozen=True)
class IntrabarExitConfig:
    """OHLC barrier model with conservative ordering for ambiguous candles."""

    side: Side = "long"
    entry_delay_bars: int = 1
    hold_bars: int = 6
    overlap: OverlapPolicy = "single_position"
    stop_loss_fraction: float = 0.01
    take_profit_fraction: float = 0.02
    break_even_activation_r_multiple: float | None = None
    break_even_cost_buffer: float = 0.0
    same_bar_policy: SameBarPolicy = "adverse_first"
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
        if self.stop_loss_fraction <= 0 or self.take_profit_fraction <= 0:
            raise ValueError("stop and target fractions must be positive")
        if self.break_even_cost_buffer < 0:
            raise ValueError("break_even_cost_buffer must be non-negative")
        if self.same_bar_policy != "adverse_first":
            raise ValueError("only the conservative adverse_first policy is supported")
        if self.short_return_convention not in ("linear", "inverse"):
            raise ValueError("short_return_convention must be 'linear' or 'inverse'")
        activation = self.break_even_activation_r_multiple
        if activation is not None:
            if activation <= 0:
                raise ValueError("break-even activation must be positive")
            activation_fraction = activation * self.stop_loss_fraction
            if self.break_even_cost_buffer >= activation_fraction:
                raise ValueError("break-even stop must remain behind its activation price")
            if activation_fraction >= self.take_profit_fraction:
                raise ValueError("break-even activation must occur before take-profit")


def _validate_ohlc_bars(bars: pd.DataFrame, time_column: str) -> None:
    required = {"open", "high", "low", "close", time_column}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"bars missing required columns: {sorted(missing)}")
    prices = bars[["open", "high", "low", "close"]].apply(
        pd.to_numeric, errors="raise"
    )
    if not np.isfinite(prices.to_numpy(dtype=float)).all():
        raise ValueError("OHLC prices must be finite")
    if (prices <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    invalid = (
        (prices["high"] < prices[["open", "close"]].max(axis=1))
        | (prices["low"] > prices[["open", "close"]].min(axis=1))
        | (prices["high"] < prices["low"])
    )
    if invalid.any():
        raise ValueError("OHLC bars contain an invalid price range")


def _intrabar_levels(entry_price: float, config: IntrabarExitConfig) -> tuple:
    if config.side == "long":
        stop_price = entry_price * (1.0 - config.stop_loss_fraction)
        target_price = entry_price * (1.0 + config.take_profit_fraction)
        break_even_price = entry_price * (1.0 + config.break_even_cost_buffer)
        activation_price = entry_price * (
            1.0
            + config.stop_loss_fraction
            * (config.break_even_activation_r_multiple or 0.0)
        )
    else:
        stop_price = entry_price * (1.0 + config.stop_loss_fraction)
        target_price = entry_price * (1.0 - config.take_profit_fraction)
        break_even_price = entry_price * (1.0 - config.break_even_cost_buffer)
        activation_price = entry_price * (
            1.0
            - config.stop_loss_fraction
            * (config.break_even_activation_r_multiple or 0.0)
        )
    return stop_price, target_price, break_even_price, activation_price


def _barrier_exit(
    row: pd.Series,
    *,
    side: Side,
    stop_price: float,
    target_price: float,
    stop_reason: str,
) -> tuple[float, str] | None:
    open_price = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    if side == "long":
        if open_price <= stop_price:
            return open_price, stop_reason
        if open_price >= target_price:
            return open_price, "take_profit"
        stop_touched = low <= stop_price
        target_touched = high >= target_price
    else:
        if open_price >= stop_price:
            return open_price, stop_reason
        if open_price <= target_price:
            return open_price, "take_profit"
        stop_touched = high >= stop_price
        target_touched = low <= target_price
    if stop_touched:
        return stop_price, stop_reason
    if target_touched:
        return target_price, "take_profit"
    return None


def simulate_intrabar_exits(
    bars: pd.DataFrame,
    signals: pd.Series,
    config: IntrabarExitConfig | None = None,
    *,
    time_column: str = "open_time",
) -> pd.DataFrame:
    """Simulate stop, target and next-bar break-even using OHLC candles.

    When stop and target are both touched in one candle, the stop wins. A
    break-even trigger observed inside a candle becomes active only on the next
    candle, because OHLC data cannot establish whether its high/low came first.
    """

    cfg = config or IntrabarExitConfig()
    _validate_ohlc_bars(bars, time_column)
    if len(signals) != len(bars) or not signals.index.equals(bars.index):
        raise ValueError("signals must have the same length and index as bars")

    candidates = np.flatnonzero(signals.fillna(False).to_numpy(dtype=bool))
    candidates = candidates[candidates + cfg.hold_bars < len(bars)]
    rows = []
    next_allowed_signal = 0
    for signal_position in candidates:
        signal_position = int(signal_position)
        if cfg.overlap == "single_position" and signal_position < next_allowed_signal:
            continue
        entry_position = signal_position + cfg.entry_delay_bars
        horizon_position = signal_position + cfg.hold_bars
        entry_price = float(bars.iloc[entry_position]["open"])
        stop_price, target_price, break_even_price, activation_price = (
            _intrabar_levels(entry_price, cfg)
        )
        active_stop = stop_price
        stop_reason = "stop_loss"
        break_even_activated = False
        activation_position = None
        exit_position = horizon_position
        exit_price = float(bars.iloc[horizon_position]["close"])
        exit_reason = "horizon"

        for position in range(entry_position, horizon_position + 1):
            bar = bars.iloc[position]
            barrier_exit = _barrier_exit(
                bar,
                side=cfg.side,
                stop_price=active_stop,
                target_price=target_price,
                stop_reason=stop_reason,
            )
            if barrier_exit is not None:
                exit_price, exit_reason = barrier_exit
                exit_position = position
                break

            if (
                cfg.break_even_activation_r_multiple is not None
                and not break_even_activated
            ):
                activated = (
                    float(bar["high"]) >= activation_price
                    if cfg.side == "long"
                    else float(bar["low"]) <= activation_price
                )
                if activated:
                    break_even_activated = True
                    activation_position = position
                    active_stop = break_even_price
                    stop_reason = "break_even"

        if cfg.side == "long":
            gross_return = exit_price / entry_price - 1.0
        elif cfg.short_return_convention == "inverse":
            gross_return = entry_price / exit_price - 1.0
        else:
            gross_return = 1.0 - exit_price / entry_price
        rows.append({
            "signal_time": bars[time_column].iloc[signal_position],
            "entry_time": bars[time_column].iloc[entry_position],
            "exit_time": bars[time_column].iloc[exit_position],
            "side": cfg.side,
            "signal_position": signal_position,
            "entry_position": entry_position,
            "exit_position": exit_position,
            "entry_price": entry_price,
            "initial_stop_price": stop_price,
            "take_profit_price": target_price,
            "break_even_price": break_even_price if break_even_activated else np.nan,
            "break_even_activated": break_even_activated,
            "activation_position": activation_position,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "gross_return": gross_return,
            "cost": cfg.costs.round_trip,
            "net_return": gross_return - cfg.costs.round_trip,
        })
        if cfg.overlap == "single_position":
            next_allowed_signal = exit_position

    columns = [
        "signal_time", "entry_time", "exit_time", "side", "signal_position",
        "entry_position", "exit_position", "entry_price", "initial_stop_price",
        "take_profit_price", "break_even_price", "break_even_activated",
        "activation_position", "exit_price", "exit_reason", "gross_return",
        "cost", "net_return",
    ]
    return pd.DataFrame(rows, columns=columns)

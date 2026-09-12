"""Pure strategy signal generation with no exchange or portfolio concerns."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from research.c2_spec import (
    EXTREME_UP_QUANTILE,
    FRESH_LOOKBACK_BARS,
    LOOKBACK,
    MIN_PERIODS,
    RETURN_Z_THRESHOLD,
)


@dataclass(frozen=True)
class C2SignalConfig:
    lookback: int = LOOKBACK
    min_periods: int = MIN_PERIODS
    extreme_quantile: float = EXTREME_UP_QUANTILE
    z_threshold: float = RETURN_Z_THRESHOLD
    fresh_lookback_bars: int = FRESH_LOOKBACK_BARS

    def __post_init__(self) -> None:
        if self.lookback < 2:
            raise ValueError("lookback must be at least 2")
        if not 2 <= self.min_periods <= self.lookback:
            raise ValueError("min_periods must be between 2 and lookback")
        if not 0 < self.extreme_quantile < 1:
            raise ValueError("extreme_quantile must be between 0 and 1")
        if self.fresh_lookback_bars < 1:
            raise ValueError("fresh_lookback_bars must be positive")


def build_c2_signals(
    bars: pd.DataFrame,
    config: C2SignalConfig | None = None,
) -> pd.DataFrame:
    """Build frozen C2 features and raw signals using data available by bar t."""

    cfg = config or C2SignalConfig()
    missing = {"open", "close"}.difference(bars.columns)
    if missing:
        raise ValueError(f"bars missing required columns: {sorted(missing)}")

    frame = pd.DataFrame(index=bars.index)
    frame["ret_5m"] = bars["close"] / bars["open"] - 1.0
    past = frame["ret_5m"].rolling(
        cfg.lookback, min_periods=cfg.min_periods
    )
    frame["ret_std_7d"] = past.std().shift(1)
    frame["ret_q975"] = past.quantile(cfg.extreme_quantile).shift(1)
    frame["return_z"] = frame["ret_5m"] / frame["ret_std_7d"]
    frame["extreme_up"] = (
        frame["ret_5m"] >= frame["ret_q975"]
    ).fillna(False)
    frame["prior_extreme_count"] = (
        frame["extreme_up"].astype(int).shift(1).rolling(
            cfg.fresh_lookback_bars, min_periods=1
        ).sum().fillna(0)
    )
    frame["signal"] = (
        frame["extreme_up"]
        & (frame["return_z"] >= cfg.z_threshold)
        & (frame["prior_extreme_count"] == 0)
    ).fillna(False)
    return frame


def build_trend_short_signal(frame: pd.DataFrame) -> pd.Series:
    """Reproduce the frozen EMA/MACD/ADX/volume short hypothesis."""

    required = {"ema_9", "ema_21", "ema_35", "macd_hist", "adx", "volume_ratio"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"features missing required columns: {sorted(missing)}")
    return (
        (frame["ema_9"] < frame["ema_21"])
        & (frame["ema_21"] < frame["ema_35"])
        & (frame["macd_hist"] < 0)
        & (frame["adx"] >= 25)
        & (frame["volume_ratio"] >= 1.5)
    ).fillna(False)

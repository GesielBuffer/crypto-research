import numpy as np
import pandas as pd


# ============================================================
# EMA
# ============================================================

def add_ema(
    df: pd.DataFrame,
    periods=(9, 21, 35),
) -> pd.DataFrame:

    df = df.copy()

    for period in periods:

        df[f"ema_{period}"] = (
            df["close"]
            .ewm(
                span=period,
                adjust=False,
            )
            .mean()
        )

    return df


# ============================================================
# MACD
# ============================================================

def add_macd(
    df: pd.DataFrame,
    fast=12,
    slow=26,
    signal=9,
) -> pd.DataFrame:

    df = df.copy()

    ema_fast = (
        df["close"]
        .ewm(
            span=fast,
            adjust=False,
        )
        .mean()
    )

    ema_slow = (
        df["close"]
        .ewm(
            span=slow,
            adjust=False,
        )
        .mean()
    )

    df["macd"] = (
        ema_fast - ema_slow
    )

    df["macd_signal"] = (
        df["macd"]
        .ewm(
            span=signal,
            adjust=False,
        )
        .mean()
    )

    df["macd_hist"] = (
        df["macd"]
        - df["macd_signal"]
    )

    return df


# ============================================================
# RSI
# ============================================================

def add_rsi(
    df: pd.DataFrame,
    period=14,
) -> pd.DataFrame:

    df = df.copy()

    delta = df["close"].diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = (
        gain
        .ewm(
            alpha=1 / period,
            adjust=False,
        )
        .mean()
    )

    avg_loss = (
        loss
        .ewm(
            alpha=1 / period,
            adjust=False,
        )
        .mean()
    )

    rs = (
        avg_gain
        / avg_loss.replace(
            0,
            np.nan,
        )
    )

    df["rsi"] = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    return df


# ============================================================
# ATR
# ============================================================

def add_atr(
    df: pd.DataFrame,
    period=14,
) -> pd.DataFrame:

    df = df.copy()

    previous_close = (
        df["close"].shift(1)
    )

    tr1 = (
        df["high"]
        - df["low"]
    )

    tr2 = (
        df["high"]
        - previous_close
    ).abs()

    tr3 = (
        df["low"]
        - previous_close
    ).abs()

    true_range = pd.concat(
        [
            tr1,
            tr2,
            tr3,
        ],
        axis=1,
    ).max(axis=1)

    df["tr"] = true_range

    df["atr"] = (
        true_range
        .ewm(
            alpha=1 / period,
            adjust=False,
        )
        .mean()
    )

    return df


# ============================================================
# ADX
# ============================================================

def add_adx(
    df: pd.DataFrame,
    period=14,
) -> pd.DataFrame:

    df = df.copy()

    high = df["high"]
    low = df["low"]

    previous_high = high.shift(1)
    previous_low = low.shift(1)

    up_move = (
        high - previous_high
    )

    down_move = (
        previous_low - low
    )

    plus_dm = np.where(
        (up_move > down_move)
        & (up_move > 0),
        up_move,
        0,
    )

    minus_dm = np.where(
        (down_move > up_move)
        & (down_move > 0),
        down_move,
        0,
    )

    plus_dm = pd.Series(
        plus_dm,
        index=df.index,
    )

    minus_dm = pd.Series(
        minus_dm,
        index=df.index,
    )

    tr = df["tr"]

    atr = (
        tr
        .ewm(
            alpha=1 / period,
            adjust=False,
        )
        .mean()
    )

    plus_di = (
        100
        * plus_dm
        .ewm(
            alpha=1 / period,
            adjust=False,
        )
        .mean()
        / atr
    )

    minus_di = (
        100
        * minus_dm
        .ewm(
            alpha=1 / period,
            adjust=False,
        )
        .mean()
        / atr
    )

    dx = (
        100
        * (
            (plus_di - minus_di).abs()
            / (
                plus_di + minus_di
            )
        )
    )

    adx = (
        dx
        .ewm(
            alpha=1 / period,
            adjust=False,
        )
        .mean()
    )

    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    df["adx"] = adx

    return df


# ============================================================
# VOLUME
# ============================================================

def add_volume_features(
    df: pd.DataFrame,
    period=20,
) -> pd.DataFrame:

    df = df.copy()

    df["volume_ma"] = (
        df["volume"]
        .rolling(period)
        .mean()
    )

    df["volume_ratio"] = (
        df["volume"]
        / df["volume_ma"]
    )

    return df


# ============================================================
# TODOS
# ============================================================

def add_all_indicators(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    df = add_ema(df)

    df = add_macd(df)

    df = add_rsi(df)

    df = add_atr(df)

    df = add_adx(df)

    df = add_volume_features(df)

    return df
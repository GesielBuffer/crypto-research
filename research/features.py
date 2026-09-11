import numpy as np
import pandas as pd


# ============================================================
# DISTÂNCIA ENTRE EMAs
# ============================================================

def add_ema_distance(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # Distância EMA9 -> EMA21
    df["ema_9_21_distance"] = (
        (df["ema_9"] - df["ema_21"])
        / df["close"]
    )

    # Distância EMA21 -> EMA35
    df["ema_21_35_distance"] = (
        (df["ema_21"] - df["ema_35"])
        / df["close"]
    )

    # Distância EMA9 -> EMA35
    df["ema_9_35_distance"] = (
        (df["ema_9"] - df["ema_35"])
        / df["close"]
    )

    return df


# ============================================================
# ACELERAÇÃO DA TENDÊNCIA
# ============================================================

def add_trend_acceleration(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # Diferença entre EMA9 e EMA21
    trend_distance = (
        df["ema_9"]
        - df["ema_21"]
    )

    # Velocidade da tendência
    df["trend_velocity"] = (
        trend_distance.diff()
    )

    # Aceleração
    df["trend_acceleration"] = (
        df["trend_velocity"].diff()
    )

    return df


# ============================================================
# FORÇA RELATIVA DO VOLUME
# ============================================================

def add_volume_features(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # Mudança do volume relativo
    df["volume_ratio_change"] = (
        df["volume_ratio"].diff()
    )

    # Volume relativo suavizado
    df["volume_ratio_ma"] = (
        df["volume_ratio"]
        .rolling(5)
        .mean()
    )

    return df


# ============================================================
# EXPANSÃO DE VOLATILIDADE
# ============================================================

def add_volatility_features(
    df: pd.DataFrame,
    period=20,
) -> pd.DataFrame:

    df = df.copy()

    # ATR relativo ao preço
    df["atr_percent"] = (
        df["atr"]
        / df["close"]
    )

    # ATR médio
    df["atr_mean"] = (
        df["atr"]
        .rolling(period)
        .mean()
    )

    # Expansão da volatilidade
    df["atr_expansion"] = (
        df["atr"]
        / df["atr_mean"]
    )

    return df


# ============================================================
# PRESSÃO DO CANDLE
# ============================================================

def add_candle_pressure(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    candle_range = (
        df["high"]
        - df["low"]
    )

    candle_range = (
        candle_range.replace(
            0,
            np.nan,
        )
    )

    # Posição do fechamento dentro do candle
    df["close_position"] = (
        (df["close"] - df["low"])
        / candle_range
    )

    # Corpo do candle
    df["body_size"] = (
        (df["close"] - df["open"])
        / df["close"]
    )

    # Tamanho total do candle
    df["range_percent"] = (
        candle_range
        / df["close"]
    )

    return df


# ============================================================
# MOMENTUM
# ============================================================

def add_momentum_features(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # Retorno de curto prazo
    df["return_1"] = (
        df["close"]
        .pct_change(1)
    )

    # Retorno de 3 candles
    df["return_3"] = (
        df["close"]
        .pct_change(3)
    )

    # Retorno de 6 candles
    df["return_6"] = (
        df["close"]
        .pct_change(6)
    )

    # Retorno de 12 candles
    df["return_12"] = (
        df["close"]
        .pct_change(12)
    )

    return df


# ============================================================
# FORÇA DO ADX
# ============================================================

def add_adx_features(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # Diferença entre compradores e vendedores
    df["di_difference"] = (
        df["plus_di"]
        - df["minus_di"]
    )

    # Força direcional normalizada
    di_sum = (
        df["plus_di"]
        + df["minus_di"]
    )

    df["di_strength"] = (
        df["di_difference"]
        / di_sum.replace(
            0,
            np.nan,
        )
    )

    # Aceleração do ADX
    df["adx_change"] = (
        df["adx"].diff()
    )

    return df


# ============================================================
# SCORE DIRECIONAL
# ============================================================

def add_directional_score(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    score = pd.Series(
        0.0,
        index=df.index,
    )

    # Tendência pelas EMAs
    score += np.where(
        df["ema_9"] > df["ema_21"],
        1,
        -1,
    )

    score += np.where(
        df["ema_21"] > df["ema_35"],
        1,
        -1,
    )

    # MACD
    score += np.where(
        df["macd_hist"] > 0,
        1,
        -1,
    )

    # DI
    score += np.where(
        df["plus_di"] > df["minus_di"],
        1,
        -1,
    )

    # RSI
    score += np.where(
        df["rsi"] > 50,
        1,
        -1,
    )

    df["directional_score"] = score

    return df


# ============================================================
# FEATURES PRINCIPAIS
# ============================================================

def add_all_features(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    df = add_ema_distance(df)

    df = add_trend_acceleration(df)

    df = add_volume_features(df)

    df = add_volatility_features(df)

    df = add_candle_pressure(df)

    df = add_momentum_features(df)

    df = add_adx_features(df)

    df = add_directional_score(df)

    return df
from research.binance_data import fetch_klines
from research.indicators import add_all_indicators
from research.features import add_all_features


# ============================================================
# COLETA
# ============================================================

df = fetch_klines(
    "BTCUSDT",
    "5m",
    "2026-01-01",
    "2026-01-02",
)


# ============================================================
# INDICADORES
# ============================================================

df = add_all_indicators(df)


# ============================================================
# FEATURES
# ============================================================

df = add_all_features(df)


# ============================================================
# COLUNAS DE INTERESSE
# ============================================================

columns = [
    "open_time",
    "close",

    # EMAs
    "ema_9",
    "ema_21",
    "ema_35",

    # Distância
    "ema_9_21_distance",
    "ema_21_35_distance",
    "ema_9_35_distance",

    # Tendência
    "trend_velocity",
    "trend_acceleration",

    # MACD
    "macd_hist",

    # RSI
    "rsi",

    # ADX
    "adx",
    "di_difference",
    "di_strength",
    "adx_change",

    # Volume
    "volume_ratio",
    "volume_ratio_change",

    # Volatilidade
    "atr_percent",
    "atr_expansion",

    # Candle
    "close_position",
    "body_size",
    "range_percent",

    # Momentum
    "return_1",
    "return_3",
    "return_6",
    "return_12",

    # Score
    "directional_score",
]


# ============================================================
# RESULTADO
# ============================================================

print()

print("=" * 100)

print(
    "CRYPTO RESEARCH — FEATURES"
)

print("=" * 100)

print()

print(
    df[columns].tail(15)
)

print()

print("=" * 100)

print(
    "TOTAL DE FEATURES:",
    len(columns),
)

print("=" * 100)
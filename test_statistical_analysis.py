from pathlib import Path

import pandas as pd

from research.binance_data import fetch_klines
from research.indicators import add_all_indicators
from research.features import add_all_features
from research.targets import add_future_targets
from research.statistics import analyze_condition


# ============================================================
# CONFIGURAÇÕES DO EXPERIMENTO
# ============================================================

SYMBOL = "BTCUSDT"

INTERVAL = "5m"

START_DATE = "2026-01-01"

END_DATE = "2026-02-01"


# Custo aproximado completo:
# entrada + saída + slippage estimado
#
# 0.0008 = 0.08%
ROUND_TRIP_COST = 0.0008


HORIZONS = [
    1,
    3,
    6,
    12,
]


# ============================================================
# DADOS
# ============================================================

print()

print(
    "Baixando histórico..."
)

df = fetch_klines(
    SYMBOL,
    INTERVAL,
    START_DATE,
    END_DATE,
)


print(
    "Candles:",
    len(df),
)


# ============================================================
# INDICADORES
# ============================================================

df = add_all_indicators(
    df
)


# ============================================================
# FEATURES
# ============================================================

df = add_all_features(
    df
)


# ============================================================
# TARGETS FUTUROS
# ============================================================

df = add_future_targets(
    df,
    HORIZONS,
)


# ============================================================
# CONDIÇÕES BULLISH
# ============================================================

ema_bull = (
    (df["ema_9"] > df["ema_21"])
    &
    (df["ema_21"] > df["ema_35"])
)


macd_bull = (
    df["macd_hist"] > 0
)


di_bull = (
    df["plus_di"]
    > df["minus_di"]
)


adx_strong = (
    df["adx"] >= 25
)


volume_strong = (
    df["volume_ratio"] >= 1.5
)


score_bull = (
    df["directional_score"] >= 4
)


# ============================================================
# CONDIÇÕES BEARISH
# ============================================================

ema_bear = (
    (df["ema_9"] < df["ema_21"])
    &
    (df["ema_21"] < df["ema_35"])
)


macd_bear = (
    df["macd_hist"] < 0
)


di_bear = (
    df["minus_di"]
    > df["plus_di"]
)


score_bear = (
    df["directional_score"] <= -4
)


# ============================================================
# EXPERIMENTOS
# ============================================================

experiments = {

    # --------------------------------------------
    # LONG
    # --------------------------------------------

    "LONG_EMA": (
        ema_bull,
        "LONG",
    ),

    "LONG_EMA_MACD": (
        ema_bull
        & macd_bull,
        "LONG",
    ),

    "LONG_EMA_MACD_ADX": (
        ema_bull
        & macd_bull
        & adx_strong,
        "LONG",
    ),

    "LONG_EMA_MACD_VOLUME": (
        ema_bull
        & macd_bull
        & volume_strong,
        "LONG",
    ),

    "LONG_EMA_MACD_ADX_VOLUME": (
        ema_bull
        & macd_bull
        & adx_strong
        & volume_strong,
        "LONG",
    ),

    "LONG_SCORE_4": (
        score_bull,
        "LONG",
    ),

    "LONG_SCORE_4_ADX_VOLUME": (
        score_bull
        & adx_strong
        & volume_strong,
        "LONG",
    ),

    # --------------------------------------------
    # SHORT
    # --------------------------------------------

    "SHORT_EMA": (
        ema_bear,
        "SHORT",
    ),

    "SHORT_EMA_MACD": (
        ema_bear
        & macd_bear,
        "SHORT",
    ),

    "SHORT_EMA_MACD_ADX": (
        ema_bear
        & macd_bear
        & adx_strong,
        "SHORT",
    ),

    "SHORT_EMA_MACD_VOLUME": (
        ema_bear
        & macd_bear
        & volume_strong,
        "SHORT",
    ),

    "SHORT_EMA_MACD_ADX_VOLUME": (
        ema_bear
        & macd_bear
        & adx_strong
        & volume_strong,
        "SHORT",
    ),

    "SHORT_SCORE_4": (
        score_bear,
        "SHORT",
    ),

    "SHORT_SCORE_4_ADX_VOLUME": (
        score_bear
        & adx_strong
        & volume_strong,
        "SHORT",
    ),
}


# ============================================================
# EXECUTA PESQUISA
# ============================================================

results = []


for name, (
    condition,
    side,
) in experiments.items():

    for horizon in HORIZONS:

        stats = analyze_condition(

            df=df,

            mask=condition,

            side=side,

            horizon=horizon,

            cost=ROUND_TRIP_COST,

        )


        results.append({

            "strategy": name,

            "side": side,

            "horizon": horizon,

            **stats,

        })


# ============================================================
# DATAFRAME
# ============================================================

results_df = pd.DataFrame(
    results
)


# ============================================================
# FORMATAÇÃO
# ============================================================

results_df[
    "win_rate"
] *= 100


for column in [

    "mean_return",
    "median_return",
    "best_trade",
    "worst_trade",

]:

    results_df[column] *= 100


# ============================================================
# ORDENA
# ============================================================

results_df = (
    results_df
    .sort_values(
        [
            "horizon",
            "profit_factor",
        ],
        ascending=[
            True,
            False,
        ],
    )
)


# ============================================================
# RESULTADO
# ============================================================

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    250,
)


print()

print(
    "=" * 160
)

print(
    "CRYPTO RESEARCH — "
    "PRIMEIRO EXPERIMENTO ESTATÍSTICO"
)

print(
    "=" * 160
)

print()


print(
    results_df.to_string(
        index=False
    )
)


# ============================================================
# SALVA
# ============================================================

Path("results").mkdir(
    parents=True,
    exist_ok=True,
)


output_file = (
    "results/"
    "first_statistical_experiment.csv"
)


results_df.to_csv(
    output_file,
    index=False,
)


print()

print(
    "=" * 160
)

print(
    "Resultado salvo em:"
)

print(
    output_file
)

print(
    "=" * 160
)
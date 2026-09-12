from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv

from research.indicators import (
    add_all_indicators,
)

from research.features import (
    add_all_features,
)

from research.targets import (
    add_future_targets,
)

from research.statistics import (
    calculate_profit_factor,
)

from research.validation import (
    non_overlapping_mask,
)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]


PERIODS = [

    (
        "2026-02",
        "2026-02-01",
        "2026-03-01",
    ),

    (
        "2026-03",
        "2026-03-01",
        "2026-04-01",
    ),

    (
        "2026-04",
        "2026-04-01",
        "2026-05-01",
    ),

    (
        "2026-05",
        "2026-05-01",
        "2026-06-01",
    ),

    (
        "2026-06",
        "2026-06-01",
        "2026-07-01",
    ),

    (
        "2026-07",
        "2026-07-01",
        "2026-08-01",
    ),

]


INTERVAL = "5m"

HORIZON = 12


DATA_DIR = Path("data")

RESULTS_DIR = Path("results")

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# BUCKETS FIXOS
#
# Não vamos procurar "o melhor threshold".
# Queremos observar a forma da curva.
# ============================================================

ATR_BINS = [

    0.00,
    0.70,
    0.80,
    0.90,
    1.00,
    1.10,
    1.20,
    1.40,
    np.inf,

]


ATR_LABELS = [

    "<0.70",
    "0.70-0.80",
    "0.80-0.90",
    "0.90-1.00",
    "1.00-1.10",
    "1.10-1.20",
    "1.20-1.40",
    ">1.40",

]


all_events = []


# ============================================================
# LOOP
# ============================================================

for symbol in SYMBOLS:

    print()

    print("=" * 100)

    print(
        f"ATIVO: {symbol}"
    )

    print("=" * 100)


    for (
        period,
        start_date,
        end_date,
    ) in PERIODS:


        filename = (

            f"{symbol}_"
            f"{INTERVAL}_"
            f"{start_date}_"
            f"{end_date}.csv"

        )


        path = (
            DATA_DIR
            / filename
        )


        if not path.exists():

            print(
                f"Arquivo ausente: {path}"
            )

            continue


        # ====================================================
        # CARREGA
        # ====================================================

        df = load_csv(
            path
        )


        # ====================================================
        # INDICADORES
        # ====================================================

        df = add_all_indicators(
            df
        )


        # ====================================================
        # FEATURES
        # ====================================================

        df = add_all_features(
            df
        )


        # ====================================================
        # TARGET
        # ====================================================

        df = add_future_targets(

            df,

            [HORIZON],

        )


        # ====================================================
        # SINAL BASE
        #
        # IMPORTANTE:
        # NÃO usamos ATR aqui.
        #
        # Queremos descobrir o comportamento do ATR
        # dentro do mesmo conjunto de sinais.
        # ====================================================

        base_short = (

            (df["ema_9"] < df["ema_21"])

            &

            (df["ema_21"] < df["ema_35"])

            &

            (df["macd_hist"] < 0)

            &

            (df["adx"] >= 25)

            &

            (df["volume_ratio"] >= 1.5)

        )


        # ====================================================
        # REMOVE SOBREPOSIÇÃO PRIMEIRO
        #
        # Depois classificamos os eventos por ATR.
        #
        # Isso é importante para os buckets formarem
        # grupos do mesmo universo de eventos.
        # ====================================================

        clean_mask = (

            non_overlapping_mask(

                base_short,

                HORIZON,

            )

        )


        events = df.loc[
            clean_mask
        ].copy()


        if events.empty:

            continue


        # ====================================================
        # RETORNO FUTURO SHORT BRUTO
        # ====================================================

        events["future_return"] = (

            events[
                f"future_short_{HORIZON}"
            ]

        )


        # ====================================================
        # BUCKET DE ATR
        # ====================================================

        events["atr_bucket"] = pd.cut(

            events["atr_expansion"],

            bins=ATR_BINS,

            labels=ATR_LABELS,

            right=False,

        )


        events["symbol"] = symbol

        events["period"] = period


        # Mantemos apenas colunas importantes.

        keep = [

            "symbol",
            "period",
            "open_time",

            "atr_expansion",

            "adx",
            "adx_change",

            "volume_ratio",
            "volume_ratio_change",

            "ema_9_21_distance",

            "trend_velocity",
            "trend_acceleration",

            "close_position",

            "atr_bucket",

            "future_return",

        ]


        all_events.append(
            events[keep]
        )


# ============================================================
# CONSOLIDA
# ============================================================

events_df = pd.concat(

    all_events,

    ignore_index=True,

)


events_df = events_df.dropna(

    subset=[
        "atr_expansion",
        "future_return",
    ]

)


# ============================================================
# FUNÇÃO DE RESUMO
# ============================================================

def summarize_group(
    group,
):

    returns = (

        group["future_return"]
        .dropna()

    )


    if returns.empty:

        return pd.Series({

            "samples": 0,

            "mean_return": np.nan,

            "median_return": np.nan,

            "win_rate": np.nan,

            "profit_factor": np.nan,

            "best_trade": np.nan,

            "worst_trade": np.nan,

        })


    return pd.Series({

        "samples":
            len(returns),

        "mean_return":
            returns.mean(),

        "median_return":
            returns.median(),

        "win_rate":
            (returns > 0).mean(),

        "profit_factor":
            calculate_profit_factor(
                returns
            ),

        "best_trade":
            returns.max(),

        "worst_trade":
            returns.min(),

    })


# ============================================================
# CURVA GLOBAL
# ============================================================

curve = (

    events_df

    .groupby(
        "atr_bucket",
        observed=False,
    )

    .apply(
        summarize_group,
        include_groups=False,
    )

    .reset_index()

)


# ============================================================
# RESULTADO POR ATIVO
# ============================================================

curve_asset = (

    events_df

    .groupby(
        [
            "symbol",
            "atr_bucket",
        ],
        observed=False,
    )

    .apply(
        summarize_group,
        include_groups=False,
    )

    .reset_index()

)


# ============================================================
# RESULTADO POR MÊS
# ============================================================

curve_period = (

    events_df

    .groupby(
        [
            "period",
            "atr_bucket",
        ],
        observed=False,
    )

    .apply(
        summarize_group,
        include_groups=False,
    )

    .reset_index()

)


# ============================================================
# CORRELAÇÃO CONTÍNUA
#
# Spearman sem depender do scipy:
# correlação dos ranks.
# ============================================================

valid = events_df[
    [
        "atr_expansion",
        "future_return",
    ]
].dropna()


spearman = (

    valid[
        "atr_expansion"
    ]
    .rank()

    .corr(

        valid[
            "future_return"
        ]
        .rank()

    )

)


pearson = (

    valid[
        "atr_expansion"
    ]

    .corr(

        valid[
            "future_return"
        ]

    )

)


# ============================================================
# DISPLAY
# ============================================================

display = curve.copy()


for column in [

    "mean_return",
    "median_return",
    "win_rate",
    "best_trade",
    "worst_trade",

]:

    display[column] *= 100


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    250,
)


print()

print("=" * 160)

print(
    "EXPERIMENTO 5 — "
    "ATR COMPRESSION CURVE"
)

print(
    "EDGE BRUTO | "
    "SHORT | "
    "60 MIN | "
    "NON OVERLAP"
)

print("=" * 160)

print()


print(
    display.to_string(
        index=False
    )
)


print()

print("=" * 100)

print(
    "CORRELAÇÃO ATR EXPANSION "
    "VS RETORNO FUTURO SHORT"
)

print("=" * 100)

print(
    f"Pearson : {pearson:.6f}"
)

print(
    f"Spearman: {spearman:.6f}"
)


# ============================================================
# JULHO
# ============================================================

july = curve_period[

    curve_period["period"]
    ==
    "2026-07"

].copy()


for column in [
    "mean_return",
    "median_return",
    "win_rate",
    "best_trade",
    "worst_trade",
]:
    july[column] *= 100


print()

print("=" * 160)

print(
    "JULHO 2026 — "
    "CURVA DE ATR"
)

print("=" * 160)

print()


print(
    july.to_string(
        index=False
    )
)


# ============================================================
# SALVA
# ============================================================

events_df.to_csv(

    RESULTS_DIR
    / "atr_curve_events.csv",

    index=False,

)


curve.to_csv(

    RESULTS_DIR
    / "atr_curve_global.csv",

    index=False,

)


curve_asset.to_csv(

    RESULTS_DIR
    / "atr_curve_by_asset.csv",

    index=False,

)


curve_period.to_csv(

    RESULTS_DIR
    / "atr_curve_by_period.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
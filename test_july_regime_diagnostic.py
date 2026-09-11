from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv
from research.indicators import add_all_indicators
from research.features import add_all_features
from research.targets import add_future_targets
from research.statistics import calculate_profit_factor
from research.validation import non_overlapping_mask


# ============================================================
# CONFIG
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
# FEATURES QUE VAMOS COMPARAR
# ============================================================

FEATURES = [

    "atr_expansion",
    "atr_percent",

    "adx",
    "adx_change",

    "di_strength",

    "volume_ratio",
    "volume_ratio_change",

    "ema_9_21_distance",

    "trend_velocity",
    "trend_acceleration",

    "close_position",
    "body_size",
    "range_percent",

    "return_1",
    "return_3",
    "return_6",
    "return_12",

    "macd_hist",
    "rsi",

]


all_events = []


# ============================================================
# CARREGA SÉRIE CONTÍNUA POR ATIVO
# ============================================================

for symbol in SYMBOLS:

    print()

    print("=" * 100)

    print(
        f"PROCESSANDO {symbol}"
    )

    print("=" * 100)


    frames = []


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


        temp = load_csv(
            path
        )


        temp["period"] = period


        frames.append(
            temp
        )


    if not frames:

        continue


    # ========================================================
    # CONCATENA FEV → JUL
    # ========================================================

    df = pd.concat(

        frames,

        ignore_index=True,

    )


    df = (

        df

        .drop_duplicates(
            subset=["open_time"]
        )

        .sort_values(
            "open_time"
        )

        .reset_index(
            drop=True
        )

    )


    # ========================================================
    # INDICADORES NA SÉRIE CONTÍNUA
    # ========================================================

    df = add_all_indicators(
        df
    )


    # ========================================================
    # FEATURES
    # ========================================================

    df = add_all_features(
        df
    )


    # ========================================================
    # TARGET
    # ========================================================

    df = add_future_targets(

        df,

        [HORIZON],

    )


    # ========================================================
    # SINAL BASE
    # ========================================================

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


    # ========================================================
    # NON OVERLAP
    # ========================================================

    clean_mask = (

        non_overlapping_mask(

            base_short,

            HORIZON,

        )

    )


    events = df.loc[
        clean_mask
    ].copy()


    # ========================================================
    # ZONA DE COMPRESSÃO CANDIDATA
    #
    # IMPORTANTE:
    # isto ainda é DESENVOLVIMENTO.
    #
    # Agosto continua intocado.
    # ========================================================

    events = events[

        (events["atr_expansion"] >= 0.80)

        &

        (events["atr_expansion"] < 1.00)

    ].copy()


    if events.empty:

        continue


    # ========================================================
    # RETORNO SHORT
    # ========================================================

    events["future_return"] = (

        events[
            f"future_short_{HORIZON}"
        ]

    )


    # ========================================================
    # GRUPO TEMPORAL
    # ========================================================

    events["regime_group"] = np.where(

        events["period"] == "2026-07",

        "JULY",

        "FEB_JUN",

    )


    events["symbol"] = symbol


    all_events.append(
        events
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
        "future_return",
    ]

)


# ============================================================
# VISÃO GERAL
# ============================================================

def performance_summary(
    group,
):

    returns = (

        group["future_return"]
        .dropna()

    )


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

    })


general = (

    events_df

    .groupby(
        "regime_group"
    )

    .apply(
        performance_summary,
        include_groups=False,
    )

    .reset_index()

)


# ============================================================
# DISTRIBUIÇÃO DAS FEATURES
# ============================================================

feature_rows = []


for feature in FEATURES:

    if feature not in events_df.columns:

        continue


    pre = events_df.loc[

        events_df["regime_group"]
        ==
        "FEB_JUN",

        feature,

    ].dropna()


    july = events_df.loc[

        events_df["regime_group"]
        ==
        "JULY",

        feature,

    ].dropna()


    if len(pre) == 0 or len(july) == 0:

        continue


    pre_q25 = pre.quantile(0.25)

    pre_q75 = pre.quantile(0.75)

    pre_iqr = (
        pre_q75
        - pre_q25
    )


    pre_median = (
        pre.median()
    )


    july_median = (
        july.median()
    )


    delta = (

        july_median
        - pre_median

    )


    robust_shift = (

        delta / pre_iqr

        if pre_iqr != 0

        else np.nan

    )


    feature_rows.append({

        "feature":
            feature,

        "pre_samples":
            len(pre),

        "july_samples":
            len(july),

        "pre_mean":
            pre.mean(),

        "july_mean":
            july.mean(),

        "pre_median":
            pre_median,

        "july_median":
            july_median,

        "delta_median":
            delta,

        "pre_q25":
            pre_q25,

        "pre_q75":
            pre_q75,

        "robust_shift":
            robust_shift,

    })


feature_shift = pd.DataFrame(
    feature_rows
)


feature_shift[
    "abs_robust_shift"
] = (

    feature_shift[
        "robust_shift"
    ].abs()

)


feature_shift = (

    feature_shift

    .sort_values(

        "abs_robust_shift",

        ascending=False,

    )

)


# ============================================================
# ESTADOS DINÂMICOS
# ============================================================

state_masks = {

    "ADX_RISING":

        events_df[
            "adx_change"
        ] > 0,


    "ADX_FALLING":

        events_df[
            "adx_change"
        ] <= 0,


    "SPREAD_WIDENING":

        events_df[
            "trend_velocity"
        ] < 0,


    "SPREAD_NARROWING":

        events_df[
            "trend_velocity"
        ] >= 0,


    "BEAR_ACCELERATION":

        events_df[
            "trend_acceleration"
        ] < 0,


    "BEAR_DECELERATION":

        events_df[
            "trend_acceleration"
        ] >= 0,


    "VOLUME_ACCELERATING":

        events_df[
            "volume_ratio_change"
        ] > 0,


    "VOLUME_DECELERATING":

        events_df[
            "volume_ratio_change"
        ] <= 0,


    "BEAR_CLOSE":

        events_df[
            "close_position"
        ] <= 0.35,


    "MID_CLOSE":

        (
            events_df[
                "close_position"
            ] > 0.35
        )

        &

        (
            events_df[
                "close_position"
            ] < 0.65
        ),


    "BULL_CLOSE":

        events_df[
            "close_position"
        ] >= 0.65,

}


state_rows = []


# ============================================================
# PERFORMANCE POR ESTADO
# ============================================================

for (
    state_name,
    state_mask,
) in state_masks.items():


    for regime_group in [

        "FEB_JUN",
        "JULY",

    ]:


        mask = (

            state_mask

            &

            (
                events_df[
                    "regime_group"
                ]
                ==
                regime_group
            )

        )


        subset = events_df.loc[
            mask
        ]


        returns = (

            subset[
                "future_return"
            ]
            .dropna()

        )


        if len(returns) == 0:

            continue


        state_rows.append({

            "state":
                state_name,

            "regime_group":
                regime_group,

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

        })


state_results = pd.DataFrame(
    state_rows
)


# ============================================================
# JULHO POR ATIVO
# ============================================================

july_asset = (

    events_df[

        events_df[
            "regime_group"
        ]
        ==
        "JULY"

    ]

    .groupby(
        "symbol"
    )

    .apply(
        performance_summary,
        include_groups=False,
    )

    .reset_index()

)


# ============================================================
# FORMAT DISPLAY
# ============================================================

general_display = (
    general.copy()
)


for column in [

    "mean_return",
    "median_return",
    "win_rate",

]:

    general_display[column] *= 100


state_display = (
    state_results.copy()
)


for column in [

    "mean_return",
    "median_return",
    "win_rate",

]:

    state_display[column] *= 100


july_asset_display = (
    july_asset.copy()
)


for column in [

    "mean_return",
    "median_return",
    "win_rate",

]:

    july_asset_display[column] *= 100


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    250,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 150)

print(
    "EXPERIMENTO 6 — "
    "JULY REGIME DIAGNOSTIC"
)

print(
    "ATR 0.80–1.00 | "
    "SHORT | 60 MIN | "
    "CONTINUOUS SERIES"
)

print("=" * 150)

print()


print(
    general_display.to_string(
        index=False
    )
)


print()

print("=" * 150)

print(
    "MAIORES MUDANÇAS DE FEATURES "
    "EM JULHO"
)

print("=" * 150)

print()


print(

    feature_shift[

        [
            "feature",
            "pre_median",
            "july_median",
            "delta_median",
            "robust_shift",
        ]

    ]

    .head(15)

    .to_string(
        index=False
    )

)


print()

print("=" * 150)

print(
    "PERFORMANCE POR ESTADO"
)

print("=" * 150)

print()


print(

    state_display

    .sort_values(

        [
            "state",
            "regime_group",
        ]

    )

    .to_string(
        index=False
    )

)


print()

print("=" * 150)

print(
    "JULHO — POR ATIVO"
)

print("=" * 150)

print()


print(

    july_asset_display.to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

events_df.to_csv(

    RESULTS_DIR
    / "july_regime_events.csv",

    index=False,

)


feature_shift.to_csv(

    RESULTS_DIR
    / "july_feature_shift.csv",

    index=False,

)


state_results.to_csv(

    RESULTS_DIR
    / "july_state_performance.csv",

    index=False,

)


july_asset.to_csv(

    RESULTS_DIR
    / "july_by_asset.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
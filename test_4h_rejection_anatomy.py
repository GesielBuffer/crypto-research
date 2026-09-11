from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv


# ============================================================
# CONFIG
# ============================================================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]


MONTH_STARTS = pd.date_range(
    "2024-01-01",
    "2026-07-01",
    freq="MS",
)


PERIODS = []

for start in MONTH_STARTS:

    end = (
        start
        + pd.offsets.MonthBegin(1)
    )

    PERIODS.append(
        (
            start.strftime("%Y-%m"),
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )
    )


DATA_DIR = Path("data")

RESULTS_DIR = Path("results")

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


HORIZONS = [
    1,
    3,
    6,
    12,
]


COSTS = [
    0.0000,
    0.0002,
    0.0004,
]


MAX_HORIZON = 12


# ============================================================
# LOAD
# ============================================================

def load_symbol(symbol):

    frames = []

    for (
        period,
        start_date,
        end_date,
    ) in PERIODS:

        filename = (
            f"{symbol}_5m_"
            f"{start_date}_"
            f"{end_date}.csv"
        )

        path = (
            DATA_DIR
            / filename
        )

        if not path.exists():
            continue

        temp = load_csv(
            path
        )

        temp["period"] = period

        frames.append(
            temp
        )

    if not frames:
        return None


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


    return df


# ============================================================
# PROFIT FACTOR
# ============================================================

def profit_factor(returns):

    returns = (
        pd.Series(returns)
        .dropna()
    )


    if len(returns) == 0:
        return np.nan


    positive = (
        returns[
            returns > 0
        ]
        .sum()
    )


    negative = (

        returns[
            returns < 0
        ]
        .abs()
        .sum()

    )


    if negative == 0:

        if positive > 0:
            return np.inf

        return np.nan


    return (
        positive
        /
        negative
    )


# ============================================================
# SUMMARY
# ============================================================

def summarize(returns):

    returns = (
        pd.Series(returns)
        .dropna()
    )


    if len(returns) == 0:

        return {

            "samples": 0,

            "mean_return": np.nan,

            "median_return": np.nan,

            "win_rate": np.nan,

            "profit_factor": np.nan,

            "q10": np.nan,

            "q90": np.nan,

        }


    return {

        "samples":
            len(returns),

        "mean_return":
            returns.mean(),

        "median_return":
            returns.median(),

        "win_rate":
            (
                returns > 0
            ).mean(),

        "profit_factor":
            profit_factor(
                returns
            ),

        "q10":
            returns.quantile(
                0.10
            ),

        "q90":
            returns.quantile(
                0.90
            ),

    }


# ============================================================
# EVENT CONTAINER
# ============================================================

event_rows = []


# ============================================================
# LOOP
# ============================================================

for symbol in SYMBOLS:

    print()

    print("=" * 100)

    print(
        f"PROCESSANDO {symbol}"
    )

    print("=" * 100)


    df = load_symbol(
        symbol
    )


    if df is None:
        continue


    # ========================================================
    # ESTRUTURA 4H
    #
    # Candle atual não entra na referência.
    # ========================================================

    df["prior_high_4h"] = (

        df["high"]

        .rolling(48)

        .max()

        .shift(1)

    )


    df["prior_low_4h"] = (

        df["low"]

        .rolling(48)

        .min()

        .shift(1)

    )


    # ========================================================
    # RANGE DA ESTRUTURA
    # ========================================================

    df["prior_range_4h"] = (

        df["prior_high_4h"]
        -
        df["prior_low_4h"]

    )


    # ========================================================
    # REJEIÇÕES
    # ========================================================

    reject_up = (

        (
            df["high"]
            >
            df["prior_high_4h"]
        )

        &

        (
            df["close"]
            <=
            df["prior_high_4h"]
        )

    )


    reject_down = (

        (
            df["low"]
            <
            df["prior_low_4h"]
        )

        &

        (
            df["close"]
            >=
            df["prior_low_4h"]
        )

    )


    events = {

        "REJECT_UP_4H":

            (
                reject_up

                &

                ~reject_up.shift(
                    1,
                    fill_value=False,
                )
            ),


        "REJECT_DOWN_4H":

            (
                reject_down

                &

                ~reject_down.shift(
                    1,
                    fill_value=False,
                )
            ),

    }


    # ========================================================
    # LOOP EVENT TYPE
    # ========================================================

    for event_name, mask in events.items():


        if "UP" in event_name:

            side = "SHORT"

        else:

            side = "LONG"


        positions = np.flatnonzero(
            mask.to_numpy()
        )


        for i in positions:


            # =================================================
            # PRECISAMOS DE 12 CANDLES FUTUROS
            # =================================================

            if (
                i + MAX_HORIZON
                >=
                len(df)
            ):
                continue


            row = df.iloc[i]


            entry_price = float(

                df.iloc[
                    i + 1
                ]["open"]

            )


            if (
                not np.isfinite(
                    entry_price
                )

                or

                entry_price <= 0
            ):
                continue


            prior_range = float(
                row[
                    "prior_range_4h"
                ]
            )


            if (
                not np.isfinite(
                    prior_range
                )

                or

                prior_range <= 0
            ):
                continue


            candle_high = float(
                row["high"]
            )

            candle_low = float(
                row["low"]
            )

            candle_close = float(
                row["close"]
            )


            candle_range = (

                candle_high
                -
                candle_low

            )


            if candle_range <= 0:
                continue


            # =================================================
            # REJECTION ANATOMY
            # =================================================

            if side == "SHORT":

                level = float(
                    row[
                        "prior_high_4h"
                    ]
                )


                penetration_abs = (

                    candle_high
                    -
                    level

                )


                rejection_abs = (

                    candle_high
                    -
                    candle_close

                )


                # Quanto do candle é wick/rejeição superior
                rejection_wick_ratio = (

                    rejection_abs
                    /
                    candle_range

                )


            else:

                level = float(
                    row[
                        "prior_low_4h"
                    ]
                )


                penetration_abs = (

                    level
                    -
                    candle_low

                )


                rejection_abs = (

                    candle_close
                    -
                    candle_low

                )


                # Quanto do candle é wick/rejeição inferior
                rejection_wick_ratio = (

                    rejection_abs
                    /
                    candle_range

                )


            # =================================================
            # NORMALIZAÇÃO PELA ESTRUTURA 4H
            # =================================================

            penetration_norm = (

                penetration_abs
                /
                prior_range

            )


            rejection_norm = (

                rejection_abs
                /
                prior_range

            )


            # =================================================
            # CLOSE POSITION
            #
            # 0 = fundo do candle
            # 1 = topo do candle
            # =================================================

            close_position = (

                (
                    candle_close
                    -
                    candle_low
                )

                /
                candle_range

            )


            # =================================================
            # FORWARD WINDOW
            # =================================================

            future = df.iloc[

                i + 1
                :
                i + MAX_HORIZON + 1

            ].copy()


            highs = (

                future["high"]

                .astype(float)

                .to_numpy()

            )


            lows = (

                future["low"]

                .astype(float)

                .to_numpy()

            )


            # =================================================
            # MFE / MAE
            #
            # Usamos excursão de preço relativa à entrada.
            # =================================================

            if side == "LONG":


                favorable = (

                    highs
                    /
                    entry_price
                    -
                    1

                )


                adverse = (

                    entry_price
                    -
                    lows

                ) / entry_price


            else:


                favorable = (

                    entry_price
                    -
                    lows

                ) / entry_price


                adverse = (

                    highs
                    -
                    entry_price

                ) / entry_price


            mfe_index = int(
                np.argmax(
                    favorable
                )
            )


            mae_index = int(
                np.argmax(
                    adverse
                )
            )


            mfe = float(
                favorable[
                    mfe_index
                ]
            )


            mae = float(
                adverse[
                    mae_index
                ]
            )


            event = {

                "symbol":
                    symbol,

                "period":
                    row["period"],

                "year":
                    str(
                        row["period"]
                    )[:4],

                "open_time":
                    row["open_time"],

                "event":
                    event_name,

                "side":
                    side,

                "entry_price":
                    entry_price,

                "penetration_norm":
                    penetration_norm,

                "rejection_norm":
                    rejection_norm,

                "rejection_wick_ratio":
                    rejection_wick_ratio,

                "close_position":
                    close_position,

                "mfe":
                    mfe,

                "mae":
                    mae,

                "time_to_mfe":
                    mfe_index + 1,

                "time_to_mae":
                    mae_index + 1,

            }


            # =================================================
            # FORWARD RETURNS
            # =================================================

            for horizon in HORIZONS:


                exit_price = float(

                    df.iloc[
                        i + horizon
                    ]["close"]

                )


                if side == "LONG":

                    future_return = (

                        exit_price
                        /
                        entry_price
                        -
                        1

                    )


                else:

                    future_return = (

                        entry_price
                        /
                        exit_price
                        -
                        1

                    )


                event[
                    f"return_{horizon}"
                ] = future_return


            event_rows.append(
                event
            )


# ============================================================
# EVENTS
# ============================================================

events_df = pd.DataFrame(
    event_rows
)


print()

print(
    f"Eventos únicos: "
    f"{len(events_df)}"
)


# ============================================================
# FORWARD PATH
# ============================================================

path_rows = []


for event_name in sorted(

    events_df[
        "event"
    ].unique()

):


    subset_event = events_df[

        events_df[
            "event"
        ]
        ==
        event_name

    ]


    for horizon in HORIZONS:


        returns = subset_event[
            f"return_{horizon}"
        ]


        stats = summarize(
            returns
        )


        path_rows.append({

            "event":
                event_name,

            "horizon":
                horizon,

            "minutes":
                horizon * 5,

            **stats,

        })


path_df = pd.DataFrame(
    path_rows
)


# ============================================================
# EXCURSION SUMMARY
# ============================================================

excursion_rows = []


for event_name, group in events_df.groupby(
    "event"
):


    excursion_rows.append({

        "event":
            event_name,

        "samples":
            len(group),

        "mean_mfe":
            group[
                "mfe"
            ].mean(),

        "median_mfe":
            group[
                "mfe"
            ].median(),

        "mean_mae":
            group[
                "mae"
            ].mean(),

        "median_mae":
            group[
                "mae"
            ].median(),

        "median_time_to_mfe":
            group[
                "time_to_mfe"
            ].median(),

        "median_time_to_mae":
            group[
                "time_to_mae"
            ].median(),

        "mfe_gt_020_rate":

            (
                group[
                    "mfe"
                ]
                >=
                0.002
            ).mean(),

        "mfe_gt_040_rate":

            (
                group[
                    "mfe"
                ]
                >=
                0.004
            ).mean(),

        "mae_gt_020_rate":

            (
                group[
                    "mae"
                ]
                >=
                0.002
            ).mean(),

        "mae_gt_040_rate":

            (
                group[
                    "mae"
                ]
                >=
                0.004
            ).mean(),

    })


excursion_df = pd.DataFrame(
    excursion_rows
)


# ============================================================
# QUARTIS
#
# DIAGNÓSTICO APENAS.
#
# Não reutilizar thresholds automaticamente
# no holdout.
# ============================================================

for feature in [

    "penetration_norm",
    "rejection_norm",
    "rejection_wick_ratio",

]:


    events_df[

        f"{feature}_quartile"

    ] = pd.qcut(

        events_df[
            feature
        ],

        q=4,

        labels=[
            "Q1",
            "Q2",
            "Q3",
            "Q4",
        ],

        duplicates="drop",

    )


# ============================================================
# BUCKET ANALYSIS
# ============================================================

bucket_rows = []


BUCKET_FEATURES = [

    "penetration_norm",
    "rejection_norm",
    "rejection_wick_ratio",

]


for feature in BUCKET_FEATURES:


    bucket_column = (
        f"{feature}_quartile"
    )


    for event_name in sorted(

        events_df[
            "event"
        ].unique()

    ):


        for bucket in [

            "Q1",
            "Q2",
            "Q3",
            "Q4",

        ]:


            subset = events_df[

                (
                    events_df[
                        "event"
                    ]
                    ==
                    event_name
                )

                &

                (
                    events_df[
                        bucket_column
                    ]
                    ==
                    bucket
                )

            ]


            if subset.empty:
                continue


            gross = subset[
                "return_12"
            ]


            for cost in COSTS:


                net = (
                    gross
                    -
                    cost
                )


                stats = summarize(
                    net
                )


                bucket_rows.append({

                    "feature":
                        feature,

                    "event":
                        event_name,

                    "bucket":
                        bucket,

                    "cost":
                        cost,

                    "feature_min":
                        subset[
                            feature
                        ].min(),

                    "feature_median":
                        subset[
                            feature
                        ].median(),

                    "feature_max":
                        subset[
                            feature
                        ].max(),

                    **stats,

                })


bucket_df = pd.DataFrame(
    bucket_rows
)


# ============================================================
# YEAR × QUARTILE
#
# Só custo zero para avaliar estabilidade.
# ============================================================

year_bucket_rows = []


for feature in BUCKET_FEATURES:


    bucket_column = (
        f"{feature}_quartile"
    )


    for (
        year,
        event_name,
        bucket,
    ), group in events_df.groupby(

        [
            "year",
            "event",
            bucket_column,
        ],

        observed=True,

    ):


        stats = summarize(

            group[
                "return_12"
            ]

        )


        year_bucket_rows.append({

            "feature":
                feature,

            "year":
                year,

            "event":
                event_name,

            "bucket":
                str(bucket),

            **stats,

        })


year_bucket_df = pd.DataFrame(
    year_bucket_rows
)


# ============================================================
# WINNERS VS LOSERS
# ============================================================

events_df[
    "winner_60m"
] = (

    events_df[
        "return_12"
    ]
    >
    0

)


winner_loser_rows = []


for (
    event_name,
    winner,
), group in events_df.groupby(

    [
        "event",
        "winner_60m",
    ]

):


    winner_loser_rows.append({

        "event":
            event_name,

        "winner":
            winner,

        "samples":
            len(group),

        "penetration_median":
            group[
                "penetration_norm"
            ].median(),

        "rejection_norm_median":
            group[
                "rejection_norm"
            ].median(),

        "wick_ratio_median":
            group[
                "rejection_wick_ratio"
            ].median(),

        "mfe_median":
            group[
                "mfe"
            ].median(),

        "mae_median":
            group[
                "mae"
            ].median(),

        "time_to_mfe_median":
            group[
                "time_to_mfe"
            ].median(),

        "time_to_mae_median":
            group[
                "time_to_mae"
            ].median(),

    })


winner_loser_df = pd.DataFrame(
    winner_loser_rows
)


# ============================================================
# DISPLAY HELPERS
# ============================================================

def percent_display(
    df,
    columns,
):

    output = df.copy()

    for column in columns:

        if column in output.columns:

            output[
                column
            ] *= 100

    return output


path_display = percent_display(

    path_df,

    [
        "mean_return",
        "median_return",
        "win_rate",
        "q10",
        "q90",
    ],

)


excursion_display = percent_display(

    excursion_df,

    [
        "mean_mfe",
        "median_mfe",
        "mean_mae",
        "median_mae",
        "mfe_gt_020_rate",
        "mfe_gt_040_rate",
        "mae_gt_020_rate",
        "mae_gt_040_rate",
    ],

)


bucket_display = percent_display(

    bucket_df,

    [
        "cost",
        "mean_return",
        "median_return",
        "win_rate",
        "q10",
        "q90",
    ],

)


year_bucket_display = percent_display(

    year_bucket_df,

    [
        "mean_return",
        "median_return",
        "win_rate",
        "q10",
        "q90",
    ],

)


winner_loser_display = percent_display(

    winner_loser_df,

    [
        "penetration_median",
        "rejection_norm_median",
        "wick_ratio_median",
        "mfe_median",
        "mae_median",
    ],

)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    300,
)


# ============================================================
# OUTPUT 1
# ============================================================

print()

print("=" * 190)

print(
    "EXPERIMENTO 16 — "
    "4H REJECTION ANATOMY"
)

print("=" * 190)

print()


print(
    path_display.to_string(
        index=False
    )
)


# ============================================================
# OUTPUT 2
# ============================================================

print()

print("=" * 190)

print(
    "MFE / MAE"
)

print("=" * 190)

print()


print(

    excursion_display

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 3
# ============================================================

print()

print("=" * 190)

print(
    "INTENSIDADE DA REJEIÇÃO — "
    "QUARTIS"
)

print("=" * 190)

print()


print(

    bucket_display

    .sort_values(

        [
            "feature",
            "event",
            "cost",
            "bucket",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 4
# ============================================================

print()

print("=" * 190)

print(
    "QUARTIS × ANO — "
    "RETORNO BRUTO 60 MIN"
)

print("=" * 190)

print()


print(

    year_bucket_display

    .sort_values(

        [
            "feature",
            "event",
            "bucket",
            "year",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 5
# ============================================================

print()

print("=" * 190)

print(
    "WINNERS VS LOSERS — "
    "ANATOMIA"
)

print("=" * 190)

print()


print(

    winner_loser_display

    .sort_values(

        [
            "event",
            "winner",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
#
# Agora salvamos UM evento por linha.
# Não multiplicamos por custos/horizontes.
# ============================================================

events_df.to_csv(

    RESULTS_DIR
    / "rejection_4h_anatomy_events.csv",

    index=False,

)


path_df.to_csv(

    RESULTS_DIR
    / "rejection_4h_forward_path.csv",

    index=False,

)


excursion_df.to_csv(

    RESULTS_DIR
    / "rejection_4h_excursion.csv",

    index=False,

)


bucket_df.to_csv(

    RESULTS_DIR
    / "rejection_4h_buckets.csv",

    index=False,

)


year_bucket_df.to_csv(

    RESULTS_DIR
    / "rejection_4h_buckets_by_year.csv",

    index=False,

)


winner_loser_df.to_csv(

    RESULTS_DIR
    / "rejection_4h_winner_loser.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
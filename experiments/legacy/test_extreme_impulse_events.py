from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv
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


DATA_DIR = Path("data")
RESULTS_DIR = Path("results")

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


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


# ============================================================
# EVENT DEFINITION
#
# 7 dias * 288 candles de 5m
# ============================================================

LOOKBACK = (
    288 * 7
)

MIN_PERIODS = (
    288 * 3
)


LOW_QUANTILE = 0.025
HIGH_QUANTILE = 0.975


HORIZONS = [
    1,   # 5m
    3,   # 15m
    6,   # 30m
    12,  # 60m
]


MAX_HORIZON = max(
    HORIZONS
)


COSTS = [
    0.0000,
    0.0002,
    0.0004,
]


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

        path = (

            DATA_DIR

            /

            (
                f"{symbol}_5m_"
                f"{start_date}_"
                f"{end_date}.csv"
            )

        )

        if not path.exists():
            continue


        temp = load_csv(
            path
        )

        temp["period"] = (
            period
        )

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

        pd.Series(
            returns
        )

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

        pd.Series(
            returns
        )

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

event_frames = []


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
    # RETORNO DO CANDLE
    # ========================================================

    df["ret_5m"] = (

        df["close"]
        /
        df["open"]
        -
        1

    )


    # ========================================================
    # RETURN VOLATILITY
    #
    # Tudo shift(1).
    # Apenas passado.
    # ========================================================

    df["ret_std_7d"] = (

        df["ret_5m"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .std()

        .shift(1)

    )


    # ========================================================
    # QUANTIS ADAPTATIVOS
    # ========================================================

    df["ret_q025"] = (

        df["ret_5m"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            LOW_QUANTILE
        )

        .shift(1)

    )


    df["ret_q975"] = (

        df["ret_5m"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            HIGH_QUANTILE
        )

        .shift(1)

    )


    # ========================================================
    # RETURN Z-SCORE
    # ========================================================

    df["return_z"] = (

        df["ret_5m"]
        /
        df["ret_std_7d"]

    )


    # ========================================================
    # RANGE
    # ========================================================

    df["range_percent"] = (

        df["high"]
        -
        df["low"]

    ) / df["open"]


    df["range_median_7d"] = (

        df["range_percent"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .median()

        .shift(1)

    )


    df["range_ratio"] = (

        df["range_percent"]
        /
        df["range_median_7d"]

    )


    # ========================================================
    # VOLUME
    # ========================================================

    df["volume_median_7d"] = (

        df["volume"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .median()

        .shift(1)

    )


    df["volume_ratio_7d"] = (

        df["volume"]
        /
        df["volume_median_7d"]

    )


    # ========================================================
    # CLOSE POSITION
    # ========================================================

    candle_range = (

        df["high"]
        -
        df["low"]

    )


    df["close_position"] = (

        (
            df["close"]
            -
            df["low"]
        )

        /
        candle_range.replace(
            0,
            np.nan,
        )

    )


    # ========================================================
    # EXTREME EVENTS
    # ========================================================

    extreme_down = (

        df["ret_5m"]
        <=
        df["ret_q025"]

    )


    extreme_up = (

        df["ret_5m"]
        >=
        df["ret_q975"]

    )


    # ========================================================
    # NON-OVERLAP
    #
    # Um evento bloqueia novos eventos
    # da mesma direção por 60 minutos.
    # ========================================================

    extreme_down = (

        non_overlapping_mask(

            extreme_down.fillna(False),

            MAX_HORIZON,

        )

    )


    extreme_up = (

        non_overlapping_mask(

            extreme_up.fillna(False),

            MAX_HORIZON,

        )

    )


    # ========================================================
    # ENTRY
    # ========================================================

    entry = (

        df["open"]
        .shift(-1)

    )


    # ========================================================
    # FUTURE RETURNS
    # ========================================================

    for horizon in HORIZONS:


        future_close = (

            df["close"]
            .shift(-horizon)

        )


        df[
            f"future_long_{horizon}"
        ] = (

            future_close
            /
            entry
            -
            1

        )


        df[
            f"future_short_{horizon}"
        ] = (

            entry
            /
            future_close
            -
            1

        )


    # ========================================================
    # SAVE UNIQUE EVENTS
    # ========================================================

    for (
        event_name,
        mask,
    ) in [

        (
            "EXTREME_DOWN",
            extreme_down,
        ),

        (
            "EXTREME_UP",
            extreme_up,
        ),

    ]:


        temp = df.loc[
            mask
        ].copy()


        temp = temp.dropna(

            subset=[

                "return_z",
                "range_ratio",
                "volume_ratio_7d",

                f"future_long_{MAX_HORIZON}",
                f"future_short_{MAX_HORIZON}",

            ]

        )


        if temp.empty:
            continue


        temp[
            "event"
        ] = event_name


        temp[
            "symbol"
        ] = symbol


        temp[
            "year"
        ] = (

            temp[
                "period"
            ]
            .astype(str)
            .str[:4]

        )


        columns = [

            "symbol",
            "period",
            "year",
            "open_time",

            "event",

            "ret_5m",
            "return_z",

            "range_ratio",
            "volume_ratio_7d",

            "close_position",

        ]


        for horizon in HORIZONS:

            columns.extend(

                [

                    f"future_long_{horizon}",
                    f"future_short_{horizon}",

                ]

            )


        event_frames.append(
            temp[columns]
        )


# ============================================================
# EVENTS
# ============================================================

events = pd.concat(

    event_frames,

    ignore_index=True,

)


print()

print(
    f"Eventos extremos únicos: "
    f"{len(events)}"
)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    # ========================================================
    # DOWN IMPULSE
    # ========================================================

    "DOWN_CONTINUATION_SHORT": {

        "event":
            "EXTREME_DOWN",

        "side":
            "SHORT",

    },


    "DOWN_REVERSAL_LONG": {

        "event":
            "EXTREME_DOWN",

        "side":
            "LONG",

    },


    # ========================================================
    # UP IMPULSE
    # ========================================================

    "UP_CONTINUATION_LONG": {

        "event":
            "EXTREME_UP",

        "side":
            "LONG",

    },


    "UP_REVERSAL_SHORT": {

        "event":
            "EXTREME_UP",

        "side":
            "SHORT",

    },

}


# ============================================================
# SUMMARY GLOBAL
# ============================================================

summary_rows = []


for (
    hypothesis,
    config,
) in HYPOTHESES.items():


    subset = events[

        events[
            "event"
        ]
        ==
        config[
            "event"
        ]

    ]


    side = config[
        "side"
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            gross = subset[
                f"future_long_{horizon}"
            ]

        else:

            gross = subset[
                f"future_short_{horizon}"
            ]


        for cost in COSTS:


            net = (

                gross
                -
                cost

            )


            summary_rows.append({

                "hypothesis":
                    hypothesis,

                "event":
                    config["event"],

                "side":
                    side,

                "horizon":
                    horizon,

                "minutes":
                    horizon * 5,

                "cost":
                    cost,

                **summarize(net),

            })


summary = pd.DataFrame(
    summary_rows
)


# ============================================================
# 60 MIN — BY YEAR
# ============================================================

year_rows = []


for (
    hypothesis,
    config,
) in HYPOTHESES.items():


    subset = events[

        events[
            "event"
        ]
        ==
        config[
            "event"
        ]

    ]


    side = config[
        "side"
    ]


    for year, group in subset.groupby(
        "year"
    ):


        if side == "LONG":

            gross = group[
                "future_long_12"
            ]

        else:

            gross = group[
                "future_short_12"
            ]


        for cost in COSTS:


            year_rows.append({

                "year":
                    year,

                "hypothesis":
                    hypothesis,

                "side":
                    side,

                "cost":
                    cost,

                **summarize(
                    gross - cost
                ),

            })


year_summary = pd.DataFrame(
    year_rows
)


# ============================================================
# 60 MIN — BY ASSET
# ============================================================

asset_rows = []


for (
    hypothesis,
    config,
) in HYPOTHESES.items():


    subset = events[

        events[
            "event"
        ]
        ==
        config[
            "event"
        ]

    ]


    side = config[
        "side"
    ]


    for symbol, group in subset.groupby(
        "symbol"
    ):


        if side == "LONG":

            gross = group[
                "future_long_12"
            ]

        else:

            gross = group[
                "future_short_12"
            ]


        for cost in COSTS:


            asset_rows.append({

                "symbol":
                    symbol,

                "hypothesis":
                    hypothesis,

                "side":
                    side,

                "cost":
                    cost,

                **summarize(
                    gross - cost
                ),

            })


asset_summary = pd.DataFrame(
    asset_rows
)


# ============================================================
# EVENT FEATURE DISTRIBUTION
#
# Ainda sem filtros.
# ============================================================

feature_rows = []


for event_name, group in events.groupby(
    "event"
):


    feature_rows.append({

        "event":
            event_name,

        "samples":
            len(group),

        "return_z_median":
            group[
                "return_z"
            ].median(),

        "return_z_q10":
            group[
                "return_z"
            ].quantile(
                0.10
            ),

        "return_z_q90":
            group[
                "return_z"
            ].quantile(
                0.90
            ),

        "range_ratio_median":
            group[
                "range_ratio"
            ].median(),

        "volume_ratio_median":
            group[
                "volume_ratio_7d"
            ].median(),

        "close_position_median":
            group[
                "close_position"
            ].median(),

    })


feature_summary = pd.DataFrame(
    feature_rows
)


# ============================================================
# DISPLAY
# ============================================================

def percent_display(df):

    output = df.copy()


    for column in [

        "cost",
        "mean_return",
        "median_return",
        "win_rate",
        "q10",
        "q90",

    ]:

        if column in output.columns:

            output[
                column
            ] *= 100


    return output


summary_display = percent_display(
    summary
)


year_display = percent_display(
    year_summary
)


asset_display = percent_display(
    asset_summary
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    280,
)


# ============================================================
# OUTPUT 1
# ============================================================

print()

print("=" * 200)

print(
    "EXPERIMENTO 18 — "
    "EXTREME IMPULSE EVENT STUDY"
)

print("=" * 200)

print()


print(

    summary_display

    .sort_values(

        [
            "hypothesis",
            "cost",
            "horizon",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 2
# ============================================================

print()

print("=" * 200)

print(
    "60 MIN — RESULTADO POR ANO"
)

print("=" * 200)

print()


print(

    year_display

    .sort_values(

        [
            "hypothesis",
            "cost",
            "year",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 3
# ============================================================

print()

print("=" * 200)

print(
    "60 MIN — RESULTADO POR ATIVO"
)

print("=" * 200)

print()


print(

    asset_display

    .sort_values(

        [
            "hypothesis",
            "cost",
            "symbol",
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

print("=" * 200)

print(
    "ANATOMIA DOS EVENTOS EXTREMOS"
)

print("=" * 200)

print()


print(

    feature_summary

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

events.to_csv(

    RESULTS_DIR
    / "extreme_impulse_events.csv",

    index=False,

)


summary.to_csv(

    RESULTS_DIR
    / "extreme_impulse_summary.csv",

    index=False,

)


year_summary.to_csv(

    RESULTS_DIR
    / "extreme_impulse_by_year.csv",

    index=False,

)


asset_summary.to_csv(

    RESULTS_DIR
    / "extreme_impulse_by_asset.csv",

    index=False,

)


feature_summary.to_csv(

    RESULTS_DIR
    / "extreme_impulse_features.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
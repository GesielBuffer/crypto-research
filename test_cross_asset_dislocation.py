from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv


# ============================================================
# EXPERIMENTO 27
# BRANCH 04 — CROSS-ASSET DISLOCATION
#
# DEVELOPMENT:
# 2024-01 -> 2026-07
#
# NÃO USAR:
# agosto/2026
# setembro/2026
#
# Setembro fica reservado para futuro holdout.
# ============================================================


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


# ============================================================
# DEVELOPMENT PERIOD
# ============================================================

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
# ============================================================

BARS_PER_DAY = 288

LOOKBACK = (
    7
    *
    BARS_PER_DAY
)

MIN_PERIODS = (
    3
    *
    BARS_PER_DAY
)


LOW_QUANTILE = 0.01

HIGH_QUANTILE = 0.99


# ============================================================
# FUTURE WINDOWS
# ============================================================

HORIZONS = [
    1,   # 5 min
    3,   # 15 min
    6,   # 30 min
    12,  # 60 min
]


BAR_MINUTES = 5


# ============================================================
# COST MODEL
# ============================================================

COSTS = [
    0.0000,
    0.0004,
    0.0006,
]


# ============================================================
# LOAD SYMBOL
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

            raise FileNotFoundError(
                f"Arquivo não encontrado: {path}"
            )


        temp = load_csv(
            path
        )


        temp["period"] = period


        temp["open_time"] = pd.to_datetime(
            temp["open_time"],
            utc=True,
        )


        for column in [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]:

            temp[column] = pd.to_numeric(
                temp[column],
                errors="coerce",
            )


        frames.append(
            temp
        )


    df = pd.concat(
        frames,
        ignore_index=True,
    )


    df = (
        df

        .dropna(
            subset=[
                "open_time",
                "open",
                "close",
            ]
        )

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

    values = (
        pd.Series(returns)
        .dropna()
    )


    if len(values) == 0:
        return np.nan


    gains = (
        values[
            values > 0
        ]
        .sum()
    )


    losses = (
        values[
            values < 0
        ]
        .abs()
        .sum()
    )


    if losses == 0:

        if gains > 0:
            return np.inf

        return np.nan


    return (
        gains
        /
        losses
    )


# ============================================================
# TRIMMED MEAN
# ============================================================

def trimmed_mean(
    returns,
    trim=0.05,
):

    values = np.asarray(
        pd.Series(returns)
        .dropna(),
        dtype=float,
    )


    if len(values) == 0:
        return np.nan


    values = np.sort(
        values
    )


    cut = int(
        len(values)
        *
        trim
    )


    if (
        cut == 0
        or
        len(values)
        <=
        2 * cut
    ):

        return values.mean()


    return (
        values[
            cut:-cut
        ]
        .mean()
    )


# ============================================================
# WINSORIZED MEAN
# ============================================================

def winsorized_mean(
    returns,
    limit=0.05,
):

    values = np.asarray(
        pd.Series(returns)
        .dropna(),
        dtype=float,
    )


    if len(values) == 0:
        return np.nan


    low = np.quantile(
        values,
        limit,
    )


    high = np.quantile(
        values,
        1 - limit,
    )


    return (
        np.clip(
            values,
            low,
            high,
        )
        .mean()
    )


# ============================================================
# SUMMARY
# ============================================================

def summarize(returns):

    values = (
        pd.Series(returns)
        .dropna()
    )


    if len(values) == 0:

        return {
            "samples": 0,
            "mean_return": np.nan,
            "median_return": np.nan,
            "trimmed_mean_5": np.nan,
            "winsorized_mean_5": np.nan,
            "win_rate": np.nan,
            "profit_factor": np.nan,
            "q10": np.nan,
            "q90": np.nan,
        }


    return {

        "samples":
            len(values),

        "mean_return":
            values.mean(),

        "median_return":
            values.median(),

        "trimmed_mean_5":
            trimmed_mean(
                values
            ),

        "winsorized_mean_5":
            winsorized_mean(
                values
            ),

        "win_rate":
            (
                values > 0
            ).mean(),

        "profit_factor":
            profit_factor(
                values
            ),

        "q10":
            values.quantile(
                0.10
            ),

        "q90":
            values.quantile(
                0.90
            ),

    }


# ============================================================
# LOAD ALL SYMBOLS
# ============================================================

raw = {}


for symbol in SYMBOLS:

    print(
        f"Carregando {symbol}..."
    )

    raw[symbol] = load_symbol(
        symbol
    )


# ============================================================
# BUILD ALIGNED MARKET FRAME
#
# Apenas timestamps presentes nos quatro ativos.
# ============================================================

aligned = None


for symbol in SYMBOLS:


    temp = (
        raw[symbol][
            [
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "period",
            ]
        ]
        .copy()
    )


    rename = {

        "open":
            f"open_{symbol}",

        "high":
            f"high_{symbol}",

        "low":
            f"low_{symbol}",

        "close":
            f"close_{symbol}",

        "period":
            f"period_{symbol}",
    }


    temp = temp.rename(
        columns=rename
    )


    if aligned is None:

        aligned = temp

    else:

        aligned = aligned.merge(
            temp,
            on="open_time",
            how="inner",
        )


aligned = (
    aligned

    .sort_values(
        "open_time"
    )

    .reset_index(
        drop=True
    )
)


# ============================================================
# PERIOD / YEAR
# ============================================================

aligned["period"] = (
    aligned[
        "open_time"
    ]
    .dt.strftime(
        "%Y-%m"
    )
)


aligned["year"] = (
    aligned[
        "open_time"
    ]
    .dt.strftime(
        "%Y"
    )
)


print()

print(
    f"Candles alinhados: "
    f"{len(aligned)}"
)


# ============================================================
# CURRENT RETURNS
# ============================================================

for symbol in SYMBOLS:


    aligned[
        f"ret_{symbol}"
    ] = (

        aligned[
            f"close_{symbol}"
        ]

        /

        aligned[
            f"open_{symbol}"
        ]

        -

        1

    )


# ============================================================
# FUTURE RETURNS
#
# IMPORTANT:
#
# LONG futures PnL:
# exit / entry - 1
#
# SHORT linear futures PnL:
# (entry - exit) / entry
# = 1 - exit / entry
#
# ============================================================

for symbol in SYMBOLS:


    entry = (
        aligned[
            f"open_{symbol}"
        ]
        .shift(-1)
    )


    for horizon in HORIZONS:


        exit_price = (
            aligned[
                f"close_{symbol}"
            ]
            .shift(
                -horizon
            )
        )


        aligned[
            f"future_long_{symbol}_{horizon}"
        ] = (

            exit_price
            /
            entry
            -
            1

        )


        aligned[
            f"future_short_{symbol}_{horizon}"
        ] = (

            1
            -
            exit_price
            /
            entry

        )


# ============================================================
# BUILD CROSS-ASSET EVENTS
# ============================================================

event_frames = []


for symbol in SYMBOLS:


    print()

    print(
        "=" * 100
    )

    print(
        f"PROCESSANDO DISLOCATION — {symbol}"
    )

    print(
        "=" * 100
    )


    others = [
        other
        for other in SYMBOLS
        if other != symbol
    ]


    # ========================================================
    # MARKET RETURN
    #
    # Mediana dos OUTROS 3 ativos.
    # O próprio ativo não participa.
    # ========================================================

    other_return_columns = [
        f"ret_{other}"
        for other in others
    ]


    market_return = (
        aligned[
            other_return_columns
        ]
        .median(
            axis=1
        )
    )


    # ========================================================
    # RESIDUAL RETURN
    # ========================================================

    residual = (

        aligned[
            f"ret_{symbol}"
        ]

        -

        market_return

    )


    # ========================================================
    # HISTORICAL RESIDUAL VOLATILITY
    # ========================================================

    residual_std = (
        residual

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .std()

        .shift(1)
    )


    # ========================================================
    # ADAPTIVE 1% / 99% QUANTILES
    # ========================================================

    residual_q01 = (
        residual

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            LOW_QUANTILE
        )

        .shift(1)
    )


    residual_q99 = (
        residual

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
    # RESIDUAL Z
    #
    # Apenas métrica de anatomia.
    # NÃO define o evento.
    # ========================================================

    residual_z = (
        residual
        /
        residual_std
    )


    # ========================================================
    # RAW TAIL STATES
    # ========================================================

    positive_tail = (
        residual
        >=
        residual_q99
    ).fillna(False)


    negative_tail = (
        residual
        <=
        residual_q01
    ).fillna(False)


    # ========================================================
    # FIRST CROSSING
    #
    # Evita contar cada candle consecutivo
    # de um mesmo tail state como novo evento.
    #
    # NÃO usa cooldown arbitrário.
    # ========================================================

    positive_event = (

        positive_tail

        &

        ~positive_tail
        .shift(1)
        .fillna(False)

    )


    negative_event = (

        negative_tail

        &

        ~negative_tail
        .shift(1)
        .fillna(False)

    )


    masks = {

        "POS_DISLOCATION":
            positive_event,

        "NEG_DISLOCATION":
            negative_event,

    }


    for event_name, mask in masks.items():


        temp = aligned.loc[
            mask
        ].copy()


        temp[
            "symbol"
        ] = symbol


        temp[
            "event"
        ] = event_name


        temp[
            "asset_return"
        ] = aligned.loc[
            temp.index,
            f"ret_{symbol}"
        ]


        temp[
            "market_return"
        ] = market_return.loc[
            temp.index
        ]


        temp[
            "residual_return"
        ] = residual.loc[
            temp.index
        ]


        temp[
            "residual_z"
        ] = residual_z.loc[
            temp.index
        ]


        temp[
            "residual_q01"
        ] = residual_q01.loc[
            temp.index
        ]


        temp[
            "residual_q99"
        ] = residual_q99.loc[
            temp.index
        ]


        # ====================================================
        # FUTURE RETURNS
        # ====================================================

        for horizon in HORIZONS:


            temp[
                f"future_long_{horizon}"
            ] = aligned.loc[

                temp.index,

                f"future_long_{symbol}_{horizon}",

            ]


            temp[
                f"future_short_{horizon}"
            ] = aligned.loc[

                temp.index,

                f"future_short_{symbol}_{horizon}",

            ]


            # ================================================
            # FUTURE CROSS-ASSET RELATIVE RETURN
            #
            # Diagnostic only.
            # ================================================

            other_future_columns = [

                f"future_long_{other}_{horizon}"

                for other
                in others

            ]


            future_market_return = (

                aligned.loc[
                    temp.index,
                    other_future_columns,
                ]

                .median(
                    axis=1
                )

            )


            temp[
                f"future_market_{horizon}"
            ] = (
                future_market_return
            )


            temp[
                f"future_relative_long_{horizon}"
            ] = (

                temp[
                    f"future_long_{horizon}"
                ]

                -

                future_market_return

            )


        event_frames.append(

            temp[
                [
                    "open_time",
                    "period",
                    "year",
                    "symbol",
                    "event",
                    "asset_return",
                    "market_return",
                    "residual_return",
                    "residual_z",
                    "residual_q01",
                    "residual_q99",
                ]
                +
                [

                    column

                    for horizon
                    in HORIZONS

                    for column
                    in [

                        f"future_long_{horizon}",
                        f"future_short_{horizon}",
                        f"future_market_{horizon}",
                        f"future_relative_long_{horizon}",

                    ]

                ]
            ]

        )


# ============================================================
# CONCAT EVENTS
# ============================================================

events = pd.concat(
    event_frames,
    ignore_index=True,
)


events = (
    events

    .sort_values(
        [
            "open_time",
            "symbol",
        ]
    )

    .reset_index(
        drop=True
    )
)


# ============================================================
# DROP EVENTS WITHOUT MAX FUTURE HORIZON
# ============================================================

required_future = [

    f"future_long_{max(HORIZONS)}",

    f"future_short_{max(HORIZONS)}",

]


events = events.dropna(
    subset=required_future
)


# ============================================================
# EVENT COUNTS
# ============================================================

counts = (

    events

    .groupby(
        [
            "event",
            "symbol",
        ]
    )

    .size()

    .rename(
        "samples"
    )

    .reset_index()

)


# ============================================================
# EVENT ANATOMY
# ============================================================

anatomy = (

    events

    .groupby(
        "event",
        as_index=False,
    )

    .agg(

        samples=(
            "event",
            "size",
        ),

        mean_asset_return=(
            "asset_return",
            "mean",
        ),

        median_asset_return=(
            "asset_return",
            "median",
        ),

        mean_market_return=(
            "market_return",
            "mean",
        ),

        mean_residual_return=(
            "residual_return",
            "mean",
        ),

        median_residual_return=(
            "residual_return",
            "median",
        ),

        median_residual_z=(
            "residual_z",
            "median",
        ),

        mean_abs_residual_z=(

            "residual_z",

            lambda x:
                np.abs(x).mean(),

        ),

    )

)


# ============================================================
# HYPOTHESIS DEFINITIONS
# ============================================================

HYPOTHESES = {

    "POS_CONTINUATION_LONG":
        (
            "POS_DISLOCATION",
            "LONG",
        ),

    "POS_REVERSION_SHORT":
        (
            "POS_DISLOCATION",
            "SHORT",
        ),

    "NEG_CONTINUATION_SHORT":
        (
            "NEG_DISLOCATION",
            "SHORT",
        ),

    "NEG_REVERSION_LONG":
        (
            "NEG_DISLOCATION",
            "LONG",
        ),

}


# ============================================================
# GLOBAL RESULTS
# ============================================================

global_rows = []


for hypothesis, (
    event_name,
    direction,
) in HYPOTHESES.items():


    subset = events[
        events[
            "event"
        ]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if direction == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

            relative_returns = (
                subset[
                    f"future_relative_long_{horizon}"
                ]
            )


        else:

            return_column = (
                f"future_short_{horizon}"
            )

            # If asset underperforms peers,
            # this is positive for relative SHORT.

            relative_returns = (

                -subset[
                    f"future_relative_long_{horizon}"
                ]

            )


        gross_returns = (
            subset[
                return_column
            ]
        )


        for cost in COSTS:


            net_returns = (
                gross_returns
                -
                cost
            )


            stats = summarize(
                net_returns
            )


            global_rows.append(
                {

                    "hypothesis":
                        hypothesis,

                    "horizon_bars":
                        horizon,

                    "minutes":
                        horizon
                        *
                        BAR_MINUTES,

                    "cost":
                        cost,

                    "mean_relative_return":
                        relative_returns.mean(),

                    **stats,

                }
            )


global_results = pd.DataFrame(
    global_rows
)


# ============================================================
# BY YEAR
# ============================================================

year_rows = []


for hypothesis, (
    event_name,
    direction,
) in HYPOTHESES.items():


    subset = events[
        events[
            "event"
        ]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if direction == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for year, group in subset.groupby(
            "year"
        ):


            for cost in COSTS:


                returns = (
                    group[
                        return_column
                    ]
                    -
                    cost
                )


                year_rows.append(
                    {

                        "hypothesis":
                            hypothesis,

                        "horizon_bars":
                            horizon,

                        "minutes":
                            horizon
                            *
                            BAR_MINUTES,

                        "year":
                            year,

                        "cost":
                            cost,

                        **summarize(
                            returns
                        ),

                    }
                )


by_year = pd.DataFrame(
    year_rows
)


# ============================================================
# BY ASSET
# ============================================================

asset_rows = []


for hypothesis, (
    event_name,
    direction,
) in HYPOTHESES.items():


    subset = events[
        events[
            "event"
        ]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if direction == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for symbol, group in subset.groupby(
            "symbol"
        ):


            for cost in COSTS:


                returns = (
                    group[
                        return_column
                    ]
                    -
                    cost
                )


                asset_rows.append(
                    {

                        "hypothesis":
                            hypothesis,

                        "horizon_bars":
                            horizon,

                        "minutes":
                            horizon
                            *
                            BAR_MINUTES,

                        "symbol":
                            symbol,

                        "cost":
                            cost,

                        **summarize(
                            returns
                        ),

                    }
                )


by_asset = pd.DataFrame(
    asset_rows
)


# ============================================================
# STABILITY TABLE @ 0.06%
#
# Discovery diagnostic.
# NOT approval.
# ============================================================

BASE_COST = 0.0006


stability_rows = []


for hypothesis in HYPOTHESES.keys():


    for horizon in HORIZONS:


        global_match = global_results[
            (
                global_results[
                    "hypothesis"
                ]
                ==
                hypothesis
            )
            &
            (
                global_results[
                    "horizon_bars"
                ]
                ==
                horizon
            )
            &
            (
                np.isclose(
                    global_results[
                        "cost"
                    ],
                    BASE_COST,
                )
            )
        ]


        if global_match.empty:
            continue


        global_row = (
            global_match.iloc[0]
        )


        years = by_year[
            (
                by_year[
                    "hypothesis"
                ]
                ==
                hypothesis
            )
            &
            (
                by_year[
                    "horizon_bars"
                ]
                ==
                horizon
            )
            &
            (
                np.isclose(
                    by_year[
                        "cost"
                    ],
                    BASE_COST,
                )
            )
        ]


        assets = by_asset[
            (
                by_asset[
                    "hypothesis"
                ]
                ==
                hypothesis
            )
            &
            (
                by_asset[
                    "horizon_bars"
                ]
                ==
                horizon
            )
            &
            (
                np.isclose(
                    by_asset[
                        "cost"
                    ],
                    BASE_COST,
                )
            )
        ]


        stability_rows.append(
            {

                "hypothesis":
                    hypothesis,

                "minutes":
                    horizon
                    *
                    BAR_MINUTES,

                "samples":
                    global_row[
                        "samples"
                    ],

                "mean_return":
                    global_row[
                        "mean_return"
                    ],

                "trimmed_mean_5":
                    global_row[
                        "trimmed_mean_5"
                    ],

                "winsorized_mean_5":
                    global_row[
                        "winsorized_mean_5"
                    ],

                "profit_factor":
                    global_row[
                        "profit_factor"
                    ],

                "mean_relative_return":
                    global_row[
                        "mean_relative_return"
                    ],

                "years_pf_gt_1":
                    int(
                        (
                            years[
                                "profit_factor"
                            ]
                            >
                            1
                        ).sum()
                    ),

                "total_years":
                    len(years),

                "worst_year_pf":
                    years[
                        "profit_factor"
                    ].min(),

                "median_year_pf":
                    years[
                        "profit_factor"
                    ].median(),

                "assets_pf_gt_1":
                    int(
                        (
                            assets[
                                "profit_factor"
                            ]
                            >
                            1
                        ).sum()
                    ),

                "total_assets":
                    len(assets),

                "worst_asset_pf":
                    assets[
                        "profit_factor"
                    ].min(),

                "median_asset_pf":
                    assets[
                        "profit_factor"
                    ].median(),

            }
        )


stability = pd.DataFrame(
    stability_rows
)


# ============================================================
# DISPLAY HELPER
# ============================================================

def percent_display(df):

    result = df.copy()


    percentage_columns = [
        "cost",
        "mean_return",
        "median_return",
        "trimmed_mean_5",
        "winsorized_mean_5",
        "win_rate",
        "q10",
        "q90",
        "mean_relative_return",
        "mean_asset_return",
        "median_asset_return",
        "mean_market_return",
        "mean_residual_return",
        "median_residual_return",
    ]


    for column in percentage_columns:

        if column in result.columns:

            result[
                column
            ] *= 100


    return result


anatomy_display = percent_display(
    anatomy
)


global_display = percent_display(
    global_results
)


stability_display = percent_display(
    stability
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    360,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print(
    "=" * 210
)

print(
    "EXPERIMENTO 27 — "
    "BRANCH 04 CROSS-ASSET DISLOCATION"
)

print(
    "=" * 210
)

print()


print(
    "EVENT COUNTS"
)

print()


print(
    counts.to_string(
        index=False
    )
)


print()

print(
    "=" * 210
)

print(
    "EVENT ANATOMY"
)

print(
    "=" * 210
)

print()


print(
    anatomy_display.to_string(
        index=False
    )
)


print()

print(
    "=" * 210
)

print(
    "GLOBAL HYPOTHESES"
)

print(
    "=" * 210
)

print()


print(

    global_display

    .sort_values(
        [
            "hypothesis",
            "minutes",
            "cost",
        ]
    )

    .to_string(
        index=False
    )

)


print()

print(
    "=" * 210
)

print(
    "STABILITY @ 0.06%"
)

print(
    "=" * 210
)

print()


print(

    stability_display

    .sort_values(
        "profit_factor",
        ascending=False,
    )

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

events.to_csv(

    RESULTS_DIR
    / "cross_asset_dislocation_events.csv",

    index=False,

)


counts.to_csv(

    RESULTS_DIR
    / "cross_asset_dislocation_counts.csv",

    index=False,

)


anatomy.to_csv(

    RESULTS_DIR
    / "cross_asset_dislocation_anatomy.csv",

    index=False,

)


global_results.to_csv(

    RESULTS_DIR
    / "cross_asset_dislocation_global.csv",

    index=False,

)


by_year.to_csv(

    RESULTS_DIR
    / "cross_asset_dislocation_by_year.csv",

    index=False,

)


by_asset.to_csv(

    RESULTS_DIR
    / "cross_asset_dislocation_by_asset.csv",

    index=False,

)


stability.to_csv(

    RESULTS_DIR
    / "cross_asset_dislocation_stability.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
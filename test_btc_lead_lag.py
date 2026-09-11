from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv


# ============================================================
# EXPERIMENTO 30
# BRANCH 07 — BTC LEADER / ALT FOLLOWER
#
# DEVELOPMENT:
# 2024-01 -> 2026-07
#
# Agosto já foi observado.
# Setembro/2026 permanece INTOCADO.
# ============================================================


LEADER = "BTCUSDT"

FOLLOWERS = [
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]

SYMBOLS = [
    LEADER,
    *FOLLOWERS,
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
# EVENT
#
# BTC shock definido somente pelo histórico do BTC.
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
    1,    # 5m
    3,    # 15m
    6,    # 30m
    12,   # 60m
]


BAR_MINUTES = 5


# ============================================================
# COSTS
# ============================================================

COSTS = [
    0.0000,
    0.0004,
    0.0006,
]


BASE_COST = 0.0006


# ============================================================
# DISCOVERY GATES
# ============================================================

MIN_SAMPLES = 500

TARGET_PF = 1.08

MIN_FOLLOWERS_PF_GT_1 = 2


# ============================================================
# HELPERS
# ============================================================

def cost_column(cost):

    return (
        f"net_"
        f"{int(round(cost * 10000))}"
        f"bps"
    )


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


        df = load_csv(path)


        df["open_time"] = pd.to_datetime(
            df["open_time"],
            utc=True,
        )


        for column in [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )


        frames.append(df)


    result = pd.concat(
        frames,
        ignore_index=True,
    )


    result = (
        result

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


    return result


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


    return gains / losses


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


    values = np.sort(values)


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
            trimmed_mean(values),

        "winsorized_mean_5":
            winsorized_mean(values),

        "win_rate":
            (
                values > 0
            ).mean(),

        "profit_factor":
            profit_factor(values),

        "q10":
            values.quantile(0.10),

        "q90":
            values.quantile(0.90),

    }


# ============================================================
# LOAD + ALIGN
# ============================================================

raw = {}


for symbol in SYMBOLS:

    print(
        f"Carregando {symbol}..."
    )

    raw[symbol] = load_symbol(
        symbol
    )


aligned = None


for symbol in SYMBOLS:


    temp = (
        raw[symbol][
            [
                "open_time",
                "open",
                "close",
            ]
        ]
        .copy()
    )


    temp = temp.rename(
        columns={
            "open":
                f"open_{symbol}",

            "close":
                f"close_{symbol}",
        }
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
# BTC EVENT THRESHOLDS
#
# Past only.
# ============================================================

btc_return = aligned[
    f"ret_{LEADER}"
]


aligned["btc_q01"] = (
    btc_return

    .rolling(
        LOOKBACK,
        min_periods=MIN_PERIODS,
    )

    .quantile(
        LOW_QUANTILE
    )

    .shift(1)
)


aligned["btc_q99"] = (
    btc_return

    .rolling(
        LOOKBACK,
        min_periods=MIN_PERIODS,
    )

    .quantile(
        HIGH_QUANTILE
    )

    .shift(1)
)


aligned["btc_std"] = (
    btc_return

    .rolling(
        LOOKBACK,
        min_periods=MIN_PERIODS,
    )

    .std()

    .shift(1)
)


aligned["btc_return_z"] = (
    btc_return
    /
    aligned["btc_std"]
)


# ============================================================
# BTC EXTREME STATES
# ============================================================

btc_up_state = (
    btc_return
    >=
    aligned["btc_q99"]
).fillna(False)


btc_down_state = (
    btc_return
    <=
    aligned["btc_q01"]
).fillna(False)


# ============================================================
# FIRST CROSSING
#
# Avoid consecutive tail candles being counted
# as independent new shocks.
# ============================================================

btc_up_event = (
    btc_up_state

    &

    ~btc_up_state
    .shift(1)
    .fillna(False)
)


btc_down_event = (
    btc_down_state

    &

    ~btc_down_state
    .shift(1)
    .fillna(False)
)


print()

print(
    f"BTC_UP events: "
    f"{int(btc_up_event.sum())}"
)

print(
    f"BTC_DOWN events: "
    f"{int(btc_down_event.sum())}"
)


# ============================================================
# FOLLOWER FUTURE RETURNS
#
# Signal known only after BTC candle t closes.
#
# Entry:
# follower OPEN t+1
#
# Exit:
# follower CLOSE t+horizon
# ============================================================

for follower in FOLLOWERS:


    entry = (
        aligned[
            f"open_{follower}"
        ]
        .shift(-1)
    )


    for horizon in HORIZONS:


        exit_price = (
            aligned[
                f"close_{follower}"
            ]
            .shift(
                -horizon
            )
        )


        aligned[
            f"future_long_{follower}_{horizon}"
        ] = (

            exit_price
            /
            entry
            -
            1

        )


        aligned[
            f"future_short_{follower}_{horizon}"
        ] = (

            1
            -
            exit_price
            /
            entry

        )


# ============================================================
# EVENT TABLE
# ============================================================

event_frames = []


masks = {

    "BTC_UP":
        btc_up_event,

    "BTC_DOWN":
        btc_down_event,

}


for event_name, mask in masks.items():


    base = aligned.loc[
        mask
    ].copy()


    base["event"] = event_name


    base["btc_signal_return"] = (
        aligned.loc[
            base.index,
            f"ret_{LEADER}"
        ]
    )


    base["btc_return_z"] = (
        aligned.loc[
            base.index,
            "btc_return_z"
        ]
    )


    for follower in FOLLOWERS:


        temp = base.copy()


        temp["follower"] = follower


        temp[
            "follower_signal_return"
        ] = (

            aligned.loc[
                temp.index,
                f"ret_{follower}"
            ]
        )


        # ====================================================
        # Same-candle response ratio.
        #
        # Diagnostic only.
        # NOT a filter.
        # ====================================================

        temp[
            "response_ratio"
        ] = (

            temp[
                "follower_signal_return"
            ]

            /

            temp[
                "btc_signal_return"
            ]
            .replace(
                0,
                np.nan,
            )

        )


        for horizon in HORIZONS:


            temp[
                f"future_long_{horizon}"
            ] = (

                aligned.loc[
                    temp.index,
                    f"future_long_{follower}_{horizon}"
                ]

            )


            temp[
                f"future_short_{horizon}"
            ] = (

                aligned.loc[
                    temp.index,
                    f"future_short_{follower}_{horizon}"
                ]

            )


        event_frames.append(
            temp
        )


events = pd.concat(
    event_frames,
    ignore_index=True,
)


events = events.dropna(
    subset=[
        f"future_long_{max(HORIZONS)}",
        f"future_short_{max(HORIZONS)}",
    ]
)


events = (
    events

    .sort_values(
        [
            "open_time",
            "follower",
        ]
    )

    .reset_index(
        drop=True
    )
)


# ============================================================
# EVENT COUNTS
# ============================================================

counts = (

    events

    .groupby(
        [
            "event",
            "follower",
        ]
    )

    .size()

    .rename("samples")

    .reset_index()
)


# ============================================================
# ANATOMY
# ============================================================

anatomy = (

    events

    .groupby(
        [
            "event",
            "follower",
        ],
        as_index=False,
    )

    .agg(

        samples=(
            "event",
            "size",
        ),

        mean_btc_return=(
            "btc_signal_return",
            "mean",
        ),

        median_btc_return=(
            "btc_signal_return",
            "median",
        ),

        median_btc_z=(
            "btc_return_z",
            "median",
        ),

        mean_follower_return=(
            "follower_signal_return",
            "mean",
        ),

        median_follower_return=(
            "follower_signal_return",
            "median",
        ),

        mean_response_ratio=(
            "response_ratio",
            "mean",
        ),

        median_response_ratio=(
            "response_ratio",
            "median",
        ),

    )

)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    "BTC_UP_FOLLOW_LONG":
        (
            "BTC_UP",
            "LONG",
        ),

    "BTC_UP_REVERSE_SHORT":
        (
            "BTC_UP",
            "SHORT",
        ),

    "BTC_DOWN_FOLLOW_SHORT":
        (
            "BTC_DOWN",
            "SHORT",
        ),

    "BTC_DOWN_REVERSE_LONG":
        (
            "BTC_DOWN",
            "LONG",
        ),

}


# ============================================================
# GLOBAL RESULTS
# ============================================================

global_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "event"
        ]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for cost in COSTS:


            returns = (
                subset[
                    return_column
                ]
                -
                cost
            )


            global_rows.append({

                "hypothesis":
                    hypothesis,

                "minutes":
                    horizon
                    *
                    BAR_MINUTES,

                "cost":
                    cost,

                **summarize(
                    returns
                ),

            })


global_results = pd.DataFrame(
    global_rows
)


# ============================================================
# BY YEAR
# ============================================================

year_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events["event"]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

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


                year_rows.append({

                    "hypothesis":
                        hypothesis,

                    "minutes":
                        horizon
                        *
                        BAR_MINUTES,

                    "year":
                        year,

                    "cost":
                        cost,

                    **summarize(
                        group[
                            return_column
                        ]
                        -
                        cost
                    ),

                })


by_year = pd.DataFrame(
    year_rows
)


# ============================================================
# BY FOLLOWER
# ============================================================

follower_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events["event"]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for follower, group in subset.groupby(
            "follower"
        ):


            for cost in COSTS:


                follower_rows.append({

                    "hypothesis":
                        hypothesis,

                    "minutes":
                        horizon
                        *
                        BAR_MINUTES,

                    "follower":
                        follower,

                    "cost":
                        cost,

                    **summarize(
                        group[
                            return_column
                        ]
                        -
                        cost
                    ),

                })


by_follower = pd.DataFrame(
    follower_rows
)


# ============================================================
# MONTHLY @ BASE COST
# ============================================================

monthly_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events["event"]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for period, group in subset.groupby(
            "period"
        ):


            monthly_rows.append({

                "hypothesis":
                    hypothesis,

                "minutes":
                    horizon
                    *
                    BAR_MINUTES,

                "period":
                    period,

                **summarize(
                    group[
                        return_column
                    ]
                    -
                    BASE_COST
                ),

            })


monthly = pd.DataFrame(
    monthly_rows
)


# ============================================================
# STABILITY @ 0.06%
# ============================================================

stability_rows = []


for hypothesis in HYPOTHESES:


    for horizon in HORIZONS:


        minutes = (
            horizon
            *
            BAR_MINUTES
        )


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
                    "minutes"
                ]
                ==
                minutes
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


        row = (
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
                    "minutes"
                ]
                ==
                minutes
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


        followers = by_follower[
            (
                by_follower[
                    "hypothesis"
                ]
                ==
                hypothesis
            )
            &
            (
                by_follower[
                    "minutes"
                ]
                ==
                minutes
            )
            &
            (
                np.isclose(
                    by_follower[
                        "cost"
                    ],
                    BASE_COST,
                )
            )
        ]


        months = monthly[
            (
                monthly[
                    "hypothesis"
                ]
                ==
                hypothesis
            )
            &
            (
                monthly[
                    "minutes"
                ]
                ==
                minutes
            )
        ]


        stability_rows.append({

            "hypothesis":
                hypothesis,

            "minutes":
                minutes,

            "samples":
                int(
                    row["samples"]
                ),

            "mean_return":
                row["mean_return"],

            "trimmed_mean_5":
                row[
                    "trimmed_mean_5"
                ],

            "winsorized_mean_5":
                row[
                    "winsorized_mean_5"
                ],

            "win_rate":
                row["win_rate"],

            "profit_factor":
                row[
                    "profit_factor"
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

            "followers_pf_gt_1":
                int(
                    (
                        followers[
                            "profit_factor"
                        ]
                        >
                        1
                    ).sum()
                ),

            "total_followers":
                len(followers),

            "worst_follower_pf":
                followers[
                    "profit_factor"
                ].min(),

            "median_follower_pf":
                followers[
                    "profit_factor"
                ].median(),

            "months_pf_gt_1":
                int(
                    (
                        months[
                            "profit_factor"
                        ]
                        >
                        1
                    ).sum()
                ),

            "total_months":
                len(months),

            "median_month_pf":
                months[
                    "profit_factor"
                ].median(),

        })


stability = pd.DataFrame(
    stability_rows
)


# ============================================================
# DISCOVERY GATE
# ============================================================

stability[
    "basic_discovery_gate"
] = (

    (
        stability[
            "samples"
        ]
        >=
        MIN_SAMPLES
    )

    &

    (
        stability[
            "mean_return"
        ]
        >
        0
    )

    &

    (
        stability[
            "trimmed_mean_5"
        ]
        >
        0
    )

    &

    (
        stability[
            "winsorized_mean_5"
        ]
        >
        0
    )

    &

    (
        stability[
            "profit_factor"
        ]
        >=
        TARGET_PF
    )

    &

    (
        stability[
            "years_pf_gt_1"
        ]
        ==
        stability[
            "total_years"
        ]
    )

    &

    (
        stability[
            "followers_pf_gt_1"
        ]
        >=
        MIN_FOLLOWERS_PF_GT_1
    )

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

        "trimmed_mean_5",
        "winsorized_mean_5",

        "win_rate",

        "q10",
        "q90",

        "mean_btc_return",
        "median_btc_return",

        "mean_follower_return",
        "median_follower_return",

    ]:

        if column in output.columns:

            output[
                column
            ] *= 100


    return output


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
    380,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 220)

print(
    "EXPERIMENTO 30 — "
    "BRANCH 07 BTC LEAD/LAG"
)

print("=" * 220)

print()


print("EVENT COUNTS")
print()

print(
    counts.to_string(
        index=False
    )
)


print()

print("=" * 220)

print("EVENT ANATOMY")

print("=" * 220)

print()

print(
    anatomy_display.to_string(
        index=False
    )
)


print()

print("=" * 220)

print("GLOBAL HYPOTHESES")

print("=" * 220)

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

print("=" * 220)

print("STABILITY @ 0.06%")

print("=" * 220)

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


print()

print("=" * 220)

print("DISCOVERY GATE")

print("=" * 220)

print()


passed = stability[
    stability[
        "basic_discovery_gate"
    ]
]


if passed.empty:

    print(
        "Nenhuma hipótese passou "
        "o gate básico."
    )

else:

    print(
        passed[
            [
                "hypothesis",
                "minutes",
                "samples",
                "mean_return",
                "profit_factor",
                "years_pf_gt_1",
                "followers_pf_gt_1",
                "months_pf_gt_1",
            ]
        ]
        .to_string(
            index=False
        )
    )


# ============================================================
# SAVE
# ============================================================

events.to_csv(
    RESULTS_DIR
    / "btc_lead_lag_events.csv",
    index=False,
)


counts.to_csv(
    RESULTS_DIR
    / "btc_lead_lag_counts.csv",
    index=False,
)


anatomy.to_csv(
    RESULTS_DIR
    / "btc_lead_lag_anatomy.csv",
    index=False,
)


global_results.to_csv(
    RESULTS_DIR
    / "btc_lead_lag_global.csv",
    index=False,
)


by_year.to_csv(
    RESULTS_DIR
    / "btc_lead_lag_by_year.csv",
    index=False,
)


by_follower.to_csv(
    RESULTS_DIR
    / "btc_lead_lag_by_follower.csv",
    index=False,
)


monthly.to_csv(
    RESULTS_DIR
    / "btc_lead_lag_monthly.csv",
    index=False,
)


stability.to_csv(
    RESULTS_DIR
    / "btc_lead_lag_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
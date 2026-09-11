from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# EXPERIMENTO 29
# BRANCH 06 — FLOW / PRICE ABSORPTION
#
# Development:
# 2024-01 -> 2026-07
#
# Agosto já observado.
# Setembro/2026 continua INTOCADO.
# ============================================================


RESULTS_DIR = Path("results")

INPUT_FILE = (
    RESULTS_DIR
    / "taker_flow_events.csv"
)


HORIZONS = [
    1,   # 5m
    3,   # 15m
    6,   # 30m
    12,  # 60m
]


BAR_MINUTES = 5


COSTS = [
    0.0000,
    0.0004,
    0.0006,
]


BASE_COST = 0.0006


# ============================================================
# DISCOVERY GATES
#
# Pré-declarados antes de observar o Exp.29.
# ============================================================

MIN_SAMPLES = 500

TARGET_PF = 1.08


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
# LOAD EVENTS
# ============================================================

if not INPUT_FILE.exists():

    raise FileNotFoundError(
        f"Arquivo não encontrado: "
        f"{INPUT_FILE}"
    )


events = pd.read_csv(
    INPUT_FILE
)


events["open_time"] = pd.to_datetime(
    events["open_time"],
    utc=True,
)


# ============================================================
# REQUIRED COLUMNS
# ============================================================

required_columns = [
    "open_time",
    "period",
    "year",
    "symbol",
    "event",
    "flow_imbalance",
    "flow_z",
    "signal_return",
]


for horizon in HORIZONS:

    required_columns.extend(
        [
            f"future_long_{horizon}",
            f"future_short_{horizon}",
        ]
    )


missing = [
    column
    for column in required_columns
    if column not in events.columns
]


if missing:

    raise RuntimeError(
        "Colunas ausentes no arquivo "
        "taker_flow_events.csv:\n"
        +
        "\n".join(missing)
    )


# ============================================================
# NORMALIZE NUMERIC
# ============================================================

numeric_columns = [
    "flow_imbalance",
    "flow_z",
    "signal_return",
]


for horizon in HORIZONS:

    numeric_columns.extend(
        [
            f"future_long_{horizon}",
            f"future_short_{horizon}",
        ]
    )


for column in numeric_columns:

    events[column] = pd.to_numeric(
        events[column],
        errors="coerce",
    )


# ============================================================
# CLASSIFICATION
#
# ABSORPTION:
#
# EXTREME_BUY
# mas candle <= 0
#
# EXTREME_SELL
# mas candle >= 0
#
# CONFIRMED:
# fluxo e preço concordam.
# ============================================================

conditions = [

    (
        (events["event"] == "EXTREME_BUY")
        &
        (events["signal_return"] <= 0)
    ),

    (
        (events["event"] == "EXTREME_BUY")
        &
        (events["signal_return"] > 0)
    ),

    (
        (events["event"] == "EXTREME_SELL")
        &
        (events["signal_return"] >= 0)
    ),

    (
        (events["event"] == "EXTREME_SELL")
        &
        (events["signal_return"] < 0)
    ),

]


choices = [

    "BUY_ABSORPTION",

    "BUY_CONFIRMED",

    "SELL_ABSORPTION",

    "SELL_CONFIRMED",

]


events["flow_price_state"] = np.select(
    conditions,
    choices,
    default="OTHER",
)


events = events[
    events[
        "flow_price_state"
    ]
    !=
    "OTHER"
].copy()


# ============================================================
# FLOW / PRICE EFFICIENCY
#
# Apenas anatomia.
# NÃO é filtro.
# ============================================================

events[
    "price_response_per_flow"
] = (

    events[
        "signal_return"
    ]

    /

    events[
        "flow_imbalance"
    ]
    .abs()
    .replace(
        0,
        np.nan,
    )

)


# ============================================================
# COUNTS
# ============================================================

counts = (

    events

    .groupby(
        [
            "flow_price_state",
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
# ANATOMY
# ============================================================

anatomy = (

    events

    .groupby(
        "flow_price_state",
        as_index=False,
    )

    .agg(

        samples=(
            "flow_price_state",
            "size",
        ),

        mean_flow_imbalance=(
            "flow_imbalance",
            "mean",
        ),

        median_flow_imbalance=(
            "flow_imbalance",
            "median",
        ),

        mean_flow_z=(
            "flow_z",
            "mean",
        ),

        median_flow_z=(
            "flow_z",
            "median",
        ),

        mean_signal_return=(
            "signal_return",
            "mean",
        ),

        median_signal_return=(
            "signal_return",
            "median",
        ),

        mean_price_response_per_flow=(
            "price_response_per_flow",
            "mean",
        ),

    )

)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    # --------------------------------------------------------
    # Absorption hypotheses
    # --------------------------------------------------------

    "BUY_ABSORPTION_SHORT":
        (
            "BUY_ABSORPTION",
            "SHORT",
        ),

    "SELL_ABSORPTION_LONG":
        (
            "SELL_ABSORPTION",
            "LONG",
        ),


    # --------------------------------------------------------
    # Controls:
    # flow and price aligned
    # --------------------------------------------------------

    "BUY_CONFIRMED_LONG":
        (
            "BUY_CONFIRMED",
            "LONG",
        ),

    "SELL_CONFIRMED_SHORT":
        (
            "SELL_CONFIRMED",
            "SHORT",
        ),

}


# ============================================================
# GLOBAL
# ============================================================

global_rows = []


for hypothesis, (
    state,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "flow_price_state"
        ]
        ==
        state
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

                "state":
                    state,

                "side":
                    side,

                "horizon_bars":
                    horizon,

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
    state,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "flow_price_state"
        ]
        ==
        state
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


                returns = (
                    group[
                        return_column
                    ]
                    -
                    cost
                )


                year_rows.append({

                    "hypothesis":
                        hypothesis,

                    "minutes":
                        horizon
                        *
                        BAR_MINUTES,

                    "year":
                        str(year),

                    "cost":
                        cost,

                    **summarize(
                        returns
                    ),

                })


by_year = pd.DataFrame(
    year_rows
)


# ============================================================
# BY ASSET
# ============================================================

asset_rows = []


for hypothesis, (
    state,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "flow_price_state"
        ]
        ==
        state
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


                asset_rows.append({

                    "hypothesis":
                        hypothesis,

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

                })


by_asset = pd.DataFrame(
    asset_rows
)


# ============================================================
# MONTHLY
# ============================================================

monthly_rows = []


for hypothesis, (
    state,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "flow_price_state"
        ]
        ==
        state
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


            returns = (
                group[
                    return_column
                ]
                -
                BASE_COST
            )


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
                    returns
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


        row = global_match.iloc[0]


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
                    "minutes"
                ]
                ==
                minutes
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
                    row[
                        "samples"
                    ]
                ),

            "mean_return":
                row[
                    "mean_return"
                ],

            "trimmed_mean_5":
                row[
                    "trimmed_mean_5"
                ],

            "winsorized_mean_5":
                row[
                    "winsorized_mean_5"
                ],

            "win_rate":
                row[
                    "win_rate"
                ],

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
# PASS FLAGS
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
            "assets_pf_gt_1"
        ]
        >=
        3
    )

)


# ============================================================
# DISPLAY
# ============================================================

def percent_display(df):

    result = df.copy()


    for column in [

        "cost",

        "mean_return",
        "median_return",
        "trimmed_mean_5",
        "winsorized_mean_5",

        "win_rate",

        "q10",
        "q90",

        "mean_signal_return",
        "median_signal_return",

        "mean_price_response_per_flow",

    ]:

        if column in result.columns:

            result[column] *= 100


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
    380,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 220)

print(
    "EXPERIMENTO 29 — "
    "BRANCH 06 FLOW-PRICE ABSORPTION"
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

print("ABSORPTION ANATOMY")

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
].copy()


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
                "assets_pf_gt_1",
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
    / "flow_price_absorption_events.csv",
    index=False,
)


counts.to_csv(
    RESULTS_DIR
    / "flow_price_absorption_counts.csv",
    index=False,
)


anatomy.to_csv(
    RESULTS_DIR
    / "flow_price_absorption_anatomy.csv",
    index=False,
)


global_results.to_csv(
    RESULTS_DIR
    / "flow_price_absorption_global.csv",
    index=False,
)


by_year.to_csv(
    RESULTS_DIR
    / "flow_price_absorption_by_year.csv",
    index=False,
)


by_asset.to_csv(
    RESULTS_DIR
    / "flow_price_absorption_by_asset.csv",
    index=False,
)


monthly.to_csv(
    RESULTS_DIR
    / "flow_price_absorption_monthly.csv",
    index=False,
)


stability.to_csv(
    RESULTS_DIR
    / "flow_price_absorption_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

RESULTS_DIR = Path("results")

INPUT_FILE = (
    RESULTS_DIR
    / "extreme_impulse_events.csv"
)


THRESHOLDS = [
    2.5,
    3.0,
    3.5,
    4.0,
]


COSTS = [
    0.0004,   # 0.04%
    0.0006,   # 0.06%
]


BOOTSTRAP_ITERATIONS = 1000

RANDOM_SEED = 42


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
# TRIMMED MEAN
# ============================================================

def trimmed_mean(
    returns,
    trim=0.05,
):

    values = np.asarray(
        pd.Series(
            returns
        )
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
        len(values) <= 2 * cut
    ):

        return (
            values.mean()
        )


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
        pd.Series(
            returns
        )
        .dropna(),
        dtype=float,
    )


    if len(values) == 0:
        return np.nan


    lower = np.quantile(
        values,
        limit,
    )


    upper = np.quantile(
        values,
        1 - limit,
    )


    clipped = np.clip(

        values,

        lower,

        upper,

    )


    return clipped.mean()


# ============================================================
# SUMMARY
# ============================================================

def summarize(
    returns,
):

    returns = (
        pd.Series(returns)
        .dropna()
    )


    if len(returns) == 0:

        return {

            "samples": 0,

            "mean_return":
                np.nan,

            "median_return":
                np.nan,

            "trimmed_mean_5":
                np.nan,

            "winsorized_mean_5":
                np.nan,

            "win_rate":
                np.nan,

            "profit_factor":
                np.nan,

            "q05":
                np.nan,

            "q10":
                np.nan,

            "q90":
                np.nan,

            "q95":
                np.nan,

        }


    return {

        "samples":
            len(returns),

        "mean_return":
            returns.mean(),

        "median_return":
            returns.median(),

        "trimmed_mean_5":
            trimmed_mean(
                returns,
                0.05,
            ),

        "winsorized_mean_5":
            winsorized_mean(
                returns,
                0.05,
            ),

        "win_rate":
            (
                returns > 0
            ).mean(),

        "profit_factor":
            profit_factor(
                returns
            ),

        "q05":
            returns.quantile(
                0.05
            ),

        "q10":
            returns.quantile(
                0.10
            ),

        "q90":
            returns.quantile(
                0.90
            ),

        "q95":
            returns.quantile(
                0.95
            ),

    }


# ============================================================
# BOOTSTRAP
# ============================================================

def bootstrap_stats(
    returns,
):

    values = np.asarray(

        pd.Series(
            returns
        )
        .dropna(),

        dtype=float,

    )


    if len(values) < 50:

        return {

            "mean_ci_low":
                np.nan,

            "mean_ci_high":
                np.nan,

            "pf_ci_low":
                np.nan,

            "pf_ci_high":
                np.nan,

            "prob_mean_gt_0":
                np.nan,

            "prob_pf_gt_1":
                np.nan,

        }


    rng = np.random.default_rng(
        RANDOM_SEED
    )


    means = []

    pfs = []


    n = len(values)


    for _ in range(
        BOOTSTRAP_ITERATIONS
    ):


        sample = rng.choice(

            values,

            size=n,

            replace=True,

        )


        means.append(
            sample.mean()
        )


        pf = profit_factor(
            sample
        )


        if np.isfinite(pf):

            pfs.append(
                pf
            )


    means = np.asarray(
        means
    )


    pfs = np.asarray(
        pfs
    )


    return {

        "mean_ci_low":

            np.quantile(
                means,
                0.025,
            ),

        "mean_ci_high":

            np.quantile(
                means,
                0.975,
            ),

        "pf_ci_low":

            (
                np.quantile(
                    pfs,
                    0.025,
                )
                if len(pfs)
                else np.nan
            ),

        "pf_ci_high":

            (
                np.quantile(
                    pfs,
                    0.975,
                )
                if len(pfs)
                else np.nan
            ),

        "prob_mean_gt_0":

            (
                means > 0
            ).mean(),

        "prob_pf_gt_1":

            (
                pfs > 1
            ).mean()
            if len(pfs)
            else np.nan,

    }


# ============================================================
# LOAD
# ============================================================

events = pd.read_csv(
    INPUT_FILE
)


events = events[

    events[
        "event"
    ]
    ==
    "EXTREME_UP"

].copy()


events[
    "abs_return_z"
] = (

    events[
        "return_z"
    ]
    .abs()

)


events = events.dropna(

    subset=[

        "symbol",
        "period",
        "year",

        "abs_return_z",

        "future_long_6",

    ]

).copy()


print()

print(
    f"EXTREME_UP disponíveis: "
    f"{len(events)}"
)


# ============================================================
# GLOBAL THRESHOLD CURVE
# ============================================================

global_rows = []


for threshold in THRESHOLDS:


    subset = events[

        events[
            "abs_return_z"
        ]
        >=
        threshold

    ]


    for cost in COSTS:


        returns = (

            subset[
                "future_long_6"
            ]

            -
            cost

        )


        stats = summarize(
            returns
        )


        bootstrap = bootstrap_stats(
            returns
        )


        global_rows.append({

            "threshold":
                threshold,

            "cost":
                cost,

            **stats,

            **bootstrap,

        })


global_results = pd.DataFrame(
    global_rows
)


# ============================================================
# YEAR
# ============================================================

year_rows = []


for threshold in THRESHOLDS:


    subset = events[

        events[
            "abs_return_z"
        ]
        >=
        threshold

    ]


    for year, group in subset.groupby(
        "year"
    ):


        for cost in COSTS:


            returns = (

                group[
                    "future_long_6"
                ]

                -
                cost

            )


            year_rows.append({

                "threshold":
                    threshold,

                "year":
                    str(year),

                "cost":
                    cost,

                **summarize(
                    returns
                ),

            })


year_results = pd.DataFrame(
    year_rows
)


# ============================================================
# ASSET
# ============================================================

asset_rows = []


for threshold in THRESHOLDS:


    subset = events[

        events[
            "abs_return_z"
        ]
        >=
        threshold

    ]


    for symbol, group in subset.groupby(
        "symbol"
    ):


        for cost in COSTS:


            returns = (

                group[
                    "future_long_6"
                ]

                -
                cost

            )


            asset_rows.append({

                "threshold":
                    threshold,

                "symbol":
                    symbol,

                "cost":
                    cost,

                **summarize(
                    returns
                ),

            })


asset_results = pd.DataFrame(
    asset_rows
)


# ============================================================
# MONTHLY WINDOWS
# ============================================================

monthly_rows = []


for threshold in THRESHOLDS:


    subset = events[

        events[
            "abs_return_z"
        ]
        >=
        threshold

    ]


    for (
        period,
        symbol,
    ), group in subset.groupby(

        [
            "period",
            "symbol",
        ]

    ):


        for cost in COSTS:


            returns = (

                group[
                    "future_long_6"
                ]

                -
                cost

            )


            monthly_rows.append({

                "threshold":
                    threshold,

                "period":
                    period,

                "symbol":
                    symbol,

                "cost":
                    cost,

                **summarize(
                    returns
                ),

            })


monthly_results = pd.DataFrame(
    monthly_rows
)


# ============================================================
# MONTHLY STABILITY
# ============================================================

monthly_stability = (

    monthly_results

    .groupby(

        [
            "threshold",
            "cost",
        ],

        as_index=False,

    )

    .agg(

        windows=(
            "period",
            "count",
        ),

        positive_mean_windows=(

            "mean_return",

            lambda x:
                (
                    x > 0
                ).sum(),

        ),

        pf_gt_1_windows=(

            "profit_factor",

            lambda x:
                (
                    x > 1
                ).sum(),

        ),

        median_window_return=(
            "mean_return",
            "median",
        ),

        median_window_pf=(
            "profit_factor",
            "median",
        ),

        worst_window_return=(
            "mean_return",
            "min",
        ),

        best_window_return=(
            "mean_return",
            "max",
        ),

    )

)


monthly_stability[

    "positive_window_rate"

] = (

    monthly_stability[
        "positive_mean_windows"
    ]

    /
    monthly_stability[
        "windows"
    ]

)


# ============================================================
# LEAVE ONE ASSET OUT
# ============================================================

loo_rows = []


symbols = sorted(

    events[
        "symbol"
    ]
    .unique()

)


for threshold in THRESHOLDS:


    subset = events[

        events[
            "abs_return_z"
        ]
        >=
        threshold

    ]


    for excluded in symbols:


        group = subset[

            subset[
                "symbol"
            ]
            !=
            excluded

        ]


        for cost in COSTS:


            returns = (

                group[
                    "future_long_6"
                ]

                -
                cost

            )


            loo_rows.append({

                "threshold":
                    threshold,

                "excluded_asset":
                    excluded,

                "cost":
                    cost,

                **summarize(
                    returns
                ),

            })


loo_results = pd.DataFrame(
    loo_rows
)


# ============================================================
# DISPLAY HELPERS
# ============================================================

def percent_display(df):

    output = df.copy()


    percentage_columns = [

        "cost",

        "mean_return",
        "median_return",

        "trimmed_mean_5",
        "winsorized_mean_5",

        "win_rate",

        "q05",
        "q10",
        "q90",
        "q95",

        "mean_ci_low",
        "mean_ci_high",

        "median_window_return",

        "worst_window_return",
        "best_window_return",

        "positive_window_rate",

        "prob_mean_gt_0",
        "prob_pf_gt_1",

    ]


    for column in percentage_columns:

        if column in output.columns:

            output[
                column
            ] *= 100


    return output


global_display = percent_display(
    global_results
)


year_display = percent_display(
    year_results
)


asset_display = percent_display(
    asset_results
)


monthly_display = percent_display(
    monthly_stability
)


loo_display = percent_display(
    loo_results
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    320,
)


# ============================================================
# OUTPUT 1
# ============================================================

print()

print("=" * 200)

print(
    "EXPERIMENTO 20 — "
    "EXTREME UP ROBUSTNESS"
)

print("=" * 200)

print()


print(
    global_display.to_string(
        index=False
    )
)


# ============================================================
# OUTPUT 2
# ============================================================

print()

print("=" * 200)

print(
    "POR ANO"
)

print("=" * 200)

print()


print(

    year_display

    .sort_values(

        [
            "threshold",
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
    "POR ATIVO"
)

print("=" * 200)

print()


print(

    asset_display

    .sort_values(

        [
            "threshold",
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
    "ESTABILIDADE MENSAL"
)

print("=" * 200)

print()


print(

    monthly_display

    .sort_values(

        [
            "threshold",
            "cost",
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

print("=" * 200)

print(
    "LEAVE-ONE-ASSET-OUT"
)

print("=" * 200)

print()


print(

    loo_display

    .sort_values(

        [
            "threshold",
            "cost",
            "excluded_asset",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

global_results.to_csv(

    RESULTS_DIR
    / "extreme_up_robustness_global.csv",

    index=False,

)


year_results.to_csv(

    RESULTS_DIR
    / "extreme_up_robustness_by_year.csv",

    index=False,

)


asset_results.to_csv(

    RESULTS_DIR
    / "extreme_up_robustness_by_asset.csv",

    index=False,

)


monthly_results.to_csv(

    RESULTS_DIR
    / "extreme_up_robustness_monthly.csv",

    index=False,

)


monthly_stability.to_csv(

    RESULTS_DIR
    / "extreme_up_robustness_monthly_stability.csv",

    index=False,

)


loo_results.to_csv(

    RESULTS_DIR
    / "extreme_up_robustness_leave_one_out.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
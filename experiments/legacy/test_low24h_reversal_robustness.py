from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# EXPERIMENTO 38
# BRANCH 14 — LOW 24H REVERSAL ROBUSTNESS
#
# IMPORTANT:
#
# Este experimento NÃO procura nova estratégia.
#
# Candidate já identificado:
#
# EVENT:
# BREAK_LOW_24H
#
# SIDE:
# LONG
#
# HORIZONS:
# 60m
# 120m
#
# Nenhum threshold será alterado.
# Nenhum ativo será removido.
# Nenhum novo horizonte será testado.
#
# Development permanece:
# Jan/2024 -> Jul/2026
#
# Agosto:
# já observado / proibido
#
# Setembro:
# intocado
# ============================================================


RESULTS_DIR = Path("results")


EVENT_FILE = (
    RESULTS_DIR
    /
    "multitimeframe_extremes_events.csv"
)


EVENT_NAME = "BREAK_LOW_24H"


HORIZONS = {
    60: 12,
    120: 24,
}


COSTS = [
    0.0000,
    0.0004,
    0.0006,
]


BASE_COST = 0.0006


BOOTSTRAP_RUNS = 5000


RANDOM_SEED = 42


rng = np.random.default_rng(
    RANDOM_SEED
)


# ============================================================
# HELPERS
# ============================================================

def profit_factor(values):

    values = (
        pd.Series(values)
        .dropna()
    )

    if values.empty:
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


def trimmed_mean(
    values,
    trim=0.05,
):

    values = np.asarray(
        pd.Series(values).dropna(),
        dtype=float,
    )

    if len(values) == 0:
        return np.nan

    values = np.sort(values)

    cut = int(
        len(values) * trim
    )

    if (
        cut == 0
        or
        len(values) <= 2 * cut
    ):

        return values.mean()

    return (
        values[
            cut:-cut
        ]
        .mean()
    )


def winsorized_mean(
    values,
    limit=0.05,
):

    values = np.asarray(
        pd.Series(values).dropna(),
        dtype=float,
    )

    if len(values) == 0:
        return np.nan

    lo = np.quantile(
        values,
        limit,
    )

    hi = np.quantile(
        values,
        1 - limit,
    )

    return (
        np.clip(
            values,
            lo,
            hi,
        )
        .mean()
    )


def summarize(values):

    values = (
        pd.Series(values)
        .dropna()
    )

    if values.empty:

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
            (values > 0).mean(),

        "profit_factor":
            profit_factor(values),

        "q10":
            values.quantile(0.10),

        "q90":
            values.quantile(0.90),
    }


# ============================================================
# LOAD
# ============================================================

if not EVENT_FILE.exists():

    raise FileNotFoundError(
        f"Arquivo não encontrado: {EVENT_FILE}"
    )


events = pd.read_csv(
    EVENT_FILE
)


events["open_time"] = pd.to_datetime(
    events["open_time"],
    format="mixed",
    utc=True,
    errors="coerce",
)


events = events[
    events["event"]
    ==
    EVENT_NAME
].copy()


events = (
    events

    .dropna(
        subset=[
            "open_time",
            "symbol",
        ]
    )

    .sort_values(
        "open_time"
    )

    .reset_index(
        drop=True
    )
)


events["year"] = (
    events["open_time"]
    .dt.year
)


events["month"] = (
    events["open_time"]
    .dt.strftime("%Y-%m")
)


events["half"] = np.where(
    events["open_time"].dt.month <= 6,
    "H1",
    "H2",
)


events["semester"] = (
    events["year"]
    .astype(str)
    +
    "-"
    +
    events["half"]
)


print()

print("=" * 110)

print(
    "EXPERIMENTO 38 — "
    "LOW 24H REVERSAL ROBUSTNESS"
)

print("=" * 110)

print(
    f"Eventos carregados: {len(events)}"
)


# ============================================================
# VALIDATE RETURN COLUMNS
# ============================================================

for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )

    if column not in events.columns:

        raise RuntimeError(
            f"Coluna ausente: {column}"
        )


# ============================================================
# GLOBAL COST CURVE
# ============================================================

global_rows = []


for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )

    gross = (
        events[column]
        .dropna()
    )

    for cost in COSTS:

        global_rows.append({

            "minutes":
                minutes,

            "cost":
                cost,

            **summarize(
                gross - cost
            ),
        })


global_results = pd.DataFrame(
    global_rows
)


# ============================================================
# YEAR
# ============================================================

year_rows = []


for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )

    for year, group in events.groupby(
        "year"
    ):

        returns = (
            group[column]
            .dropna()
            -
            BASE_COST
        )

        year_rows.append({

            "minutes":
                minutes,

            "year":
                year,

            **summarize(
                returns
            ),
        })


by_year = pd.DataFrame(
    year_rows
)


# ============================================================
# ASSET
# ============================================================

asset_rows = []


for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )

    for symbol, group in events.groupby(
        "symbol"
    ):

        returns = (
            group[column]
            .dropna()
            -
            BASE_COST
        )

        asset_rows.append({

            "minutes":
                minutes,

            "symbol":
                symbol,

            **summarize(
                returns
            ),
        })


by_asset = pd.DataFrame(
    asset_rows
)


# ============================================================
# YEAR × ASSET
# ============================================================

year_asset_rows = []


for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )

    for (
        year,
        symbol,
    ), group in events.groupby(
        [
            "year",
            "symbol",
        ]
    ):

        returns = (
            group[column]
            .dropna()
            -
            BASE_COST
        )

        year_asset_rows.append({

            "minutes":
                minutes,

            "year":
                year,

            "symbol":
                symbol,

            **summarize(
                returns
            ),
        })


by_year_asset = pd.DataFrame(
    year_asset_rows
)


# ============================================================
# MONTH
# ============================================================

month_rows = []


for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )

    for month, group in events.groupby(
        "month"
    ):

        returns = (
            group[column]
            .dropna()
            -
            BASE_COST
        )

        month_rows.append({

            "minutes":
                minutes,

            "month":
                month,

            **summarize(
                returns
            ),
        })


by_month = pd.DataFrame(
    month_rows
)


# ============================================================
# SEMESTER
# ============================================================

semester_rows = []


for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )

    for semester, group in events.groupby(
        "semester"
    ):

        returns = (
            group[column]
            .dropna()
            -
            BASE_COST
        )

        semester_rows.append({

            "minutes":
                minutes,

            "semester":
                semester,

            **summarize(
                returns
            ),
        })


by_semester = pd.DataFrame(
    semester_rows
)


# ============================================================
# MONTH-BLOCK BOOTSTRAP
#
# Resample whole months.
#
# Preserves within-month dependence better than
# IID trade bootstrap.
# ============================================================

bootstrap_rows = []


for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )

    month_groups = {

        month:
            (
                group[column]
                .dropna()
                .to_numpy(
                    dtype=float
                )
                -
                BASE_COST
            )

        for month, group
        in events.groupby(
            "month"
        )
    }


    months = list(
        month_groups.keys()
    )


    boot_mean = []

    boot_pf = []


    for _ in range(
        BOOTSTRAP_RUNS
    ):

        sampled_months = rng.choice(
            months,
            size=len(months),
            replace=True,
        )


        sampled_returns = np.concatenate(
            [
                month_groups[m]
                for m
                in sampled_months
            ]
        )


        boot_mean.append(
            np.mean(
                sampled_returns
            )
        )


        boot_pf.append(
            profit_factor(
                sampled_returns
            )
        )


    boot_mean = np.asarray(
        boot_mean,
        dtype=float,
    )


    boot_pf = np.asarray(
        boot_pf,
        dtype=float,
    )


    bootstrap_rows.append({

        "minutes":
            minutes,

        "bootstrap_runs":
            BOOTSTRAP_RUNS,

        "mean_ci_low":
            np.quantile(
                boot_mean,
                0.025,
            ),

        "mean_ci_high":
            np.quantile(
                boot_mean,
                0.975,
            ),

        "pf_ci_low":
            np.nanquantile(
                boot_pf,
                0.025,
            ),

        "pf_ci_high":
            np.nanquantile(
                boot_pf,
                0.975,
            ),

        "prob_mean_gt_0":
            np.mean(
                boot_mean > 0
            ),

        "prob_pf_gt_1":
            np.mean(
                boot_pf > 1
            ),

        "prob_pf_ge_1_08":
            np.mean(
                boot_pf >= 1.08
            ),
    })


bootstrap = pd.DataFrame(
    bootstrap_rows
)


# ============================================================
# LEAVE-ONE-ASSET-OUT
#
# Candidate must not depend on one asset.
# ============================================================

loo_asset_rows = []


symbols = sorted(
    events["symbol"]
    .unique()
)


for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )

    for excluded in symbols:

        subset = events[
            events["symbol"]
            !=
            excluded
        ]

        returns = (
            subset[column]
            .dropna()
            -
            BASE_COST
        )

        loo_asset_rows.append({

            "minutes":
                minutes,

            "excluded_asset":
                excluded,

            **summarize(
                returns
            ),
        })


loo_asset = pd.DataFrame(
    loo_asset_rows
)


# ============================================================
# LEAVE-ONE-YEAR-OUT
# ============================================================

loo_year_rows = []


years = sorted(
    events["year"]
    .unique()
)


for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )

    for excluded in years:

        subset = events[
            events["year"]
            !=
            excluded
        ]

        returns = (
            subset[column]
            .dropna()
            -
            BASE_COST
        )

        loo_year_rows.append({

            "minutes":
                minutes,

            "excluded_year":
                excluded,

            **summarize(
                returns
            ),
        })


loo_year = pd.DataFrame(
    loo_year_rows
)


# ============================================================
# CONCENTRATION
#
# How much of total positive P&L comes from best months?
# ============================================================

concentration_rows = []


for minutes, bars in HORIZONS.items():

    column = (
        f"future_long_{bars}"
    )


    month_pnl = (

        events

        .assign(
            net_return=(
                events[column]
                -
                BASE_COST
            )
        )

        .groupby(
            "month"
        )["net_return"]

        .sum()

        .sort_values(
            ascending=False
        )
    )


    total_positive = (
        month_pnl[
            month_pnl > 0
        ]
        .sum()
    )


    top1 = (
        month_pnl
        .head(1)
        .clip(lower=0)
        .sum()
    )


    top3 = (
        month_pnl
        .head(3)
        .clip(lower=0)
        .sum()
    )


    top5 = (
        month_pnl
        .head(5)
        .clip(lower=0)
        .sum()
    )


    concentration_rows.append({

        "minutes":
            minutes,

        "top1_positive_share":
            (
                top1
                /
                total_positive
                if total_positive > 0
                else np.nan
            ),

        "top3_positive_share":
            (
                top3
                /
                total_positive
                if total_positive > 0
                else np.nan
            ),

        "top5_positive_share":
            (
                top5
                /
                total_positive
                if total_positive > 0
                else np.nan
            ),
    })


concentration = pd.DataFrame(
    concentration_rows
)


# ============================================================
# ROBUSTNESS DECISION
#
# This is NOT a production pass.
#
# It only determines whether Branch 14 deserves
# to remain alive for prospective validation.
# ============================================================

decision_rows = []


for minutes in HORIZONS.keys():

    global_row = global_results[
        (
            global_results["minutes"]
            ==
            minutes
        )
        &
        (
            np.isclose(
                global_results["cost"],
                BASE_COST,
            )
        )
    ].iloc[0]


    boot = bootstrap[
        bootstrap["minutes"]
        ==
        minutes
    ].iloc[0]


    asset_loo = loo_asset[
        loo_asset["minutes"]
        ==
        minutes
    ]


    year_loo = loo_year[
        loo_year["minutes"]
        ==
        minutes
    ]


    years_table = by_year[
        by_year["minutes"]
        ==
        minutes
    ]


    assets_table = by_asset[
        by_asset["minutes"]
        ==
        minutes
    ]


    semesters_table = by_semester[
        by_semester["minutes"]
        ==
        minutes
    ]


    pass_global = (

        global_row[
            "profit_factor"
        ]
        >=
        1.08

        and

        global_row[
            "mean_return"
        ]
        >
        0

        and

        global_row[
            "trimmed_mean_5"
        ]
        >
        0

        and

        global_row[
            "winsorized_mean_5"
        ]
        >
        0
    )


    pass_bootstrap = (

        boot[
            "prob_pf_gt_1"
        ]
        >=
        0.95

        and

        boot[
            "prob_mean_gt_0"
        ]
        >=
        0.95
    )


    pass_assets = (

        (
            assets_table[
                "profit_factor"
            ]
            >
            1
        )
        .sum()
        >=
        3
    )


    pass_loo_asset = (

        asset_loo[
            "profit_factor"
        ]
        .min()
        >
        1
    )


    pass_loo_year = (

        year_loo[
            "profit_factor"
        ]
        .min()
        >
        1
    )


    positive_semesters = int(
        (
            semesters_table[
                "profit_factor"
            ]
            >
            1
        )
        .sum()
    )


    total_semesters = len(
        semesters_table
    )


    # Diagnostic requirement:
    # at least 4 of available semesters PF > 1.
    pass_semesters = (
        positive_semesters
        >=
        min(
            4,
            total_semesters,
        )
    )


    overall = (
        pass_global
        and
        pass_bootstrap
        and
        pass_assets
        and
        pass_loo_asset
        and
        pass_loo_year
        and
        pass_semesters
    )


    decision_rows.append({

        "minutes":
            minutes,

        "global_pf":
            global_row[
                "profit_factor"
            ],

        "global_mean":
            global_row[
                "mean_return"
            ],

        "pass_global":
            pass_global,

        "bootstrap_prob_pf_gt_1":
            boot[
                "prob_pf_gt_1"
            ],

        "bootstrap_prob_mean_gt_0":
            boot[
                "prob_mean_gt_0"
            ],

        "pass_bootstrap":
            pass_bootstrap,

        "assets_pf_gt_1":
            int(
                (
                    assets_table[
                        "profit_factor"
                    ]
                    >
                    1
                )
                .sum()
            ),

        "pass_assets":
            pass_assets,

        "worst_loo_asset_pf":
            asset_loo[
                "profit_factor"
            ]
            .min(),

        "pass_loo_asset":
            pass_loo_asset,

        "worst_loo_year_pf":
            year_loo[
                "profit_factor"
            ]
            .min(),

        "pass_loo_year":
            pass_loo_year,

        "positive_semesters":
            positive_semesters,

        "total_semesters":
            total_semesters,

        "pass_semesters":
            pass_semesters,

        "ROBUSTNESS_PASS":
            overall,
    })


decision = pd.DataFrame(
    decision_rows
)


# ============================================================
# DISPLAY %
# ============================================================

def pct(df):

    output = df.copy()

    columns = [
        "cost",
        "mean_return",
        "median_return",
        "trimmed_mean_5",
        "winsorized_mean_5",
        "win_rate",
        "q10",
        "q90",
        "mean_ci_low",
        "mean_ci_high",
        "global_mean",
        "top1_positive_share",
        "top3_positive_share",
        "top5_positive_share",
    ]

    for column in columns:

        if column in output.columns:

            output[column] *= 100

    return output


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    450,
)


# ============================================================
# PRINT
# ============================================================

print()
print("=" * 180)
print("GLOBAL COST CURVE")
print("=" * 180)

print(
    pct(global_results)
    .to_string(index=False)
)


print()
print("=" * 180)
print("BY YEAR @ 0.06%")
print("=" * 180)

print(
    pct(by_year)
    .to_string(index=False)
)


print()
print("=" * 180)
print("BY ASSET @ 0.06%")
print("=" * 180)

print(
    pct(by_asset)
    .to_string(index=False)
)


print()
print("=" * 180)
print("YEAR x ASSET @ 0.06%")
print("=" * 180)

print(
    pct(by_year_asset)
    .to_string(index=False)
)


print()
print("=" * 180)
print("BY SEMESTER @ 0.06%")
print("=" * 180)

print(
    pct(by_semester)
    .to_string(index=False)
)


print()
print("=" * 180)
print("MONTH BLOCK BOOTSTRAP")
print("=" * 180)

print(
    pct(bootstrap)
    .to_string(index=False)
)


print()
print("=" * 180)
print("LEAVE ONE ASSET OUT")
print("=" * 180)

print(
    pct(loo_asset)
    .to_string(index=False)
)


print()
print("=" * 180)
print("LEAVE ONE YEAR OUT")
print("=" * 180)

print(
    pct(loo_year)
    .to_string(index=False)
)


print()
print("=" * 180)
print("PNL CONCENTRATION")
print("=" * 180)

print(
    pct(concentration)
    .to_string(index=False)
)


print()
print("=" * 180)
print("ROBUSTNESS DECISION")
print("=" * 180)

print(
    pct(decision)
    .to_string(index=False)
)


# ============================================================
# SAVE
# ============================================================

global_results.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_global.csv",
    index=False,
)


by_year.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_by_year.csv",
    index=False,
)


by_asset.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_by_asset.csv",
    index=False,
)


by_year_asset.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_year_asset.csv",
    index=False,
)


by_month.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_monthly.csv",
    index=False,
)


by_semester.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_semester.csv",
    index=False,
)


bootstrap.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_bootstrap.csv",
    index=False,
)


loo_asset.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_loo_asset.csv",
    index=False,
)


loo_year.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_loo_year.csv",
    index=False,
)


concentration.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_concentration.csv",
    index=False,
)


decision.to_csv(
    RESULTS_DIR
    /
    "low24h_robustness_decision.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# EXPERIMENTO 42
# BRANCH 18 — LOW BASIS NARROWING ROBUSTNESS
#
# Candidate congelado:
#
# EVENT:
# LOW_BASIS_NARROWING
#
# SIDE:
# LONG
#
# HORIZON:
# 120m
#
# COST:
# 0.06%
#
# Nenhum threshold será alterado.
# Nenhum ativo será removido.
# Nenhum novo horizonte será testado.
#
# Development:
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
    "mark_index_dislocation_events.csv"
)


EVENT_NAME = "LOW_BASIS_NARROWING"

HORIZON_BARS = 24
HORIZON_MINUTES = 120

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
        pd.Series(values)
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
        pd.Series(values)
        .dropna(),
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
# LOAD EVENTS
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


events = (
    events[
        events["event"]
        ==
        EVENT_NAME
    ]
    .copy()
)


events = (
    events

    .dropna(
        subset=[
            "open_time",
            "symbol",
            f"future_long_{HORIZON_BARS}",
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


events["semester"] = (
    events["year"]
    .astype(str)
    +
    "-"
    +
    np.where(
        events["open_time"]
        .dt.month
        <=
        6,
        "H1",
        "H2",
    )
)


events["net_return"] = (
    events[
        f"future_long_{HORIZON_BARS}"
    ]
    -
    BASE_COST
)


print()
print("=" * 140)

print(
    "EXPERIMENTO 42 — "
    "LOW BASIS NARROWING ROBUSTNESS"
)

print("=" * 140)

print(
    f"Eventos carregados: {len(events)}"
)


# ============================================================
# GLOBAL
# ============================================================

global_result = pd.DataFrame(
    [
        {
            "minutes":
                HORIZON_MINUTES,

            "cost":
                BASE_COST,

            **summarize(
                events["net_return"]
            ),
        }
    ]
)


# ============================================================
# YEAR
# ============================================================

year_rows = []


for year, group in events.groupby(
    "year"
):

    year_rows.append({

        "year":
            year,

        **summarize(
            group["net_return"]
        ),
    })


by_year = pd.DataFrame(
    year_rows
)


# ============================================================
# ASSET
# ============================================================

asset_rows = []


for symbol, group in events.groupby(
    "symbol"
):

    asset_rows.append({

        "symbol":
            symbol,

        **summarize(
            group["net_return"]
        ),
    })


by_asset = pd.DataFrame(
    asset_rows
)


# ============================================================
# YEAR × ASSET
# ============================================================

year_asset_rows = []


for (
    year,
    symbol,
), group in events.groupby(
    [
        "year",
        "symbol",
    ]
):

    year_asset_rows.append({

        "year":
            year,

        "symbol":
            symbol,

        **summarize(
            group["net_return"]
        ),
    })


by_year_asset = pd.DataFrame(
    year_asset_rows
)


# ============================================================
# SEMESTER
# ============================================================

semester_rows = []


for semester, group in events.groupby(
    "semester"
):

    semester_rows.append({

        "semester":
            semester,

        **summarize(
            group["net_return"]
        ),
    })


by_semester = pd.DataFrame(
    semester_rows
)


# ============================================================
# MONTH
# ============================================================

month_rows = []


for month, group in events.groupby(
    "month"
):

    month_rows.append({

        "month":
            month,

        **summarize(
            group["net_return"]
        ),
    })


by_month = pd.DataFrame(
    month_rows
)


# ============================================================
# MONTH BLOCK BOOTSTRAP
#
# Reamostra meses inteiros.
# ============================================================

month_groups = {

    month:
        group["net_return"]
        .dropna()
        .to_numpy(
            dtype=float
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
        sampled_returns.mean()
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


bootstrap = pd.DataFrame(
    [
        {
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

            "prob_pf_ge_1_03":
                np.mean(
                    boot_pf >= 1.03
                ),

            "prob_pf_ge_1_08":
                np.mean(
                    boot_pf >= 1.08
                ),
        }
    ]
)


# ============================================================
# LEAVE ONE ASSET OUT
# ============================================================

loo_asset_rows = []


symbols = sorted(
    events["symbol"]
    .unique()
)


for excluded in symbols:

    subset = events[
        events["symbol"]
        !=
        excluded
    ]

    loo_asset_rows.append({

        "excluded_asset":
            excluded,

        **summarize(
            subset["net_return"]
        ),
    })


loo_asset = pd.DataFrame(
    loo_asset_rows
)


# ============================================================
# LEAVE ONE YEAR OUT
# ============================================================

loo_year_rows = []


years = sorted(
    events["year"]
    .unique()
)


for excluded in years:

    subset = events[
        events["year"]
        !=
        excluded
    ]

    loo_year_rows.append({

        "excluded_year":
            excluded,

        **summarize(
            subset["net_return"]
        ),
    })


loo_year = pd.DataFrame(
    loo_year_rows
)


# ============================================================
# PNL CONCENTRATION BY MONTH
# ============================================================

month_pnl = (

    events

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


def positive_share(n):

    if total_positive <= 0:
        return np.nan

    value = (
        month_pnl
        .head(n)
        .clip(lower=0)
        .sum()
    )

    return (
        value
        /
        total_positive
    )


concentration = pd.DataFrame(
    [
        {
            "top1_positive_share":
                positive_share(1),

            "top3_positive_share":
                positive_share(3),

            "top5_positive_share":
                positive_share(5),

            "top10_positive_share":
                positive_share(10),
        }
    ]
)


# ============================================================
# ROBUSTNESS DECISION
#
# Como candidato original tinha PF 1.073:
# não exigimos artificialmente PF>=1.08 aqui.
#
# Mas exigimos evidência estatística e
# estabilidade estrutural para mantê-lo vivo.
# ============================================================

g = global_result.iloc[0]
b = bootstrap.iloc[0]


positive_years = int(
    (
        by_year[
            "profit_factor"
        ]
        >
        1
    )
    .sum()
)


positive_assets = int(
    (
        by_asset[
            "profit_factor"
        ]
        >
        1
    )
    .sum()
)


positive_semesters = int(
    (
        by_semester[
            "profit_factor"
        ]
        >
        1
    )
    .sum()
)


total_semesters = len(
    by_semester
)


positive_months = int(
    (
        by_month[
            "profit_factor"
        ]
        >
        1
    )
    .sum()
)


# ------------------------------------------------------------
# PASS CONDITIONS
#
# Não é production pass.
# Apenas determina se Branch 18 continua viva.
# ------------------------------------------------------------

pass_global = (

    g["profit_factor"]
    >=
    1.03

    and

    g["mean_return"]
    >
    0

    and

    g["trimmed_mean_5"]
    >
    0

    and

    g["winsorized_mean_5"]
    >
    0
)


pass_bootstrap = (

    b["prob_pf_gt_1"]
    >=
    0.95

    and

    b["prob_mean_gt_0"]
    >=
    0.95
)


pass_assets = (
    positive_assets
    >=
    3
)


pass_loo_asset = (

    loo_asset[
        "profit_factor"
    ]
    .min()
    >
    1
)


pass_loo_year = (

    loo_year[
        "profit_factor"
    ]
    .min()
    >
    1
)


# Majority of semesters
pass_semesters = (

    positive_semesters
    >=
    4
)


# At least half months positive
pass_months = (

    positive_months
    >=
    int(
        np.ceil(
            len(by_month)
            *
            0.50
        )
    )
)


ROBUSTNESS_PASS = (

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
    and
    pass_months
)


decision = pd.DataFrame(
    [
        {
            "global_pf":
                g["profit_factor"],

            "global_mean":
                g["mean_return"],

            "pass_global":
                pass_global,

            "bootstrap_prob_pf_gt_1":
                b["prob_pf_gt_1"],

            "bootstrap_prob_mean_gt_0":
                b["prob_mean_gt_0"],

            "bootstrap_pf_ci_low":
                b["pf_ci_low"],

            "pass_bootstrap":
                pass_bootstrap,

            "years_pf_gt_1":
                positive_years,

            "total_years":
                len(by_year),

            "assets_pf_gt_1":
                positive_assets,

            "total_assets":
                len(by_asset),

            "pass_assets":
                pass_assets,

            "worst_loo_asset_pf":
                loo_asset[
                    "profit_factor"
                ]
                .min(),

            "pass_loo_asset":
                pass_loo_asset,

            "worst_loo_year_pf":
                loo_year[
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

            "positive_months":
                positive_months,

            "total_months":
                len(by_month),

            "pass_months":
                pass_months,

            "ROBUSTNESS_PASS":
                ROBUSTNESS_PASS,
        }
    ]
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
        "top10_positive_share",
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
    480,
)


# ============================================================
# PRINT
# ============================================================

print()
print("=" * 180)
print("GLOBAL @ 0.06%")
print("=" * 180)

print(
    pct(global_result)
    .to_string(index=False)
)


print()
print("=" * 180)
print("BY YEAR")
print("=" * 180)

print(
    pct(by_year)
    .to_string(index=False)
)


print()
print("=" * 180)
print("BY ASSET")
print("=" * 180)

print(
    pct(by_asset)
    .to_string(index=False)
)


print()
print("=" * 180)
print("YEAR x ASSET")
print("=" * 180)

print(
    pct(by_year_asset)
    .to_string(index=False)
)


print()
print("=" * 180)
print("BY SEMESTER")
print("=" * 180)

print(
    pct(by_semester)
    .to_string(index=False)
)


print()
print("=" * 180)
print("BY MONTH")
print("=" * 180)

print(
    pct(by_month)
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

global_result.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_global.csv",
    index=False,
)

by_year.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_by_year.csv",
    index=False,
)

by_asset.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_by_asset.csv",
    index=False,
)

by_year_asset.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_year_asset.csv",
    index=False,
)

by_semester.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_semester.csv",
    index=False,
)

by_month.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_monthly.csv",
    index=False,
)

bootstrap.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_bootstrap.csv",
    index=False,
)

loo_asset.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_loo_asset.csv",
    index=False,
)

loo_year.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_loo_year.csv",
    index=False,
)

concentration.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_concentration.csv",
    index=False,
)

decision.to_csv(
    RESULTS_DIR
    /
    "low_narrow_robustness_decision.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
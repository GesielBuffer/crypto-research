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
# FROZEN DEFINITIONS
# ============================================================

LOOKBACK = 288 * 7
MIN_PERIODS = 288 * 3

HIGH_QUANTILE = 0.975

Z_THRESHOLD = 4.0

HORIZON = 6

FRESH_LOOKBACK = 12   # 60 minutos


COSTS = [
    0.0004,
    0.0006,
    0.0008,
]


BOOTSTRAP_ITERATIONS = 2000
RANDOM_SEED = 42


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


        temp = load_csv(path)

        temp["period"] = period

        frames.append(temp)


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

        .sort_values("open_time")

        .reset_index(drop=True)

    )


    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True,
    )


    return df


# ============================================================
# PF
# ============================================================

def profit_factor(returns):

    values = (
        pd.Series(returns)
        .dropna()
    )


    positive = (
        values[
            values > 0
        ]
        .sum()
    )


    negative = (
        values[
            values < 0
        ]
        .abs()
        .sum()
    )


    if negative == 0:

        if positive > 0:
            return np.inf

        return np.nan


    return positive / negative


# ============================================================
# TRIMMED
# ============================================================

def trimmed_mean(
    returns,
    trim=0.05,
):

    values = np.sort(

        np.asarray(

            pd.Series(
                returns
            )
            .dropna(),

            dtype=float,

        )

    )


    if len(values) == 0:
        return np.nan


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
# WINSORIZED
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
# BLOCK BOOTSTRAP
# ============================================================

def month_block_bootstrap(
    trades,
    return_column,
):

    months = sorted(

        trades[
            "period"
        ].unique()

    )


    blocks = {

        month:

            trades.loc[

                trades[
                    "period"
                ]
                ==
                month,

                return_column,

            ]
            .dropna()
            .to_numpy()

        for month in months

    }


    rng = np.random.default_rng(
        RANDOM_SEED
    )


    means = []
    pfs = []


    for _ in range(
        BOOTSTRAP_ITERATIONS
    ):


        selected = rng.choice(

            months,

            size=len(months),

            replace=True,

        )


        pieces = [

            blocks[month]

            for month in selected

            if len(
                blocks[month]
            )
            > 0

        ]


        sample = np.concatenate(
            pieces
        )


        means.append(
            sample.mean()
        )


        pfs.append(
            profit_factor(sample)
        )


    means = np.asarray(means)
    pfs = np.asarray(pfs)


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
            np.quantile(
                pfs,
                0.025,
            ),

        "pf_ci_high":
            np.quantile(
                pfs,
                0.975,
            ),

        "prob_mean_gt_0":
            (
                means > 0
            ).mean(),

        "prob_pf_gt_1":
            (
                pfs > 1
            ).mean(),

    }


# ============================================================
# BUILD EVENTS
# ============================================================

frames = []


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
    # RETURN
    # ========================================================

    df["ret_5m"] = (

        df["close"]
        /
        df["open"]
        -
        1

    )


    # ========================================================
    # VOLATILITY
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
    # QUANTILE
    # ========================================================

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
    # Z
    # ========================================================

    df["return_z"] = (

        df["ret_5m"]
        /
        df["ret_std_7d"]

    )


    # ========================================================
    # RAW EXTREME UP
    # ========================================================

    extreme_up = (

        df["ret_5m"]
        >=
        df["ret_q975"]

    ).fillna(False)


    # ========================================================
    # RAW Z>=4 CANDIDATE
    # ========================================================

    candidate_raw = (

        extreme_up

        &

        (
            df["return_z"]
            >=
            Z_THRESHOLD
        )

    )


    # ========================================================
    # PRIOR EXTREMES DURING PREVIOUS 60 MINUTES
    #
    # SHIFT(1):
    # current candle never participates.
    # ========================================================

    prior_extreme_count = (

        extreme_up
        .astype(int)

        .shift(1)

        .rolling(
            FRESH_LOOKBACK,
            min_periods=1,
        )

        .sum()

        .fillna(0)

    )


    # ========================================================
    # CANONICAL 30M EVENTS
    # ========================================================

    canonical = (

        non_overlapping_mask(

            candidate_raw,

            HORIZON,

        )

    )


    # ========================================================
    # CLASSIFICATION
    # ========================================================

    fresh = (

        canonical

        &

        (
            prior_extreme_count
            ==
            0
        )

    )


    clustered = (

        canonical

        &

        (
            prior_extreme_count
            >
            0
        )

    )


    # ========================================================
    # LEGACY FOR COMPARISON ONLY
    # ========================================================

    legacy = (

        non_overlapping_mask(

            extreme_up,

            12,

        )

        &

        (
            df["return_z"]
            >=
            Z_THRESHOLD
        )

    )


    # ========================================================
    # TARGET
    # ========================================================

    entry = (
        df["open"]
        .shift(-1)
    )


    exit_price = (
        df["close"]
        .shift(-HORIZON)
    )


    df["future_return"] = (

        exit_price
        /
        entry
        -
        1

    )


    masks = {

        "CANONICAL_ALL":
            canonical,

        "FRESH_60":
            fresh,

        "NOT_FRESH_60":
            clustered,

        "LEGACY_REFERENCE":
            legacy,

    }


    for variant, mask in masks.items():


        temp = df.loc[
            mask
        ].copy()


        temp = temp.dropna(

            subset=[

                "future_return",
                "return_z",

            ]

        )


        temp[
            "variant"
        ] = variant


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


        temp[
            "prior_extreme_count_60m"
        ] = (

            prior_extreme_count.loc[
                temp.index
            ]

        )


        frames.append(

            temp[

                [
                    "variant",

                    "symbol",
                    "period",
                    "year",
                    "open_time",

                    "return_z",

                    "prior_extreme_count_60m",

                    "future_return",

                ]

            ]

        )


# ============================================================
# CONCAT
# ============================================================

trades = pd.concat(
    frames,
    ignore_index=True,
)


print()

print("=" * 180)

print(
    "CONTAGEM"
)

print("=" * 180)

print()


print(

    trades

    .groupby("variant")

    .size()

    .rename("samples")

    .to_string()

)


# ============================================================
# COST COLUMNS
# ============================================================

for cost in COSTS:


    column = (
        f"net_{int(cost * 10000)}bps"
    )


    trades[column] = (

        trades[
            "future_return"
        ]

        -
        cost

    )


# ============================================================
# GLOBAL
# ============================================================

global_rows = []


for variant, group in trades.groupby(
    "variant"
):


    for cost in COSTS:


        column = (
            f"net_{int(cost * 10000)}bps"
        )


        global_rows.append({

            "variant":
                variant,

            "cost":
                cost,

            **summarize(
                group[column]
            ),

        })


global_results = pd.DataFrame(
    global_rows
)


# ============================================================
# BY YEAR
# ============================================================

year_rows = []


for (
    variant,
    year,
), group in trades.groupby(

    [
        "variant",
        "year",
    ]

):


    for cost in COSTS:


        column = (
            f"net_{int(cost * 10000)}bps"
        )


        year_rows.append({

            "variant":
                variant,

            "year":
                year,

            "cost":
                cost,

            **summarize(
                group[column]
            ),

        })


by_year = pd.DataFrame(
    year_rows
)


# ============================================================
# BY ASSET
# ============================================================

asset_rows = []


for (
    variant,
    symbol,
), group in trades.groupby(

    [
        "variant",
        "symbol",
    ]

):


    for cost in COSTS:


        column = (
            f"net_{int(cost * 10000)}bps"
        )


        asset_rows.append({

            "variant":
                variant,

            "symbol":
                symbol,

            "cost":
                cost,

            **summarize(
                group[column]
            ),

        })


by_asset = pd.DataFrame(
    asset_rows
)


# ============================================================
# BOOTSTRAP
# ============================================================

bootstrap_rows = []


for variant, group in trades.groupby(
    "variant"
):


    for cost in COSTS:


        column = (
            f"net_{int(cost * 10000)}bps"
        )


        bootstrap_rows.append({

            "variant":
                variant,

            "cost":
                cost,

            **month_block_bootstrap(
                group,
                column,
            ),

        })


bootstrap = pd.DataFrame(
    bootstrap_rows
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

        "mean_ci_low",
        "mean_ci_high",

        "prob_mean_gt_0",
        "prob_pf_gt_1",

    ]:

        if column in result.columns:

            result[column] *= 100


    return result


global_display = percent_display(
    global_results
)

year_display = percent_display(
    by_year
)

asset_display = percent_display(
    by_asset
)

bootstrap_display = percent_display(
    bootstrap
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    300,
)


print()

print("=" * 190)

print(
    "EXPERIMENTO 23 — "
    "FRESH EXTREME IMPULSE"
)

print("=" * 190)

print()


print(
    global_display.to_string(
        index=False
    )
)


print()

print("=" * 190)

print("POR ANO")

print("=" * 190)

print()


print(

    year_display

    .sort_values(
        [
            "variant",
            "cost",
            "year",
        ]
    )

    .to_string(
        index=False
    )

)


print()

print("=" * 190)

print("POR ATIVO")

print("=" * 190)

print()


print(

    asset_display

    .sort_values(
        [
            "variant",
            "cost",
            "symbol",
        ]
    )

    .to_string(
        index=False
    )

)


print()

print("=" * 190)

print("MONTH-BLOCK BOOTSTRAP")

print("=" * 190)

print()


print(

    bootstrap_display

    .sort_values(
        [
            "variant",
            "cost",
        ]
    )

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

trades.to_csv(

    RESULTS_DIR
    / "fresh_impulse_trades.csv",

    index=False,

)


global_results.to_csv(

    RESULTS_DIR
    / "fresh_impulse_global.csv",

    index=False,

)


by_year.to_csv(

    RESULTS_DIR
    / "fresh_impulse_by_year.csv",

    index=False,

)


by_asset.to_csv(

    RESULTS_DIR
    / "fresh_impulse_by_asset.csv",

    index=False,

)


bootstrap.to_csv(

    RESULTS_DIR
    / "fresh_impulse_bootstrap.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
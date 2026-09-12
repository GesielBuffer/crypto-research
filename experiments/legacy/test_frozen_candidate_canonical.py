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
# DEFINIÇÃO ORIGINAL DO EXTREME EVENT
# ============================================================

LOOKBACK = 288 * 7

MIN_PERIODS = 288 * 3

HIGH_QUANTILE = 0.975


# ============================================================
# CANDIDATO CONGELADO
# ============================================================

Z_THRESHOLD = 4.0

HORIZON = 6       # 30 minutos


# ============================================================
# CUSTOS
# ============================================================

COSTS = [
    0.0004,
    0.0006,
    0.0008,
]


BOOTSTRAP_ITERATIONS = 2000

RANDOM_SEED = 42


# ============================================================
# VARIANTES
#
# NÃO SÃO PARÂMETROS PARA OTIMIZAR.
#
# Servem apenas para decompor
# o erro metodológico anterior.
# ============================================================

VARIANTS = [

    "LEGACY_EVENT_FIRST_60M",

    "CANDIDATE_FIRST_60M",

    "CANDIDATE_FIRST_30M",

]


# ============================================================
# LOAD CONTÍNUO
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


    df["open_time"] = pd.to_datetime(

        df["open_time"],

        utc=True,

    )


    return df


# ============================================================
# PROFIT FACTOR
# ============================================================

def profit_factor(returns):

    values = (

        pd.Series(
            returns
        )

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


    return (

        np.clip(
            values,
            lower,
            upper,
        )

        .mean()

    )


# ============================================================
# LOSING STREAK
# ============================================================

def max_losing_streak(
    returns,
):

    streak = 0
    maximum = 0


    for value in returns:

        if value < 0:

            streak += 1

            maximum = max(
                maximum,
                streak,
            )

        else:

            streak = 0


    return maximum


# ============================================================
# SUMMARY
# ============================================================

def summarize(returns):

    values = (

        pd.Series(
            returns
        )

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

            "max_losing_streak": np.nan,

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

        "max_losing_streak":
            max_losing_streak(
                values.to_numpy()
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
# MONTH BLOCK BOOTSTRAP
# ============================================================

def month_block_bootstrap(
    trades,
    return_column,
):

    months = sorted(

        trades[
            "period"
        ]

        .unique()

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

            for month
            in selected

            if len(
                blocks[month]
            )
            > 0

        ]


        if not pieces:
            continue


        sample = np.concatenate(
            pieces
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

all_events = []


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
    # RETURN DO CANDLE
    # ========================================================

    df["ret_5m"] = (

        df["close"]
        /
        df["open"]
        -
        1

    )


    # ========================================================
    # STD 7D
    #
    # Somente passado.
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
    # 97.5% QUANTILE
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
    # RETURN Z
    # ========================================================

    df["return_z"] = (

        df["ret_5m"]
        /
        df["ret_std_7d"]

    )


    # ========================================================
    # EXTREME UP RAW
    # ========================================================

    extreme_up_raw = (

        df["ret_5m"]
        >=
        df["ret_q975"]

    ).fillna(False)


    # ========================================================
    # CANDIDATE RAW
    #
    # ESTA É A REGRA FINAL ANTES
    # DO NON-OVERLAP.
    # ========================================================

    candidate_raw = (

        extreme_up_raw

        &

        (
            df["return_z"]
            >=
            Z_THRESHOLD
        )

    ).fillna(False)


    # ========================================================
    # A — LEGACY
    #
    # Primeiro filtra todos os EXTREME_UP
    # por 60m.
    #
    # Só depois aplica z>=4.
    #
    # Deve reproduzir Experimentos 20/21.
    # ========================================================

    legacy_event_mask = (

        non_overlapping_mask(

            extreme_up_raw,

            12,

        )

    )


    legacy_mask = (

        legacy_event_mask

        &

        (
            df["return_z"]
            >=
            Z_THRESHOLD
        )

    )


    # ========================================================
    # B — CANDIDATE FIRST / 60M
    #
    # Corrige apenas a ordem.
    # ========================================================

    candidate_first_60 = (

        non_overlapping_mask(

            candidate_raw,

            12,

        )

    )


    # ========================================================
    # C — CANDIDATE FIRST / 30M
    #
    # IMPLEMENTAÇÃO CANÔNICA FINAL.
    # ========================================================

    candidate_first_30 = (

        non_overlapping_mask(

            candidate_raw,

            HORIZON,

        )

    )


    masks = {

        "LEGACY_EVENT_FIRST_60M":
            legacy_mask,

        "CANDIDATE_FIRST_60M":
            candidate_first_60,

        "CANDIDATE_FIRST_30M":
            candidate_first_30,

    }


    # ========================================================
    # FUTURE RETURN
    #
    # signal candle fecha em t
    # entry OPEN t+1
    # exit CLOSE t+6
    # ========================================================

    entry = (

        df["open"]
        .shift(-1)

    )


    exit_price = (

        df["close"]
        .shift(-HORIZON)

    )


    df["future_long_30m"] = (

        exit_price
        /
        entry
        -
        1

    )


    # ========================================================
    # SAVE
    # ========================================================

    for variant, mask in masks.items():


        temp = df.loc[
            mask
        ].copy()


        temp = temp.dropna(

            subset=[

                "return_z",

                "future_long_30m",

            ]

        )


        if temp.empty:
            continue


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
            "entry_time"
        ] = (

            temp[
                "open_time"
            ]

            +
            pd.Timedelta(
                minutes=5
            )

        )


        temp[
            "exit_time"
        ] = (

            temp[
                "open_time"
            ]

            +
            pd.Timedelta(
                minutes=35
            )

        )


        all_events.append(

            temp[

                [
                    "variant",

                    "symbol",
                    "period",
                    "year",

                    "open_time",

                    "entry_time",
                    "exit_time",

                    "ret_5m",
                    "return_z",

                    "future_long_30m",

                ]

            ]

        )


# ============================================================
# CONCAT
# ============================================================

trades = pd.concat(

    all_events,

    ignore_index=True,

)


trades = (

    trades

    .sort_values(

        [
            "variant",
            "entry_time",
            "symbol",
        ]

    )

    .reset_index(
        drop=True
    )

)


# ============================================================
# SANITY CHECK
# ============================================================

print()

print("=" * 190)

print(
    "SANITY CHECK — CONTAGEM"
)

print("=" * 190)

print()


counts = (

    trades

    .groupby(
        "variant"
    )

    .size()

    .rename(
        "samples"
    )

    .reset_index()

)


print(
    counts.to_string(
        index=False
    )
)


print()

print(
    "Esperado para "
    "LEGACY_EVENT_FIRST_60M: "
    "aproximadamente 1677."
)


# ============================================================
# COST COLUMNS
# ============================================================

for cost in COSTS:


    name = (
        f"net_{int(cost * 10000)}bps"
    )


    trades[
        name
    ] = (

        trades[
            "future_long_30m"
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


        stats = summarize(
            group[column]
        )


        global_rows.append({

            "variant":
                variant,

            "cost":
                cost,

            **stats,

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
# MONTHLY ASSET WINDOWS
# ============================================================

monthly_rows = []


for (
    variant,
    period,
    symbol,
), group in trades.groupby(

    [
        "variant",
        "period",
        "symbol",
    ]

):


    for cost in COSTS:


        column = (
            f"net_{int(cost * 10000)}bps"
        )


        monthly_rows.append({

            "variant":
                variant,

            "period":
                period,

            "symbol":
                symbol,

            "cost":
                cost,

            **summarize(
                group[column]
            ),

        })


monthly = pd.DataFrame(
    monthly_rows
)


# ============================================================
# MONTHLY STABILITY
# ============================================================

monthly_stability = (

    monthly

    .groupby(

        [
            "variant",
            "cost",
        ],

        as_index=False,

    )

    .agg(

        windows=(
            "period",
            "count",
        ),

        positive_windows=(

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

    )

)


monthly_stability[
    "positive_window_rate"
] = (

    monthly_stability[
        "positive_windows"
    ]

    /
    monthly_stability[
        "windows"
    ]

)


# ============================================================
# BLOCK BOOTSTRAP
# ============================================================

bootstrap_rows = []


for variant, group in trades.groupby(
    "variant"
):


    for cost in COSTS:


        column = (
            f"net_{int(cost * 10000)}bps"
        )


        stats = month_block_bootstrap(

            group,

            column,

        )


        bootstrap_rows.append({

            "variant":
                variant,

            "cost":
                cost,

            **stats,

        })


bootstrap = pd.DataFrame(
    bootstrap_rows
)


# ============================================================
# DISPLAY
# ============================================================

def percent_display(df):

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

        "positive_window_rate",

        "median_window_return",

        "mean_ci_low",
        "mean_ci_high",

        "prob_mean_gt_0",
        "prob_pf_gt_1",

    ]


    for column in columns:

        if column in output.columns:

            output[
                column
            ] *= 100


    return output


global_display = percent_display(
    global_results
)

year_display = percent_display(
    by_year
)

asset_display = percent_display(
    by_asset
)

monthly_display = percent_display(
    monthly_stability
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
    320,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 200)

print(
    "EXPERIMENTO 22 — "
    "CANONICAL FROZEN CANDIDATE"
)

print("=" * 200)

print()


print(
    global_display.to_string(
        index=False
    )
)


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
            "variant",
            "cost",
        ]

    )

    .to_string(
        index=False
    )

)


print()

print("=" * 200)

print(
    "MONTH-BLOCK BOOTSTRAP"
)

print("=" * 200)

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
    / "frozen_canonical_trades.csv",

    index=False,

)


global_results.to_csv(

    RESULTS_DIR
    / "frozen_canonical_global.csv",

    index=False,

)


by_year.to_csv(

    RESULTS_DIR
    / "frozen_canonical_by_year.csv",

    index=False,

)


by_asset.to_csv(

    RESULTS_DIR
    / "frozen_canonical_by_asset.csv",

    index=False,

)


monthly.to_csv(

    RESULTS_DIR
    / "frozen_canonical_monthly.csv",

    index=False,

)


monthly_stability.to_csv(

    RESULTS_DIR
    / "frozen_canonical_monthly_stability.csv",

    index=False,

)


bootstrap.to_csv(

    RESULTS_DIR
    / "frozen_canonical_bootstrap.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
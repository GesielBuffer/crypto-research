from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv

from research.indicators import (
    add_all_indicators,
)

from research.features import (
    add_all_features,
)

from research.targets import (
    add_future_targets,
)

from research.statistics import (
    analyze_condition,
)

from research.validation import (
    non_overlapping_mask,
)


# ============================================================
# CONFIG
# ============================================================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]


PERIODS = [

    (
        "2026-02",
        "2026-02-01",
        "2026-03-01",
    ),

    (
        "2026-03",
        "2026-03-01",
        "2026-04-01",
    ),

    (
        "2026-04",
        "2026-04-01",
        "2026-05-01",
    ),

    (
        "2026-05",
        "2026-05-01",
        "2026-06-01",
    ),

    (
        "2026-06",
        "2026-06-01",
        "2026-07-01",
    ),

    (
        "2026-07",
        "2026-07-01",
        "2026-08-01",
    ),

]


INTERVAL = "5m"

HORIZON = 12


# ============================================================
# CUSTOS
# ============================================================

COSTS = [

    0.0000,   # 0.00%
    0.0002,   # 0.02%
    0.0004,   # 0.04%
    0.0006,   # 0.06%
    0.0008,   # 0.08%
    0.0010,   # 0.10%

]


DATA_DIR = Path(
    "data"
)

RESULTS_DIR = Path(
    "results"
)


RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# RESULTADOS
# ============================================================

results = []


# ============================================================
# LOOP
# ============================================================

for symbol in SYMBOLS:

    print()

    print(
        "=" * 100
    )

    print(
        f"ATIVO: {symbol}"
    )

    print(
        "=" * 100
    )


    for (
        period,
        start_date,
        end_date,
    ) in PERIODS:


        filename = (

            f"{symbol}_"
            f"{INTERVAL}_"
            f"{start_date}_"
            f"{end_date}.csv"

        )


        path = (
            DATA_DIR
            / filename
        )


        if not path.exists():

            print(
                f"Arquivo não encontrado: "
                f"{path}"
            )

            continue


        # ====================================================
        # DATA
        # ====================================================

        df = load_csv(
            path
        )


        # ====================================================
        # INDICADORES
        # ====================================================

        df = add_all_indicators(
            df
        )


        # ====================================================
        # FEATURES
        # ====================================================

        df = add_all_features(
            df
        )


        # ====================================================
        # TARGET
        # ====================================================

        df = add_future_targets(

            df,

            [HORIZON],

        )


        # ====================================================
        # BASE SHORT
        # ====================================================

        base_short = (

            (df["ema_9"] < df["ema_21"])

            &

            (df["ema_21"] < df["ema_35"])

            &

            (df["macd_hist"] < 0)

            &

            (df["adx"] >= 25)

            &

            (df["volume_ratio"] >= 1.5)

        )


        # ====================================================
        # REGIMES ATR
        # ====================================================

        atr_contracting = (

            df["atr_expansion"] <= 1

        )


        atr_expanding = (

            df["atr_expansion"] > 1

        )


        # ====================================================
        # EXPERIMENTOS
        # ====================================================

        experiments = {

            "BASE_SHORT":
                base_short,

            "ATR_CONTRACTING":
                base_short
                & atr_contracting,

            "ATR_EXPANDING":
                base_short
                & atr_expanding,

        }


        # ====================================================
        # LOOP EXPERIMENTOS
        # ====================================================

        for (
            experiment,
            original_mask,
        ) in experiments.items():


            mask = non_overlapping_mask(

                original_mask,

                HORIZON,

            )


            # ================================================
            # CUSTOS
            # ================================================

            for cost in COSTS:


                stats = analyze_condition(

                    df=df,

                    mask=mask,

                    side="SHORT",

                    horizon=HORIZON,

                    cost=cost,

                )


                results.append({

                    "symbol": symbol,

                    "period": period,

                    "experiment": experiment,

                    "cost": cost,

                    **stats,

                })


# ============================================================
# DATAFRAME
# ============================================================

results_df = pd.DataFrame(
    results
)


# ============================================================
# LIMPA INF
# ============================================================

results_df[
    "profit_factor_clean"
] = (

    results_df[
        "profit_factor"
    ]

    .replace(

        [
            np.inf,
            -np.inf,
        ],

        np.nan,

    )

)


# ============================================================
# RESUMO GLOBAL
# ============================================================

summary = (

    results_df

    .groupby(

        [
            "experiment",
            "cost",
        ],

        as_index=False,

    )

    .agg(

        windows=(
            "period",
            "count",
        ),

        total_samples=(
            "samples",
            "sum",
        ),

        positive_windows=(

            "mean_return",

            lambda x: int(
                (x > 0).sum()
            ),

        ),

        positive_window_rate=(

            "mean_return",

            lambda x: (
                x > 0
            ).mean(),

        ),

        pf_above_1_rate=(

            "profit_factor_clean",

            lambda x: (
                x > 1
            ).mean(),

        ),

        median_profit_factor=(

            "profit_factor_clean",

            "median",

        ),

        median_mean_return=(

            "mean_return",

            "median",

        ),

        median_win_rate=(

            "win_rate",

            "median",

        ),

    )

)


# ============================================================
# RESUMO POR ATIVO
# ============================================================

asset_summary = (

    results_df

    .groupby(

        [
            "symbol",
            "experiment",
            "cost",
        ],

        as_index=False,

    )

    .agg(

        windows=(
            "period",
            "count",
        ),

        samples=(
            "samples",
            "sum",
        ),

        positive_windows=(

            "mean_return",

            lambda x: int(
                (x > 0).sum()
            ),

        ),

        mean_return=(

            "mean_return",

            "mean",

        ),

        median_profit_factor=(

            "profit_factor_clean",

            "median",

        ),

    )

)


# ============================================================
# RESUMO POR MÊS
# ============================================================

period_summary = (

    results_df

    .groupby(

        [
            "period",
            "experiment",
            "cost",
        ],

        as_index=False,

    )

    .agg(

        assets=(
            "symbol",
            "count",
        ),

        samples=(
            "samples",
            "sum",
        ),

        positive_assets=(

            "mean_return",

            lambda x: int(
                (x > 0).sum()
            ),

        ),

        mean_return=(

            "mean_return",

            "mean",

        ),

        median_profit_factor=(

            "profit_factor_clean",

            "median",

        ),

    )

)


# ============================================================
# SALVA
# ============================================================

results_df.to_csv(

    RESULTS_DIR
    / "atr_candidate_detailed.csv",

    index=False,

)


summary.to_csv(

    RESULTS_DIR
    / "atr_candidate_summary.csv",

    index=False,

)


asset_summary.to_csv(

    RESULTS_DIR
    / "atr_candidate_by_asset.csv",

    index=False,

)


period_summary.to_csv(

    RESULTS_DIR
    / "atr_candidate_by_period.csv",

    index=False,

)


# ============================================================
# DISPLAY GLOBAL
# ============================================================

display = (
    summary.copy()
)


display[
    "cost"
] *= 100


display[
    "positive_window_rate"
] *= 100


display[
    "pf_above_1_rate"
] *= 100


display[
    "median_mean_return"
] *= 100


display[
    "median_win_rate"
] *= 100


display = (

    display

    .sort_values(

        [
            "experiment",
            "cost",
        ]

    )

)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    250,
)


print()

print(
    "=" * 170
)

print(
    "EXPERIMENTO 4 — "
    "ATR CANDIDATE COST VALIDATION"
)

print(
    "=" * 170
)

print()


print(

    display.to_string(
        index=False
    )

)


# ============================================================
# ATIVOS — CUSTO ZERO
# ============================================================

asset_zero = asset_summary[

    asset_summary[
        "cost"
    ] == 0

].copy()


asset_zero[
    "mean_return"
] *= 100


print()

print(
    "=" * 170
)

print(
    "ATR CANDIDATE — "
    "RESULTADO BRUTO POR ATIVO"
)

print(
    "=" * 170
)

print()


print(

    asset_zero[
        asset_zero[
            "experiment"
        ]
        ==
        "ATR_CONTRACTING"
    ]

    .to_string(
        index=False
    )

)


# ============================================================
# MESES — CUSTO ZERO
# ============================================================

period_zero = period_summary[

    period_summary[
        "cost"
    ] == 0

].copy()


period_zero[
    "mean_return"
] *= 100


print()

print(
    "=" * 170
)

print(
    "ATR CANDIDATE — "
    "RESULTADO BRUTO POR MÊS"
)

print(
    "=" * 170
)

print()


print(

    period_zero[
        period_zero[
            "experiment"
        ]
        ==
        "ATR_CONTRACTING"
    ]

    .to_string(
        index=False
    )

)

print()

print("=" * 170)

print(
    "ATR CONTRACTING — "
    "SENSIBILIDADE A CUSTOS"
)

print("=" * 170)

cost_focus = display[
    display["experiment"]
    == "ATR_CONTRACTING"
].copy()

columns = [
    "cost",
    "windows",
    "total_samples",
    "positive_windows",
    "positive_window_rate",
    "pf_above_1_rate",
    "median_profit_factor",
    "median_mean_return",
    "median_win_rate",
]

print(
    cost_focus[
        columns
    ].to_string(
        index=False
    )
)
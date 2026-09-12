from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import (
    load_csv,
)

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

from research.regimes import (
    build_regimes,
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
# IMPORTANTE
#
# Primeiro procuramos EDGE BRUTO.
#
# Portanto:
#
# custo = ZERO
#
# Depois aplicaremos custo nos candidatos
# que sobreviverem.
# ============================================================

COST = 0.0


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
        f"ANALISANDO {symbol}"
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
        # NOSSO SINAL BASE
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
        # REGIMES
        # ====================================================

        regimes = build_regimes(
            df
        )


        # ====================================================
        # BASELINE
        # ====================================================

        experiments = {

            "BASE_SHORT": (
                base_short
            )

        }


        # ====================================================
        # BASE + CADA REGIME
        # ====================================================

        for (
            regime_name,
            regime_mask,
        ) in regimes.items():

            experiments[
                regime_name
            ] = (

                base_short
                & regime_mask

            )


        # ====================================================
        # EXECUTA
        # ====================================================

        for (
            experiment_name,
            mask,
        ) in experiments.items():


            clean_mask = (
                non_overlapping_mask(

                    mask,

                    HORIZON,

                )
            )


            stats = analyze_condition(

                df=df,

                mask=clean_mask,

                side="SHORT",

                horizon=HORIZON,

                cost=COST,

            )


            results.append({

                "symbol": symbol,

                "period": period,

                "experiment": experiment_name,

                **stats,

            })


# ============================================================
# DATAFRAME
# ============================================================

results_df = pd.DataFrame(
    results
)


# ============================================================
# REMOVE PF INFINITO PARA RESUMO
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
# RESUMO
# ============================================================

summary = (

    results_df

    .groupby(
        "experiment",
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

        median_samples=(
            "samples",
            "median",
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

        worst_mean_return=(

            "mean_return",

            "min",

        ),

        best_mean_return=(

            "mean_return",

            "max",

        ),

    )

)


# ============================================================
# DISPLAY
# ============================================================

display = summary.copy()


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


display[
    "worst_mean_return"
] *= 100


display[
    "best_mean_return"
] *= 100


# ============================================================
# ORDENAR
# ============================================================

display = (

    display

    .sort_values(

        [

            "positive_window_rate",

            "median_profit_factor",

        ],

        ascending=[

            False,

            False,

        ],

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
    "=" * 180
)

print(
    "EXPERIMENTO 3 — "
    "REGIME DIAGNOSTIC"
)

print(
    "EDGE BRUTO | "
    "SEM CUSTOS | "
    "60 MIN | "
    "NON OVERLAP"
)

print(
    "=" * 180
)

print()


columns = [

    "experiment",

    "windows",

    "total_samples",

    "median_samples",

    "positive_windows",

    "positive_window_rate",

    "pf_above_1_rate",

    "median_profit_factor",

    "median_mean_return",

    "median_win_rate",

    "worst_mean_return",

    "best_mean_return",

]


print(

    display[
        columns
    ].to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

results_df.to_csv(

    RESULTS_DIR
    / "regime_diagnostic_detailed.csv",

    index=False,

)


summary.to_csv(

    RESULTS_DIR
    / "regime_diagnostic_summary.csv",

    index=False,

)


print()

print(
    "=" * 100
)

print(
    "Arquivos salvos."
)

print(
    "=" * 100
)
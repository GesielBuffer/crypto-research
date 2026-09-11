from pathlib import Path

import pandas as pd

from research.binance_data import (
    fetch_klines,
    load_csv,
    save_csv,
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
# CUSTOS A TESTAR
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


DATA_DIR.mkdir(
    exist_ok=True,
)

RESULTS_DIR.mkdir(
    exist_ok=True,
)


# ============================================================
# LOAD DATA
# ============================================================

def load_data(
    symbol,
    start_date,
    end_date,
):

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


    if path.exists():

        return load_csv(
            path
        )


    df = fetch_klines(

        symbol,

        INTERVAL,

        start_date,

        end_date,

    )


    save_csv(
        df,
        path,
    )


    return df


# ============================================================
# RESULTADOS
# ============================================================

results = []


# ============================================================
# LOOP
# ============================================================

for symbol in SYMBOLS:

    for (
        period,
        start_date,
        end_date,
    ) in PERIODS:


        df = load_data(

            symbol,

            start_date,

            end_date,

        )


        df = add_all_indicators(
            df
        )


        df = add_all_features(
            df
        )


        df = add_future_targets(

            df,

            [HORIZON],

        )


        # ====================================================
        # MESMA ESTRATÉGIA
        # ====================================================

        signal = (

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


        signal = non_overlapping_mask(

            signal,

            HORIZON,

        )


        # ====================================================
        # TESTE DOS CUSTOS
        # ====================================================

        for cost in COSTS:


            stats = analyze_condition(

                df=df,

                mask=signal,

                side="SHORT",

                horizon=HORIZON,

                cost=cost,

            )


            results.append({

                "symbol": symbol,

                "period": period,

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
# RESUMO
# ============================================================

summary = (

    results_df

    .groupby(
        "cost",
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

        median_mean_return=(

            "mean_return",

            "median",

        ),

        median_profit_factor=(

            "profit_factor",

            "median",

        ),

        median_win_rate=(

            "win_rate",

            "median",

        ),

    )

)


# ============================================================
# FORMAT DISPLAY
# ============================================================

display = summary.copy()


display[
    "cost"
] *= 100


display[
    "positive_window_rate"
] *= 100


display[
    "median_mean_return"
] *= 100


display[
    "median_win_rate"
] *= 100


print()

print(
    "=" * 140
)

print(
    "COST SENSITIVITY"
)

print(
    "=" * 140
)

print()


print(

    display.to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

results_df.to_csv(

    RESULTS_DIR
    / "cost_sensitivity_detailed.csv",

    index=False,

)


summary.to_csv(

    RESULTS_DIR
    / "cost_sensitivity_summary.csv",

    index=False,

)
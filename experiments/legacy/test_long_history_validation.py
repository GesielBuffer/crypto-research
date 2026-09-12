from pathlib import Path

import numpy as np
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
    calculate_profit_factor,
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


INTERVAL = "5m"

HORIZON = 12


# ============================================================
# 2024-01 até 2026-07
#
# AGOSTO/2026 CONTINUA INTACTO.
# ============================================================

MONTH_STARTS = pd.date_range(
    start="2024-01-01",
    end="2026-07-01",
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
# CUSTOS
# ============================================================

COSTS = [
    0.0000,
    0.0002,
    0.0004,
    0.0006,
    0.0008,
]


DATA_DIR = Path("data")

RESULTS_DIR = Path("results")


DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# LOAD / DOWNLOAD
# ============================================================

def load_month(
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


    print(
        f"🌐 Baixando "
        f"{symbol} "
        f"{start_date}"
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
# PROFIT FACTOR SEGURO
# ============================================================

def safe_profit_factor(
    returns,
):

    returns = (
        pd.Series(returns)
        .dropna()
    )


    if len(returns) == 0:
        return np.nan


    positives = (
        returns[
            returns > 0
        ]
        .sum()
    )


    negatives = (

        returns[
            returns < 0
        ]
        .abs()
        .sum()

    )


    if negatives == 0:

        if positives > 0:
            return np.inf

        return np.nan


    return (
        positives
        /
        negatives
    )


# ============================================================
# CLASSIFICA ERA
# ============================================================

def classify_era(
    period,
):

    if (
        period.startswith("2024")
        or
        period.startswith("2025")
    ):

        return "HIST_2024_2025"


    if period == "2026-01":

        return "DISCOVERY_2026_01"


    return "DEV_2026_FEB_JUL"


# ============================================================
# EVENTOS
# ============================================================

event_frames = []


# ============================================================
# LOOP POR ATIVO
# ============================================================

for symbol in SYMBOLS:

    print()

    print("=" * 110)

    print(
        f"PROCESSANDO {symbol}"
    )

    print("=" * 110)


    frames = []


    # ========================================================
    # CARREGA TODA SÉRIE
    # ========================================================

    for (
        period,
        start_date,
        end_date,
    ) in PERIODS:


        temp = load_month(
            symbol,
            start_date,
            end_date,
        )


        if temp.empty:
            continue


        temp = temp.copy()

        temp["period"] = period


        frames.append(
            temp
        )


    if not frames:

        continue


    # ========================================================
    # SÉRIE CONTÍNUA
    # ========================================================

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


    print(
        f"Candles contínuos: "
        f"{len(df)}"
    )


    # ========================================================
    # INDICADORES
    # ========================================================

    df = add_all_indicators(
        df
    )


    # ========================================================
    # FEATURES
    # ========================================================

    df = add_all_features(
        df
    )


    # ========================================================
    # TARGET
    # ========================================================

    df = add_future_targets(
        df,
        [HORIZON],
    )


    # ========================================================
    # BASE
    # ========================================================

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


    # ========================================================
    # CANDIDATO CONGELADO
    #
    # IMPORTANTE:
    # ATR PRIMEIRO.
    # NON-OVERLAP DEPOIS.
    # ========================================================

    atr_candidate = (

        base_short

        &

        (df["atr_expansion"] >= 0.80)

        &

        (df["atr_expansion"] < 1.00)

    )


    # ========================================================
    # ESTRATÉGIAS
    # ========================================================

    strategies = {

        "BASE_SHORT":
            base_short,

        "ATR_080_100":
            atr_candidate,

    }


    # ========================================================
    # NON OVERLAP POR ESTRATÉGIA
    # ========================================================

    for (
        strategy,
        signal,
    ) in strategies.items():


        clean_mask = (

            non_overlapping_mask(

                signal.fillna(False),

                HORIZON,

            )

        )


        events = df.loc[
            clean_mask
        ].copy()


        events = events.dropna(

            subset=[
                f"future_short_{HORIZON}"
            ]

        )


        if events.empty:
            continue


        events["strategy"] = (
            strategy
        )


        events["symbol"] = (
            symbol
        )


        events["gross_return"] = (

            events[
                f"future_short_{HORIZON}"
            ]

        )


        events["era"] = (

            events[
                "period"
            ]
            .apply(
                classify_era
            )

        )


        events["year"] = (

            events[
                "period"
            ]
            .str[:4]

        )


        keep = [

            "symbol",
            "period",
            "year",
            "era",

            "strategy",

            "open_time",

            "gross_return",

            "atr_expansion",

            "adx",
            "volume_ratio",

        ]


        event_frames.append(
            events[keep]
        )


# ============================================================
# CONSOLIDA EVENTOS
# ============================================================

events = pd.concat(

    event_frames,

    ignore_index=True,

)


print()

print(
    f"Total de eventos: "
    f"{len(events)}"
)


# ============================================================
# EXPANDE CUSTOS
# ============================================================

cost_frames = []


for cost in COSTS:

    temp = events.copy()

    temp["cost"] = cost

    temp["net_return"] = (

        temp["gross_return"]

        -

        cost

    )

    cost_frames.append(
        temp
    )


net_events = pd.concat(

    cost_frames,

    ignore_index=True,

)


# ============================================================
# STATS POR JANELA ATIVO-MÊS
# ============================================================

window_rows = []


group_columns = [

    "symbol",
    "period",
    "year",
    "era",
    "strategy",
    "cost",

]


for keys, group in net_events.groupby(
    group_columns
):


    (
        symbol,
        period,
        year,
        era,
        strategy,
        cost,
    ) = keys


    returns = (

        group[
            "net_return"
        ]
        .dropna()

    )


    if len(returns) == 0:
        continue


    window_rows.append({

        "symbol":
            symbol,

        "period":
            period,

        "year":
            year,

        "era":
            era,

        "strategy":
            strategy,

        "cost":
            cost,

        "samples":
            len(returns),

        "mean_return":
            returns.mean(),

        "median_return":
            returns.median(),

        "win_rate":
            (returns > 0).mean(),

        "profit_factor":
            safe_profit_factor(
                returns
            ),

    })


windows = pd.DataFrame(
    window_rows
)


# ============================================================
# LIMPA PF PARA MEDIANA
# ============================================================

windows[
    "profit_factor_clean"
] = (

    windows[
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
# SUMMARY FUNCTION
# ============================================================

def build_summary(
    event_data,
    window_data,
    group_columns,
):

    rows = []


    grouped = window_data.groupby(
        group_columns,
        dropna=False,
    )


    for keys, win_group in grouped:


        if not isinstance(
            keys,
            tuple,
        ):

            keys = (
                keys,
            )


        filters = pd.Series(
            True,
            index=event_data.index,
        )


        row = {}


        for (
            column,
            value,
        ) in zip(
            group_columns,
            keys,
        ):

            row[column] = value

            filters &= (
                event_data[
                    column
                ]
                ==
                value
            )


        ev = event_data.loc[
            filters
        ]


        returns = (

            ev[
                "net_return"
            ]
            .dropna()

        )


        row.update({

            "windows":
                len(win_group),

            "total_samples":
                int(
                    win_group[
                        "samples"
                    ]
                    .sum()
                ),

            "positive_windows":
                int(
                    (
                        win_group[
                            "mean_return"
                        ]
                        >
                        0
                    )
                    .sum()
                ),

            "positive_window_rate":

                (
                    win_group[
                        "mean_return"
                    ]
                    >
                    0
                )
                .mean(),

            "pf_above_1_rate":

                (
                    win_group[
                        "profit_factor_clean"
                    ]
                    >
                    1
                )
                .mean(),

            "median_profit_factor":

                win_group[
                    "profit_factor_clean"
                ]
                .median(),

            "median_window_return":

                win_group[
                    "mean_return"
                ]
                .median(),

            "pooled_mean_return":

                returns.mean(),

            "pooled_median_return":

                returns.median(),

            "pooled_win_rate":

                (
                    returns > 0
                )
                .mean(),

            "pooled_profit_factor":

                safe_profit_factor(
                    returns
                ),

        })


        rows.append(
            row
        )


    return pd.DataFrame(
        rows
    )


# ============================================================
# RESUMO POR ERA
# ============================================================

era_summary = build_summary(

    net_events,

    windows,

    [
        "era",
        "strategy",
        "cost",
    ],

)


# ============================================================
# RESUMO POR ANO
# ============================================================

year_summary = build_summary(

    net_events,

    windows,

    [
        "year",
        "strategy",
        "cost",
    ],

)


# ============================================================
# RESUMO POR ATIVO
# ============================================================

asset_summary = build_summary(

    net_events,

    windows,

    [
        "era",
        "symbol",
        "strategy",
        "cost",
    ],

)


# ============================================================
# HISTÓRICO NÃO UTILIZADO
# ============================================================

historical = era_summary[

    era_summary[
        "era"
    ]
    ==
    "HIST_2024_2025"

].copy()


# ============================================================
# DISPLAY %
# ============================================================

def display_percent(
    df,
):

    output = df.copy()


    percentage_columns = [

        "cost",

        "positive_window_rate",
        "pf_above_1_rate",

        "median_window_return",

        "pooled_mean_return",
        "pooled_median_return",
        "pooled_win_rate",

    ]


    for column in percentage_columns:

        if column in output.columns:

            output[
                column
            ] *= 100


    return output


historical_display = display_percent(
    historical
)


year_display = display_percent(
    year_summary
)


asset_display = display_percent(
    asset_summary
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    300,
)


# ============================================================
# OUTPUT 1
# ============================================================

print()

print("=" * 220)

print(
    "EXPERIMENTO 10 — "
    "LONG HISTORICAL ROBUSTNESS"
)

print(
    "HISTÓRICO NÃO UTILIZADO: "
    "2024 + 2025"
)

print("=" * 220)

print()


columns = [

    "strategy",
    "cost",

    "windows",
    "total_samples",

    "positive_windows",
    "positive_window_rate",

    "pf_above_1_rate",

    "median_profit_factor",
    "median_window_return",

    "pooled_mean_return",
    "pooled_median_return",
    "pooled_win_rate",
    "pooled_profit_factor",

]


print(

    historical_display[
        columns
    ]

    .sort_values(
        [
            "strategy",
            "cost",
        ]
    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 2 — ANOS
# ============================================================

print()

print("=" * 220)

print(
    "RESULTADO POR ANO"
)

print("=" * 220)

print()


print(

    year_display[
        [
            "year",
            "strategy",
            "cost",

            "windows",
            "total_samples",

            "positive_window_rate",

            "median_profit_factor",
            "median_window_return",

            "pooled_mean_return",
            "pooled_profit_factor",
        ]
    ]

    .sort_values(
        [
            "year",
            "strategy",
            "cost",
        ]
    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 3 — ATIVOS 2024-2025
#
# Apenas custo 0 e 0.04 para não poluir.
# ============================================================

asset_focus = asset_display[

    (
        asset_display[
            "era"
        ]
        ==
        "HIST_2024_2025"
    )

    &

    (
        asset_display[
            "cost"
        ]
        .isin(
            [
                0.00,
                0.04,
            ]
        )
    )

].copy()


print()

print("=" * 220)

print(
    "2024–2025 — "
    "RESULTADO POR ATIVO"
)

print("=" * 220)

print()


print(

    asset_focus[
        [
            "symbol",
            "strategy",
            "cost",

            "windows",
            "total_samples",

            "positive_window_rate",

            "median_profit_factor",
            "median_window_return",

            "pooled_mean_return",
            "pooled_profit_factor",
        ]
    ]

    .sort_values(
        [
            "strategy",
            "cost",
            "symbol",
        ]
    )

    .to_string(
        index=False
    )

)


# ============================================================
# PIORES JANELAS DO CANDIDATO
#
# GROSS / CUSTO ZERO
# ============================================================

worst = windows[

    (
        windows[
            "era"
        ]
        ==
        "HIST_2024_2025"
    )

    &

    (
        windows[
            "strategy"
        ]
        ==
        "ATR_080_100"
    )

    &

    (
        windows[
            "cost"
        ]
        ==
        0
    )

].copy()


worst[
    "mean_return"
] *= 100


worst[
    "win_rate"
] *= 100


worst = (

    worst

    .sort_values(
        "mean_return"
    )

    .head(15)

)


print()

print("=" * 180)

print(
    "15 PIORES JANELAS HISTÓRICAS "
    "DO ATR_080_100"
)

print("=" * 180)

print()


print(

    worst[
        [
            "symbol",
            "period",
            "samples",

            "mean_return",
            "win_rate",
            "profit_factor",
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
    / "long_history_events_gross.csv",

    index=False,

)


windows.to_csv(

    RESULTS_DIR
    / "long_history_window_stats.csv",

    index=False,

)


era_summary.to_csv(

    RESULTS_DIR
    / "long_history_era_summary.csv",

    index=False,

)


year_summary.to_csv(

    RESULTS_DIR
    / "long_history_year_summary.csv",

    index=False,

)


asset_summary.to_csv(

    RESULTS_DIR
    / "long_history_asset_summary.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
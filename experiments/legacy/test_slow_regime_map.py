from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv
from research.indicators import add_all_indicators
from research.features import add_all_features
from research.targets import add_future_targets
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


INTERVAL = "5m"

HORIZON = 12


DATA_DIR = Path("data")

RESULTS_DIR = Path("results")

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2024-01 → 2026-07
# ============================================================

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
# SAFE PROFIT FACTOR
# ============================================================

def profit_factor(
    returns,
):

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
# LOAD CONTINUOUS
# ============================================================

def load_symbol(
    symbol,
):

    frames = []


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
                f"Ausente: {path}"
            )

            continue


        temp = load_csv(
            path
        )


        temp["period"] = period


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


    return df


# ============================================================
# PREPARA CONTEXTO
# ============================================================

prepared = {}


for symbol in SYMBOLS:

    print()

    print("=" * 100)

    print(
        f"PREPARANDO {symbol}"
    )

    print("=" * 100)


    df = load_symbol(
        symbol
    )


    if df is None:
        continue


    # ========================================================
    # INDICADORES
    # ========================================================

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


    # ========================================================
    # CONTEXTO LENTO
    #
    # 288 candles = 1 dia
    # ========================================================

    df["ret_1d"] = (
        df["close"]
        .pct_change(288)
    )


    df["ret_3d"] = (
        df["close"]
        .pct_change(
            288 * 3
        )
    )


    df["ret_7d"] = (
        df["close"]
        .pct_change(
            288 * 7
        )
    )


    df["ret_30d"] = (
        df["close"]
        .pct_change(
            288 * 30
        )
    )


    # ========================================================
    # VOLATILIDADE REALIZADA
    # ========================================================

    returns_5m = (
        df["close"]
        .pct_change()
    )


    df["rv_1d"] = (

        returns_5m

        .rolling(
            288
        )

        .std()

        *

        np.sqrt(
            288
        )

    )


    df["rv_7d"] = (

        returns_5m

        .rolling(
            288 * 7
        )

        .std()

        *

        np.sqrt(
            288
        )

    )


    # ========================================================
    # MÉDIAS LENTAS
    # ========================================================

    df["sma_1d"] = (

        df["close"]

        .rolling(
            288
        )

        .mean()

    )


    df["sma_7d"] = (

        df["close"]

        .rolling(
            288 * 7
        )

        .mean()

    )


    df["price_vs_sma_7d"] = (

        df["close"]
        /
        df["sma_7d"]
        -
        1

    )


    df["sma_1d_vs_7d"] = (

        df["sma_1d"]
        /
        df["sma_7d"]
        -
        1

    )


    prepared[
        symbol
    ] = df


# ============================================================
# CROSS-MARKET PANEL
# ============================================================

panel = None


CONTEXT_COLUMNS = [

    "ret_1d",
    "ret_3d",
    "ret_7d",
    "ret_30d",

    "rv_1d",
    "rv_7d",

    "price_vs_sma_7d",
    "sma_1d_vs_7d",

]


for symbol in SYMBOLS:

    df = prepared[
        symbol
    ]


    part = df[

        ["open_time"]
        +
        CONTEXT_COLUMNS

    ].copy()


    part = part.rename(

        columns={

            column:
                f"{symbol}_{column}"

            for column in CONTEXT_COLUMNS

        }

    )


    if panel is None:

        panel = part

    else:

        panel = panel.merge(

            part,

            on="open_time",

            how="outer",

        )


# ============================================================
# EVENTOS
# ============================================================

event_rows = []


for symbol in SYMBOLS:

    print(
        f"EVENTOS {symbol}"
    )


    df = prepared[
        symbol
    ].copy()


    df = df.merge(

        panel,

        on="open_time",

        how="left",

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
    # ========================================================

    candidate = (

        base_short

        &

        (
            df["atr_expansion"]
            >=
            0.80
        )

        &

        (
            df["atr_expansion"]
            <
            1.00
        )

    )


    # ========================================================
    # CORRETO:
    # FILTRO PRIMEIRO
    # NON-OVERLAP DEPOIS
    # ========================================================

    clean_mask = (

        non_overlapping_mask(

            candidate.fillna(
                False
            ),

            HORIZON,

        )

    )


    events = df.loc[
        clean_mask
    ].copy()


    events = events.dropna(

        subset=[

            f"future_short_{HORIZON}",

            "ret_7d",
            "ret_30d",

        ]

    )


    # ========================================================
    # OUTROS ATIVOS
    # ========================================================

    others = [

        other

        for other in SYMBOLS

        if other != symbol

    ]


    for _, row in events.iterrows():


        def other_values(
            feature,
        ):

            values = []


            for other in others:

                value = row.get(

                    f"{other}_"
                    f"{feature}",

                    np.nan,

                )


                if pd.notna(
                    value
                ):

                    values.append(
                        float(value)
                    )


            return values


        market_1d = other_values(
            "ret_1d"
        )

        market_3d = other_values(
            "ret_3d"
        )

        market_7d = other_values(
            "ret_7d"
        )

        market_30d = other_values(
            "ret_30d"
        )


        market_rv_1d = other_values(
            "rv_1d"
        )

        market_rv_7d = other_values(
            "rv_7d"
        )


        if (

            not market_7d

            or

            not market_30d

        ):

            continue


        # ====================================================
        # BTC CONTEXT
        # ====================================================

        btc_7d = row.get(
            "BTCUSDT_ret_7d",
            np.nan,
        )


        btc_30d = row.get(
            "BTCUSDT_ret_30d",
            np.nan,
        )


        # ====================================================
        # MARKET CONTEXT
        # ====================================================

        market_mean_1d = np.mean(
            market_1d
        )

        market_mean_3d = np.mean(
            market_3d
        )

        market_mean_7d = np.mean(
            market_7d
        )

        market_mean_30d = np.mean(
            market_30d
        )


        breadth_down_7d = np.mean(

            np.array(
                market_7d
            )
            <
            0

        )


        breadth_down_30d = np.mean(

            np.array(
                market_30d
            )
            <
            0

        )


        dispersion_7d = np.std(
            market_7d
        )


        # ====================================================
        # MACRO QUADRANT
        #
        # SHORT-TERM vs LONG-TERM CONTEXT
        # ====================================================

        if (
            market_mean_7d < 0
            and
            market_mean_30d < 0
        ):

            macro_regime = (
                "7D_DOWN__30D_DOWN"
            )


        elif (
            market_mean_7d < 0
            and
            market_mean_30d >= 0
        ):

            macro_regime = (
                "7D_DOWN__30D_UP"
            )


        elif (
            market_mean_7d >= 0
            and
            market_mean_30d < 0
        ):

            macro_regime = (
                "7D_UP__30D_DOWN"
            )


        else:

            macro_regime = (
                "7D_UP__30D_UP"
            )


        event_rows.append({

            "symbol":
                symbol,

            "period":
                row["period"],

            "year":
                row["period"][:4],

            "open_time":
                row["open_time"],

            "future_return":
                row[
                    f"future_short_{HORIZON}"
                ],

            # ----------------------------------------------
            # PRÓPRIO ATIVO
            # ----------------------------------------------

            "asset_ret_1d":
                row["ret_1d"],

            "asset_ret_3d":
                row["ret_3d"],

            "asset_ret_7d":
                row["ret_7d"],

            "asset_ret_30d":
                row["ret_30d"],

            "asset_rv_1d":
                row["rv_1d"],

            "asset_rv_7d":
                row["rv_7d"],

            "asset_price_vs_sma7d":
                row["price_vs_sma_7d"],

            "asset_sma1d_vs_7d":
                row["sma_1d_vs_7d"],

            # ----------------------------------------------
            # MERCADO EXCLUINDO O PRÓPRIO ATIVO
            # ----------------------------------------------

            "market_mean_1d":
                market_mean_1d,

            "market_mean_3d":
                market_mean_3d,

            "market_mean_7d":
                market_mean_7d,

            "market_mean_30d":
                market_mean_30d,

            "market_rv_1d":
                np.mean(
                    market_rv_1d
                ),

            "market_rv_7d":
                np.mean(
                    market_rv_7d
                ),

            "breadth_down_7d":
                breadth_down_7d,

            "breadth_down_30d":
                breadth_down_30d,

            "dispersion_7d":
                dispersion_7d,

            # ----------------------------------------------
            # BTC
            # ----------------------------------------------

            "btc_ret_7d":
                btc_7d,

            "btc_ret_30d":
                btc_30d,

            # ----------------------------------------------

            "macro_regime":
                macro_regime,

        })


events = pd.DataFrame(
    event_rows
)


# ============================================================
# CORRELAÇÕES
# ============================================================

FEATURES = [

    "asset_ret_1d",
    "asset_ret_3d",
    "asset_ret_7d",
    "asset_ret_30d",

    "asset_rv_1d",
    "asset_rv_7d",

    "asset_price_vs_sma7d",
    "asset_sma1d_vs_7d",

    "market_mean_1d",
    "market_mean_3d",
    "market_mean_7d",
    "market_mean_30d",

    "market_rv_1d",
    "market_rv_7d",

    "breadth_down_7d",
    "breadth_down_30d",

    "dispersion_7d",

    "btc_ret_7d",
    "btc_ret_30d",

]


correlation_rows = []


for feature in FEATURES:


    valid = events[

        [
            feature,
            "future_return",
        ]

    ].dropna()


    if len(valid) == 0:
        continue


    pearson = (

        valid[feature]

        .corr(

            valid[
                "future_return"
            ]

        )

    )


    spearman = (

        valid[feature]

        .rank()

        .corr(

            valid[
                "future_return"
            ]

            .rank()

        )

    )


    correlation_rows.append({

        "feature":
            feature,

        "samples":
            len(valid),

        "pearson":
            pearson,

        "spearman":
            spearman,

        "abs_spearman":
            abs(
                spearman
            ),

    })


correlations = pd.DataFrame(
    correlation_rows
)


correlations = correlations.sort_values(

    "abs_spearman",

    ascending=False,

)


# ============================================================
# SUMMARY
# ============================================================

def summarize(
    group,
):

    returns = (

        group[
            "future_return"
        ]

        .dropna()

    )


    return pd.Series({

        "samples":
            len(returns),

        "mean_return":
            returns.mean(),

        "median_return":
            returns.median(),

        "win_rate":
            (
                returns > 0
            ).mean(),

        "profit_factor":
            profit_factor(
                returns
            ),

    })


# ============================================================
# MACRO REGIME × YEAR
# ============================================================

regime_year = (

    events

    .groupby(

        [
            "year",
            "macro_regime",
        ]

    )

    .apply(
        summarize,
        include_groups=False,
    )

    .reset_index()

)


# ============================================================
# MACRO REGIME GLOBAL
# ============================================================

regime_global = (

    events

    .groupby(
        "macro_regime"
    )

    .apply(
        summarize,
        include_groups=False,
    )

    .reset_index()

)


# ============================================================
# CURVA 7D
# ============================================================

events[
    "market_7d_bucket"
] = pd.cut(

    events[
        "market_mean_7d"
    ],

    bins=[

        -np.inf,
        -0.10,
        -0.03,
        0.03,
        0.10,
        np.inf,

    ],

    labels=[

        "<-10%",
        "-10%--3%",
        "-3%-+3%",
        "+3%-+10%",
        ">+10%",

    ],

)


curve_7d = (

    events

    .groupby(
        "market_7d_bucket",
        observed=False,
    )

    .apply(
        summarize,
        include_groups=False,
    )

    .reset_index()

)


# ============================================================
# CURVA 30D
# ============================================================

events[
    "market_30d_bucket"
] = pd.cut(

    events[
        "market_mean_30d"
    ],

    bins=[

        -np.inf,
        -0.20,
        -0.05,
        0.05,
        0.20,
        np.inf,

    ],

    labels=[

        "<-20%",
        "-20%--5%",
        "-5%-+5%",
        "+5%-+20%",
        ">+20%",

    ],

)


curve_30d = (

    events

    .groupby(
        "market_30d_bucket",
        observed=False,
    )

    .apply(
        summarize,
        include_groups=False,
    )

    .reset_index()

)


# ============================================================
# DISPLAY
# ============================================================

def percent_display(
    df,
):

    output = df.copy()


    for column in [

        "mean_return",
        "median_return",
        "win_rate",

    ]:

        if column in output.columns:

            output[
                column
            ] *= 100


    return output


regime_year_display = percent_display(
    regime_year
)


regime_global_display = percent_display(
    regime_global
)


curve_7d_display = percent_display(
    curve_7d
)


curve_30d_display = percent_display(
    curve_30d
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    250,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 170)

print(
    "EXPERIMENTO 11 — "
    "SLOW MARKET REGIME MAP"
)

print("=" * 170)

print()


print(
    "MAIORES CORRELAÇÕES "
    "COM RETORNO FUTURO SHORT"
)

print()


print(

    correlations[
        [
            "feature",
            "samples",
            "pearson",
            "spearman",
        ]
    ]

    .head(15)

    .to_string(
        index=False
    )

)


print()

print("=" * 170)

print(
    "MACRO REGIME — GLOBAL"
)

print("=" * 170)

print()


print(

    regime_global_display

    .sort_values(
        "profit_factor",
        ascending=False,
    )

    .to_string(
        index=False
    )

)


print()

print("=" * 170)

print(
    "MACRO REGIME × ANO"
)

print("=" * 170)

print()


print(

    regime_year_display

    .sort_values(
        [
            "macro_regime",
            "year",
        ]
    )

    .to_string(
        index=False
    )

)


print()

print("=" * 170)

print(
    "CURVA — RETORNO MÉDIO DO MERCADO 7D"
)

print("=" * 170)

print()


print(
    curve_7d_display.to_string(
        index=False
    )
)


print()

print("=" * 170)

print(
    "CURVA — RETORNO MÉDIO DO MERCADO 30D"
)

print("=" * 170)

print()


print(
    curve_30d_display.to_string(
        index=False
    )
)


# ============================================================
# SAVE
# ============================================================

events.to_csv(

    RESULTS_DIR
    / "slow_regime_events.csv",

    index=False,

)


correlations.to_csv(

    RESULTS_DIR
    / "slow_regime_correlations.csv",

    index=False,

)


regime_global.to_csv(

    RESULTS_DIR
    / "slow_regime_global.csv",

    index=False,

)


regime_year.to_csv(

    RESULTS_DIR
    / "slow_regime_by_year.csv",

    index=False,

)


curve_7d.to_csv(

    RESULTS_DIR
    / "slow_regime_7d_curve.csv",

    index=False,

)


curve_30d.to_csv(

    RESULTS_DIR
    / "slow_regime_30d_curve.csv",

    index=False,

)


print()

print(
    f"Eventos analisados: "
    f"{len(events)}"
)

print(
    "Arquivos salvos em results/"
)
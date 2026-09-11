from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv
from research.indicators import add_all_indicators
from research.features import add_all_features
from research.targets import add_future_targets
from research.statistics import calculate_profit_factor
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
# CARREGA CONTÍNUO
# ============================================================

def load_continuous_symbol(
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
                f"Arquivo ausente: {path}"
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
# PREPARA CADA ATIVO
# ============================================================

prepared = {}


for symbol in SYMBOLS:

    print()

    print(
        "=" * 100
    )

    print(
        f"PREPARANDO {symbol}"
    )

    print(
        "=" * 100
    )

    df = load_continuous_symbol(
        symbol
    )

    if df is None:
        continue


    # ========================================================
    # INDICADORES / FEATURES
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
    # RETORNOS DE CONTEXTO
    # ========================================================

    df["market_return_1h"] = (

        df["close"]
        .pct_change(12)

    )


    df["market_return_6h"] = (

        df["close"]
        .pct_change(72)

    )


    df["market_return_24h"] = (

        df["close"]
        .pct_change(288)

    )


    # ========================================================
    # ESTADOS
    # ========================================================

    df["bear_state"] = (

        (df["ema_9"] < df["ema_21"])

        &

        (df["ema_21"] < df["ema_35"])

        &

        (df["macd_hist"] < 0)

    )


    df["down_1h"] = (

        df["market_return_1h"] < 0

    )


    df["down_6h"] = (

        df["market_return_6h"] < 0

    )


    df["down_24h"] = (

        df["market_return_24h"] < 0

    )


    df["vol_expanding"] = (

        df["atr_expansion"] > 1

    )


    df["strong_trend"] = (

        df["adx"] >= 25

    )


    prepared[
        symbol
    ] = df


# ============================================================
# PAINEL DE MERCADO SINCRONIZADO
# ============================================================

panel = None


for symbol in SYMBOLS:

    if symbol not in prepared:
        continue

    df = prepared[
        symbol
    ]


    part = df[

        [
            "open_time",

            "bear_state",

            "down_1h",
            "down_6h",
            "down_24h",

            "vol_expanding",
            "strong_trend",

            "market_return_1h",
            "market_return_6h",
            "market_return_24h",

        ]

    ].copy()


    rename = {

        column:
            f"{symbol}_{column}"

        for column in part.columns

        if column != "open_time"

    }


    part = part.rename(
        columns=rename
    )


    if panel is None:

        panel = part

    else:

        panel = panel.merge(

            part,

            on="open_time",

            how="outer",

        )


panel = (

    panel

    .sort_values(
        "open_time"
    )

    .reset_index(
        drop=True
    )

)


# ============================================================
# EVENTOS
# ============================================================

event_rows = []


for symbol in SYMBOLS:

    print(
        f"ANALISANDO EVENTOS {symbol}"
    )


    if symbol not in prepared:
        continue


    df = prepared[
        symbol
    ].copy()


    # ========================================================
    # ADICIONA PAINEL
    # ========================================================

    df = df.merge(

        panel,

        on="open_time",

        how="left",

    )


    # ========================================================
    # SINAL BASE
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
    # NON OVERLAP
    # ========================================================

    clean_mask = non_overlapping_mask(

        base_short,

        HORIZON,

    )


    positions = np.flatnonzero(

        clean_mask.to_numpy()

    )


    for i in positions:

        row = df.iloc[i]


        # ====================================================
        # ATR CANDIDATO
        # ====================================================

        atr = row[
            "atr_expansion"
        ]


        if pd.isna(atr):
            continue


        if not (
            0.80
            <= atr
            < 1.00
        ):
            continue


        future_return = row[

            f"future_short_{HORIZON}"

        ]


        if pd.isna(
            future_return
        ):
            continue


        # ====================================================
        # OUTROS ATIVOS
        # ====================================================

        others = [

            s

            for s in SYMBOLS

            if s != symbol

        ]


        # ====================================================
        # FUNÇÃO AUXILIAR
        # ====================================================

        def values_for(
            feature,
        ):

            values = []

            for other in others:

                column = (
                    f"{other}_"
                    f"{feature}"
                )

                value = row.get(
                    column,
                    np.nan,
                )

                if pd.notna(
                    value
                ):

                    values.append(
                        float(value)
                    )

            return values


        # ====================================================
        # BREADTH
        # ====================================================

        bear_values = values_for(
            "bear_state"
        )

        down_1h_values = values_for(
            "down_1h"
        )

        down_6h_values = values_for(
            "down_6h"
        )

        down_24h_values = values_for(
            "down_24h"
        )

        vol_values = values_for(
            "vol_expanding"
        )

        strong_values = values_for(
            "strong_trend"
        )


        # ====================================================
        # RETORNOS CROSS-ASSET
        # ====================================================

        returns_1h = values_for(
            "market_return_1h"
        )

        returns_6h = values_for(
            "market_return_6h"
        )

        returns_24h = values_for(
            "market_return_24h"
        )


        if (
            len(bear_values)
            == 0
        ):
            continue


        # ====================================================
        # FEATURES DE BREADTH
        # ====================================================

        bear_breadth = np.mean(
            bear_values
        )

        down_1h_breadth = np.mean(
            down_1h_values
        )

        down_6h_breadth = np.mean(
            down_6h_values
        )

        down_24h_breadth = np.mean(
            down_24h_values
        )

        vol_breadth = np.mean(
            vol_values
        )

        strong_breadth = np.mean(
            strong_values
        )


        mean_return_1h = np.mean(
            returns_1h
        )

        mean_return_6h = np.mean(
            returns_6h
        )

        mean_return_24h = np.mean(
            returns_24h
        )


        dispersion_1h = np.std(
            returns_1h
        )


        # ====================================================
        # PRESSÃO AGREGADA
        # ====================================================

        market_bear_pressure = np.mean(

            [

                bear_breadth,

                down_1h_breadth,

                down_6h_breadth,

                down_24h_breadth,

            ]

        )


        event_rows.append({

            "symbol":
                symbol,

            "period":
                row["period"],

            "open_time":
                row["open_time"],

            "future_return":
                future_return,

            "bear_breadth":
                bear_breadth,

            "down_1h_breadth":
                down_1h_breadth,

            "down_6h_breadth":
                down_6h_breadth,

            "down_24h_breadth":
                down_24h_breadth,

            "vol_breadth":
                vol_breadth,

            "strong_breadth":
                strong_breadth,

            "mean_return_1h":
                mean_return_1h,

            "mean_return_6h":
                mean_return_6h,

            "mean_return_24h":
                mean_return_24h,

            "dispersion_1h":
                dispersion_1h,

            "market_bear_pressure":
                market_bear_pressure,

            "regime_group":

                (
                    "JULY"

                    if row[
                        "period"
                    ]
                    ==
                    "2026-07"

                    else
                    "FEB_JUN"
                ),

        })


# ============================================================
# DATAFRAME
# ============================================================

events = pd.DataFrame(
    event_rows
)


# ============================================================
# SUMMARY
# ============================================================

def summarize(
    data,
):

    returns = (

        data[
            "future_return"
        ]
        .dropna()

    )


    if len(returns) == 0:

        return {

            "samples": 0,

            "mean_return": np.nan,

            "median_return": np.nan,

            "win_rate": np.nan,

            "profit_factor": np.nan,

        }


    return {

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
            calculate_profit_factor(
                returns
            ),

    }


# ============================================================
# BASE
# ============================================================

rows = []


for group in [

    "FEB_JUN",

    "JULY",

]:

    subset = events[

        events[
            "regime_group"
        ]
        ==
        group

    ]


    rows.append({

        "state":
            "BASE",

        "regime_group":
            group,

        **summarize(
            subset
        ),

    })


# ============================================================
# ESTADOS DE BREADTH
# ============================================================

states = {

    # --------------------------------------------------------
    # MAIORIA DOS OUTROS ATIVOS
    # --------------------------------------------------------

    "BEAR_BREADTH_MAJORITY":

        events[
            "bear_breadth"
        ] >= (2 / 3),


    "BEAR_BREADTH_MINORITY":

        events[
            "bear_breadth"
        ] < (2 / 3),


    "1H_DOWN_MAJORITY":

        events[
            "down_1h_breadth"
        ] >= (2 / 3),


    "1H_DOWN_MINORITY":

        events[
            "down_1h_breadth"
        ] < (2 / 3),


    "6H_DOWN_MAJORITY":

        events[
            "down_6h_breadth"
        ] >= (2 / 3),


    "6H_DOWN_MINORITY":

        events[
            "down_6h_breadth"
        ] < (2 / 3),


    "24H_DOWN_MAJORITY":

        events[
            "down_24h_breadth"
        ] >= (2 / 3),


    "24H_DOWN_MINORITY":

        events[
            "down_24h_breadth"
        ] < (2 / 3),


    # --------------------------------------------------------
    # MÉDIA DE RETORNO DO RESTO DO MERCADO
    # --------------------------------------------------------

    "MARKET_1H_DOWN":

        events[
            "mean_return_1h"
        ] < 0,


    "MARKET_1H_UP":

        events[
            "mean_return_1h"
        ] >= 0,


    "MARKET_6H_DOWN":

        events[
            "mean_return_6h"
        ] < 0,


    "MARKET_6H_UP":

        events[
            "mean_return_6h"
        ] >= 0,


    "MARKET_24H_DOWN":

        events[
            "mean_return_24h"
        ] < 0,


    "MARKET_24H_UP":

        events[
            "mean_return_24h"
        ] >= 0,


    # --------------------------------------------------------
    # VOLATILIDADE DO RESTO DO MERCADO
    # --------------------------------------------------------

    "VOL_EXPANSION_MAJORITY":

        events[
            "vol_breadth"
        ] >= (2 / 3),


    "VOL_EXPANSION_MINORITY":

        events[
            "vol_breadth"
        ] < (2 / 3),

}


# ============================================================
# EXECUTA STATES
# ============================================================

for (
    state_name,
    state_mask,
) in states.items():


    for group in [

        "FEB_JUN",

        "JULY",

    ]:


        subset = events[

            state_mask

            &

            (
                events[
                    "regime_group"
                ]
                ==
                group
            )

        ]


        rows.append({

            "state":
                state_name,

            "regime_group":
                group,

            **summarize(
                subset
            ),

        })


state_results = pd.DataFrame(
    rows
)


# ============================================================
# SHIFT DE BREADTH
# ============================================================

BREADTH_FEATURES = [

    "bear_breadth",

    "down_1h_breadth",
    "down_6h_breadth",
    "down_24h_breadth",

    "vol_breadth",
    "strong_breadth",

    "mean_return_1h",
    "mean_return_6h",
    "mean_return_24h",

    "dispersion_1h",

    "market_bear_pressure",

]


shift_rows = []


for feature in BREADTH_FEATURES:

    pre = events.loc[

        events[
            "regime_group"
        ]
        ==
        "FEB_JUN",

        feature,

    ].dropna()


    july = events.loc[

        events[
            "regime_group"
        ]
        ==
        "JULY",

        feature,

    ].dropna()


    if (
        len(pre) == 0
        or len(july) == 0
    ):
        continue


    q25 = pre.quantile(
        0.25
    )

    q75 = pre.quantile(
        0.75
    )

    iqr = (
        q75 - q25
    )


    pre_median = (
        pre.median()
    )

    july_median = (
        july.median()
    )


    robust_shift = (

        (
            july_median
            -
            pre_median
        )

        /
        iqr

        if iqr != 0

        else np.nan

    )


    shift_rows.append({

        "feature":
            feature,

        "pre_median":
            pre_median,

        "july_median":
            july_median,

        "robust_shift":
            robust_shift,

    })


shift_df = pd.DataFrame(
    shift_rows
)


shift_df[
    "abs_shift"
] = (

    shift_df[
        "robust_shift"
    ]
    .abs()

)


shift_df = (

    shift_df

    .sort_values(

        "abs_shift",

        ascending=False,

    )

)


# ============================================================
# PRESSURE BUCKETS
# ============================================================

events[
    "pressure_bucket"
] = pd.cut(

    events[
        "market_bear_pressure"
    ],

    bins=[

        -0.001,

        0.25,

        0.50,

        0.75,

        1.001,

    ],

    labels=[

        "0.00-0.25",

        "0.25-0.50",

        "0.50-0.75",

        "0.75-1.00",

    ],

)


pressure_rows = []


for bucket in (

    events[
        "pressure_bucket"
    ]
    .dropna()
    .unique()

):


    for group in [

        "FEB_JUN",

        "JULY",

    ]:


        subset = events[

            (
                events[
                    "pressure_bucket"
                ]
                ==
                bucket
            )

            &

            (
                events[
                    "regime_group"
                ]
                ==
                group
            )

        ]


        pressure_rows.append({

            "pressure_bucket":
                str(bucket),

            "regime_group":
                group,

            **summarize(
                subset
            ),

        })


pressure_results = pd.DataFrame(
    pressure_rows
)


# ============================================================
# DISPLAY
# ============================================================

def format_percentages(
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


state_display = format_percentages(
    state_results
)


pressure_display = format_percentages(
    pressure_results
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    260,
)


print()

print("=" * 180)

print(
    "EXPERIMENTO 9 — "
    "MARKET BREADTH DIAGNOSTIC"
)

print("=" * 180)

print()


print(

    state_display

    .sort_values(

        [
            "state",
            "regime_group",
        ]

    )

    .to_string(
        index=False
    )

)


print()

print("=" * 180)

print(
    "MUDANÇA DE BREADTH "
    "FEV-JUN VS JULHO"
)

print("=" * 180)

print()


print(

    shift_df.to_string(
        index=False
    )

)


print()

print("=" * 180)

print(
    "MARKET BEAR PRESSURE — "
    "BUCKETS"
)

print("=" * 180)

print()


print(

    pressure_display

    .sort_values(

        [
            "pressure_bucket",
            "regime_group",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

events.to_csv(

    RESULTS_DIR
    / "market_breadth_events.csv",

    index=False,

)


state_results.to_csv(

    RESULTS_DIR
    / "market_breadth_states.csv",

    index=False,

)


shift_df.to_csv(

    RESULTS_DIR
    / "market_breadth_shift.csv",

    index=False,

)


pressure_results.to_csv(

    RESULTS_DIR
    / "market_breadth_pressure.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
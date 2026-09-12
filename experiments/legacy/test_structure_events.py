from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv
from research.statistics import calculate_profit_factor


# ============================================================
# CONFIG
# ============================================================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]


PERIODS = []

month_starts = pd.date_range(
    "2024-01-01",
    "2026-07-01",
    freq="MS",
)

for start in month_starts:

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


DATA_DIR = Path("data")

RESULTS_DIR = Path("results")

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


HORIZONS = [
    1,   # 5m
    3,   # 15m
    6,   # 30m
    12,  # 60m
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

        filename = (
            f"{symbol}_5m_"
            f"{start_date}_"
            f"{end_date}.csv"
        )

        path = (
            DATA_DIR
            / filename
        )

        if not path.exists():
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
        .sort_values("open_time")
        .reset_index(drop=True)
    )

    return df


# ============================================================
# PF
# ============================================================

def safe_pf(returns):

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

    return positives / negatives


# ============================================================
# SUMMARY
# ============================================================

def summarize(returns):

    returns = (
        pd.Series(returns)
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
            (returns > 0).mean(),

        "profit_factor":
            safe_pf(returns),
    }


# ============================================================
# RESULTADOS
# ============================================================

rows = []


# ============================================================
# LOOP
# ============================================================

for symbol in SYMBOLS:

    print()
    print("=" * 100)
    print(f"PROCESSANDO {symbol}")
    print("=" * 100)

    df = load_symbol(
        symbol
    )

    if df is None:
        continue


    # ========================================================
    # ESTRUTURA PASSADA
    #
    # SHIFT(1) É FUNDAMENTAL:
    # candle atual NÃO participa da referência.
    # ========================================================

    df["prior_high_1h"] = (

        df["high"]

        .rolling(12)

        .max()

        .shift(1)

    )


    df["prior_low_1h"] = (

        df["low"]

        .rolling(12)

        .min()

        .shift(1)

    )


    df["prior_high_4h"] = (

        df["high"]

        .rolling(48)

        .max()

        .shift(1)

    )


    df["prior_low_4h"] = (

        df["low"]

        .rolling(48)

        .min()

        .shift(1)

    )


    # ========================================================
    # EVENTOS
    # ========================================================

    events = {

        "BREAKOUT_UP_1H":

            df["close"]
            >
            df["prior_high_1h"],


        "BREAKOUT_DOWN_1H":

            df["close"]
            <
            df["prior_low_1h"],


        "BREAKOUT_UP_4H":

            df["close"]
            >
            df["prior_high_4h"],


        "BREAKOUT_DOWN_4H":

            df["close"]
            <
            df["prior_low_4h"],

    }


    # ========================================================
    # FUTURE RETURNS
    #
    # Sinal fecha no candle t.
    # Entrada ocorre no OPEN t+1.
    # ========================================================

    entry = (
        df["open"]
        .shift(-1)
    )


    for horizon in HORIZONS:

        future_close = (

            df["close"]
            .shift(-horizon)

        )


        df[
            f"future_long_{horizon}"
        ] = (

            future_close
            /
            entry
            -
            1

        )


        df[
            f"future_short_{horizon}"
        ] = (

            entry
            /
            future_close
            -
            1

        )


    # ========================================================
    # EVENT STUDY
    # ========================================================

    for (
        event_name,
        mask,
    ) in events.items():


        # ----------------------------------------------------
        # EVITA EVENTOS CONSECUTIVOS IDÊNTICOS
        #
        # Queremos começo do breakout,
        # não todo candle subsequente.
        # ----------------------------------------------------

        event_start = (

            mask

            &

            ~mask.shift(
                1,
                fill_value=False,
            )

        )


        # ----------------------------------------------------
        # DIREÇÃO NATURAL
        # ----------------------------------------------------

        if "UP" in event_name:

            side = "LONG"

        else:

            side = "SHORT"


        for horizon in HORIZONS:


            if side == "LONG":

                returns = df.loc[

                    event_start,

                    f"future_long_{horizon}",

                ]


            else:

                returns = df.loc[

                    event_start,

                    f"future_short_{horizon}",

                ]


            stats = summarize(
                returns
            )


            rows.append({

                "symbol":
                    symbol,

                "event":
                    event_name,

                "side":
                    side,

                "horizon":
                    horizon,

                "minutes":
                    horizon * 5,

                **stats,

            })


# ============================================================
# RESULTS
# ============================================================

results = pd.DataFrame(
    rows
)


# ============================================================
# AGREGADO
# ============================================================

summary_rows = []


for (
    event,
    side,
    horizon,
    minutes,
), group in results.groupby(

    [
        "event",
        "side",
        "horizon",
        "minutes",
    ]

):


    # Aqui usamos média entre ativos apenas como
    # diagnóstico inicial.

    summary_rows.append({

        "event":
            event,

        "side":
            side,

        "horizon":
            horizon,

        "minutes":
            minutes,

        "total_samples":
            int(
                group[
                    "samples"
                ]
                .sum()
            ),

        "profitable_assets":

            int(
                (
                    group[
                        "mean_return"
                    ]
                    >
                    0
                )
                .sum()
            ),

        "median_asset_pf":

            group[
                "profit_factor"
            ]
            .replace(
                [np.inf, -np.inf],
                np.nan,
            )
            .median(),

        "median_asset_return":

            group[
                "mean_return"
            ]
            .median(),

        "median_asset_win_rate":

            group[
                "win_rate"
            ]
            .median(),

    })


summary = pd.DataFrame(
    summary_rows
)


# ============================================================
# DISPLAY
# ============================================================

display = summary.copy()


for column in [

    "median_asset_return",
    "median_asset_win_rate",

]:

    display[column] *= 100


display = (

    display

    .sort_values(

        [
            "median_asset_pf",
            "median_asset_return",
        ],

        ascending=False,

    )

)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    220,
)


print()

print("=" * 170)

print(
    "EXPERIMENTO 14 — "
    "PRICE STRUCTURE EVENT STUDY"
)

print("=" * 170)

print()


print(

    display.to_string(
        index=False
    )

)


print()

print("=" * 170)

print(
    "RESULTADO DETALHADO POR ATIVO"
)

print("=" * 170)

print()


detailed = results.copy()


detailed[
    "mean_return"
] *= 100

detailed[
    "median_return"
] *= 100

detailed[
    "win_rate"
] *= 100


print(

    detailed

    .sort_values(

        [
            "event",
            "horizon",
            "symbol",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

results.to_csv(

    RESULTS_DIR
    / "structure_events_by_asset.csv",

    index=False,

)


summary.to_csv(

    RESULTS_DIR
    / "structure_events_summary.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
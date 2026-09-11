from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv


# ============================================================
# CONFIG
# ============================================================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]


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


COSTS = [
    0.0000,  # bruto
    0.0002,  # 0.02%
    0.0004,  # 0.04%
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

    return df


# ============================================================
# PROFIT FACTOR
# ============================================================

def profit_factor(returns):

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
            profit_factor(returns),

    }


# ============================================================
# EVENTOS
# ============================================================

event_rows = []


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
    # ESTRUTURA PASSADA
    #
    # Candle atual nunca entra no cálculo.
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
    # FALSE BREAKOUT / WICK REJECTION
    #
    # UP:
    # high ultrapassa estrutura,
    # mas close volta para dentro.
    #
    # DOWN:
    # low rompe estrutura,
    # mas close volta para dentro.
    # ========================================================

    events = {

        # ----------------------------------------------------
        # 1H
        # ----------------------------------------------------

        "REJECT_UP_1H":

            (
                df["high"]
                >
                df["prior_high_1h"]
            )

            &

            (
                df["close"]
                <=
                df["prior_high_1h"]
            ),


        "REJECT_DOWN_1H":

            (
                df["low"]
                <
                df["prior_low_1h"]
            )

            &

            (
                df["close"]
                >=
                df["prior_low_1h"]
            ),


        # ----------------------------------------------------
        # 4H
        # ----------------------------------------------------

        "REJECT_UP_4H":

            (
                df["high"]
                >
                df["prior_high_4h"]
            )

            &

            (
                df["close"]
                <=
                df["prior_high_4h"]
            ),


        "REJECT_DOWN_4H":

            (
                df["low"]
                <
                df["prior_low_4h"]
            )

            &

            (
                df["close"]
                >=
                df["prior_low_4h"]
            ),

    }


    # ========================================================
    # ENTRADA
    # ========================================================

    entry = (
        df["open"]
        .shift(-1)
    )


    # ========================================================
    # TARGETS
    # ========================================================

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
    # LOOP DOS EVENTOS
    # ========================================================

    for (
        event_name,
        raw_mask,
    ) in events.items():


        # ----------------------------------------------------
        # Evita várias rejeições consecutivas sendo contadas
        # como eventos completamente novos.
        # ----------------------------------------------------

        event_start = (

            raw_mask

            &

            ~raw_mask.shift(
                1,
                fill_value=False,
            )

        )


        # ----------------------------------------------------
        # Rejeição superior -> SHORT
        #
        # Rejeição inferior -> LONG
        # ----------------------------------------------------

        if "REJECT_UP" in event_name:

            side = "SHORT"

        else:

            side = "LONG"


        indices = df.index[
            event_start
        ]


        for i in indices:

            row = df.loc[i]


            year = (
                str(
                    row["period"]
                )[:4]
            )


            # =================================================
            # TAMANHO DA REJEIÇÃO
            #
            # Só para salvar como feature.
            # Ainda NÃO filtramos por ela.
            # =================================================

            if "UP" in event_name:

                if "1H" in event_name:
                    level = row["prior_high_1h"]

                else:
                    level = row["prior_high_4h"]


                penetration = (

                    row["high"]
                    /
                    level
                    -
                    1

                )


                rejection_distance = (

                    row["high"]
                    -
                    row["close"]

                ) / row["close"]


            else:

                if "1H" in event_name:
                    level = row["prior_low_1h"]

                else:
                    level = row["prior_low_4h"]


                penetration = (

                    level
                    /
                    row["low"]
                    -
                    1

                )


                rejection_distance = (

                    row["close"]
                    -
                    row["low"]

                ) / row["close"]


            # =================================================
            # CANDLE RANGE
            # =================================================

            candle_range = (

                row["high"]
                -
                row["low"]

            )


            if candle_range > 0:

                close_position = (

                    row["close"]
                    -
                    row["low"]

                ) / candle_range

            else:

                close_position = np.nan


            # =================================================
            # HORIZONS
            # =================================================

            for horizon in HORIZONS:


                if side == "SHORT":

                    gross_return = row[

                        f"future_short_{horizon}"

                    ]

                else:

                    gross_return = row[

                        f"future_long_{horizon}"

                    ]


                if pd.isna(
                    gross_return
                ):
                    continue


                for cost in COSTS:


                    event_rows.append({

                        "symbol":
                            symbol,

                        "period":
                            row["period"],

                        "year":
                            year,

                        "event":
                            event_name,

                        "side":
                            side,

                        "horizon":
                            horizon,

                        "minutes":
                            horizon * 5,

                        "cost":
                            cost,

                        "gross_return":
                            gross_return,

                        "net_return":
                            gross_return
                            -
                            cost,

                        "penetration":
                            penetration,

                        "rejection_distance":
                            rejection_distance,

                        "close_position":
                            close_position,

                    })


# ============================================================
# DATAFRAME
# ============================================================

events_df = pd.DataFrame(
    event_rows
)


# ============================================================
# SUMMARY GLOBAL
# ============================================================

summary_rows = []


group_columns = [

    "event",
    "side",
    "horizon",
    "minutes",
    "cost",

]


for keys, group in events_df.groupby(
    group_columns
):


    (
        event,
        side,
        horizon,
        minutes,
        cost,
    ) = keys


    returns = group[
        "net_return"
    ]


    summary_rows.append({

        "event":
            event,

        "side":
            side,

        "horizon":
            horizon,

        "minutes":
            minutes,

        "cost":
            cost,

        **summarize(
            returns
        ),

    })


summary = pd.DataFrame(
    summary_rows
)


# ============================================================
# POR ANO
# ============================================================

year_rows = []


for keys, group in events_df.groupby(

    [
        "year",
        "event",
        "side",
        "horizon",
        "minutes",
        "cost",
    ]

):


    (
        year,
        event,
        side,
        horizon,
        minutes,
        cost,
    ) = keys


    year_rows.append({

        "year":
            year,

        "event":
            event,

        "side":
            side,

        "horizon":
            horizon,

        "minutes":
            minutes,

        "cost":
            cost,

        **summarize(
            group[
                "net_return"
            ]
        ),

    })


year_summary = pd.DataFrame(
    year_rows
)


# ============================================================
# POR ATIVO
# ============================================================

asset_rows = []


for keys, group in events_df.groupby(

    [
        "symbol",
        "event",
        "side",
        "horizon",
        "minutes",
        "cost",
    ]

):


    (
        symbol,
        event,
        side,
        horizon,
        minutes,
        cost,
    ) = keys


    asset_rows.append({

        "symbol":
            symbol,

        "event":
            event,

        "side":
            side,

        "horizon":
            horizon,

        "minutes":
            minutes,

        "cost":
            cost,

        **summarize(
            group[
                "net_return"
            ]
        ),

    })


asset_summary = pd.DataFrame(
    asset_rows
)


# ============================================================
# DISPLAY
# ============================================================

def display_percentages(df):

    output = df.copy()

    for column in [

        "cost",
        "mean_return",
        "median_return",
        "win_rate",

    ]:

        if column in output.columns:

            output[column] *= 100

    return output


summary_display = display_percentages(
    summary
)


year_display = display_percentages(
    year_summary
)


asset_display = display_percentages(
    asset_summary
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    260,
)


# ============================================================
# OUTPUT GLOBAL
# ============================================================

print()

print("=" * 190)

print(
    "EXPERIMENTO 15 — "
    "FALSE BREAKOUT / REJECTION"
)

print("=" * 190)

print()


print(

    summary_display

    .sort_values(

        [
            "profit_factor",
            "mean_return",
        ],

        ascending=False,

    )

    .to_string(
        index=False
    )

)


# ============================================================
# MELHORES BRUTOS POR ANO
# ============================================================

year_focus = year_display[

    year_display[
        "cost"
    ]
    ==
    0

].copy()


print()

print("=" * 190)

print(
    "RESULTADO BRUTO POR ANO"
)

print("=" * 190)

print()


print(

    year_focus

    .sort_values(

        [
            "event",
            "horizon",
            "year",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# MELHORES BRUTOS POR ATIVO
# ============================================================

asset_focus = asset_display[

    asset_display[
        "cost"
    ]
    ==
    0

].copy()


print()

print("=" * 190)

print(
    "RESULTADO BRUTO POR ATIVO"
)

print("=" * 190)

print()


print(

    asset_focus

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

events_df.to_csv(

    RESULTS_DIR
    / "false_breakout_events.csv",

    index=False,

)


summary.to_csv(

    RESULTS_DIR
    / "false_breakout_summary.csv",

    index=False,

)


year_summary.to_csv(

    RESULTS_DIR
    / "false_breakout_by_year.csv",

    index=False,

)


asset_summary.to_csv(

    RESULTS_DIR
    / "false_breakout_by_asset.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
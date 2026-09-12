from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv
from research.indicators import add_all_indicators
from research.features import add_all_features
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
    ("2026-02", "2026-02-01", "2026-03-01"),
    ("2026-03", "2026-03-01", "2026-04-01"),
    ("2026-04", "2026-04-01", "2026-05-01"),
    ("2026-05", "2026-05-01", "2026-06-01"),
    ("2026-06", "2026-06-01", "2026-07-01"),
    ("2026-07", "2026-07-01", "2026-08-01"),
]


INTERVAL = "5m"

MAX_HORIZON = 12


PATH_HORIZONS = [
    1,   # 5 min
    2,   # 10 min
    3,   # 15 min
    4,   # 20 min
    6,   # 30 min
    8,   # 40 min
    10,  # 50 min
    12,  # 60 min
]


DATA_DIR = Path("data")
RESULTS_DIR = Path("results")

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# CARREGA SÉRIE CONTÍNUA
# ============================================================

def load_continuous_symbol(symbol):

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

    return df


# ============================================================
# EVENTOS
# ============================================================

event_rows = []


for symbol in SYMBOLS:

    print()

    print("=" * 100)
    print(f"PROCESSANDO {symbol}")
    print("=" * 100)

    df = load_continuous_symbol(
        symbol
    )

    if df is None:
        continue


    # ========================================================
    # INDICADORES
    # ========================================================

    df = add_all_indicators(df)

    df = add_all_features(df)


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

        MAX_HORIZON,

    )


    positions = np.flatnonzero(
        clean_mask.to_numpy()
    )


    # ========================================================
    # LOOP DOS EVENTOS
    # ========================================================

    for i in positions:

        # Precisamos de 12 candles futuros.
        if (
            i + MAX_HORIZON
            >= len(df)
        ):
            continue


        # ====================================================
        # FILTRO ATR
        # ====================================================

        atr_expansion = (
            df.iloc[i][
                "atr_expansion"
            ]
        )


        if pd.isna(
            atr_expansion
        ):
            continue


        if not (
            0.80
            <= atr_expansion
            < 1.00
        ):
            continue


        # ====================================================
        # ENTRADA
        #
        # sinal em candle i
        # entrada no OPEN i+1
        # ====================================================

        entry_price = float(

            df.iloc[
                i + 1
            ]["open"]

        )


        if (
            not np.isfinite(
                entry_price
            )
            or entry_price <= 0
        ):
            continue


        row = {

            "symbol":
                symbol,

            "period":
                df.iloc[i][
                    "period"
                ],

            "signal_time":
                df.iloc[i][
                    "open_time"
                ],

            "entry_price":
                entry_price,

            "atr_expansion":
                atr_expansion,

        }


        # ====================================================
        # CAMINHO DO RETORNO
        # ====================================================

        for horizon in PATH_HORIZONS:

            exit_price = float(

                df.iloc[
                    i + horizon
                ]["close"]

            )


            # SHORT:
            #
            # entry / exit - 1
            #
            short_return = (

                entry_price
                / exit_price
                - 1

            )


            row[
                f"return_{horizon}"
            ] = short_return


        # ====================================================
        # MFE / MAE
        #
        # próximos 12 candles
        # ====================================================

        future_window = df.iloc[

            i + 1
            :
            i + MAX_HORIZON + 1

        ]


        lows = (
            future_window[
                "low"
            ]
            .astype(float)
            .to_numpy()
        )


        highs = (
            future_window[
                "high"
            ]
            .astype(float)
            .to_numpy()
        )


        # ----------------------------------------------------
        # MFE SHORT
        #
        # maior queda a nosso favor
        # ----------------------------------------------------

        favorable = (

            entry_price
            / lows
            - 1

        )


        mfe_index = int(
            np.argmax(
                favorable
            )
        )


        mfe = float(
            favorable[
                mfe_index
            ]
        )


        # ----------------------------------------------------
        # MAE SHORT
        #
        # alta contra nossa posição
        #
        # positivo = magnitude da perda
        # ----------------------------------------------------

        adverse = (

            highs
            / entry_price
            - 1

        )


        mae_index = int(
            np.argmax(
                adverse
            )
        )


        mae = float(
            adverse[
                mae_index
            ]
        )


        row[
            "mfe"
        ] = mfe


        row[
            "mae"
        ] = mae


        row[
            "time_to_mfe"
        ] = (
            mfe_index + 1
        )


        row[
            "time_to_mae"
        ] = (
            mae_index + 1
        )


        # ====================================================
        # FECHAMENTO 60 MIN
        # ====================================================

        row[
            "final_return"
        ] = row[
            "return_12"
        ]


        row[
            "regime_group"
        ] = (

            "JULY"

            if row[
                "period"
            ]
            == "2026-07"

            else
            "FEB_JUN"

        )


        event_rows.append(
            row
        )


# ============================================================
# DATAFRAME
# ============================================================

events = pd.DataFrame(
    event_rows
)


# ============================================================
# PERFORMANCE DO CAMINHO
# ============================================================

path_rows = []


for group_name in [
    "FEB_JUN",
    "JULY",
]:

    subset = events[

        events[
            "regime_group"
        ]
        ==
        group_name

    ]


    for horizon in PATH_HORIZONS:

        returns = (

            subset[
                f"return_{horizon}"
            ]
            .dropna()

        )


        if len(returns) == 0:
            continue


        path_rows.append({

            "regime_group":
                group_name,

            "horizon":
                horizon,

            "minutes":
                horizon * 5,

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

            "q10":
                returns.quantile(
                    0.10
                ),

            "q25":
                returns.quantile(
                    0.25
                ),

            "q75":
                returns.quantile(
                    0.75
                ),

            "q90":
                returns.quantile(
                    0.90
                ),

        })


path_df = pd.DataFrame(
    path_rows
)


# ============================================================
# MFE / MAE
# ============================================================

excursion_rows = []


for group_name in [
    "FEB_JUN",
    "JULY",
]:

    subset = events[

        events[
            "regime_group"
        ]
        ==
        group_name

    ].copy()


    if subset.empty:
        continue


    excursion_rows.append({

        "regime_group":
            group_name,

        "samples":
            len(subset),

        "mean_mfe":
            subset[
                "mfe"
            ].mean(),

        "median_mfe":
            subset[
                "mfe"
            ].median(),

        "mean_mae":
            subset[
                "mae"
            ].mean(),

        "median_mae":
            subset[
                "mae"
            ].median(),

        "median_time_to_mfe":
            subset[
                "time_to_mfe"
            ].median(),

        "median_time_to_mae":
            subset[
                "time_to_mae"
            ].median(),

        "mfe_gt_020_rate":

            (
                subset[
                    "mfe"
                ]
                >= 0.002
            ).mean(),

        "mfe_gt_040_rate":

            (
                subset[
                    "mfe"
                ]
                >= 0.004
            ).mean(),

        "mfe_gt_060_rate":

            (
                subset[
                    "mfe"
                ]
                >= 0.006
            ).mean(),

        "mae_gt_020_rate":

            (
                subset[
                    "mae"
                ]
                >= 0.002
            ).mean(),

        "mae_gt_040_rate":

            (
                subset[
                    "mae"
                ]
                >= 0.004
            ).mean(),

    })


excursion_df = pd.DataFrame(
    excursion_rows
)


# ============================================================
# CAUDA DE RETORNOS 60 MIN
# ============================================================

tail_rows = []


for group_name in [
    "FEB_JUN",
    "JULY",
]:

    returns = events.loc[

        events[
            "regime_group"
        ]
        ==
        group_name,

        "final_return",

    ].dropna()


    if len(returns) == 0:
        continue


    tail_rows.append({

        "regime_group":
            group_name,

        "samples":
            len(returns),

        "min":
            returns.min(),

        "q05":
            returns.quantile(
                0.05
            ),

        "q10":
            returns.quantile(
                0.10
            ),

        "q25":
            returns.quantile(
                0.25
            ),

        "median":
            returns.median(),

        "q75":
            returns.quantile(
                0.75
            ),

        "q90":
            returns.quantile(
                0.90
            ),

        "q95":
            returns.quantile(
                0.95
            ),

        "max":
            returns.max(),

    })


tail_df = pd.DataFrame(
    tail_rows
)


# ============================================================
# DISPLAY
# ============================================================

path_display = (
    path_df.copy()
)


for column in [

    "mean_return",
    "median_return",
    "win_rate",
    "q10",
    "q25",
    "q75",
    "q90",

]:

    path_display[
        column
    ] *= 100


excursion_display = (
    excursion_df.copy()
)


for column in [

    "mean_mfe",
    "median_mfe",
    "mean_mae",
    "median_mae",

    "mfe_gt_020_rate",
    "mfe_gt_040_rate",
    "mfe_gt_060_rate",

    "mae_gt_020_rate",
    "mae_gt_040_rate",

]:

    excursion_display[
        column
    ] *= 100


tail_display = (
    tail_df.copy()
)


for column in [

    "min",
    "q05",
    "q10",
    "q25",
    "median",
    "q75",
    "q90",
    "q95",
    "max",

]:

    tail_display[
        column
    ] *= 100


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    260,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 180)

print(
    "EXPERIMENTO 8 — "
    "FORWARD RETURN PATH"
)

print("=" * 180)

print()


print(
    path_display.to_string(
        index=False
    )
)


print()

print("=" * 180)

print(
    "MFE / MAE — "
    "EXCURSÃO FAVORÁVEL E ADVERSA"
)

print("=" * 180)

print()


print(
    excursion_display.to_string(
        index=False
    )
)


print()

print("=" * 180)

print(
    "DISTRIBUIÇÃO DO RETORNO "
    "EM 60 MINUTOS"
)

print("=" * 180)

print()


print(
    tail_display.to_string(
        index=False
    )
)


# ============================================================
# SALVA
# ============================================================

events.to_csv(

    RESULTS_DIR
    / "forward_path_events.csv",

    index=False,

)


path_df.to_csv(

    RESULTS_DIR
    / "forward_path_summary.csv",

    index=False,

)


excursion_df.to_csv(

    RESULTS_DIR
    / "forward_excursion_summary.csv",

    index=False,

)


tail_df.to_csv(

    RESULTS_DIR
    / "forward_return_distribution.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
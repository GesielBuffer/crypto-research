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
# CANDIDATO CONGELADO
# ============================================================

PENETRATION_MIN = 0.035
PENETRATION_MAX = 0.070

MAX_HOLD = 12


COSTS = [
    0.0000,
    0.0002,
    0.0004,
]


# ============================================================
# LOAD
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


    return positive / negative


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
            "q10": np.nan,
            "q90": np.nan,

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
            profit_factor(
                returns
            ),

        "q10":
            returns.quantile(0.10),

        "q90":
            returns.quantile(0.90),

    }


# ============================================================
# EVENTOS
# ============================================================

trade_rows = []


for symbol in SYMBOLS:

    print()

    print("=" * 100)

    print(
        f"PROCESSANDO {symbol}"
    )

    print("=" * 100)


    df = load_symbol(symbol)


    if df is None:
        continue


    # ========================================================
    # ESTRUTURA PASSADA 4H
    # ========================================================

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


    df["prior_range_4h"] = (

        df["prior_high_4h"]
        -
        df["prior_low_4h"]

    )


    # ========================================================
    # REJECT DOWN
    # ========================================================

    raw_reject = (

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
        )

    )


    # ========================================================
    # APENAS COMEÇO DO EVENTO
    # ========================================================

    event_start = (

        raw_reject

        &

        ~raw_reject.shift(
            1,
            fill_value=False,
        )

    )


    positions = np.flatnonzero(
        event_start.to_numpy()
    )


    for i in positions:


        if (
            i + MAX_HOLD + 1
            >=
            len(df)
        ):
            continue


        signal = df.iloc[i]


        prior_range = float(
            signal["prior_range_4h"]
        )


        prior_low = float(
            signal["prior_low_4h"]
        )


        rejection_low = float(
            signal["low"]
        )


        if (

            not np.isfinite(
                prior_range
            )

            or

            prior_range <= 0

        ):
            continue


        penetration = (

            prior_low
            -
            rejection_low

        ) / prior_range


        # ====================================================
        # CANDIDATO CONGELADO
        # ====================================================

        if not (

            PENETRATION_MIN
            <=
            penetration
            <
            PENETRATION_MAX

        ):
            continue


        entry_index = i + 1


        entry_price = float(

            df.iloc[
                entry_index
            ]["open"]

        )


        if (

            not np.isfinite(
                entry_price
            )

            or

            entry_price <= 0

        ):
            continue


        # ====================================================
        # 1 — TIME ONLY
        # ====================================================

        exit_index = (
            i + MAX_HOLD
        )


        time_exit = float(

            df.iloc[
                exit_index
            ]["close"]

        )


        time_return = (

            time_exit
            /
            entry_price
            -
            1

        )


        trade_rows.append({

            "symbol":
                symbol,

            "period":
                signal["period"],

            "year":
                str(
                    signal["period"]
                )[:4],

            "open_time":
                signal["open_time"],

            "strategy":
                "TIME_ONLY",

            "penetration_norm":
                penetration,

            "entry_price":
                entry_price,

            "exit_price":
                time_exit,

            "holding_bars":
                MAX_HOLD,

            "exit_reason":
                "TIME",

            "gross_return":
                time_return,

        })


        # ====================================================
        # 2 — HARD STOP NA MÍNIMA DA REJEIÇÃO
        # ====================================================

        stop_price = (
            rejection_low
        )


        exit_price = (
            time_exit
        )

        holding_bars = (
            MAX_HOLD
        )

        exit_reason = (
            "TIME"
        )


        for step in range(
            1,
            MAX_HOLD + 1,
        ):


            bar = df.iloc[
                i + step
            ]


            bar_open = float(
                bar["open"]
            )

            bar_low = float(
                bar["low"]
            )


            # ------------------------------------------------
            # GAP / OPEN ABAIXO DO STOP
            #
            # Conservador: sai no open real,
            # não no stop teórico.
            # ------------------------------------------------

            if (
                bar_open
                <=
                stop_price
            ):

                exit_price = (
                    bar_open
                )

                holding_bars = (
                    step
                )

                exit_reason = (
                    "STOP_GAP"
                )

                break


            # ------------------------------------------------
            # STOP INTRABAR
            # ------------------------------------------------

            if (
                bar_low
                <=
                stop_price
            ):

                exit_price = (
                    stop_price
                )

                holding_bars = (
                    step
                )

                exit_reason = (
                    "STOP_REJECTION_LOW"
                )

                break


        gross_return = (

            exit_price
            /
            entry_price
            -
            1

        )


        trade_rows.append({

            "symbol":
                symbol,

            "period":
                signal["period"],

            "year":
                str(
                    signal["period"]
                )[:4],

            "open_time":
                signal["open_time"],

            "strategy":
                "STOP_REJECTION_LOW",

            "penetration_norm":
                penetration,

            "entry_price":
                entry_price,

            "exit_price":
                exit_price,

            "holding_bars":
                holding_bars,

            "exit_reason":
                exit_reason,

            "gross_return":
                gross_return,

        })


        # ====================================================
        # 3 — RECLAIM FAILURE
        #
        # Se um candle fechar novamente abaixo
        # da antiga mínima 4H, saímos no OPEN
        # do candle seguinte.
        #
        # Não há look-ahead.
        # ====================================================

        exit_price = (
            time_exit
        )

        holding_bars = (
            MAX_HOLD
        )

        exit_reason = (
            "TIME"
        )


        # Só podemos reagir até o candle 11,
        # pois precisamos do open seguinte.
        for step in range(
            1,
            MAX_HOLD,
        ):


            bar = df.iloc[
                i + step
            ]


            close_price = float(
                bar["close"]
            )


            if (
                close_price
                <
                prior_low
            ):


                next_bar = df.iloc[
                    i + step + 1
                ]


                exit_price = float(
                    next_bar["open"]
                )


                holding_bars = (
                    step + 1
                )


                exit_reason = (
                    "RECLAIM_FAILURE"
                )

                break


        gross_return = (

            exit_price
            /
            entry_price
            -
            1

        )


        trade_rows.append({

            "symbol":
                symbol,

            "period":
                signal["period"],

            "year":
                str(
                    signal["period"]
                )[:4],

            "open_time":
                signal["open_time"],

            "strategy":
                "RECLAIM_FAILURE",

            "penetration_norm":
                penetration,

            "entry_price":
                entry_price,

            "exit_price":
                exit_price,

            "holding_bars":
                holding_bars,

            "exit_reason":
                exit_reason,

            "gross_return":
                gross_return,

        })


# ============================================================
# DATAFRAME
# ============================================================

trades = pd.DataFrame(
    trade_rows
)


print()

print(
    f"Registros de estratégia: "
    f"{len(trades)}"
)


print(
    f"Eventos únicos aproximados: "
    f"{len(trades) // 3}"
)


# ============================================================
# COST EXPANSION
#
# Aqui é pequeno:
# somente summary,
# não duplicamos arquivo gigante.
# ============================================================

summary_rows = []


for strategy, group in trades.groupby(
    "strategy"
):


    gross = group[
        "gross_return"
    ]


    for cost in COSTS:


        net = (
            gross
            -
            cost
        )


        summary_rows.append({

            "strategy":
                strategy,

            "cost":
                cost,

            **summarize(net),

            "median_holding_bars":

                group[
                    "holding_bars"
                ].median(),

        })


summary = pd.DataFrame(
    summary_rows
)


# ============================================================
# POR ANO
# ============================================================

year_rows = []


for (
    year,
    strategy,
), group in trades.groupby(

    [
        "year",
        "strategy",
    ]

):


    for cost in COSTS:


        net = (

            group[
                "gross_return"
            ]

            -
            cost

        )


        year_rows.append({

            "year":
                year,

            "strategy":
                strategy,

            "cost":
                cost,

            **summarize(net),

            "median_holding_bars":

                group[
                    "holding_bars"
                ].median(),

        })


year_summary = pd.DataFrame(
    year_rows
)


# ============================================================
# POR ATIVO
# ============================================================

asset_rows = []


for (
    symbol,
    strategy,
), group in trades.groupby(

    [
        "symbol",
        "strategy",
    ]

):


    for cost in COSTS:


        net = (

            group[
                "gross_return"
            ]

            -
            cost

        )


        asset_rows.append({

            "symbol":
                symbol,

            "strategy":
                strategy,

            "cost":
                cost,

            **summarize(net),

            "median_holding_bars":

                group[
                    "holding_bars"
                ].median(),

        })


asset_summary = pd.DataFrame(
    asset_rows
)


# ============================================================
# EXIT REASONS
# ============================================================

exit_reason_summary = (

    trades

    .groupby(

        [
            "strategy",
            "exit_reason",
        ],

        as_index=False,

    )

    .agg(

        samples=(
            "gross_return",
            "size",
        ),

        mean_return=(
            "gross_return",
            "mean",
        ),

        median_return=(
            "gross_return",
            "median",
        ),

        median_holding_bars=(
            "holding_bars",
            "median",
        ),

    )

)


# ============================================================
# DISPLAY
# ============================================================

def percent_display(
    df,
):

    output = df.copy()


    for column in [

        "cost",
        "mean_return",
        "median_return",
        "win_rate",
        "q10",
        "q90",

    ]:

        if column in output.columns:

            output[
                column
            ] *= 100


    return output


summary_display = percent_display(
    summary
)


year_display = percent_display(
    year_summary
)


asset_display = percent_display(
    asset_summary
)


exit_display = percent_display(
    exit_reason_summary
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
# OUTPUT 1
# ============================================================

print()

print("=" * 190)

print(
    "EXPERIMENTO 17 — "
    "REJECTION OPERATIONAL BACKTEST"
)

print("=" * 190)

print()


print(

    summary_display

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
# OUTPUT 2
# ============================================================

print()

print("=" * 190)

print(
    "RESULTADO POR ANO"
)

print("=" * 190)

print()


print(

    year_display

    .sort_values(

        [
            "strategy",
            "cost",
            "year",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 3
# ============================================================

print()

print("=" * 190)

print(
    "RESULTADO POR ATIVO"
)

print("=" * 190)

print()


print(

    asset_display

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
# OUTPUT 4
# ============================================================

print()

print("=" * 190)

print(
    "MOTIVOS DE SAÍDA"
)

print("=" * 190)

print()


print(

    exit_display

    .sort_values(

        [
            "strategy",
            "exit_reason",
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
    / "rejection_operational_trades.csv",

    index=False,

)


summary.to_csv(

    RESULTS_DIR
    / "rejection_operational_summary.csv",

    index=False,

)


year_summary.to_csv(

    RESULTS_DIR
    / "rejection_operational_by_year.csv",

    index=False,

)


asset_summary.to_csv(

    RESULTS_DIR
    / "rejection_operational_by_asset.csv",

    index=False,

)


exit_reason_summary.to_csv(

    RESULTS_DIR
    / "rejection_operational_exit_reasons.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
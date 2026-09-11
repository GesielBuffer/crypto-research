from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv


# ============================================================
# EXPERIMENTO 28
# BRANCH 05 — TAKER FLOW IMBALANCE
#
# DEVELOPMENT ONLY:
# 2024-01 -> 2026-07
#
# AGOSTO JÁ FOI OBSERVADO.
# SETEMBRO/2026 CONTINUA INTOCADO.
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


# ============================================================
# DEVELOPMENT PERIOD
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
# EVENT SPEC
# ============================================================

BARS_PER_DAY = 288

LOOKBACK = 7 * BARS_PER_DAY

MIN_PERIODS = 3 * BARS_PER_DAY


LOW_QUANTILE = 0.01
HIGH_QUANTILE = 0.99


# ============================================================
# HORIZONS
# ============================================================

HORIZONS = [
    1,    # 5m
    3,    # 15m
    6,    # 30m
    12,   # 60m
]


BAR_MINUTES = 5


# ============================================================
# COSTS
# ============================================================

COSTS = [
    0.0000,
    0.0004,
    0.0006,
]


BASE_COST = 0.0006


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

            raise FileNotFoundError(
                f"Arquivo não encontrado: {path}"
            )


        df = load_csv(path)


        df["period"] = period


        df["open_time"] = pd.to_datetime(
            df["open_time"],
            utc=True,
        )


        # ----------------------------------------------------
        # Binance files may contain either quote-level
        # or base-level taker volume.
        # ----------------------------------------------------

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]


        optional_numeric = [
            "quote_volume",
            "taker_buy_base",
            "taker_buy_quote",
        ]


        for column in (
            numeric_columns
            +
            optional_numeric
        ):

            if column in df.columns:

                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )


        # ----------------------------------------------------
        # Prefer quote-volume imbalance.
        # Fall back to base-volume imbalance.
        # ----------------------------------------------------

        if (
            "quote_volume" in df.columns
            and
            "taker_buy_quote" in df.columns
        ):

            df["flow_total"] = (
                df["quote_volume"]
            )

            df["flow_taker_buy"] = (
                df["taker_buy_quote"]
            )


        elif (
            "volume" in df.columns
            and
            "taker_buy_base" in df.columns
        ):

            df["flow_total"] = (
                df["volume"]
            )

            df["flow_taker_buy"] = (
                df["taker_buy_base"]
            )


        else:

            raise RuntimeError(
                f"{symbol}: arquivos não possuem "
                "taker_buy_quote/quote_volume "
                "nem taker_buy_base/volume."
            )


        frames.append(df)


    result = pd.concat(
        frames,
        ignore_index=True,
    )


    result = (
        result

        .dropna(
            subset=[
                "open_time",
                "open",
                "close",
                "flow_total",
                "flow_taker_buy",
            ]
        )

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


    return result


# ============================================================
# PROFIT FACTOR
# ============================================================

def profit_factor(returns):

    values = (
        pd.Series(returns)
        .dropna()
    )


    if len(values) == 0:
        return np.nan


    gains = (
        values[
            values > 0
        ]
        .sum()
    )


    losses = (
        values[
            values < 0
        ]
        .abs()
        .sum()
    )


    if losses == 0:

        if gains > 0:
            return np.inf

        return np.nan


    return gains / losses


# ============================================================
# TRIMMED MEAN
# ============================================================

def trimmed_mean(
    returns,
    trim=0.05,
):

    values = np.asarray(
        pd.Series(returns)
        .dropna(),
        dtype=float,
    )


    if len(values) == 0:
        return np.nan


    values = np.sort(values)


    cut = int(
        len(values)
        *
        trim
    )


    if (
        cut == 0
        or
        len(values)
        <= 2 * cut
    ):

        return values.mean()


    return (
        values[
            cut:-cut
        ]
        .mean()
    )


# ============================================================
# WINSORIZED MEAN
# ============================================================

def winsorized_mean(
    returns,
    limit=0.05,
):

    values = np.asarray(
        pd.Series(returns)
        .dropna(),
        dtype=float,
    )


    if len(values) == 0:
        return np.nan


    low = np.quantile(
        values,
        limit,
    )


    high = np.quantile(
        values,
        1 - limit,
    )


    return (
        np.clip(
            values,
            low,
            high,
        )
        .mean()
    )


# ============================================================
# SUMMARY
# ============================================================

def summarize(returns):

    values = (
        pd.Series(returns)
        .dropna()
    )


    if len(values) == 0:

        return {
            "samples": 0,
            "mean_return": np.nan,
            "median_return": np.nan,
            "trimmed_mean_5": np.nan,
            "winsorized_mean_5": np.nan,
            "win_rate": np.nan,
            "profit_factor": np.nan,
            "q10": np.nan,
            "q90": np.nan,
        }


    return {

        "samples":
            len(values),

        "mean_return":
            values.mean(),

        "median_return":
            values.median(),

        "trimmed_mean_5":
            trimmed_mean(values),

        "winsorized_mean_5":
            winsorized_mean(values),

        "win_rate":
            (
                values > 0
            ).mean(),

        "profit_factor":
            profit_factor(values),

        "q10":
            values.quantile(0.10),

        "q90":
            values.quantile(0.90),

    }


# ============================================================
# BUILD EVENTS
# ============================================================

event_frames = []


for symbol in SYMBOLS:


    print()

    print("=" * 100)

    print(
        f"PROCESSANDO TAKER FLOW — {symbol}"
    )

    print("=" * 100)


    df = load_symbol(symbol)


    # ========================================================
    # BUY SHARE
    # ========================================================

    df["buy_share"] = np.where(

        df["flow_total"] > 0,

        df["flow_taker_buy"]
        /
        df["flow_total"],

        np.nan,

    )


    # ========================================================
    # IMBALANCE
    #
    # [-1, +1] approximately
    # ========================================================

    df["flow_imbalance"] = (
        2.0
        *
        df["buy_share"]
        -
        1.0
    )


    # ========================================================
    # CLIP ONLY NUMERICAL NOISE
    # ========================================================

    df["flow_imbalance"] = (
        df["flow_imbalance"]
        .clip(
            lower=-1.0,
            upper=1.0,
        )
    )


    # ========================================================
    # ROLLING ADAPTIVE TAILS
    #
    # Past only.
    # ========================================================

    df["flow_q01"] = (
        df["flow_imbalance"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            LOW_QUANTILE
        )

        .shift(1)
    )


    df["flow_q99"] = (
        df["flow_imbalance"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            HIGH_QUANTILE
        )

        .shift(1)
    )


    # ========================================================
    # HISTORICAL FLOW STD
    # ========================================================

    df["flow_std"] = (
        df["flow_imbalance"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .std()

        .shift(1)
    )


    df["flow_z"] = (
        df["flow_imbalance"]
        /
        df["flow_std"]
    )


    # ========================================================
    # EXTREME FLOW STATES
    # ========================================================

    extreme_buy_state = (
        df["flow_imbalance"]
        >=
        df["flow_q99"]
    ).fillna(False)


    extreme_sell_state = (
        df["flow_imbalance"]
        <=
        df["flow_q01"]
    ).fillna(False)


    # ========================================================
    # FIRST CROSSING
    #
    # Avoid repeated consecutive tail candles.
    # ========================================================

    extreme_buy = (
        extreme_buy_state

        &

        ~extreme_buy_state
        .shift(1)
        .fillna(False)
    )


    extreme_sell = (
        extreme_sell_state

        &

        ~extreme_sell_state
        .shift(1)
        .fillna(False)
    )


    # ========================================================
    # SIGNAL CANDLE PRICE RETURN
    # Diagnostic only.
    # ========================================================

    df["signal_return"] = (
        df["close"]
        /
        df["open"]
        -
        1
    )


    # ========================================================
    # FUTURE RETURNS
    # ========================================================

    entry = (
        df["open"]
        .shift(-1)
    )


    for horizon in HORIZONS:


        exit_price = (
            df["close"]
            .shift(-horizon)
        )


        df[
            f"future_long_{horizon}"
        ] = (
            exit_price
            /
            entry
            -
            1
        )


        # Linear USDT-margined futures short PnL

        df[
            f"future_short_{horizon}"
        ] = (
            1
            -
            exit_price
            /
            entry
        )


    masks = {

        "EXTREME_BUY":
            extreme_buy,

        "EXTREME_SELL":
            extreme_sell,

    }


    for event_name, mask in masks.items():


        temp = (
            df.loc[
                mask
            ]
            .copy()
        )


        temp["symbol"] = symbol

        temp["event"] = event_name

        temp["year"] = (
            temp["period"]
            .astype(str)
            .str[:4]
        )


        event_frames.append(
            temp
        )


# ============================================================
# CONCAT
# ============================================================

events = pd.concat(
    event_frames,
    ignore_index=True,
)


events = (
    events

    .sort_values(
        [
            "open_time",
            "symbol",
        ]
    )

    .reset_index(
        drop=True
    )
)


events = events.dropna(
    subset=[
        f"future_long_{max(HORIZONS)}",
        f"future_short_{max(HORIZONS)}",
    ]
)


# ============================================================
# COUNTS
# ============================================================

counts = (
    events

    .groupby(
        [
            "event",
            "symbol",
        ]
    )

    .size()

    .rename("samples")

    .reset_index()
)


# ============================================================
# ANATOMY
# ============================================================

anatomy = (
    events

    .groupby(
        "event",
        as_index=False,
    )

    .agg(

        samples=(
            "event",
            "size",
        ),

        mean_flow_imbalance=(
            "flow_imbalance",
            "mean",
        ),

        median_flow_imbalance=(
            "flow_imbalance",
            "median",
        ),

        mean_flow_z=(
            "flow_z",
            "mean",
        ),

        median_flow_z=(
            "flow_z",
            "median",
        ),

        mean_signal_return=(
            "signal_return",
            "mean",
        ),

        median_signal_return=(
            "signal_return",
            "median",
        ),

    )
)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    "BUY_CONTINUATION_LONG":
        (
            "EXTREME_BUY",
            "LONG",
        ),

    "BUY_EXHAUSTION_SHORT":
        (
            "EXTREME_BUY",
            "SHORT",
        ),

    "SELL_CONTINUATION_SHORT":
        (
            "EXTREME_SELL",
            "SHORT",
        ),

    "SELL_EXHAUSTION_LONG":
        (
            "EXTREME_SELL",
            "LONG",
        ),

}


# ============================================================
# GLOBAL
# ============================================================

global_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events["event"]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for cost in COSTS:


            net_returns = (
                subset[
                    return_column
                ]
                -
                cost
            )


            global_rows.append({

                "hypothesis":
                    hypothesis,

                "horizon_bars":
                    horizon,

                "minutes":
                    horizon
                    *
                    BAR_MINUTES,

                "cost":
                    cost,

                **summarize(
                    net_returns
                ),

            })


global_results = pd.DataFrame(
    global_rows
)


# ============================================================
# BY YEAR
# ============================================================

year_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events["event"]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for year, group in subset.groupby(
            "year"
        ):


            for cost in COSTS:


                returns = (
                    group[
                        return_column
                    ]
                    -
                    cost
                )


                year_rows.append({

                    "hypothesis":
                        hypothesis,

                    "minutes":
                        horizon
                        *
                        BAR_MINUTES,

                    "year":
                        year,

                    "cost":
                        cost,

                    **summarize(
                        returns
                    ),

                })


by_year = pd.DataFrame(
    year_rows
)


# ============================================================
# BY ASSET
# ============================================================

asset_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events["event"]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for symbol, group in subset.groupby(
            "symbol"
        ):


            for cost in COSTS:


                returns = (
                    group[
                        return_column
                    ]
                    -
                    cost
                )


                asset_rows.append({

                    "hypothesis":
                        hypothesis,

                    "minutes":
                        horizon
                        *
                        BAR_MINUTES,

                    "symbol":
                        symbol,

                    "cost":
                        cost,

                    **summarize(
                        returns
                    ),

                })


by_asset = pd.DataFrame(
    asset_rows
)


# ============================================================
# STABILITY @ 0.06%
# ============================================================

stability_rows = []


for hypothesis in HYPOTHESES:


    for horizon in HORIZONS:


        minutes = (
            horizon
            *
            BAR_MINUTES
        )


        global_match = (
            global_results[
                (
                    global_results[
                        "hypothesis"
                    ]
                    ==
                    hypothesis
                )
                &
                (
                    global_results[
                        "minutes"
                    ]
                    ==
                    minutes
                )
                &
                (
                    np.isclose(
                        global_results[
                            "cost"
                        ],
                        BASE_COST,
                    )
                )
            ]
        )


        if global_match.empty:
            continue


        row = global_match.iloc[0]


        years = by_year[
            (
                by_year[
                    "hypothesis"
                ]
                ==
                hypothesis
            )
            &
            (
                by_year[
                    "minutes"
                ]
                ==
                minutes
            )
            &
            (
                np.isclose(
                    by_year[
                        "cost"
                    ],
                    BASE_COST,
                )
            )
        ]


        assets = by_asset[
            (
                by_asset[
                    "hypothesis"
                ]
                ==
                hypothesis
            )
            &
            (
                by_asset[
                    "minutes"
                ]
                ==
                minutes
            )
            &
            (
                np.isclose(
                    by_asset[
                        "cost"
                    ],
                    BASE_COST,
                )
            )
        ]


        stability_rows.append({

            "hypothesis":
                hypothesis,

            "minutes":
                minutes,

            "samples":
                row["samples"],

            "mean_return":
                row["mean_return"],

            "trimmed_mean_5":
                row["trimmed_mean_5"],

            "winsorized_mean_5":
                row["winsorized_mean_5"],

            "win_rate":
                row["win_rate"],

            "profit_factor":
                row["profit_factor"],

            "years_pf_gt_1":
                int(
                    (
                        years[
                            "profit_factor"
                        ]
                        >
                        1
                    ).sum()
                ),

            "total_years":
                len(years),

            "worst_year_pf":
                years[
                    "profit_factor"
                ].min(),

            "median_year_pf":
                years[
                    "profit_factor"
                ].median(),

            "assets_pf_gt_1":
                int(
                    (
                        assets[
                            "profit_factor"
                        ]
                        >
                        1
                    ).sum()
                ),

            "total_assets":
                len(assets),

            "worst_asset_pf":
                assets[
                    "profit_factor"
                ].min(),

            "median_asset_pf":
                assets[
                    "profit_factor"
                ].median(),

        })


stability = pd.DataFrame(
    stability_rows
)


# ============================================================
# DISPLAY
# ============================================================

def percent_display(df):

    result = df.copy()


    for column in [
        "cost",
        "mean_return",
        "median_return",
        "trimmed_mean_5",
        "winsorized_mean_5",
        "win_rate",
        "q10",
        "q90",
        "mean_signal_return",
        "median_signal_return",
    ]:

        if column in result.columns:

            result[column] *= 100


    return result


anatomy_display = percent_display(
    anatomy
)


global_display = percent_display(
    global_results
)


stability_display = percent_display(
    stability
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    360,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 210)

print(
    "EXPERIMENTO 28 — "
    "BRANCH 05 TAKER FLOW IMBALANCE"
)

print("=" * 210)

print()


print("EVENT COUNTS")
print()

print(
    counts.to_string(
        index=False
    )
)


print()

print("=" * 210)

print("EVENT ANATOMY")

print("=" * 210)

print()

print(
    anatomy_display.to_string(
        index=False
    )
)


print()

print("=" * 210)

print("GLOBAL HYPOTHESES")

print("=" * 210)

print()

print(
    global_display

    .sort_values(
        [
            "hypothesis",
            "minutes",
            "cost",
        ]
    )

    .to_string(
        index=False
    )
)


print()

print("=" * 210)

print("STABILITY @ 0.06%")

print("=" * 210)

print()

print(
    stability_display

    .sort_values(
        "profit_factor",
        ascending=False,
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
    / "taker_flow_events.csv",
    index=False,
)


counts.to_csv(
    RESULTS_DIR
    / "taker_flow_counts.csv",
    index=False,
)


anatomy.to_csv(
    RESULTS_DIR
    / "taker_flow_anatomy.csv",
    index=False,
)


global_results.to_csv(
    RESULTS_DIR
    / "taker_flow_global.csv",
    index=False,
)


by_year.to_csv(
    RESULTS_DIR
    / "taker_flow_by_year.csv",
    index=False,
)


by_asset.to_csv(
    RESULTS_DIR
    / "taker_flow_by_asset.csv",
    index=False,
)


stability.to_csv(
    RESULTS_DIR
    / "taker_flow_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
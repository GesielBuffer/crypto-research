from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv
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
# C2 — REGRA CONGELADA
# ============================================================

LOOKBACK = 288 * 7

MIN_PERIODS = 288 * 3

HIGH_QUANTILE = 0.975

Z_THRESHOLD = 4.0

FRESH_LOOKBACK = 12      # 60 minutos

HORIZON = 6              # 30 minutos

BAR_MINUTES = 5


# ============================================================
# ATRITO
# ============================================================

COSTS = [
    0.0004,   # 0.04%
    0.0006,   # 0.06%
    0.0008,   # 0.08%
]


# ============================================================
# PORTFOLIO NORMALIZADO
#
# 25% de notional por posição em "1x".
#
# Com 4 ativos simultâneos:
#
# 1x -> máximo teórico 100% notional
# 2x -> 200%
# 3x -> 300%
# 5x -> 500%
#
# Isto NÃO modela liquidação da Binance.
# ============================================================

STARTING_EQUITY = 1.0

BASE_NOTIONAL_FRACTION = 0.25

LEVERAGE_SCENARIOS = [
    1.0,
    2.0,
    3.0,
    5.0,
]


# ============================================================
# BOOTSTRAP
# ============================================================

BOOTSTRAP_ITERATIONS = 2000
RANDOM_SEED = 42


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
        .sort_values(
            "open_time"
        )
        .reset_index(
            drop=True
        )
    )


    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True,
    )


    return df


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
        <=
        2 * cut
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
# LOSING STREAK
# ============================================================

def max_losing_streak(returns):

    streak = 0
    maximum = 0


    for value in returns:

        if value < 0:

            streak += 1

            maximum = max(
                maximum,
                streak,
            )

        else:

            streak = 0


    return maximum


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
            "max_losing_streak": np.nan,
            "q05": np.nan,
            "q10": np.nan,
            "q90": np.nan,
            "q95": np.nan,
            "worst_trade": np.nan,
            "best_trade": np.nan,
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

        "max_losing_streak":
            max_losing_streak(
                values.to_numpy()
            ),

        "q05":
            values.quantile(0.05),

        "q10":
            values.quantile(0.10),

        "q90":
            values.quantile(0.90),

        "q95":
            values.quantile(0.95),

        "worst_trade":
            values.min(),

        "best_trade":
            values.max(),

    }


# ============================================================
# MAX DRAWDOWN
# ============================================================

def max_drawdown(equity):

    values = np.asarray(
        equity,
        dtype=float,
    )


    if len(values) == 0:
        return np.nan


    peaks = np.maximum.accumulate(
        values
    )


    drawdowns = (
        values
        /
        peaks
        -
        1
    )


    return drawdowns.min()


# ============================================================
# MONTH-BLOCK BOOTSTRAP
# ============================================================

def month_block_bootstrap(
    trades,
    return_column,
):

    months = sorted(
        trades[
            "period"
        ].unique()
    )


    blocks = {

        month:

            trades.loc[
                trades[
                    "period"
                ]
                ==
                month,
                return_column,
            ]
            .dropna()
            .to_numpy()

        for month in months

    }


    rng = np.random.default_rng(
        RANDOM_SEED
    )


    means = []
    pfs = []


    for _ in range(
        BOOTSTRAP_ITERATIONS
    ):


        selected = rng.choice(
            months,
            size=len(months),
            replace=True,
        )


        pieces = [

            blocks[month]

            for month in selected

            if len(
                blocks[month]
            )
            > 0

        ]


        if not pieces:
            continue


        sample = np.concatenate(
            pieces
        )


        means.append(
            sample.mean()
        )


        pf = profit_factor(
            sample
        )


        if np.isfinite(pf):

            pfs.append(pf)


    means = np.asarray(means)
    pfs = np.asarray(pfs)


    return {

        "mean_ci_low":
            np.quantile(
                means,
                0.025,
            ),

        "mean_ci_high":
            np.quantile(
                means,
                0.975,
            ),

        "pf_ci_low":
            np.quantile(
                pfs,
                0.025,
            ),

        "pf_ci_high":
            np.quantile(
                pfs,
                0.975,
            ),

        "prob_mean_gt_0":
            (
                means > 0
            ).mean(),

        "prob_pf_gt_1":
            (
                pfs > 1
            ).mean(),

    }


# ============================================================
# CONTAINER
# ============================================================

trade_rows = []


# ============================================================
# BUILD C2
# ============================================================

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
    # CURRENT CANDLE RETURN
    # ========================================================

    df["ret_5m"] = (
        df["close"]
        /
        df["open"]
        -
        1
    )


    # ========================================================
    # PAST 7D VOLATILITY
    # ========================================================

    df["ret_std_7d"] = (
        df["ret_5m"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .std()

        .shift(1)
    )


    # ========================================================
    # PAST 97.5% RETURN QUANTILE
    # ========================================================

    df["ret_q975"] = (
        df["ret_5m"]

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
    # RETURN Z
    # ========================================================

    df["return_z"] = (
        df["ret_5m"]
        /
        df["ret_std_7d"]
    )


    # ========================================================
    # EXTREME UP
    # ========================================================

    extreme_up = (
        df["ret_5m"]
        >=
        df["ret_q975"]
    ).fillna(False)


    # ========================================================
    # FRESHNESS
    #
    # ZERO EXTREME_UP nos 12 candles ANTERIORES.
    # Current candle não participa.
    # ========================================================

    prior_extreme_count = (
        extreme_up
        .astype(int)

        .shift(1)

        .rolling(
            FRESH_LOOKBACK,
            min_periods=1,
        )

        .sum()

        .fillna(0)
    )


    fresh_60 = (
        prior_extreme_count
        ==
        0
    )


    # ========================================================
    # FULL C2 RAW
    #
    # IMPORTANTE:
    # agora TODA a regra vem antes do non-overlap.
    # ========================================================

    c2_raw = (
        extreme_up

        &

        (
            df["return_z"]
            >=
            Z_THRESHOLD
        )

        &

        fresh_60
    ).fillna(False)


    # ========================================================
    # CANONICAL C2
    # ========================================================

    c2_mask = non_overlapping_mask(
        c2_raw,
        HORIZON,
    )


    # ========================================================
    # EXP23 REFERENCE
    #
    # Somente para comparação metodológica.
    # ========================================================

    old_candidate = (
        extreme_up

        &

        (
            df["return_z"]
            >=
            Z_THRESHOLD
        )
    )


    old_canonical = non_overlapping_mask(
        old_candidate,
        HORIZON,
    )


    exp23_fresh_mask = (
        old_canonical
        &
        fresh_60
    )


    # ========================================================
    # LOOP BOTH MASKS
    # ========================================================

    masks = {

        "C2_CANONICAL":
            c2_mask,

        "EXP23_REFERENCE":
            exp23_fresh_mask,

    }


    for variant, mask in masks.items():


        positions = np.flatnonzero(
            mask.to_numpy()
        )


        for i in positions:


            if (
                i + HORIZON
                >=
                len(df)
            ):
                continue


            signal = df.iloc[i]


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


            # =================================================
            # 6 FUTURE BARS
            # =================================================

            future = df.iloc[
                i + 1
                :
                i + HORIZON + 1
            ]


            if (
                len(future)
                !=
                HORIZON
            ):
                continue


            highs = (
                future["high"]
                .astype(float)
                .to_numpy()
            )


            lows = (
                future["low"]
                .astype(float)
                .to_numpy()
            )


            closes = (
                future["close"]
                .astype(float)
                .to_numpy()
            )


            # =================================================
            # PATH RETURNS
            # =================================================

            path_returns = (
                closes
                /
                entry_price
                -
                1
            )


            # =================================================
            # MFE / MAE
            # =================================================

            favorable = (
                highs
                /
                entry_price
                -
                1
            )


            adverse = (
                entry_price
                -
                lows
            ) / entry_price


            mfe_index = int(
                np.argmax(
                    favorable
                )
            )


            mae_index = int(
                np.argmax(
                    adverse
                )
            )


            final_return = float(
                path_returns[-1]
            )


            row = {

                "variant":
                    variant,

                "symbol":
                    symbol,

                "period":
                    signal["period"],

                "year":
                    str(
                        signal["period"]
                    )[:4],

                "signal_time":
                    signal["open_time"],

                "entry_time":
                    signal["open_time"]
                    +
                    pd.Timedelta(
                        minutes=5
                    ),

                "exit_time":
                    signal["open_time"]
                    +
                    pd.Timedelta(
                        minutes=35
                    ),

                "return_z":
                    float(
                        signal["return_z"]
                    ),

                "prior_extreme_count_60m":
                    float(
                        prior_extreme_count.iloc[i]
                    ),

                "entry_price":
                    entry_price,

                "gross_return":
                    final_return,

                "mfe":
                    float(
                        favorable[
                            mfe_index
                        ]
                    ),

                "mae":
                    float(
                        adverse[
                            mae_index
                        ]
                    ),

                "time_to_mfe_bars":
                    mfe_index + 1,

                "time_to_mae_bars":
                    mae_index + 1,

            }


            for step in range(
                1,
                HORIZON + 1,
            ):

                row[
                    f"path_return_{step}"
                ] = float(
                    path_returns[
                        step - 1
                    ]
                )


            trade_rows.append(row)


# ============================================================
# DATAFRAME
# ============================================================

all_trades = pd.DataFrame(
    trade_rows
)


print()

print("=" * 190)

print(
    "SANITY CHECK — "
    "C2 CANÔNICO VS EXP23"
)

print("=" * 190)

print()


counts = (
    all_trades

    .groupby("variant")

    .size()

    .rename("samples")

    .reset_index()
)


print(
    counts.to_string(
        index=False
    )
)


print()

print(
    "EXP23_REFERENCE esperado: "
    "aproximadamente 1259 trades."
)


# ============================================================
# ONLY CANONICAL FROM HERE
# ============================================================

trades = (
    all_trades[
        all_trades[
            "variant"
        ]
        ==
        "C2_CANONICAL"
    ]
    .copy()
    .sort_values(
        [
            "entry_time",
            "symbol",
        ]
    )
    .reset_index(
        drop=True
    )
)


print()

print(
    f"C2_CANONICAL trades: "
    f"{len(trades)}"
)


# ============================================================
# COST COLUMNS
# ============================================================

for cost in COSTS:


    column = (
        f"net_{int(cost * 10000)}bps"
    )


    trades[column] = (
        trades[
            "gross_return"
        ]
        -
        cost
    )


# ============================================================
# GLOBAL SUMMARY
# ============================================================

summary_rows = []


for cost in COSTS:


    column = (
        f"net_{int(cost * 10000)}bps"
    )


    summary_rows.append({

        "cost":
            cost,

        **summarize(
            trades[column]
        ),

    })


summary = pd.DataFrame(
    summary_rows
)


# ============================================================
# BY YEAR
# ============================================================

year_rows = []


for (
    year,
    group,
) in trades.groupby("year"):


    for cost in COSTS:


        column = (
            f"net_{int(cost * 10000)}bps"
        )


        year_rows.append({

            "year":
                str(year),

            "cost":
                cost,

            **summarize(
                group[column]
            ),

        })


by_year = pd.DataFrame(
    year_rows
)


# ============================================================
# BY ASSET
# ============================================================

asset_rows = []


for (
    symbol,
    group,
) in trades.groupby("symbol"):


    for cost in COSTS:


        column = (
            f"net_{int(cost * 10000)}bps"
        )


        asset_rows.append({

            "symbol":
                symbol,

            "cost":
                cost,

            **summarize(
                group[column]
            ),

        })


by_asset = pd.DataFrame(
    asset_rows
)


# ============================================================
# BLOCK BOOTSTRAP
# ============================================================

bootstrap_rows = []


for cost in COSTS:


    column = (
        f"net_{int(cost * 10000)}bps"
    )


    bootstrap_rows.append({

        "cost":
            cost,

        **month_block_bootstrap(
            trades,
            column,
        ),

    })


bootstrap = pd.DataFrame(
    bootstrap_rows
)


# ============================================================
# EXCURSION SUMMARY
# ============================================================

excursion_rows = []


for label, group in [

    (
        "ALL",
        trades,
    ),

    (
        "WINNERS_GROSS",
        trades[
            trades[
                "gross_return"
            ]
            >
            0
        ],
    ),

    (
        "LOSERS_GROSS",
        trades[
            trades[
                "gross_return"
            ]
            <=
            0
        ],
    ),

]:


    excursion_rows.append({

        "group":
            label,

        "samples":
            len(group),

        "mean_mfe":
            group[
                "mfe"
            ].mean(),

        "median_mfe":
            group[
                "mfe"
            ].median(),

        "mfe_q90":
            group[
                "mfe"
            ].quantile(
                0.90
            ),

        "mean_mae":
            group[
                "mae"
            ].mean(),

        "median_mae":
            group[
                "mae"
            ].median(),

        "mae_q90":
            group[
                "mae"
            ].quantile(
                0.90
            ),

        "mae_q95":
            group[
                "mae"
            ].quantile(
                0.95
            ),

        "mae_q99":
            group[
                "mae"
            ].quantile(
                0.99
            ),

        "median_time_to_mfe":
            group[
                "time_to_mfe_bars"
            ].median(),

        "median_time_to_mae":
            group[
                "time_to_mae_bars"
            ].median(),

    })


excursion = pd.DataFrame(
    excursion_rows
)


# ============================================================
# FORWARD PATH
# ============================================================

path_rows = []


for step in range(
    1,
    HORIZON + 1,
):


    column = (
        f"path_return_{step}"
    )


    values = trades[column]


    path_rows.append({

        "bars":
            step,

        "minutes_after_entry":
            step * 5,

        "mean_return":
            values.mean(),

        "median_return":
            values.median(),

        "win_rate":
            (
                values > 0
            ).mean(),

        "profit_factor":
            profit_factor(values),

    })


path_summary = pd.DataFrame(
    path_rows
)


# ============================================================
# PORTFOLIO MTM
#
# Futures-style normalized accounting:
#
# realized_equity:
# capital already realized.
#
# active positions:
# notional + current unrealized return.
#
# Half the round-trip cost is charged at entry,
# half at exit.
#
# This is still NOT a liquidation model.
# ============================================================

def simulate_mtm_portfolio(
    trades,
    cost,
    leverage_multiplier,
):

    events = []


    half_cost = (
        cost
        /
        2
    )


    for idx, row in trades.iterrows():


        # ENTRY
        events.append({

            "timestamp":
                row["entry_time"],

            "priority":
                2,

            "idx":
                idx,

            "type":
                "ENTRY",

            "step":
                0,

        })


        # MARKS 5,10,15,20,25 min
        for step in range(
            1,
            HORIZON,
        ):


            events.append({

                "timestamp":
                    row["entry_time"]
                    +
                    pd.Timedelta(
                        minutes=step * 5
                    ),

                "priority":
                    1,

                "idx":
                    idx,

                "type":
                    "MARK",

                "step":
                    step,

            })


        # EXIT at 30m
        events.append({

            "timestamp":
                row["exit_time"],

            "priority":
                0,

            "idx":
                idx,

            "type":
                "EXIT",

            "step":
                HORIZON,

        })


    events = (
        pd.DataFrame(events)

        .sort_values(
            [
                "timestamp",
                "priority",
                "idx",
            ]
        )

        .reset_index(
            drop=True
        )
    )


    realized_equity = (
        STARTING_EQUITY
    )


    active = {}


    equity_rows = []


    max_concurrent = 0

    max_gross_exposure = 0.0


    # ========================================================
    # PROCESS BY TIMESTAMP
    # ========================================================

    for timestamp, batch in events.groupby(
        "timestamp",
        sort=True,
    ):


        batch = batch.sort_values(
            [
                "priority",
                "idx",
            ]
        )


        for _, event in batch.iterrows():


            idx = int(
                event["idx"]
            )


            row = trades.loc[idx]


            event_type = (
                event["type"]
            )


            # =================================================
            # EXIT FIRST
            # =================================================

            if event_type == "EXIT":


                if idx not in active:
                    continue


                position = active.pop(
                    idx
                )


                gross_return = float(
                    row[
                        "gross_return"
                    ]
                )


                realized_equity += (

                    position[
                        "notional"
                    ]
                    *
                    gross_return

                    -

                    position[
                        "notional"
                    ]
                    *
                    half_cost

                )


            # =================================================
            # MARK
            # =================================================

            elif event_type == "MARK":


                if idx not in active:
                    continue


                step = int(
                    event["step"]
                )


                active[
                    idx
                ][
                    "current_return"
                ] = float(

                    row[
                        f"path_return_{step}"
                    ]

                )


            # =================================================
            # ENTRY
            # =================================================

            else:


                # ---------------------------------------------
                # Current MTM equity before opening.
                # ---------------------------------------------

                unrealized = sum(

                    position[
                        "notional"
                    ]
                    *
                    position[
                        "current_return"
                    ]

                    for position
                    in active.values()

                )


                current_equity = (

                    realized_equity
                    +
                    unrealized

                )


                notional_fraction = (

                    BASE_NOTIONAL_FRACTION
                    *
                    leverage_multiplier

                )


                notional = (

                    current_equity
                    *
                    notional_fraction

                )


                # Entry half-cost immediately
                realized_equity -= (

                    notional
                    *
                    half_cost

                )


                active[
                    idx
                ] = {

                    "symbol":
                        row["symbol"],

                    "notional":
                        notional,

                    "current_return":
                        0.0,

                }


        # ====================================================
        # SNAPSHOT AFTER ALL EVENTS AT TIMESTAMP
        # ====================================================

        unrealized = sum(

            position[
                "notional"
            ]
            *
            position[
                "current_return"
            ]

            for position
            in active.values()

        )


        equity = (

            realized_equity
            +
            unrealized

        )


        gross_exposure = sum(

            position[
                "notional"
            ]

            for position
            in active.values()

        )


        exposure_ratio = (

            gross_exposure
            /
            equity

            if equity > 0
            else np.inf

        )


        max_concurrent = max(

            max_concurrent,

            len(active),

        )


        max_gross_exposure = max(

            max_gross_exposure,

            exposure_ratio,

        )


        equity_rows.append({

            "timestamp":
                timestamp,

            "equity":
                equity,

            "realized_equity":
                realized_equity,

            "unrealized_pnl":
                unrealized,

            "active_positions":
                len(active),

            "gross_exposure_ratio":
                exposure_ratio,

        })


    curve = pd.DataFrame(
        equity_rows
    )


    if curve.empty:

        return (
            curve,
            {},
        )


    stats = {

        "cost":
            cost,

        "leverage_multiplier":
            leverage_multiplier,

        "ending_equity":
            curve[
                "equity"
            ].iloc[-1],

        "total_return":
            (
                curve[
                    "equity"
                ].iloc[-1]
                /
                STARTING_EQUITY
                -
                1
            ),

        "max_drawdown_mtm":
            max_drawdown(
                curve[
                    "equity"
                ]
            ),

        "minimum_equity":
            curve[
                "equity"
            ].min(),

        "max_concurrent_positions":
            max_concurrent,

        "max_gross_exposure_ratio":
            max_gross_exposure,

        "ruin_flag":
            bool(
                (
                    curve[
                        "equity"
                    ]
                    <=
                    0
                )
                .any()
            ),

    }


    return (
        curve,
        stats,
    )


# ============================================================
# RUN PORTFOLIO SCENARIOS
# ============================================================

portfolio_rows = []


for cost in COSTS:


    for leverage in LEVERAGE_SCENARIOS:


        (
            curve,
            stats,

        ) = simulate_mtm_portfolio(

            trades,
            cost,
            leverage,

        )


        portfolio_rows.append(
            stats
        )


        # ----------------------------------------------------
        # Para economizar disco:
        # salvamos curvas completas apenas no custo-base 0.06%.
        # ----------------------------------------------------

        if np.isclose(
            cost,
            0.0006,
        ):


            leverage_label = (

                str(leverage)
                .replace(
                    ".",
                    "_"
                )

            )


            curve.to_csv(

                RESULTS_DIR
                /
                (
                    "c2_mtm_equity_"
                    f"6bps_"
                    f"lev_{leverage_label}.csv"
                ),

                index=False,

            )


portfolio = pd.DataFrame(
    portfolio_rows
)


# ============================================================
# DISPLAY HELPERS
# ============================================================

def percent_display(df):

    output = df.copy()


    for column in [

        "cost",

        "mean_return",
        "median_return",

        "trimmed_mean_5",
        "winsorized_mean_5",

        "win_rate",

        "q05",
        "q10",
        "q90",
        "q95",

        "worst_trade",
        "best_trade",

        "mean_ci_low",
        "mean_ci_high",

        "prob_mean_gt_0",
        "prob_pf_gt_1",

        "mean_mfe",
        "median_mfe",
        "mfe_q90",

        "mean_mae",
        "median_mae",
        "mae_q90",
        "mae_q95",
        "mae_q99",

        "total_return",
        "max_drawdown_mtm",

        "max_gross_exposure_ratio",

    ]:

        if column in output.columns:

            output[column] *= 100


    return output


summary_display = percent_display(
    summary
)


year_display = percent_display(
    by_year
)


asset_display = percent_display(
    by_asset
)


bootstrap_display = percent_display(
    bootstrap
)


excursion_display = percent_display(
    excursion
)


path_display = percent_display(
    path_summary
)


portfolio_display = percent_display(
    portfolio
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    340,
)


# ============================================================
# OUTPUT 1
# ============================================================

print()

print("=" * 210)

print(
    "EXPERIMENTO 24 — "
    "C2 CANONICAL + EXECUTION RISK AUDIT"
)

print("=" * 210)

print()


print(
    summary_display
    .to_string(
        index=False
    )
)


# ============================================================
# OUTPUT 2
# ============================================================

print()

print("=" * 210)

print("POR ANO")

print("=" * 210)

print()


print(

    year_display

    .sort_values(
        [
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

print("=" * 210)

print("POR ATIVO")

print("=" * 210)

print()


print(

    asset_display

    .sort_values(
        [
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

print("=" * 210)

print("MONTH-BLOCK BOOTSTRAP")

print("=" * 210)

print()


print(
    bootstrap_display
    .to_string(
        index=False
    )
)


# ============================================================
# OUTPUT 5
# ============================================================

print()

print("=" * 210)

print("MFE / MAE")

print("=" * 210)

print()


print(
    excursion_display
    .to_string(
        index=False
    )
)


# ============================================================
# OUTPUT 6
# ============================================================

print()

print("=" * 210)

print("FORWARD PATH")

print("=" * 210)

print()


print(
    path_display
    .to_string(
        index=False
    )
)


# ============================================================
# OUTPUT 7
# ============================================================

print()

print("=" * 210)

print(
    "PORTFOLIO MARK-TO-MARKET"
)

print("=" * 210)

print()


print(

    portfolio_display

    .sort_values(
        [
            "cost",
            "leverage_multiplier",
        ]
    )

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

all_trades.to_csv(

    RESULTS_DIR
    / "c2_canonical_vs_exp23.csv",

    index=False,

)


trades.to_csv(

    RESULTS_DIR
    / "c2_canonical_trades.csv",

    index=False,

)


summary.to_csv(

    RESULTS_DIR
    / "c2_canonical_summary.csv",

    index=False,

)


by_year.to_csv(

    RESULTS_DIR
    / "c2_canonical_by_year.csv",

    index=False,

)


by_asset.to_csv(

    RESULTS_DIR
    / "c2_canonical_by_asset.csv",

    index=False,

)


bootstrap.to_csv(

    RESULTS_DIR
    / "c2_canonical_bootstrap.csv",

    index=False,

)


excursion.to_csv(

    RESULTS_DIR
    / "c2_canonical_excursion.csv",

    index=False,

)


path_summary.to_csv(

    RESULTS_DIR
    / "c2_canonical_forward_path.csv",

    index=False,

)


portfolio.to_csv(

    RESULTS_DIR
    / "c2_portfolio_risk.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
from pathlib import Path
import heapq

import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

RESULTS_DIR = Path("results")

INPUT_FILE = (
    RESULTS_DIR
    / "extreme_impulse_events.csv"
)


# ============================================================
# REGRA CONGELADA
# ============================================================

Z_THRESHOLD = 4.0

HORIZON = 6       # 30 minutos
BAR_MINUTES = 5


# ============================================================
# CUSTOS
# ============================================================

COSTS = [
    0.0004,
    0.0006,
    0.0008,
]


# ============================================================
# PORTFÓLIO NORMALIZADO
#
# NÃO é position sizing real.
#
# 25% de notional por posição significa
# que 4 ativos simultâneos = 100% de
# exposição nominal em 1x.
# ============================================================

STARTING_EQUITY = 1.0

NOTIONAL_FRACTION = 0.25


BOOTSTRAP_ITERATIONS = 2000
RANDOM_SEED = 42


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
# MAX DRAWDOWN
# ============================================================

def max_drawdown(equity):

    equity = np.asarray(
        equity,
        dtype=float,
    )

    if len(equity) == 0:
        return np.nan

    running_max = np.maximum.accumulate(
        equity
    )

    drawdowns = (
        equity
        /
        running_max
        -
        1
    )

    return drawdowns.min()


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
            "max_losing_streak": np.nan,
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

        "max_losing_streak":
            max_losing_streak(
                returns.to_numpy()
            ),

    }


# ============================================================
# MONTH-BLOCK BOOTSTRAP
#
# Mais conservador que bootstrap IID.
#
# Reamostramos meses inteiros.
# ============================================================

def monthly_block_bootstrap(
    trades,
    return_column,
):

    months = sorted(
        trades[
            "period"
        ].unique()
    )

    if len(months) < 5:

        return {}

    monthly_blocks = {

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

        selected_months = rng.choice(

            months,

            size=len(months),

            replace=True,

        )


        pieces = [

            monthly_blocks[
                month
            ]

            for month
            in selected_months

            if len(
                monthly_blocks[
                    month
                ]
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


    means = np.asarray(
        means
    )

    pfs = np.asarray(
        pfs
    )


    return {

        "block_mean_ci_low":
            np.quantile(
                means,
                0.025,
            ),

        "block_mean_ci_high":
            np.quantile(
                means,
                0.975,
            ),

        "block_pf_ci_low":
            np.quantile(
                pfs,
                0.025,
            ),

        "block_pf_ci_high":
            np.quantile(
                pfs,
                0.975,
            ),

        "block_prob_mean_gt_0":
            (means > 0).mean(),

        "block_prob_pf_gt_1":
            (pfs > 1).mean(),

    }


# ============================================================
# PORTFOLIO SIMULATION
# ============================================================

def simulate_portfolio(
    trades,
    return_column,
):

    # --------------------------------------------------------
    # Eventos:
    # exit antes de entry no mesmo timestamp.
    # --------------------------------------------------------

    events = []


    for idx, row in trades.iterrows():

        heapq.heappush(

            events,

            (
                row[
                    "entry_time"
                ],

                1,   # entry depois de exit

                idx,

                "ENTRY",

            ),

        )


        heapq.heappush(

            events,

            (
                row[
                    "exit_time"
                ],

                0,   # exit primeiro

                idx,

                "EXIT",

            ),

        )


    equity = STARTING_EQUITY

    active = {}

    equity_rows = []

    max_concurrent = 0


    while events:

        (
            timestamp,
            _priority,
            idx,
            event_type,

        ) = heapq.heappop(
            events
        )


        row = trades.loc[
            idx
        ]


        if event_type == "ENTRY":


            notional = (

                equity
                *
                NOTIONAL_FRACTION

            )


            active[
                idx
            ] = {

                "notional":
                    notional,

                "symbol":
                    row["symbol"],

            }


            max_concurrent = max(

                max_concurrent,

                len(active),

            )


        else:


            if idx not in active:
                continue


            position = active.pop(
                idx
            )


            trade_return = float(
                row[
                    return_column
                ]
            )


            pnl = (

                position[
                    "notional"
                ]

                *
                trade_return

            )


            equity += pnl


            equity_rows.append({

                "timestamp":
                    timestamp,

                "symbol":
                    row["symbol"],

                "trade_return":
                    trade_return,

                "pnl":
                    pnl,

                "equity":
                    equity,

                "concurrent_after_exit":
                    len(active),

            })


    equity_df = pd.DataFrame(
        equity_rows
    )


    if equity_df.empty:

        return (
            equity_df,
            {},
        )


    stats = {

        "starting_equity":
            STARTING_EQUITY,

        "ending_equity":
            equity,

        "total_return":
            equity
            /
            STARTING_EQUITY
            -
            1,

        "max_drawdown_closed_equity":
            max_drawdown(
                equity_df[
                    "equity"
                ]
            ),

        "max_concurrent_positions":
            max_concurrent,

        "max_notional_exposure":
            max_concurrent
            *
            NOTIONAL_FRACTION,

    }


    return (
        equity_df,
        stats,
    )


# ============================================================
# LOAD
# ============================================================

events = pd.read_csv(
    INPUT_FILE
)


events[
    "open_time"
] = pd.to_datetime(

    events[
        "open_time"
    ],

    utc=True,

)


# ============================================================
# FROZEN FILTER
# ============================================================

trades = events[

    (
        events[
            "event"
        ]
        ==
        "EXTREME_UP"
    )

    &

    (
        events[
            "return_z"
        ]
        >=
        Z_THRESHOLD
    )

].copy()


trades = trades.dropna(

    subset=[

        "symbol",
        "period",
        "open_time",
        "return_z",
        "future_long_6",

    ]

).copy()


# ============================================================
# TIMES
#
# Signal candle opens T.
#
# It closes at T+5m.
#
# Entry:
# OPEN t+1 = T+5m
#
# Exit:
# CLOSE t+6 = T+35m
#
# Holding = 30m.
# ============================================================

trades[
    "entry_time"
] = (

    trades[
        "open_time"
    ]

    +
    pd.Timedelta(
        minutes=5
    )

)


trades[
    "exit_time"
] = (

    trades[
        "open_time"
    ]

    +
    pd.Timedelta(
        minutes=35
    )

)


trades[
    "gross_return"
] = trades[
    "future_long_6"
]


trades = (

    trades

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
    f"Trades congelados: "
    f"{len(trades)}"
)


# ============================================================
# COST SCENARIOS
# ============================================================

summary_rows = []
portfolio_rows = []
bootstrap_rows = []


for cost in COSTS:


    column = (
        f"net_return_{int(cost * 10000)}bps"
    )


    trades[
        column
    ] = (

        trades[
            "gross_return"
        ]

        -
        cost

    )


    # --------------------------------------------------------
    # Trade stats
    # --------------------------------------------------------

    stats = summarize(
        trades[
            column
        ]
    )


    summary_rows.append({

        "cost":
            cost,

        **stats,

    })


    # --------------------------------------------------------
    # Block bootstrap
    # --------------------------------------------------------

    bootstrap = monthly_block_bootstrap(

        trades,

        column,

    )


    bootstrap_rows.append({

        "cost":
            cost,

        **bootstrap,

    })


    # --------------------------------------------------------
    # Portfolio
    # --------------------------------------------------------

    (
        equity_curve,
        portfolio_stats,

    ) = simulate_portfolio(

        trades,

        column,

    )


    portfolio_rows.append({

        "cost":
            cost,

        **portfolio_stats,

    })


    equity_curve.to_csv(

        RESULTS_DIR
        /
        (
            "frozen_candidate_equity_"
            f"{int(cost * 10000)}bps.csv"
        ),

        index=False,

    )


# ============================================================
# TABLES
# ============================================================

summary = pd.DataFrame(
    summary_rows
)

portfolio = pd.DataFrame(
    portfolio_rows
)

bootstrap = pd.DataFrame(
    bootstrap_rows
)


# ============================================================
# BY YEAR
# ============================================================

year_rows = []


for cost in COSTS:


    column = (
        f"net_return_{int(cost * 10000)}bps"
    )


    for year, group in trades.groupby(
        "year"
    ):


        year_rows.append({

            "year":
                str(year),

            "cost":
                cost,

            **summarize(
                group[
                    column
                ]
            ),

        })


by_year = pd.DataFrame(
    year_rows
)


# ============================================================
# BY ASSET
# ============================================================

asset_rows = []


for cost in COSTS:


    column = (
        f"net_return_{int(cost * 10000)}bps"
    )


    for symbol, group in trades.groupby(
        "symbol"
    ):


        asset_rows.append({

            "symbol":
                symbol,

            "cost":
                cost,

            **summarize(
                group[
                    column
                ]
            ),

        })


by_asset = pd.DataFrame(
    asset_rows
)


# ============================================================
# MONTHLY
# ============================================================

monthly_rows = []


for cost in COSTS:


    column = (
        f"net_return_{int(cost * 10000)}bps"
    )


    for period, group in trades.groupby(
        "period"
    ):


        monthly_rows.append({

            "period":
                period,

            "cost":
                cost,

            **summarize(
                group[
                    column
                ]
            ),

        })


monthly = pd.DataFrame(
    monthly_rows
)


# ============================================================
# DISPLAY
# ============================================================

def display_percent(df):

    result = df.copy()


    for column in [

        "cost",

        "mean_return",
        "median_return",
        "win_rate",

        "total_return",
        "max_drawdown_closed_equity",
        "max_notional_exposure",

        "block_mean_ci_low",
        "block_mean_ci_high",

        "block_prob_mean_gt_0",
        "block_prob_pf_gt_1",

    ]:

        if column in result.columns:

            result[
                column
            ] *= 100


    return result


summary_display = display_percent(
    summary
)

portfolio_display = display_percent(
    portfolio
)

bootstrap_display = display_percent(
    bootstrap
)

year_display = display_percent(
    by_year
)

asset_display = display_percent(
    by_asset
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    300,
)


print()

print("=" * 190)

print(
    "EXPERIMENTO 21 — "
    "FROZEN CANDIDATE OPERATIONAL"
)

print("=" * 190)

print()


print(
    summary_display.to_string(
        index=False
    )
)


print()

print("=" * 190)

print("BLOCK BOOTSTRAP")

print("=" * 190)

print()


print(
    bootstrap_display.to_string(
        index=False
    )
)


print()

print("=" * 190)

print("PORTFOLIO NORMALIZADO")

print("=" * 190)

print()


print(
    portfolio_display.to_string(
        index=False
    )
)


print()

print("=" * 190)

print("POR ANO")

print("=" * 190)

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


print()

print("=" * 190)

print("POR ATIVO")

print("=" * 190)

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
# SAVE
# ============================================================

trades.to_csv(

    RESULTS_DIR
    / "frozen_candidate_trades.csv",

    index=False,

)


summary.to_csv(

    RESULTS_DIR
    / "frozen_candidate_summary.csv",

    index=False,

)


portfolio.to_csv(

    RESULTS_DIR
    / "frozen_candidate_portfolio.csv",

    index=False,

)


bootstrap.to_csv(

    RESULTS_DIR
    / "frozen_candidate_block_bootstrap.csv",

    index=False,

)


by_year.to_csv(

    RESULTS_DIR
    / "frozen_candidate_by_year.csv",

    index=False,

)


by_asset.to_csv(

    RESULTS_DIR
    / "frozen_candidate_by_asset.csv",

    index=False,

)


monthly.to_csv(

    RESULTS_DIR
    / "frozen_candidate_monthly.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
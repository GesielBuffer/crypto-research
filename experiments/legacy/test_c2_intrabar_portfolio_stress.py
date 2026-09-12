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


INPUT_TRADES = (
    RESULTS_DIR
    / "c2_canonical_trades.csv"
)


# ============================================================
# PERÍODO DE DEVELOPMENT
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
# C2 CONGELADO
# ============================================================

HORIZON = 6

BAR_MINUTES = 5


# ============================================================
# RISK / EXECUTION SCENARIOS
# ============================================================

COSTS = [
    0.0004,
    0.0006,
    0.0008,
]


# Não estamos "escolhendo" leverage aqui.
# Estamos medindo sensibilidade de risco.

LEVERAGE_SCENARIOS = [
    1.0,
    2.0,
    3.0,
]


STARTING_EQUITY = 1.0

BASE_NOTIONAL_FRACTION = 0.25


# ============================================================
# LOAD RAW SYMBOL
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


    dd = (
        values
        /
        peaks
        -
        1
    )


    return dd.min()


# ============================================================
# LOAD C2 TRADES
# ============================================================

trades = pd.read_csv(
    INPUT_TRADES,
    parse_dates=[
        "signal_time",
        "entry_time",
        "exit_time",
    ],
)


for column in [
    "signal_time",
    "entry_time",
    "exit_time",
]:

    trades[column] = pd.to_datetime(
        trades[column],
        utc=True,
    )


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
    f"C2 trades carregados: "
    f"{len(trades)}"
)


if len(trades) != 1259:

    print(
        "ATENÇÃO: esperado aproximadamente "
        "1259 trades do Experimento 24."
    )


# ============================================================
# LOAD RAW DATA
# ============================================================

raw_by_symbol = {}


for symbol in SYMBOLS:

    print(
        f"Carregando candles de {symbol}..."
    )


    df = load_symbol(
        symbol
    )


    if df is None:

        raise RuntimeError(
            f"Sem dados para {symbol}"
        )


    raw_by_symbol[
        symbol
    ] = df


# ============================================================
# RECONSTRUIR PATH INTRABAR
# ============================================================

valid_rows = []


for idx, trade in trades.iterrows():


    symbol = trade[
        "symbol"
    ]


    df = raw_by_symbol[
        symbol
    ]


    signal_time = trade[
        "signal_time"
    ]


    matches = np.flatnonzero(
        (
            df[
                "open_time"
            ]
            ==
            signal_time
        )
        .to_numpy()
    )


    if len(matches) != 1:

        print(
            f"Signal não encontrado "
            f"{symbol} {signal_time}"
        )

        continue


    i = int(
        matches[0]
    )


    if (
        i + HORIZON
        >=
        len(df)
    ):
        continue


    entry_bar = df.iloc[
        i + 1
    ]


    raw_entry = float(
        entry_bar[
            "open"
        ]
    )


    entry_price = float(
        trade[
            "entry_price"
        ]
    )


    # ========================================================
    # SANITY CHECK DE ENTRY
    # ========================================================

    entry_diff = abs(
        raw_entry
        -
        entry_price
    )


    tolerance = max(
        1e-10,
        entry_price * 1e-10,
    )


    if (
        entry_diff
        >
        tolerance
    ):

        print(
            "Entry divergence:",
            symbol,
            signal_time,
            entry_price,
            raw_entry,
        )

        continue


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


    row = trade.to_dict()


    low_returns = []

    high_returns = []

    close_returns = []


    for step in range(
        1,
        HORIZON + 1,
    ):


        bar = future.iloc[
            step - 1
        ]


        low_return = (
            float(
                bar[
                    "low"
                ]
            )
            /
            entry_price
            -
            1
        )


        high_return = (
            float(
                bar[
                    "high"
                ]
            )
            /
            entry_price
            -
            1
        )


        close_return = (
            float(
                bar[
                    "close"
                ]
            )
            /
            entry_price
            -
            1
        )


        row[
            f"low_return_{step}"
        ] = low_return


        row[
            f"high_return_{step}"
        ] = high_return


        row[
            f"close_return_{step}"
        ] = close_return


        low_returns.append(
            low_return
        )


        high_returns.append(
            high_return
        )


        close_returns.append(
            close_return
        )


    # ========================================================
    # SINGLE TRADE INTRABAR WORST CASE
    # ========================================================

    row[
        "worst_intrabar_return"
    ] = min(
        low_returns
    )


    row[
        "best_intrabar_return"
    ] = max(
        high_returns
    )


    row[
        "intrabar_mae"
    ] = max(
        0.0,
        -min(
            low_returns
        ),
    )


    row[
        "intrabar_mfe"
    ] = max(
        0.0,
        max(
            high_returns
        ),
    )


    valid_rows.append(row)


# ============================================================
# ENRICHED TRADES
# ============================================================

trades = pd.DataFrame(
    valid_rows
)


print()

print(
    f"Trades reconstruídos: "
    f"{len(trades)}"
)


# ============================================================
# SINGLE TRADE RISK DISTRIBUTION
# ============================================================

single_trade_risk = pd.DataFrame(
    [
        {

            "samples":
                len(trades),

            "mae_mean":
                trades[
                    "intrabar_mae"
                ].mean(),

            "mae_median":
                trades[
                    "intrabar_mae"
                ].median(),

            "mae_q90":
                trades[
                    "intrabar_mae"
                ].quantile(
                    0.90
                ),

            "mae_q95":
                trades[
                    "intrabar_mae"
                ].quantile(
                    0.95
                ),

            "mae_q99":
                trades[
                    "intrabar_mae"
                ].quantile(
                    0.99
                ),

            "mae_q995":
                trades[
                    "intrabar_mae"
                ].quantile(
                    0.995
                ),

            "mae_max":
                trades[
                    "intrabar_mae"
                ].max(),

            "mfe_median":
                trades[
                    "intrabar_mfe"
                ].median(),

            "mfe_q90":
                trades[
                    "intrabar_mfe"
                ].quantile(
                    0.90
                ),

        }
    ]
)


# ============================================================
# EVENT GENERATION
#
# Para cada trade:
#
# ENTRY
#
# depois, em cada candle:
#   STRESS_LOW
#   MARK_CLOSE
#
# no último:
#   STRESS_LOW
#   MARK_CLOSE
#   EXIT
#
# No mesmo timestamp:
# exits antigos ocorrem antes de novas entries.
# ============================================================

def simulate_intrabar_portfolio(
    trades,
    cost,
    leverage_multiplier,
):


    half_cost = (
        cost
        /
        2
    )


    events = []


    for idx, row in trades.iterrows():


        # ====================================================
        # ENTRY
        # ====================================================

        events.append(
            {
                "timestamp":
                    row[
                        "entry_time"
                    ],

                "type":
                    "ENTRY",

                "idx":
                    idx,

                "step":
                    0,
            }
        )


        # ====================================================
        # 6 FUTURE CANDLES
        # ====================================================

        for step in range(
            1,
            HORIZON + 1,
        ):


            timestamp = (
                row[
                    "entry_time"
                ]
                +
                pd.Timedelta(
                    minutes=
                    step
                    *
                    BAR_MINUTES
                )
            )


            events.append(
                {
                    "timestamp":
                        timestamp,

                    "type":
                        "STRESS_LOW",

                    "idx":
                        idx,

                    "step":
                        step,
                }
            )


            events.append(
                {
                    "timestamp":
                        timestamp,

                    "type":
                        "MARK_CLOSE",

                    "idx":
                        idx,

                    "step":
                        step,
                }
            )


            if (
                step
                ==
                HORIZON
            ):


                events.append(
                    {
                        "timestamp":
                            timestamp,

                        "type":
                            "EXIT",

                        "idx":
                            idx,

                        "step":
                            step,
                    }
                )


    events = pd.DataFrame(
        events
    )


    # ========================================================
    # PRIORITY IS HANDLED MANUALLY PER TIMESTAMP
    # ========================================================

    timestamps = sorted(
        events[
            "timestamp"
        ].unique()
    )


    realized_equity = (
        STARTING_EQUITY
    )


    active = {}


    snapshots = []


    max_concurrent = 0


    for timestamp in timestamps:


        batch = events[
            events[
                "timestamp"
            ]
            ==
            timestamp
        ]


        # ====================================================
        # 1 — STRESS LOW
        # ====================================================

        stress_events = batch[
            batch[
                "type"
            ]
            ==
            "STRESS_LOW"
        ]


        for _, event in stress_events.iterrows():


            idx = int(
                event[
                    "idx"
                ]
            )


            if idx not in active:
                continue


            step = int(
                event[
                    "step"
                ]
            )


            active[
                idx
            ][
                "current_return"
            ] = float(

                trades.loc[
                    idx,
                    f"low_return_{step}"
                ]

            )


        # ====================================================
        # STRESSED EQUITY SNAPSHOT
        #
        # Conservador:
        # assume todas as lows simultâneas.
        # ====================================================

        if active:


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


            stress_equity = (
                realized_equity
                +
                unrealized
            )


            gross_notional = sum(

                position[
                    "notional"
                ]

                for position
                in active.values()

            )


            snapshots.append(
                {

                    "timestamp":
                        timestamp,

                    "snapshot_type":
                        "INTRABAR_STRESS",

                    "equity":
                        stress_equity,

                    "realized_equity":
                        realized_equity,

                    "unrealized_pnl":
                        unrealized,

                    "active_positions":
                        len(active),

                    "gross_notional":
                        gross_notional,

                    "gross_exposure_ratio":
                        (
                            gross_notional
                            /
                            stress_equity

                            if stress_equity > 0

                            else np.inf
                        ),

                }
            )


        # ====================================================
        # 2 — UPDATE ALL ACTIVE TO BAR CLOSE
        # ====================================================

        mark_events = batch[
            batch[
                "type"
            ]
            ==
            "MARK_CLOSE"
        ]


        for _, event in mark_events.iterrows():


            idx = int(
                event[
                    "idx"
                ]
            )


            if idx not in active:
                continue


            step = int(
                event[
                    "step"
                ]
            )


            active[
                idx
            ][
                "current_return"
            ] = float(

                trades.loc[
                    idx,
                    f"close_return_{step}"
                ]

            )


        # ====================================================
        # 3 — EXIT
        # ====================================================

        exit_events = batch[
            batch[
                "type"
            ]
            ==
            "EXIT"
        ]


        for _, event in exit_events.iterrows():


            idx = int(
                event[
                    "idx"
                ]
            )


            if idx not in active:
                continue


            position = active.pop(
                idx
            )


            gross_return = float(
                trades.loc[
                    idx,
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


        # ====================================================
        # 4 — ENTRY
        #
        # Exits foram processados primeiro.
        # ====================================================

        entry_events = batch[
            batch[
                "type"
            ]
            ==
            "ENTRY"
        ]


        for _, event in entry_events.iterrows():


            idx = int(
                event[
                    "idx"
                ]
            )


            # ------------------------------------------------
            # Current equity usando close marks
            # das demais posições.
            # ------------------------------------------------

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


            fraction = (

                BASE_NOTIONAL_FRACTION
                *
                leverage_multiplier

            )


            notional = (
                current_equity
                *
                fraction
            )


            # Entry half-cost
            realized_equity -= (

                notional
                *
                half_cost

            )


            active[
                idx
            ] = {

                "notional":
                    notional,

                "current_return":
                    0.0,

                "symbol":
                    trades.loc[
                        idx,
                        "symbol"
                    ],

            }


            max_concurrent = max(

                max_concurrent,

                len(active),

            )


        # ====================================================
        # 5 — NORMAL CLOSE/POST-EVENT SNAPSHOT
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


        gross_notional = sum(

            position[
                "notional"
            ]

            for position
            in active.values()

        )


        snapshots.append(
            {

                "timestamp":
                    timestamp,

                "snapshot_type":
                    "CLOSE_MARK",

                "equity":
                    equity,

                "realized_equity":
                    realized_equity,

                "unrealized_pnl":
                    unrealized,

                "active_positions":
                    len(active),

                "gross_notional":
                    gross_notional,

                "gross_exposure_ratio":
                    (
                        gross_notional
                        /
                        equity

                        if equity > 0

                        else np.inf
                    ),

            }
        )


    curve = pd.DataFrame(
        snapshots
    )


    curve = (
        curve
        .sort_values(
            [
                "timestamp",
                "snapshot_type",
            ]
        )
        .reset_index(
            drop=True
        )
    )


    stressed = curve[
        curve[
            "snapshot_type"
        ]
        ==
        "INTRABAR_STRESS"
    ]


    # ========================================================
    # STATS
    # ========================================================

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

        "max_drawdown_all":
            max_drawdown(
                curve[
                    "equity"
                ]
            ),

        "max_drawdown_intrabar_only":
            max_drawdown(
                stressed[
                    "equity"
                ]
            ),

        "minimum_equity":
            curve[
                "equity"
            ].min(),

        "minimum_intrabar_equity":
            stressed[
                "equity"
            ].min(),

        "max_concurrent_positions":
            max_concurrent,

        "max_gross_exposure_ratio":
            curve[
                "gross_exposure_ratio"
            ]
            .replace(
                [np.inf, -np.inf],
                np.nan,
            )
            .max(),

        "worst_unrealized_pnl":
            curve[
                "unrealized_pnl"
            ].min(),

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
# RUN
# ============================================================

portfolio_rows = []


for cost in COSTS:


    for leverage in LEVERAGE_SCENARIOS:


        (
            curve,
            stats,
        ) = simulate_intrabar_portfolio(

            trades,

            cost,

            leverage,

        )


        portfolio_rows.append(
            stats
        )


        # ====================================================
        # SAVE BASE COST CURVES
        # ====================================================

        if np.isclose(
            cost,
            0.0006,
        ):


            label = (
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
                    "c2_intrabar_curve_"
                    f"6bps_"
                    f"lev_{label}.csv"
                ),

                index=False,

            )


portfolio = pd.DataFrame(
    portfolio_rows
)


# ============================================================
# CONCURRENCY
# ============================================================

base_curve = pd.read_csv(

    RESULTS_DIR
    / "c2_intrabar_curve_6bps_lev_1_0.csv"

)


concurrency = (

    base_curve[
        base_curve[
            "snapshot_type"
        ]
        ==
        "CLOSE_MARK"
    ]

    .groupby(
        "active_positions"
    )

    .size()

    .rename(
        "snapshots"
    )

    .reset_index()

)


concurrency[
    "share"
] = (

    concurrency[
        "snapshots"
    ]

    /
    concurrency[
        "snapshots"
    ].sum()

)


# ============================================================
# DISPLAY
# ============================================================

def percent_display(df):

    output = df.copy()


    for column in [

        "cost",

        "mae_mean",
        "mae_median",
        "mae_q90",
        "mae_q95",
        "mae_q99",
        "mae_q995",
        "mae_max",

        "mfe_median",
        "mfe_q90",

        "total_return",

        "max_drawdown_all",
        "max_drawdown_intrabar_only",

        "max_gross_exposure_ratio",

        "worst_unrealized_pnl",

        "share",

    ]:

        if column in output.columns:

            output[column] *= 100


    return output


risk_display = percent_display(
    single_trade_risk
)


portfolio_display = percent_display(
    portfolio
)


concurrency_display = percent_display(
    concurrency
)


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    320,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 200)

print(
    "EXPERIMENTO 25 — "
    "C2 INTRABAR PORTFOLIO STRESS"
)

print("=" * 200)

print()


print(
    "SINGLE TRADE INTRABAR RISK"
)

print()


print(
    risk_display.to_string(
        index=False
    )
)


print()

print("=" * 200)

print(
    "PORTFOLIO INTRABAR STRESS"
)

print("=" * 200)

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


print()

print("=" * 200)

print(
    "CONCORRÊNCIA DE POSIÇÕES"
)

print("=" * 200)

print()


print(

    concurrency_display

    .sort_values(
        "active_positions"
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
    / "c2_intrabar_trades.csv",

    index=False,

)


single_trade_risk.to_csv(

    RESULTS_DIR
    / "c2_intrabar_single_trade_risk.csv",

    index=False,

)


portfolio.to_csv(

    RESULTS_DIR
    / "c2_intrabar_portfolio_stress.csv",

    index=False,

)


concurrency.to_csv(

    RESULTS_DIR
    / "c2_position_concurrency.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
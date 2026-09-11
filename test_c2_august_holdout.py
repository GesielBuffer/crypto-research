from pathlib import Path
import time

import numpy as np
import pandas as pd
import requests

from research.validation import non_overlapping_mask


# ============================================================
# EXPERIMENTO 26
# C2 — AUGUST 2026 HOLDOUT
#
# IMPORTANTE:
# ESTE SCRIPT NÃO OTIMIZA NADA.
#
# Development:
# 2024-01 -> 2026-07
#
# Holdout:
# 2026-08-01 -> 2026-09-01
#
# Julho é usado APENAS como warm-up/contexto.
# ============================================================


# ============================================================
# FROZEN C2 SPEC
# ============================================================

C2_VERSION = "C2_FROZEN_DEV_2026_08_27"

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]

INTERVAL = "5m"

BAR_MINUTES = 5

BARS_PER_DAY = 288

LOOKBACK = 7 * BARS_PER_DAY

MIN_PERIODS = 3 * BARS_PER_DAY

EXTREME_UP_QUANTILE = 0.975

RETURN_Z_THRESHOLD = 4.0

FRESH_LOOKBACK_BARS = 12

HOLD_BARS = 6


# ============================================================
# HOLDOUT
# ============================================================

HOLDOUT_START = pd.Timestamp(
    "2026-08-01 00:00:00",
    tz="UTC",
)

HOLDOUT_END = pd.Timestamp(
    "2026-09-01 00:00:00",
    tz="UTC",
)


# ============================================================
# WARM-UP
#
# Julho é usado somente para formar:
# - rolling 7d
# - quantile 97.5%
# - volatility
# - freshness
#
# Nenhum trade de julho entra no holdout.
# ============================================================

WARMUP_START = pd.Timestamp(
    "2026-07-01 00:00:00",
    tz="UTC",
)


# ============================================================
# COSTS
# ============================================================

COSTS = [
    0.0004,
    0.0006,
    0.0008,
]

BASE_COST = 0.0006


# ============================================================
# PREDECLARED HOLDOUT GATES
#
# Estes critérios foram definidos ANTES
# de observar os resultados de agosto.
# ============================================================

MIN_HOLDOUT_TRADES = 25

PASS_PF = 1.10

MAX_ACCEPTABLE_DD_1X = -0.10


# ============================================================
# DEVELOPMENT REFERENCE
#
# Apenas referência.
# NÃO altera nenhuma regra.
# ============================================================

DEV_BASE_COST = 0.0006

DEV_SAMPLES = 1259

DEV_MEAN_RETURN = 0.00060952

DEV_PROFIT_FACTOR = 1.208935

DEV_WIN_RATE = 0.47656871


# ============================================================
# PAPER / TESTNET RISK SPEC
# ============================================================

STARTING_EQUITY = 1.0

POSITION_NOTIONAL_FRACTION = 0.25

MAX_OPEN_POSITIONS = 4


# ============================================================
# PATHS
# ============================================================

DATA_DIR = Path("data")

RESULTS_DIR = Path("results")

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# BINANCE PUBLIC DATA
# ============================================================

BINANCE_URL = (
    "https://fapi.binance.com"
    "/fapi/v1/klines"
)


# ============================================================
# COST COLUMN
#
# CORREÇÃO DO BUG:
#
# int(0.0006 * 10000)
# pode virar 5 por representação de float.
#
# Usamos round antes do int.
# ============================================================

def cost_column(cost):

    bps = int(
        round(
            cost * 10000
        )
    )

    return f"net_{bps}bps"


# ============================================================
# TIMESTAMP -> MILLISECONDS
# ============================================================

def timestamp_ms(ts):

    return int(
        ts.timestamp()
        * 1000
    )


# ============================================================
# DOWNLOAD BINANCE KLINES
# ============================================================

def download_klines(
    symbol,
    start,
    end,
):

    """
    Baixa candles públicos da Binance USD-M Futures.

    Nenhuma API key é necessária.

    O intervalo é:
    start <= open_time < end
    """

    start_ms = timestamp_ms(start)

    end_ms = timestamp_ms(end)

    rows = []

    current = start_ms


    while current < end_ms:

        params = {
            "symbol": symbol,
            "interval": INTERVAL,
            "startTime": current,
            "endTime": end_ms - 1,
            "limit": 1500,
        }


        response = requests.get(
            BINANCE_URL,
            params=params,
            timeout=30,
        )


        response.raise_for_status()


        batch = response.json()


        if not batch:
            break


        rows.extend(
            batch
        )


        last_open = int(
            batch[-1][0]
        )


        next_start = (
            last_open
            +
            1
        )


        if next_start <= current:

            raise RuntimeError(
                f"Download travado em {symbol}: "
                f"{current}"
            )


        current = next_start


        time.sleep(
            0.05
        )


    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trades",
        "taker_buy_base",
        "taker_buy_quote",
        "ignore",
    ]


    df = pd.DataFrame(
        rows,
        columns=columns,
    )


    if df.empty:
        return df


    df["open_time"] = pd.to_datetime(
        df["open_time"],
        unit="ms",
        utc=True,
    )


    df["close_time"] = pd.to_datetime(
        df["close_time"],
        unit="ms",
        utc=True,
    )


    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_base",
        "taker_buy_quote",
    ]


    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )


    df = (
        df[
            (
                df["open_time"]
                >=
                start
            )
            &
            (
                df["open_time"]
                <
                end
            )
        ]

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
# NORMALIZE DATAFRAME
# ============================================================

def normalize_dataframe(df):

    result = df.copy()


    result["open_time"] = pd.to_datetime(
        result["open_time"],
        utc=True,
    )


    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]


    for column in numeric_columns:

        if column not in result.columns:

            raise RuntimeError(
                f"Coluna ausente: {column}"
            )


        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )


    result = (
        result

        .dropna(
            subset=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
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
# LOAD JULY + AUGUST
# ============================================================

def load_period(symbol):

    july_file = (
        DATA_DIR
        /
        (
            f"{symbol}_5m_"
            "2026-07-01_"
            "2026-08-01.csv"
        )
    )


    august_file = (
        DATA_DIR
        /
        (
            f"{symbol}_5m_"
            "2026-08-01_"
            "2026-09-01.csv"
        )
    )


    # ========================================================
    # JULY
    # ========================================================

    if july_file.exists():

        print(
            f"{symbol}: julho encontrado."
        )


        july = pd.read_csv(
            july_file
        )


    else:

        print(
            f"{symbol}: julho não encontrado. "
            f"Baixando warm-up..."
        )


        july = download_klines(
            symbol,
            WARMUP_START,
            HOLDOUT_START,
        )


        if july.empty:

            raise RuntimeError(
                f"Falha ao baixar julho para {symbol}"
            )


        july.to_csv(
            july_file,
            index=False,
        )


    # ========================================================
    # AUGUST
    # ========================================================

    if august_file.exists():

        print(
            f"{symbol}: agosto encontrado."
        )


        august = pd.read_csv(
            august_file
        )


    else:

        print(
            f"{symbol}: baixando agosto/2026..."
        )


        august = download_klines(
            symbol,
            HOLDOUT_START,
            HOLDOUT_END,
        )


        if august.empty:

            raise RuntimeError(
                f"Falha ao baixar agosto para {symbol}"
            )


        august.to_csv(
            august_file,
            index=False,
        )


    # ========================================================
    # NORMALIZE
    # ========================================================

    july = normalize_dataframe(
        july
    )


    august = normalize_dataframe(
        august
    )


    # ========================================================
    # SANITY CHECK AUGUST
    # ========================================================

    august = august[
        (
            august[
                "open_time"
            ]
            >=
            HOLDOUT_START
        )
        &
        (
            august[
                "open_time"
            ]
            <
            HOLDOUT_END
        )
    ].copy()


    print(
        f"{symbol}: candles agosto = "
        f"{len(august)}"
    )


    # Agosto completo de 31 dias em 5m:
    #
    # 31 * 24 * 12 = 8928 candles
    #
    # Pequenas diferenças podem existir
    # por eventuais interrupções da exchange.
    # ========================================================

    expected_august = (
        31
        *
        24
        *
        12
    )


    if len(august) < (
        expected_august
        -
        10
    ):

        print(
            f"ATENÇÃO: {symbol} possui "
            f"{len(august)} candles em agosto. "
            f"Esperado aproximadamente "
            f"{expected_august}."
        )


    # ========================================================
    # CONCAT WARMUP + HOLDOUT
    # ========================================================

    df = pd.concat(
        [
            july,
            august,
        ],
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
# PROFIT FACTOR
# ============================================================

def profit_factor(returns):

    values = (
        pd.Series(
            returns
        )
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


    return (
        gains
        /
        losses
    )


# ============================================================
# TRIMMED MEAN
# ============================================================

def trimmed_mean(
    returns,
    trim=0.05,
):

    values = np.asarray(
        pd.Series(
            returns
        )
        .dropna(),
        dtype=float,
    )


    if len(values) == 0:
        return np.nan


    values = np.sort(
        values
    )


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
        pd.Series(
            returns
        )
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
        pd.Series(
            returns
        )
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
            trimmed_mean(
                values
            ),

        "winsorized_mean_5":
            winsorized_mean(
                values
            ),

        "win_rate":
            (
                values > 0
            ).mean(),

        "profit_factor":
            profit_factor(
                values
            ),

        "q10":
            values.quantile(
                0.10
            ),

        "q90":
            values.quantile(
                0.90
            ),

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


    drawdown = (
        values
        /
        peaks
        -
        1
    )


    return drawdown.min()


# ============================================================
# BUILD HOLDOUT
# ============================================================

trade_frames = []


for symbol in SYMBOLS:


    print()

    print(
        "=" * 100
    )

    print(
        f"PROCESSANDO HOLDOUT — {symbol}"
    )

    print(
        "=" * 100
    )


    df = load_period(
        symbol
    )


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
    # PAST VOLATILITY
    #
    # shift(1) garante que o candle atual
    # nunca entra no cálculo.
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
    # PAST EXTREME THRESHOLD
    # ========================================================

    df["ret_q975"] = (
        df["ret_5m"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            EXTREME_UP_QUANTILE
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
    ).fillna(
        False
    )


    # ========================================================
    # FRESHNESS
    #
    # Nenhum EXTREME_UP nos 12 candles anteriores.
    #
    # shift(1):
    # candle atual não participa da freshness.
    # ========================================================

    prior_extreme_count = (
        extreme_up
        .astype(int)

        .shift(1)

        .rolling(
            FRESH_LOOKBACK_BARS,
            min_periods=1,
        )

        .sum()

        .fillna(0)
    )


    fresh = (
        prior_extreme_count
        ==
        0
    )


    # ========================================================
    # FULL FROZEN C2
    # ========================================================

    c2_raw = (
        extreme_up

        &

        (
            df["return_z"]
            >=
            RETURN_Z_THRESHOLD
        )

        &

        fresh
    ).fillna(
        False
    )


    # ========================================================
    # NON-OVERLAP
    #
    # Aplicado APÓS a regra C2 completa.
    # ========================================================

    c2_mask = non_overlapping_mask(
        c2_raw,
        HOLD_BARS,
    )


    # ========================================================
    # ENTRY / EXIT
    #
    # Signal:
    # fechamento candle t
    #
    # Entry:
    # OPEN t+1
    #
    # Exit:
    # CLOSE t+6
    #
    # Holding:
    # 30 minutos
    # ========================================================

    entry_price = (
        df["open"]
        .shift(-1)
    )


    exit_price = (
        df["close"]
        .shift(-HOLD_BARS)
    )


    df["entry_price"] = (
        entry_price
    )


    df["exit_price"] = (
        exit_price
    )


    df["gross_return"] = (
        exit_price
        /
        entry_price
        -
        1
    )


    df["entry_time"] = (
        df["open_time"]
        +
        pd.Timedelta(
            minutes=5
        )
    )


    df["exit_time"] = (
        df["open_time"]
        +
        pd.Timedelta(
            minutes=35
        )
    )


    # ========================================================
    # SELECT C2 EVENTS
    # ========================================================

    temp = df.loc[
        c2_mask
    ].copy()


    temp[
        "prior_extreme_count_60m"
    ] = (
        prior_extreme_count.loc[
            temp.index
        ]
    )


    temp[
        "symbol"
    ] = symbol


    # ========================================================
    # STRICT AUGUST HOLDOUT
    #
    # Entry E exit precisam ocorrer dentro de agosto.
    # ========================================================

    temp = temp[
        (
            temp[
                "entry_time"
            ]
            >=
            HOLDOUT_START
        )
        &
        (
            temp[
                "exit_time"
            ]
            <
            HOLDOUT_END
        )
    ].copy()


    temp = temp.dropna(
        subset=[
            "return_z",
            "gross_return",
            "entry_price",
            "exit_price",
        ]
    )


    print(
        f"{symbol}: holdout trades = "
        f"{len(temp)}"
    )


    trade_frames.append(
        temp[
            [
                "symbol",
                "open_time",
                "entry_time",
                "exit_time",
                "ret_5m",
                "ret_q975",
                "ret_std_7d",
                "return_z",
                "prior_extreme_count_60m",
                "entry_price",
                "exit_price",
                "gross_return",
            ]
        ]
    )


# ============================================================
# CONCAT
# ============================================================

if not trade_frames:

    raise RuntimeError(
        "Nenhum dataframe de trades foi criado."
    )


trades = pd.concat(
    trade_frames,
    ignore_index=True,
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
    "=" * 190
)

print(
    "EXPERIMENTO 26 — "
    "C2 AUGUST 2026 HOLDOUT"
)

print(
    "=" * 190
)

print()


print(
    f"C2_VERSION: "
    f"{C2_VERSION}"
)


print(
    f"Holdout trades: "
    f"{len(trades)}"
)


# ============================================================
# COST COLUMNS
#
# CORRIGIDO
# ============================================================

for cost in COSTS:


    column = cost_column(
        cost
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


# ============================================================
# SANITY CHECK COST COLUMNS
# ============================================================

expected_cost_columns = [
    "net_4bps",
    "net_6bps",
    "net_8bps",
]


for column in expected_cost_columns:

    if column not in trades.columns:

        raise RuntimeError(
            f"Coluna de custo ausente: "
            f"{column}"
        )


print()


print(
    "Cost columns:",
    [
        column
        for column in trades.columns
        if column.startswith(
            "net_"
        )
    ]
)


# ============================================================
# GLOBAL
# ============================================================

global_rows = []


for cost in COSTS:


    column = cost_column(
        cost
    )


    global_rows.append(
        {

            "cost":
                cost,

            **summarize(
                trades[
                    column
                ]
            ),

        }
    )


global_results = pd.DataFrame(
    global_rows
)


# ============================================================
# BY ASSET
# ============================================================

asset_rows = []


for symbol, group in trades.groupby(
    "symbol"
):


    for cost in COSTS:


        column = cost_column(
            cost
        )


        asset_rows.append(
            {

                "symbol":
                    symbol,

                "cost":
                    cost,

                **summarize(
                    group[
                        column
                    ]
                ),

            }
        )


by_asset = pd.DataFrame(
    asset_rows
)


# ============================================================
# PORTFOLIO 1X
#
# 25% da equity por posição.
#
# IMPORTANTE:
# este portfólio é somente diagnóstico.
#
# A decisão principal do holdout continua sendo:
# - samples
# - mean
# - PF
#
# ============================================================

base_column = cost_column(
    BASE_COST
)


print(
    f"Base cost column: "
    f"{base_column}"
)


equity = (
    STARTING_EQUITY
)


equity_rows = []


for _, trade in trades.iterrows():


    notional = (
        equity
        *
        POSITION_NOTIONAL_FRACTION
    )


    trade_return = float(
        trade[
            base_column
        ]
    )


    pnl = (
        notional
        *
        trade_return
    )


    equity += pnl


    equity_rows.append(
        {

            "entry_time":
                trade[
                    "entry_time"
                ],

            "exit_time":
                trade[
                    "exit_time"
                ],

            "symbol":
                trade[
                    "symbol"
                ],

            "trade_return":
                trade_return,

            "notional":
                notional,

            "pnl":
                pnl,

            "equity":
                equity,

        }
    )


equity_curve = pd.DataFrame(
    equity_rows
)


if not equity_curve.empty:


    portfolio_return = (
        equity
        /
        STARTING_EQUITY
        -
        1
    )


    portfolio_dd = max_drawdown(
        equity_curve[
            "equity"
        ]
    )


else:


    portfolio_return = np.nan

    portfolio_dd = np.nan


# ============================================================
# BASE COST RESULT
# ============================================================

base_matches = global_results.loc[
    np.isclose(
        global_results[
            "cost"
        ],
        BASE_COST,
    )
]


if len(base_matches) != 1:

    raise RuntimeError(
        "Não foi possível localizar "
        "resultado base de 0.06%."
    )


base = base_matches.iloc[
    0
]


samples = int(
    base[
        "samples"
    ]
)


mean_return = float(
    base[
        "mean_return"
    ]
)


pf = float(
    base[
        "profit_factor"
    ]
)


# ============================================================
# PREDECLARED DECISION
# ============================================================

if samples < MIN_HOLDOUT_TRADES:


    decision = (
        "INCONCLUSIVE — "
        "amostra menor que o mínimo pré-declarado"
    )


elif (
    mean_return > 0
    and
    pf >= PASS_PF
    and
    portfolio_return > 0
    and
    portfolio_dd >= MAX_ACCEPTABLE_DD_1X
):


    decision = (
        "PASS — "
        "promover para TESTNET/PAPER"
    )


elif (
    mean_return <= 0
    and
    pf < 1.0
):


    decision = (
        "FAIL — "
        "holdout não confirmou o edge"
    )


else:


    decision = (
        "INCONCLUSIVE — "
        "não promover e não retunar"
    )


# ============================================================
# DISPLAY HELPER
# ============================================================

def percent_display(df):

    result = df.copy()


    percentage_columns = [
        "cost",
        "mean_return",
        "median_return",
        "trimmed_mean_5",
        "winsorized_mean_5",
        "win_rate",
        "q10",
        "q90",
        "worst_trade",
        "best_trade",
    ]


    for column in percentage_columns:

        if column in result.columns:

            result[
                column
            ] *= 100


    return result


global_display = percent_display(
    global_results
)


asset_display = percent_display(
    by_asset
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
# OUTPUT GLOBAL
# ============================================================

print()

print(
    "=" * 190
)

print(
    "HOLDOUT GLOBAL"
)

print(
    "=" * 190
)

print()


print(
    global_display.to_string(
        index=False
    )
)


# ============================================================
# OUTPUT BY ASSET
# ============================================================

print()

print(
    "=" * 190
)

print(
    "HOLDOUT POR ATIVO"
)

print(
    "=" * 190
)

print()


if not asset_display.empty:

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


else:

    print(
        "Nenhum resultado por ativo."
    )


# ============================================================
# DEVELOPMENT COMPARISON
# ============================================================

print()

print(
    "=" * 190
)

print(
    "COMPARAÇÃO COM DEVELOPMENT"
)

print(
    "=" * 190
)

print()


print(
    "Development @ 0.06%:"
)


print(
    f"  samples ........ "
    f"{DEV_SAMPLES}"
)


print(
    f"  mean/trade ..... "
    f"{DEV_MEAN_RETURN * 100:.6f}%"
)


print(
    f"  PF ............. "
    f"{DEV_PROFIT_FACTOR:.6f}"
)


print(
    f"  win rate ....... "
    f"{DEV_WIN_RATE * 100:.3f}%"
)


print()


print(
    "August holdout @ 0.06%:"
)


print(
    f"  samples ........ "
    f"{samples}"
)


print(
    f"  mean/trade ..... "
    f"{mean_return * 100:.6f}%"
)


print(
    f"  PF ............. "
    f"{pf:.6f}"
)


print(
    f"  win rate ....... "
    f"{base['win_rate'] * 100:.3f}%"
)


# ============================================================
# PORTFOLIO DIAGNOSTIC
# ============================================================

print()

print(
    "=" * 190
)

print(
    "PORTFOLIO DIAGNOSTIC — "
    "1X / 25% PER TRADE"
)

print(
    "=" * 190
)

print()


print(
    f"Starting equity: "
    f"{STARTING_EQUITY:.6f}"
)


print(
    f"Ending equity: "
    f"{equity:.6f}"
)


print(
    f"Total return: "
    f"{portfolio_return * 100:.4f}%"
)


print(
    f"Max drawdown: "
    f"{portfolio_dd * 100:.4f}%"
)


# ============================================================
# GATES
# ============================================================

print()

print(
    "=" * 190
)

print(
    "GATES PRÉ-DECLARADOS"
)

print(
    "=" * 190
)

print()


print(
    f"MIN_HOLDOUT_TRADES .... "
    f"{MIN_HOLDOUT_TRADES}"
)


print(
    f"PASS_PF ............... "
    f"{PASS_PF:.2f}"
)


print(
    f"MAX DD 1X ............. "
    f"{MAX_ACCEPTABLE_DD_1X * 100:.2f}%"
)


print()


print(
    f"Samples gate .......... "
    f"{samples} >= {MIN_HOLDOUT_TRADES} = "
    f"{samples >= MIN_HOLDOUT_TRADES}"
)


print(
    f"Mean gate ............. "
    f"{mean_return * 100:.6f}% > 0 = "
    f"{mean_return > 0}"
)


print(
    f"PF gate ............... "
    f"{pf:.6f} >= {PASS_PF} = "
    f"{pf >= PASS_PF}"
)


print(
    f"Portfolio return gate . "
    f"{portfolio_return * 100:.4f}% > 0 = "
    f"{portfolio_return > 0}"
)


print(
    f"DD gate ............... "
    f"{portfolio_dd * 100:.4f}% >= "
    f"{MAX_ACCEPTABLE_DD_1X * 100:.2f}% = "
    f"{portfolio_dd >= MAX_ACCEPTABLE_DD_1X}"
)


# ============================================================
# FINAL DECISION
# ============================================================

print()

print(
    "=" * 190
)

print(
    "DECISÃO PRÉ-DECLARADA"
)

print(
    "=" * 190
)

print()


print(
    decision
)


# ============================================================
# SAVE
# ============================================================

trades.to_csv(
    RESULTS_DIR
    / "c2_august_holdout_trades.csv",
    index=False,
)


global_results.to_csv(
    RESULTS_DIR
    / "c2_august_holdout_global.csv",
    index=False,
)


by_asset.to_csv(
    RESULTS_DIR
    / "c2_august_holdout_by_asset.csv",
    index=False,
)


equity_curve.to_csv(
    RESULTS_DIR
    / "c2_august_holdout_equity.csv",
    index=False,
)


decision_df = pd.DataFrame(
    [
        {

            "strategy_version":
                C2_VERSION,

            "holdout_start":
                HOLDOUT_START,

            "holdout_end":
                HOLDOUT_END,

            "base_cost":
                BASE_COST,

            "samples":
                samples,

            "mean_return":
                mean_return,

            "median_return":
                float(
                    base[
                        "median_return"
                    ]
                ),

            "trimmed_mean_5":
                float(
                    base[
                        "trimmed_mean_5"
                    ]
                ),

            "winsorized_mean_5":
                float(
                    base[
                        "winsorized_mean_5"
                    ]
                ),

            "win_rate":
                float(
                    base[
                        "win_rate"
                    ]
                ),

            "profit_factor":
                pf,

            "portfolio_return":
                portfolio_return,

            "portfolio_max_drawdown":
                portfolio_dd,

            "decision":
                decision,

        }
    ]
)


decision_df.to_csv(
    RESULTS_DIR
    / "c2_august_holdout_decision.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
from pathlib import Path
import time

import numpy as np
import pandas as pd
import requests


# ============================================================
# EXPERIMENTO 40
# BRANCH 17 — PREMIUM INDEX / BASIS REGIME
#
# DEVELOPMENT:
# 2024-01-01 -> 2026-08-01 EXCLUSIVE
#
# Portanto:
# Jan/2024 -> Jul/2026
#
# Agosto/2026:
# NÃO USAR
#
# Setembro/2026:
# INTOCADO
#
# Fonte:
# Binance USD-M Futures Premium Index Klines
#
# Endpoint:
# /fapi/v1/premiumIndexKlines
#
# Signal:
# premium conhecido no fechamento do candle t
#
# Entry:
# open do preço em t+1
#
# No lookahead.
# ============================================================


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]


INTERVAL = "5m"

START_DATE = "2024-01-01"
END_DATE = "2026-08-01"


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
# BINANCE USD-M
# ============================================================

BASE_URL = "https://fapi.binance.com"

PREMIUM_ENDPOINT = (
    "/fapi/v1/premiumIndexKlines"
)

API_LIMIT = 1500

REQUEST_TIMEOUT = 20

MAX_RETRIES = 7

REQUEST_PAUSE = 0.08


# ============================================================
# DEVELOPMENT MONTHS
# ============================================================

MONTH_STARTS = pd.date_range(
    START_DATE,
    "2026-07-01",
    freq="MS",
)

PERIODS = []

for start in MONTH_STARTS:

    end = (
        start
        +
        pd.offsets.MonthBegin(1)
    )

    PERIODS.append(
        (
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )
    )


# ============================================================
# PREMIUM HISTORICAL CONTEXT
# ============================================================

BARS_PER_DAY = 288

LOOKBACK = (
    7
    *
    BARS_PER_DAY
)

MIN_PERIODS = (
    3
    *
    BARS_PER_DAY
)


PREMIUM_LOW_Q = 0.10

PREMIUM_HIGH_Q = 0.90


# ============================================================
# HORIZONS
# ============================================================

HORIZONS = [
    6,      # 30m
    12,     # 60m
    24,     # 120m
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
# DISCOVERY GATE
# ============================================================

MIN_SAMPLES = 500

TARGET_PF = 1.08

MIN_ASSETS_PF_GT_1 = 3


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update(
    {
        "User-Agent":
            "crypto-research-premium-index/1.0"
    }
)


# ============================================================
# TIME HELPERS
# ============================================================

def to_ms(value):

    return int(
        pd.Timestamp(
            value,
            tz="UTC",
        ).timestamp()
        *
        1000
    )


START_MS = to_ms(
    START_DATE
)

END_MS = to_ms(
    END_DATE
)


# ============================================================
# BINANCE REQUEST
# ============================================================

def binance_get(
    endpoint,
    params,
):

    url = (
        BASE_URL
        +
        endpoint
    )

    last_error = None


    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            response = session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )


            # -----------------------------------------------
            # Rate limit
            # -----------------------------------------------

            if response.status_code in (
                418,
                429,
            ):

                wait = min(
                    2 ** attempt,
                    30,
                )

                print(
                    f"Rate limit Binance. "
                    f"Aguardando {wait}s..."
                )

                time.sleep(wait)

                continue


            response.raise_for_status()

            return response.json()


        except Exception as exc:

            last_error = exc

            wait = min(
                2 ** attempt,
                20,
            )

            print(
                f"Erro Binance tentativa "
                f"{attempt}/{MAX_RETRIES}: "
                f"{exc}"
            )

            time.sleep(wait)


    raise RuntimeError(
        f"Falha Binance após "
        f"{MAX_RETRIES} tentativas: "
        f"{last_error}"
    )


# ============================================================
# DOWNLOAD PREMIUM INDEX
# ============================================================

def download_premium_index(
    symbol,
):

    print()

    print(
        f"Baixando Premium Index "
        f"{symbol}..."
    )


    rows = []

    cursor = START_MS


    while cursor < END_MS:

        params = {

            "symbol":
                symbol,

            "interval":
                INTERVAL,

            "startTime":
                cursor,

            "endTime":
                END_MS - 1,

            "limit":
                API_LIMIT,
        }


        batch = binance_get(
            PREMIUM_ENDPOINT,
            params,
        )


        if not batch:
            break


        rows.extend(
            batch
        )


        last_open_time = int(
            batch[-1][0]
        )


        next_cursor = (
            last_open_time
            +
            5 * 60 * 1000
        )


        if next_cursor <= cursor:

            raise RuntimeError(
                "Cursor Binance não avançou."
            )


        cursor = next_cursor


        print(
            f"\r{symbol}: "
            f"{len(rows):,} candles premium",
            end="",
            flush=True,
        )


        time.sleep(
            REQUEST_PAUSE
        )


    print()


    if not rows:

        raise RuntimeError(
            f"Nenhum Premium Index "
            f"recebido para {symbol}."
        )


    columns = [

        "open_time_ms",

        "premium_open",
        "premium_high",
        "premium_low",
        "premium_close",

        "ignore_1",

        "close_time_ms",

        "ignore_2",
        "ignore_3",
        "ignore_4",
        "ignore_5",
        "ignore_6",
    ]


    df = pd.DataFrame(
        rows,
        columns=columns,
    )


    df["open_time"] = pd.to_datetime(
        df["open_time_ms"],
        unit="ms",
        utc=True,
        errors="coerce",
    )


    for column in [

        "premium_open",
        "premium_high",
        "premium_low",
        "premium_close",

    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )


    df = (

        df[
            [
                "open_time",
                "premium_open",
                "premium_high",
                "premium_low",
                "premium_close",
            ]
        ]

        .dropna()

        .drop_duplicates(
            subset=[
                "open_time"
            ]
        )

        .sort_values(
            "open_time"
        )

        .reset_index(
            drop=True
        )
    )


    df = df[
        (
            df["open_time"]
            >=
            pd.Timestamp(
                START_DATE,
                tz="UTC",
            )
        )
        &
        (
            df["open_time"]
            <
            pd.Timestamp(
                END_DATE,
                tz="UTC",
            )
        )
    ].copy()


    return df


# ============================================================
# PREMIUM CACHE
# ============================================================

def premium_cache_path(
    symbol,
):

    return (
        DATA_DIR
        /
        (
            f"{symbol}_premium_5m_"
            f"2024-01-01_2026-08-01.csv"
        )
    )


def load_or_download_premium(
    symbol,
):

    path = premium_cache_path(
        symbol
    )


    if path.exists():

        print(
            f"{symbol}: usando cache "
            f"{path}"
        )


        df = pd.read_csv(
            path
        )


        df["open_time"] = pd.to_datetime(
            df["open_time"],
            format="mixed",
            utc=True,
            errors="coerce",
        )


        for column in [

            "premium_open",
            "premium_high",
            "premium_low",
            "premium_close",

        ]:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )


        df = (

            df
            .dropna()

            .drop_duplicates(
                subset=[
                    "open_time"
                ]
            )

            .sort_values(
                "open_time"
            )

            .reset_index(
                drop=True
            )
        )


        return df


    df = download_premium_index(
        symbol
    )


    df.to_csv(
        path,
        index=False,
    )


    print(
        f"{symbol}: cache salvo em "
        f"{path}"
    )


    return df


# ============================================================
# PRICE DATA
# ============================================================

def load_price(
    symbol,
):

    frames = []


    for (
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
                f"Arquivo de preço ausente: "
                f"{path}"
            )


        df = pd.read_csv(
            path
        )


        df["open_time"] = pd.to_datetime(
            df["open_time"],
            format="mixed",
            utc=True,
            errors="coerce",
        )


        for column in [
            "open",
            "high",
            "low",
            "close",
        ]:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )


        frames.append(
            df
        )


    df = pd.concat(
        frames,
        ignore_index=True,
    )


    df = (

        df

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
            subset=[
                "open_time"
            ]
        )

        .sort_values(
            "open_time"
        )

        .reset_index(
            drop=True
        )
    )


    df["symbol"] = symbol


    df["year"] = (
        df["open_time"]
        .dt.strftime("%Y")
    )


    df["period"] = (
        df["open_time"]
        .dt.strftime("%Y-%m")
    )


    return df


# ============================================================
# STATISTICS
# ============================================================

def profit_factor(values):

    values = (
        pd.Series(values)
        .dropna()
    )


    if values.empty:
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


def trimmed_mean(
    values,
    trim=0.05,
):

    values = np.asarray(
        pd.Series(values)
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


def winsorized_mean(
    values,
    limit=0.05,
):

    values = np.asarray(
        pd.Series(values)
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


def summarize(values):

    values = (
        pd.Series(values)
        .dropna()
    )


    if values.empty:

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
        f"PROCESSANDO PREMIUM REGIME — "
        f"{symbol}"
    )

    print("=" * 100)


    price = load_price(
        symbol
    )


    premium = load_or_download_premium(
        symbol
    )


    print(
        f"{symbol}: price candles = "
        f"{len(price)}"
    )


    print(
        f"{symbol}: premium candles = "
        f"{len(premium)}"
    )


    # ========================================================
    # ALIGN
    # ========================================================

    df = price.merge(

        premium,

        on="open_time",

        how="inner",

        validate="one_to_one",
    )


    df = (
        df
        .sort_values(
            "open_time"
        )
        .reset_index(
            drop=True
        )
    )


    coverage = (
        len(df)
        /
        len(price)
        if len(price) > 0
        else 0
    )


    print(
        f"{symbol}: aligned = "
        f"{len(df)} "
        f"({coverage:.2%})"
    )


    if coverage < 0.95:

        raise RuntimeError(
            f"{symbol}: cobertura premium "
            f"insuficiente: "
            f"{coverage:.2%}"
        )


    # ========================================================
    # PREMIUM CONTEXT
    #
    # Use close of premium candle t.
    #
    # Current candle does NOT define its own threshold.
    # ========================================================

    df["premium_q10"] = (

        df["premium_close"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            PREMIUM_LOW_Q
        )

        .shift(1)

    )


    df["premium_q90"] = (

        df["premium_close"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            PREMIUM_HIGH_Q
        )

        .shift(1)

    )


    valid_context = (

        df["premium_q10"].notna()

        &

        df["premium_q90"].notna()

    )


    # ========================================================
    # PREMIUM Z-SCORE
    #
    # Diagnostic only.
    # Not used for event selection.
    # ========================================================

    df["premium_mean"] = (

        df["premium_close"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .mean()

        .shift(1)

    )


    df["premium_std"] = (

        df["premium_close"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .std()

        .shift(1)

    )


    df["premium_z"] = np.where(

        df["premium_std"] > 0,

        (
            df["premium_close"]
            -
            df["premium_mean"]
        )
        /
        df["premium_std"],

        np.nan,

    )


    # ========================================================
    # STATES
    # ========================================================

    high_premium = (

        valid_context

        &

        (
            df["premium_close"]
            >=
            df["premium_q90"]
        )

    )


    low_premium = (

        valid_context

        &

        (
            df["premium_close"]
            <=
            df["premium_q10"]
        )

    )


    # ========================================================
    # FIRST CROSSING
    #
    # We study entry into an extreme regime,
    # not every consecutive candle while extreme.
    # ========================================================

    high_event = (

        high_premium.fillna(False)

        &

        ~high_premium
        .shift(1)
        .fillna(False)

    )


    low_event = (

        low_premium.fillna(False)

        &

        ~low_premium
        .shift(1)
        .fillna(False)

    )


    # ========================================================
    # FUTURE RETURNS
    #
    # signal t close
    # entry open t+1
    # ========================================================

    entry_price = (
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
            entry_price
            -
            1
        )


        df[
            f"future_short_{horizon}"
        ] = (
            1
            -
            exit_price
            /
            entry_price
        )


    # ========================================================
    # EVENTS
    # ========================================================

    masks = {

        "HIGH_PREMIUM":
            high_event,

        "LOW_PREMIUM":
            low_event,

    }


    for event_name, mask in masks.items():


        temp = (
            df.loc[
                mask
            ]
            .copy()
        )


        temp["event"] = (
            event_name
        )


        event_frames.append(
            temp
        )


# ============================================================
# CONCAT EVENTS
# ============================================================

if not event_frames:

    raise RuntimeError(
        "Nenhum evento criado."
    )


events = pd.concat(
    event_frames,
    ignore_index=True,
)


events = events.dropna(
    subset=[
        f"future_long_{max(HORIZONS)}",
        f"future_short_{max(HORIZONS)}",
    ]
)


events = (

    events

    .sort_values(
        [
            "open_time",
            "symbol",
            "event",
        ]
    )

    .reset_index(
        drop=True
    )

)


print()

print(
    f"TOTAL EVENTS = {len(events)}"
)


# ============================================================
# EVENT COUNTS
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

    .rename(
        "samples"
    )

    .reset_index()

)


# ============================================================
# EVENT ANATOMY
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

        mean_premium=(
            "premium_close",
            "mean",
        ),

        median_premium=(
            "premium_close",
            "median",
        ),

        mean_premium_z=(
            "premium_z",
            "mean",
        ),

        median_premium_z=(
            "premium_z",
            "median",
        ),

        mean_q10=(
            "premium_q10",
            "mean",
        ),

        mean_q90=(
            "premium_q90",
            "mean",
        ),

    )

)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    # --------------------------------------------------------
    # HIGH PREMIUM
    #
    # Main thesis:
    # premium convergence -> SHORT
    #
    # Control:
    # continuation -> LONG
    # --------------------------------------------------------

    "HIGH_PREMIUM_REVERT_SHORT":
        (
            "HIGH_PREMIUM",
            "SHORT",
        ),

    "HIGH_PREMIUM_CONTINUE_LONG":
        (
            "HIGH_PREMIUM",
            "LONG",
        ),


    # --------------------------------------------------------
    # LOW PREMIUM
    #
    # Main thesis:
    # premium convergence -> LONG
    #
    # Control:
    # continuation -> SHORT
    # --------------------------------------------------------

    "LOW_PREMIUM_REVERT_LONG":
        (
            "LOW_PREMIUM",
            "LONG",
        ),

    "LOW_PREMIUM_CONTINUE_SHORT":
        (
            "LOW_PREMIUM",
            "SHORT",
        ),

}


# ============================================================
# ANALYSIS
# ============================================================

global_rows = []

year_rows = []

asset_rows = []

monthly_rows = []


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


        minutes = (
            horizon
            *
            BAR_MINUTES
        )


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        # ====================================================
        # GLOBAL
        # ====================================================

        gross = (
            subset[
                return_column
            ]
            .dropna()
        )


        for cost in COSTS:


            global_rows.append({

                "hypothesis":
                    hypothesis,

                "minutes":
                    minutes,

                "cost":
                    cost,

                **summarize(
                    gross
                    -
                    cost
                ),

            })


        # ====================================================
        # YEAR
        # ====================================================

        for year, group in subset.groupby(
            "year"
        ):


            gross_year = (
                group[
                    return_column
                ]
                .dropna()
            )


            for cost in COSTS:


                year_rows.append({

                    "hypothesis":
                        hypothesis,

                    "minutes":
                        minutes,

                    "year":
                        year,

                    "cost":
                        cost,

                    **summarize(
                        gross_year
                        -
                        cost
                    ),

                })


        # ====================================================
        # ASSET
        # ====================================================

        for symbol, group in subset.groupby(
            "symbol"
        ):


            gross_asset = (
                group[
                    return_column
                ]
                .dropna()
            )


            for cost in COSTS:


                asset_rows.append({

                    "hypothesis":
                        hypothesis,

                    "minutes":
                        minutes,

                    "symbol":
                        symbol,

                    "cost":
                        cost,

                    **summarize(
                        gross_asset
                        -
                        cost
                    ),

                })


        # ====================================================
        # MONTH
        # ====================================================

        for period, group in subset.groupby(
            "period"
        ):


            gross_month = (
                group[
                    return_column
                ]
                .dropna()
            )


            monthly_rows.append({

                "hypothesis":
                    hypothesis,

                "minutes":
                    minutes,

                "period":
                    period,

                **summarize(
                    gross_month
                    -
                    BASE_COST
                ),

            })


global_results = pd.DataFrame(
    global_rows
)


by_year = pd.DataFrame(
    year_rows
)


by_asset = pd.DataFrame(
    asset_rows
)


monthly = pd.DataFrame(
    monthly_rows
)


# ============================================================
# STABILITY
# ============================================================

stability_rows = []


for hypothesis in HYPOTHESES:


    for horizon in HORIZONS:


        minutes = (
            horizon
            *
            BAR_MINUTES
        )


        global_match = global_results[
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


        if global_match.empty:
            continue


        row = (
            global_match
            .iloc[0]
        )


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


        months = monthly[
            (
                monthly[
                    "hypothesis"
                ]
                ==
                hypothesis
            )
            &
            (
                monthly[
                    "minutes"
                ]
                ==
                minutes
            )
        ]


        stability_rows.append({

            "hypothesis":
                hypothesis,

            "minutes":
                minutes,

            "samples":
                int(
                    row[
                        "samples"
                    ]
                ),

            "mean_return":
                row[
                    "mean_return"
                ],

            "trimmed_mean_5":
                row[
                    "trimmed_mean_5"
                ],

            "winsorized_mean_5":
                row[
                    "winsorized_mean_5"
                ],

            "win_rate":
                row[
                    "win_rate"
                ],

            "profit_factor":
                row[
                    "profit_factor"
                ],


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


            "months_pf_gt_1":
                int(
                    (
                        months[
                            "profit_factor"
                        ]
                        >
                        1
                    ).sum()
                ),

            "total_months":
                len(months),

            "median_month_pf":
                months[
                    "profit_factor"
                ].median(),

        })


stability = pd.DataFrame(
    stability_rows
)


# ============================================================
# DISCOVERY GATE
# ============================================================

stability[
    "basic_discovery_gate"
] = (

    (
        stability[
            "samples"
        ]
        >=
        MIN_SAMPLES
    )

    &

    (
        stability[
            "mean_return"
        ]
        >
        0
    )

    &

    (
        stability[
            "trimmed_mean_5"
        ]
        >
        0
    )

    &

    (
        stability[
            "winsorized_mean_5"
        ]
        >
        0
    )

    &

    (
        stability[
            "profit_factor"
        ]
        >=
        TARGET_PF
    )

    &

    (
        stability[
            "years_pf_gt_1"
        ]
        ==
        stability[
            "total_years"
        ]
    )

    &

    (
        stability[
            "assets_pf_gt_1"
        ]
        >=
        MIN_ASSETS_PF_GT_1
    )

)


# ============================================================
# DISPLAY
# ============================================================

def pct(
    df,
):

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

        "mean_premium",
        "median_premium",

        "mean_q10",
        "mean_q90",

    ]


    for column in percentage_columns:

        if column in result.columns:

            result[
                column
            ] *= 100


    return result


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    460,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 220)

print(
    "EXPERIMENTO 40 — "
    "BRANCH 17 PREMIUM INDEX REGIME"
)

print("=" * 220)


print()

print(
    "EVENT COUNTS"
)

print()


print(
    counts.to_string(
        index=False
    )
)


print()

print("=" * 220)

print(
    "EVENT ANATOMY"
)

print("=" * 220)

print()


print(
    pct(
        anatomy
    )
    .to_string(
        index=False
    )
)


# ============================================================
# GLOBAL BASE COST
# ============================================================

base_global = (

    pct(
        global_results
    )[
        np.isclose(
            global_results[
                "cost"
            ],
            BASE_COST,
        )
    ]

    .sort_values(
        "profit_factor",
        ascending=False,
    )

)


print()

print("=" * 220)

print(
    "GLOBAL @ 0.06%"
)

print("=" * 220)

print()


print(
    base_global
    .to_string(
        index=False
    )
)


# ============================================================
# STABILITY
# ============================================================

print()

print("=" * 220)

print(
    "STABILITY @ 0.06%"
)

print("=" * 220)

print()


print(

    pct(
        stability
    )

    .sort_values(
        "profit_factor",
        ascending=False,
    )

    .to_string(
        index=False
    )

)


# ============================================================
# GATE
# ============================================================

passed = stability[
    stability[
        "basic_discovery_gate"
    ]
].copy()


print()

print("=" * 220)

print(
    "DISCOVERY GATE"
)

print("=" * 220)

print()


if passed.empty:

    print(
        "Nenhuma hipótese passou "
        "o gate básico."
    )


else:

    print(

        pct(
            passed[
                [
                    "hypothesis",
                    "minutes",
                    "samples",
                    "mean_return",
                    "trimmed_mean_5",
                    "winsorized_mean_5",
                    "profit_factor",
                    "years_pf_gt_1",
                    "assets_pf_gt_1",
                    "months_pf_gt_1",
                ]
            ]
        )

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
    /
    "premium_regime_events.csv",
    index=False,
)


counts.to_csv(
    RESULTS_DIR
    /
    "premium_regime_counts.csv",
    index=False,
)


anatomy.to_csv(
    RESULTS_DIR
    /
    "premium_regime_anatomy.csv",
    index=False,
)


global_results.to_csv(
    RESULTS_DIR
    /
    "premium_regime_global.csv",
    index=False,
)


by_year.to_csv(
    RESULTS_DIR
    /
    "premium_regime_by_year.csv",
    index=False,
)


by_asset.to_csv(
    RESULTS_DIR
    /
    "premium_regime_by_asset.csv",
    index=False,
)


monthly.to_csv(
    RESULTS_DIR
    /
    "premium_regime_monthly.csv",
    index=False,
)


stability.to_csv(
    RESULTS_DIR
    /
    "premium_regime_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
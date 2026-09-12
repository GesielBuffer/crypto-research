from pathlib import Path
import time

import numpy as np
import pandas as pd
import requests


# ============================================================
# EXPERIMENTO 41
# BRANCH 18 — MARK / INDEX DISLOCATION
#
# DEVELOPMENT:
# Jan/2024 -> Jul/2026
#
# Agosto/2026:
# NÃO USAR
#
# Setembro/2026:
# INTOCADO
#
# Signal:
# basis conhecido no fechamento t
#
# Entry:
# open do preço em t+1
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

MARK_ENDPOINT = "/fapi/v1/markPriceKlines"
INDEX_ENDPOINT = "/fapi/v1/indexPriceKlines"

LIMIT = 1500

REQUEST_TIMEOUT = 20
MAX_RETRIES = 7
REQUEST_PAUSE = 0.08


# ============================================================
# HISTORICAL CONTEXT
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

LOW_Q = 0.10
HIGH_Q = 0.90

CHANGE_BARS = 6   # 30m


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
# GATE
# ============================================================

MIN_SAMPLES = 500
TARGET_PF = 1.08
MIN_ASSETS_PF_GT_1 = 3


# ============================================================
# DATES
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
# HTTP
# ============================================================

session = requests.Session()

session.headers.update(
    {
        "User-Agent":
            "crypto-research-mark-index/1.0"
    }
)


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


            if response.status_code in (
                418,
                429,
            ):

                wait = min(
                    2 ** attempt,
                    30,
                )

                print(
                    f"Rate limit. "
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
                f"Erro Binance "
                f"{attempt}/{MAX_RETRIES}: "
                f"{exc}"
            )

            time.sleep(wait)


    raise RuntimeError(
        f"Falha Binance: "
        f"{last_error}"
    )


# ============================================================
# GENERIC KLINE DOWNLOAD
# ============================================================

def download_special_klines(
    symbol,
    endpoint,
    kind,
):

    print(
        f"Baixando {kind} {symbol}..."
    )

    rows = []
    cursor = START_MS

    while cursor < END_MS:

        # ====================================================
        # Binance usa parâmetros diferentes:
        #
        # markPriceKlines  -> symbol
        # indexPriceKlines -> pair
        # ====================================================

        params = {
            "interval": INTERVAL,
            "startTime": cursor,
            "endTime": END_MS - 1,
            "limit": LIMIT,
        }

        if kind == "index":
            params["pair"] = symbol
        else:
            params["symbol"] = symbol

        batch = binance_get(
            endpoint,
            params,
        )

        if not batch:
            break

        rows.extend(
            batch
        )

        last_time = int(
            batch[-1][0]
        )

        next_cursor = (
            last_time
            +
            5 * 60 * 1000
        )

        if next_cursor <= cursor:

            raise RuntimeError(
                f"{kind}: cursor não avançou."
            )

        cursor = next_cursor

        print(
            f"\r{symbol} {kind}: "
            f"{len(rows):,} candles",
            end="",
            flush=True,
        )

        time.sleep(
            REQUEST_PAUSE
        )

    print()

    if not rows:

        raise RuntimeError(
            f"Nenhum dado de {kind} "
            f"para {symbol}."
        )

    columns = [
        "open_time_ms",

        f"{kind}_open",
        f"{kind}_high",
        f"{kind}_low",
        f"{kind}_close",

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
        f"{kind}_open",
        f"{kind}_high",
        f"{kind}_low",
        f"{kind}_close",
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = (
        df[
            [
                "open_time",
                f"{kind}_open",
                f"{kind}_high",
                f"{kind}_low",
                f"{kind}_close",
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

    return df


# ============================================================
# CACHE
# ============================================================

def cache_path(
    symbol,
    kind,
):

    return (
        DATA_DIR
        /
        (
            f"{symbol}_{kind}_5m_"
            f"2024-01-01_2026-08-01.csv"
        )
    )


def load_or_download(
    symbol,
    endpoint,
    kind,
):

    path = cache_path(
        symbol,
        kind,
    )


    if path.exists():

        print(
            f"{symbol}: usando cache "
            f"{kind}"
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

            f"{kind}_open",
            f"{kind}_high",
            f"{kind}_low",
            f"{kind}_close",

        ]:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )


        return (

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


    df = download_special_klines(
        symbol,
        endpoint,
        kind,
    )


    df.to_csv(
        path,
        index=False,
    )


    print(
        f"{symbol}: cache {kind} salvo."
    )


    return df


# ============================================================
# PRICE
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
                f"Arquivo ausente: {path}"
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
# STATS
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


    return (
        gains
        /
        losses
    )


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

            "mean_return":
                np.nan,

            "median_return":
                np.nan,

            "trimmed_mean_5":
                np.nan,

            "winsorized_mean_5":
                np.nan,

            "win_rate":
                np.nan,

            "profit_factor":
                np.nan,

            "q10":
                np.nan,

            "q90":
                np.nan,
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
    }


# ============================================================
# BUILD EVENTS
# ============================================================

event_frames = []


for symbol in SYMBOLS:


    print()

    print("=" * 100)

    print(
        f"PROCESSANDO MARK/INDEX — "
        f"{symbol}"
    )

    print("=" * 100)


    price = load_price(
        symbol
    )


    mark = load_or_download(
        symbol,
        MARK_ENDPOINT,
        "mark",
    )


    index = load_or_download(
        symbol,
        INDEX_ENDPOINT,
        "index",
    )


    print(
        f"{symbol}: price={len(price)} "
        f"mark={len(mark)} "
        f"index={len(index)}"
    )


    df = (

        price

        .merge(
            mark,
            on="open_time",
            how="inner",
            validate="one_to_one",
        )

        .merge(
            index,
            on="open_time",
            how="inner",
            validate="one_to_one",
        )

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
    )


    print(
        f"{symbol}: aligned="
        f"{len(df)} "
        f"({coverage:.2%})"
    )


    if coverage < 0.95:

        raise RuntimeError(
            f"{symbol}: cobertura "
            f"insuficiente "
            f"{coverage:.2%}"
        )


    # ========================================================
    # BASIS
    # ========================================================

    df["basis"] = (

        df["mark_close"]
        /
        df["index_close"]
        -
        1
    )


    # ========================================================
    # BASIS CHANGE 30M
    # ========================================================

    df["basis_change_30m"] = (

        df["basis"]
        -
        df["basis"].shift(
            CHANGE_BARS
        )
    )


    # ========================================================
    # HISTORICAL BASIS THRESHOLDS
    #
    # Current candle excluded.
    # ========================================================

    df["basis_q10"] = (

        df["basis"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            LOW_Q
        )

        .shift(1)

    )


    df["basis_q90"] = (

        df["basis"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            HIGH_Q
        )

        .shift(1)

    )


    # ========================================================
    # HISTORICAL CHANGE THRESHOLDS
    # ========================================================

    df["change_q10"] = (

        df["basis_change_30m"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            LOW_Q
        )

        .shift(1)

    )


    df["change_q90"] = (

        df["basis_change_30m"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            HIGH_Q
        )

        .shift(1)

    )


    valid = (

        df["basis_q10"].notna()

        &

        df["basis_q90"].notna()

        &

        df["change_q10"].notna()

        &

        df["change_q90"].notna()

    )


    # ========================================================
    # EVENT STATES
    #
    # HIGH BASIS:
    # positive/extreme mark > index
    #
    # LOW BASIS:
    # negative/extreme mark < index
    #
    # WIDENING:
    # moving further away from zero/extreme direction
    #
    # NARROWING:
    # moving back toward zero
    # ========================================================

    high_basis = (

        valid

        &

        (
            df["basis"]
            >=
            df["basis_q90"]
        )

    )


    low_basis = (

        valid

        &

        (
            df["basis"]
            <=
            df["basis_q10"]
        )

    )


    high_widening = (

        high_basis

        &

        (
            df["basis_change_30m"]
            >=
            df["change_q90"]
        )

    )


    high_narrowing = (

        high_basis

        &

        (
            df["basis_change_30m"]
            <=
            df["change_q10"]
        )

    )


    low_widening = (

        low_basis

        &

        (
            df["basis_change_30m"]
            <=
            df["change_q10"]
        )

    )


    low_narrowing = (

        low_basis

        &

        (
            df["basis_change_30m"]
            >=
            df["change_q90"]
        )

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
            .shift(
                -horizon
            )
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


        df[
            f"future_short_{horizon}"
        ] = (

            1
            -
            exit_price
            /
            entry
        )


    # ========================================================
    # FIRST CROSSING
    # ========================================================

    raw_masks = {

        "HIGH_BASIS_WIDENING":
            high_widening,

        "HIGH_BASIS_NARROWING":
            high_narrowing,

        "LOW_BASIS_WIDENING":
            low_widening,

        "LOW_BASIS_NARROWING":
            low_narrowing,
    }


    for event_name, raw_mask in raw_masks.items():


        raw_mask = (
            raw_mask
            .fillna(False)
        )


        event_mask = (

            raw_mask

            &

            ~raw_mask
            .shift(1)
            .fillna(False)

        )


        temp = (

            df.loc[
                event_mask
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
# CONCAT
# ============================================================

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

    .rename(
        "samples"
    )

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

        mean_basis=(
            "basis",
            "mean",
        ),

        median_basis=(
            "basis",
            "median",
        ),

        mean_basis_change_30m=(
            "basis_change_30m",
            "mean",
        ),

        median_basis_change_30m=(
            "basis_change_30m",
            "median",
        ),

        mean_mark=(
            "mark_close",
            "mean",
        ),

        mean_index=(
            "index_close",
            "mean",
        ),
    )
)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    # HIGH BASIS WIDENING
    "HIGH_WIDEN_CONTINUE_LONG":
        (
            "HIGH_BASIS_WIDENING",
            "LONG",
        ),

    "HIGH_WIDEN_REVERT_SHORT":
        (
            "HIGH_BASIS_WIDENING",
            "SHORT",
        ),


    # HIGH BASIS NARROWING
    "HIGH_NARROW_REVERT_SHORT":
        (
            "HIGH_BASIS_NARROWING",
            "SHORT",
        ),

    "HIGH_NARROW_CONTINUE_LONG":
        (
            "HIGH_BASIS_NARROWING",
            "LONG",
        ),


    # LOW BASIS WIDENING
    "LOW_WIDEN_CONTINUE_SHORT":
        (
            "LOW_BASIS_WIDENING",
            "SHORT",
        ),

    "LOW_WIDEN_REVERT_LONG":
        (
            "LOW_BASIS_WIDENING",
            "LONG",
        ),


    # LOW BASIS NARROWING
    "LOW_NARROW_REVERT_LONG":
        (
            "LOW_BASIS_NARROWING",
            "LONG",
        ),

    "LOW_NARROW_CONTINUE_SHORT":
        (
            "LOW_BASIS_NARROWING",
            "SHORT",
        ),
}


# ============================================================
# ANALYSIS TABLES
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

            return_col = (
                f"future_long_{horizon}"
            )

        else:

            return_col = (
                f"future_short_{horizon}"
            )


        gross = (
            subset[
                return_col
            ]
            .dropna()
        )


        # ====================================================
        # GLOBAL
        # ====================================================

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


            returns = (
                group[
                    return_col
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
                        returns
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


            returns = (
                group[
                    return_col
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
                        returns
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


            returns = (

                group[
                    return_col
                ]

                .dropna()

                -
                BASE_COST
            )


            monthly_rows.append({

                "hypothesis":
                    hypothesis,

                "minutes":
                    minutes,

                "period":
                    period,

                **summarize(
                    returns
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


        g = global_results[
            (
                global_results["hypothesis"]
                ==
                hypothesis
            )
            &
            (
                global_results["minutes"]
                ==
                minutes
            )
            &
            (
                np.isclose(
                    global_results["cost"],
                    BASE_COST,
                )
            )
        ]


        if g.empty:
            continue


        row = g.iloc[0]


        years = by_year[
            (
                by_year["hypothesis"]
                ==
                hypothesis
            )
            &
            (
                by_year["minutes"]
                ==
                minutes
            )
            &
            (
                np.isclose(
                    by_year["cost"],
                    BASE_COST,
                )
            )
        ]


        assets = by_asset[
            (
                by_asset["hypothesis"]
                ==
                hypothesis
            )
            &
            (
                by_asset["minutes"]
                ==
                minutes
            )
            &
            (
                np.isclose(
                    by_asset["cost"],
                    BASE_COST,
                )
            )
        ]


        months = monthly[
            (
                monthly["hypothesis"]
                ==
                hypothesis
            )
            &
            (
                monthly["minutes"]
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
                    row["samples"]
                ),

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
                        years["profit_factor"]
                        >
                        1
                    ).sum()
                ),

            "total_years":
                len(years),

            "worst_year_pf":
                years["profit_factor"]
                .min(),

            "median_year_pf":
                years["profit_factor"]
                .median(),


            "assets_pf_gt_1":
                int(
                    (
                        assets["profit_factor"]
                        >
                        1
                    ).sum()
                ),

            "total_assets":
                len(assets),

            "worst_asset_pf":
                assets["profit_factor"]
                .min(),

            "median_asset_pf":
                assets["profit_factor"]
                .median(),


            "months_pf_gt_1":
                int(
                    (
                        months["profit_factor"]
                        >
                        1
                    ).sum()
                ),

            "total_months":
                len(months),

            "median_month_pf":
                months["profit_factor"]
                .median(),
        })


stability = pd.DataFrame(
    stability_rows
)


# ============================================================
# GATE
# ============================================================

stability[
    "basic_discovery_gate"
] = (

    (
        stability["samples"]
        >=
        MIN_SAMPLES
    )

    &

    (
        stability["mean_return"]
        >
        0
    )

    &

    (
        stability["trimmed_mean_5"]
        >
        0
    )

    &

    (
        stability["winsorized_mean_5"]
        >
        0
    )

    &

    (
        stability["profit_factor"]
        >=
        TARGET_PF
    )

    &

    (
        stability["years_pf_gt_1"]
        ==
        stability["total_years"]
    )

    &

    (
        stability["assets_pf_gt_1"]
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


    columns = [

        "cost",

        "mean_return",
        "median_return",

        "trimmed_mean_5",
        "winsorized_mean_5",

        "win_rate",

        "q10",
        "q90",

        "mean_basis",
        "median_basis",

        "mean_basis_change_30m",
        "median_basis_change_30m",
    ]


    for column in columns:

        if column in result.columns:

            result[column] *= 100


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
# PRINT
# ============================================================

print()

print("=" * 220)

print(
    "EXPERIMENTO 41 — "
    "BRANCH 18 MARK / INDEX DISLOCATION"
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


base_global = (

    pct(
        global_results
    )[
        np.isclose(
            global_results["cost"],
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
    "mark_index_dislocation_events.csv",
    index=False,
)

counts.to_csv(
    RESULTS_DIR
    /
    "mark_index_dislocation_counts.csv",
    index=False,
)

anatomy.to_csv(
    RESULTS_DIR
    /
    "mark_index_dislocation_anatomy.csv",
    index=False,
)

global_results.to_csv(
    RESULTS_DIR
    /
    "mark_index_dislocation_global.csv",
    index=False,
)

by_year.to_csv(
    RESULTS_DIR
    /
    "mark_index_dislocation_by_year.csv",
    index=False,
)

by_asset.to_csv(
    RESULTS_DIR
    /
    "mark_index_dislocation_by_asset.csv",
    index=False,
)

monthly.to_csv(
    RESULTS_DIR
    /
    "mark_index_dislocation_monthly.csv",
    index=False,
)

stability.to_csv(
    RESULTS_DIR
    /
    "mark_index_dislocation_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
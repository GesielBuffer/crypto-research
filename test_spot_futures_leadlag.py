from pathlib import Path
import time

import numpy as np
import pandas as pd
import requests


# ============================================================
# EXPERIMENTO 43
# BRANCH 19 — SPOT / FUTURES LEAD-LAG
#
# DEVELOPMENT:
# Jan/2024 -> Jul/2026
#
# Signal conhecido no fechamento de t.
# Entrada no open Futures de t+1.
#
# Agosto/2026:
# não usar
#
# Setembro/2026:
# intocado
# ============================================================


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]

START_DATE = "2024-01-01"
END_DATE = "2026-08-01"

INTERVAL = "5m"

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
# SPOT BINANCE
# ============================================================

SPOT_BASE_URL = "https://api.binance.com"
SPOT_ENDPOINT = "/api/v3/klines"

SPOT_LIMIT = 1000

REQUEST_TIMEOUT = 20
MAX_RETRIES = 7
REQUEST_PAUSE = 0.08


# ============================================================
# CONTEXT
# ============================================================

BARS_PER_DAY = 288

LOOKBACK = 7 * BARS_PER_DAY
MIN_PERIODS = 3 * BARS_PER_DAY

LOW_Q = 0.10
HIGH_Q = 0.90


# ============================================================
# FUTURE HORIZONS
# ============================================================

HORIZONS = [
    6,      # 30m
    12,     # 60m
    24,     # 120m
]

BAR_MINUTES = 5


# ============================================================
# COST
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
        * 1000
    )


START_MS = to_ms(START_DATE)
END_MS = to_ms(END_DATE)


# ============================================================
# HTTP
# ============================================================

session = requests.Session()

session.headers.update(
    {
        "User-Agent":
            "crypto-research-spot-futures-leadlag/1.0"
    }
)


def spot_get(params):

    url = (
        SPOT_BASE_URL
        +
        SPOT_ENDPOINT
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
                    f"Rate limit Spot. "
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
                f"Erro Spot "
                f"{attempt}/{MAX_RETRIES}: "
                f"{exc}"
            )

            time.sleep(wait)

    raise RuntimeError(
        f"Falha Spot Binance: {last_error}"
    )


# ============================================================
# SPOT CACHE
# ============================================================

def spot_cache_path(symbol):

    return (
        DATA_DIR
        /
        (
            f"{symbol}_spot_5m_"
            f"2024-01-01_2026-08-01.csv"
        )
    )


def download_spot(symbol):

    print(
        f"Baixando Spot {symbol}..."
    )

    rows = []
    cursor = START_MS

    while cursor < END_MS:

        params = {
            "symbol": symbol,
            "interval": INTERVAL,
            "startTime": cursor,
            "endTime": END_MS - 1,
            "limit": SPOT_LIMIT,
        }

        batch = spot_get(
            params
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
                f"{symbol}: cursor Spot "
                f"não avançou."
            )

        cursor = next_cursor

        print(
            f"\r{symbol} Spot: "
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
            f"Nenhum dado Spot para {symbol}."
        )

    columns = [
        "open_time_ms",
        "spot_open",
        "spot_high",
        "spot_low",
        "spot_close",
        "spot_volume",
        "close_time_ms",
        "spot_quote_volume",
        "spot_trades",
        "spot_taker_buy_base",
        "spot_taker_buy_quote",
        "ignore",
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

    numeric_columns = [
        "spot_open",
        "spot_high",
        "spot_low",
        "spot_close",
        "spot_volume",
        "spot_quote_volume",
        "spot_taker_buy_base",
        "spot_taker_buy_quote",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = (
        df[
            [
                "open_time",
                "spot_open",
                "spot_high",
                "spot_low",
                "spot_close",
                "spot_volume",
                "spot_quote_volume",
                "spot_trades",
                "spot_taker_buy_base",
                "spot_taker_buy_quote",
            ]
        ]
        .dropna(
            subset=[
                "open_time",
                "spot_close",
            ]
        )
        .drop_duplicates(
            subset=["open_time"]
        )
        .sort_values("open_time")
        .reset_index(drop=True)
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


def load_or_download_spot(symbol):

    path = spot_cache_path(
        symbol
    )

    if path.exists():

        print(
            f"{symbol}: usando cache Spot"
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
            "spot_open",
            "spot_high",
            "spot_low",
            "spot_close",
            "spot_volume",
            "spot_quote_volume",
            "spot_taker_buy_base",
            "spot_taker_buy_quote",
        ]:

            if column in df.columns:

                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

        return (
            df
            .drop_duplicates(
                subset=["open_time"]
            )
            .sort_values("open_time")
            .reset_index(drop=True)
        )

    df = download_spot(
        symbol
    )

    df.to_csv(
        path,
        index=False,
    )

    print(
        f"{symbol}: cache Spot salvo."
    )

    return df


# ============================================================
# FUTURES PRICE
# ============================================================

def load_futures(symbol):

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
                f"Arquivo Futures ausente: "
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
                "close",
            ]
        )
        .drop_duplicates(
            subset=["open_time"]
        )
        .sort_values("open_time")
        .reset_index(drop=True)
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

    values = pd.Series(
        values
    ).dropna()

    if values.empty:
        return np.nan

    gains = values[
        values > 0
    ].sum()

    losses = values[
        values < 0
    ].abs().sum()

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

    values = pd.Series(
        values
    ).dropna()

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
            (values > 0).mean(),

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
        f"PROCESSANDO SPOT/FUTURES — "
        f"{symbol}"
    )

    print("=" * 100)

    futures = load_futures(
        symbol
    )

    spot = load_or_download_spot(
        symbol
    )

    print(
        f"{symbol}: futures="
        f"{len(futures)} "
        f"spot={len(spot)}"
    )

    df = (
        futures
        .merge(
            spot,
            on="open_time",
            how="inner",
            validate="one_to_one",
        )
        .sort_values("open_time")
        .reset_index(drop=True)
    )

    coverage = (
        len(df)
        /
        len(futures)
    )

    print(
        f"{symbol}: aligned="
        f"{len(df)} "
        f"({coverage:.2%})"
    )

    if coverage < 0.95:

        raise RuntimeError(
            f"{symbol}: cobertura Spot "
            f"insuficiente "
            f"{coverage:.2%}"
        )


    # ========================================================
    # 5-MINUTE RETURNS
    # ========================================================

    df["futures_ret_5m"] = (
        df["close"]
        /
        df["close"].shift(1)
        -
        1
    )

    df["spot_ret_5m"] = (
        df["spot_close"]
        /
        df["spot_close"].shift(1)
        -
        1
    )


    # ========================================================
    # LEAD GAP
    #
    # Positive:
    # spot moved more positively / less negatively.
    #
    # Negative:
    # futures moved more positively / spot more negatively.
    # ========================================================

    df["lead_gap"] = (
        df["spot_ret_5m"]
        -
        df["futures_ret_5m"]
    )


    # ========================================================
    # HISTORICAL THRESHOLDS
    # ========================================================

    df["gap_q10"] = (
        df["lead_gap"]
        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )
        .quantile(
            LOW_Q
        )
        .shift(1)
    )

    df["gap_q90"] = (
        df["lead_gap"]
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
        df["gap_q10"].notna()
        &
        df["gap_q90"].notna()
    )


    # ========================================================
    # FOUR STRUCTURAL STATES
    # ========================================================

    spot_leads_up = (
        valid
        &
        (
            df["spot_ret_5m"]
            >
            0
        )
        &
        (
            df["lead_gap"]
            >=
            df["gap_q90"]
        )
    )


    spot_leads_down = (
        valid
        &
        (
            df["spot_ret_5m"]
            <
            0
        )
        &
        (
            df["lead_gap"]
            <=
            df["gap_q10"]
        )
    )


    futures_leads_up = (
        valid
        &
        (
            df["futures_ret_5m"]
            >
            0
        )
        &
        (
            df["lead_gap"]
            <=
            df["gap_q10"]
        )
    )


    futures_leads_down = (
        valid
        &
        (
            df["futures_ret_5m"]
            <
            0
        )
        &
        (
            df["lead_gap"]
            >=
            df["gap_q90"]
        )
    )


    # ========================================================
    # FUTURE RETURNS ON FUTURES
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

        "SPOT_LEADS_UP":
            spot_leads_up,

        "SPOT_LEADS_DOWN":
            spot_leads_down,

        "FUTURES_LEADS_UP":
            futures_leads_up,

        "FUTURES_LEADS_DOWN":
            futures_leads_down,
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
    .reset_index(drop=True)
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

        mean_spot_ret=(
            "spot_ret_5m",
            "mean",
        ),

        mean_futures_ret=(
            "futures_ret_5m",
            "mean",
        ),

        mean_lead_gap=(
            "lead_gap",
            "mean",
        ),

        median_lead_gap=(
            "lead_gap",
            "median",
        ),
    )
)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    # Spot leads upward:
    # primary = Futures catch-up LONG
    "SPOT_UP_CATCHUP_LONG":
        (
            "SPOT_LEADS_UP",
            "LONG",
        ),

    "SPOT_UP_REVERSE_SHORT":
        (
            "SPOT_LEADS_UP",
            "SHORT",
        ),


    # Spot leads downward:
    # primary = Futures catch-up SHORT
    "SPOT_DOWN_CATCHUP_SHORT":
        (
            "SPOT_LEADS_DOWN",
            "SHORT",
        ),

    "SPOT_DOWN_REVERSE_LONG":
        (
            "SPOT_LEADS_DOWN",
            "LONG",
        ),


    # Futures leads upward:
    # primary = Futures excess mean reversion SHORT
    "FUT_UP_REVERT_SHORT":
        (
            "FUTURES_LEADS_UP",
            "SHORT",
        ),

    "FUT_UP_CONTINUE_LONG":
        (
            "FUTURES_LEADS_UP",
            "LONG",
        ),


    # Futures leads downward:
    # primary = Futures excess mean reversion LONG
    "FUT_DOWN_REVERT_LONG":
        (
            "FUTURES_LEADS_DOWN",
            "LONG",
        ),

    "FUT_DOWN_CONTINUE_SHORT":
        (
            "FUTURES_LEADS_DOWN",
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


        # GLOBAL

        for cost in COSTS:

            global_rows.append({

                "hypothesis":
                    hypothesis,

                "minutes":
                    minutes,

                "cost":
                    cost,

                **summarize(
                    gross - cost
                ),
            })


        # YEAR

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
                        returns - cost
                    ),
                })


        # ASSET

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
                        returns - cost
                    ),
                })


        # MONTH

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

        if g.empty:
            continue

        row = g.iloc[0]

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
                    by_year["cost"],
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
                    by_asset["cost"],
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

def pct(df):

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
        "mean_spot_ret",
        "mean_futures_ret",
        "mean_lead_gap",
        "median_lead_gap",
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
# OUTPUT
# ============================================================

print()
print("=" * 220)

print(
    "EXPERIMENTO 43 — "
    "BRANCH 19 SPOT/FUTURES LEAD-LAG"
)

print("=" * 220)


print()
print("EVENT COUNTS")
print()

print(
    counts.to_string(
        index=False
    )
)


print()
print("=" * 220)
print("EVENT ANATOMY")
print("=" * 220)
print()

print(
    pct(anatomy)
    .to_string(
        index=False
    )
)


base_global = (
    pct(global_results)[
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
print("GLOBAL @ 0.06%")
print("=" * 220)
print()

print(
    base_global.to_string(
        index=False
    )
)


print()
print("=" * 220)
print("STABILITY @ 0.06%")
print("=" * 220)
print()

print(
    pct(stability)
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
print("DISCOVERY GATE")
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
    "spot_futures_leadlag_events.csv",
    index=False,
)

counts.to_csv(
    RESULTS_DIR
    /
    "spot_futures_leadlag_counts.csv",
    index=False,
)

anatomy.to_csv(
    RESULTS_DIR
    /
    "spot_futures_leadlag_anatomy.csv",
    index=False,
)

global_results.to_csv(
    RESULTS_DIR
    /
    "spot_futures_leadlag_global.csv",
    index=False,
)

by_year.to_csv(
    RESULTS_DIR
    /
    "spot_futures_leadlag_by_year.csv",
    index=False,
)

by_asset.to_csv(
    RESULTS_DIR
    /
    "spot_futures_leadlag_by_asset.csv",
    index=False,
)

monthly.to_csv(
    RESULTS_DIR
    /
    "spot_futures_leadlag_monthly.csv",
    index=False,
)

stability.to_csv(
    RESULTS_DIR
    /
    "spot_futures_leadlag_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
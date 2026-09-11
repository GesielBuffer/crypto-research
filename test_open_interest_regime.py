from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import zipfile

import numpy as np
import pandas as pd
import requests


# ============================================================
# EXPERIMENTO 45
# BRANCH 16 — PRICE × OPEN INTEREST REGIME
#
# DEVELOPMENT:
# Jan/2024 -> Jul/2026
#
# Agosto/2026:
# NÃO usar.
#
# Setembro/2026:
# INTOCADO.
#
# OI source:
# Binance Public Data
# futures/um/daily/metrics
#
# Signal:
# informação disponível até t.
#
# Entry:
# Futures open t+1.
# ============================================================


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]


START_DATE = "2024-01-01"
END_DATE_EXCLUSIVE = "2026-08-01"


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

METRICS_BASE_URL = (
    "https://data.binance.vision/"
    "data/futures/um/daily/metrics"
)

DOWNLOAD_WORKERS = 8
REQUEST_TIMEOUT = 30

MIN_OI_COVERAGE = 0.95


# ============================================================
# SIGNAL
# ============================================================

OI_CHANGE_BARS = 6       # 30m
PRICE_CHANGE_BARS = 6    # 30m

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

OI_LOW_Q = 0.10
OI_HIGH_Q = 0.90


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

    values = np.sort(values)

    cut = int(
        len(values)
        *
        trim
    )

    if (
        cut == 0
        or
        len(values) <= 2 * cut
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

    lo = np.quantile(
        values,
        limit,
    )

    hi = np.quantile(
        values,
        1 - limit,
    )

    return (
        np.clip(
            values,
            lo,
            hi,
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
            (values > 0).mean(),

        "profit_factor":
            profit_factor(values),

        "q10":
            values.quantile(0.10),

        "q90":
            values.quantile(0.90),
    }


# ============================================================
# FUTURES PRICE DATA
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
# OPEN INTEREST CACHE
# ============================================================

def oi_cache_path(symbol):

    return (
        DATA_DIR
        /
        (
            f"{symbol}_metrics_5m_"
            f"2024-01-01_2026-08-01.csv"
        )
    )


# ============================================================
# ONE DAILY METRICS FILE
# ============================================================

def fetch_metrics_day(
    symbol,
    day,
):

    date_text = (
        day.strftime("%Y-%m-%d")
    )

    filename = (
        f"{symbol}-metrics-"
        f"{date_text}.zip"
    )

    url = (
        f"{METRICS_BASE_URL}/"
        f"{symbol}/"
        f"{filename}"
    )

    try:

        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()

        with zipfile.ZipFile(
            BytesIO(response.content)
        ) as archive:

            csv_names = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".csv")
            ]

            if not csv_names:
                return None

            with archive.open(
                csv_names[0]
            ) as file:

                df = pd.read_csv(
                    file
                )

        df.columns = [
            str(c)
            .strip()
            .lower()
            for c in df.columns
        ]

        if "create_time" not in df.columns:

            raise RuntimeError(
                f"{filename}: "
                f"create_time ausente. "
                f"Colunas={list(df.columns)}"
            )

        if "sum_open_interest" not in df.columns:

            raise RuntimeError(
                f"{filename}: "
                f"sum_open_interest ausente. "
                f"Colunas={list(df.columns)}"
            )

        keep = [
            "create_time",
            "sum_open_interest",
        ]

        if (
            "sum_open_interest_value"
            in df.columns
        ):

            keep.append(
                "sum_open_interest_value"
            )

        df = df[
            keep
        ].copy()

        return df

    except Exception as exc:

        return (
            "ERROR",
            date_text,
            str(exc),
        )


# ============================================================
# DOWNLOAD ALL HISTORICAL OI
# ============================================================

def download_metrics(symbol):

    start = pd.Timestamp(
        START_DATE
    )

    end = pd.Timestamp(
        END_DATE_EXCLUSIVE
    )

    days = pd.date_range(
        start,
        end - pd.Timedelta(days=1),
        freq="D",
    )

    frames = []
    missing = []
    errors = []

    print(
        f"{symbol}: baixando "
        f"{len(days)} arquivos diários "
        f"de metrics..."
    )

    completed = 0

    with ThreadPoolExecutor(
        max_workers=DOWNLOAD_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                fetch_metrics_day,
                symbol,
                day,
            ):
            day
            for day in days
        }

        for future in as_completed(
            futures
        ):

            day = futures[future]

            result = future.result()

            completed += 1

            if result is None:

                missing.append(
                    day.strftime(
                        "%Y-%m-%d"
                    )
                )

            elif (
                isinstance(result, tuple)
                and
                result
                and
                result[0] == "ERROR"
            ):

                errors.append(
                    result
                )

            else:

                frames.append(
                    result
                )

            if (
                completed % 100 == 0
                or
                completed == len(days)
            ):

                print(
                    f"\r{symbol}: "
                    f"{completed}/{len(days)} dias",
                    end="",
                    flush=True,
                )

    print()

    if errors:

        print(
            f"{symbol}: "
            f"{len(errors)} erros de download."
        )

        for error in errors[:10]:

            print(
                "  ",
                error
            )

    if missing:

        print(
            f"{symbol}: "
            f"{len(missing)} dias 404/ausentes."
        )

        print(
            "Primeiros ausentes:",
            missing[:10],
        )

    if not frames:

        raise RuntimeError(
            f"{symbol}: nenhum arquivo "
            f"metrics foi obtido."
        )

    df = pd.concat(
        frames,
        ignore_index=True,
    )

    df["open_time"] = pd.to_datetime(
        df["create_time"],
        format="mixed",
        utc=True,
        errors="coerce",
    )

    df["sum_open_interest"] = pd.to_numeric(
        df["sum_open_interest"],
        errors="coerce",
    )

    if (
        "sum_open_interest_value"
        in df.columns
    ):

        df[
            "sum_open_interest_value"
        ] = pd.to_numeric(
            df[
                "sum_open_interest_value"
            ],
            errors="coerce",
        )

    df = (
        df
        .dropna(
            subset=[
                "open_time",
                "sum_open_interest",
            ]
        )
        .drop_duplicates(
            subset=["open_time"],
            keep="last",
        )
        .sort_values("open_time")
        .reset_index(drop=True)
    )

    keep = [
        "open_time",
        "sum_open_interest",
    ]

    if (
        "sum_open_interest_value"
        in df.columns
    ):

        keep.append(
            "sum_open_interest_value"
        )

    return df[
        keep
    ].copy()


def load_or_download_metrics(
    symbol,
):

    path = oi_cache_path(
        symbol
    )

    if path.exists():

        print(
            f"{symbol}: usando cache OI"
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

        df["sum_open_interest"] = (
            pd.to_numeric(
                df["sum_open_interest"],
                errors="coerce",
            )
        )

        return (
            df
            .dropna(
                subset=[
                    "open_time",
                    "sum_open_interest",
                ]
            )
            .drop_duplicates(
                subset=["open_time"]
            )
            .sort_values("open_time")
            .reset_index(drop=True)
        )

    df = download_metrics(
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
# BUILD EVENTS
# ============================================================

event_frames = []


for symbol in SYMBOLS:

    print()
    print("=" * 100)

    print(
        f"PROCESSANDO OPEN INTEREST — "
        f"{symbol}"
    )

    print("=" * 100)

    price = load_futures(
        symbol
    )

    metrics = load_or_download_metrics(
        symbol
    )

    # --------------------------------------------------------
    # LEFT JOIN PURPOSEFULLY.
    #
    # We preserve the full exact Futures 5m grid.
    # Missing OI is NOT forward-filled.
    # --------------------------------------------------------

    df = (
        price
        .merge(
            metrics,
            on="open_time",
            how="left",
            validate="one_to_one",
        )
        .sort_values("open_time")
        .reset_index(drop=True)
    )

    coverage = (
        df[
            "sum_open_interest"
        ]
        .notna()
        .mean()
    )

    print(
        f"{symbol}: price={len(price)} "
        f"metrics={len(metrics)} "
        f"OI coverage={coverage:.2%}"
    )

    if coverage < MIN_OI_COVERAGE:

        raise RuntimeError(
            f"{symbol}: cobertura OI "
            f"insuficiente: "
            f"{coverage:.2%}"
        )


    # ========================================================
    # 30M PRICE RETURN
    # ========================================================

    df["price_ret_30m"] = (
        df["close"]
        /
        df["close"].shift(
            PRICE_CHANGE_BARS
        )
        -
        1
    )


    # ========================================================
    # 30M OI CHANGE
    #
    # Full Futures grid means shift(6)
    # remains exactly 30 minutes.
    #
    # Missing OI naturally produces NaN.
    # ========================================================

    df["oi_change_30m"] = (
        df["sum_open_interest"]
        /
        df[
            "sum_open_interest"
        ].shift(
            OI_CHANGE_BARS
        )
        -
        1
    )


    # ========================================================
    # HISTORICAL OI CHANGE THRESHOLDS
    #
    # Current observation excluded.
    # ========================================================

    df["oi_q10"] = (
        df["oi_change_30m"]
        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )
        .quantile(
            OI_LOW_Q
        )
        .shift(1)
    )


    df["oi_q90"] = (
        df["oi_change_30m"]
        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )
        .quantile(
            OI_HIGH_Q
        )
        .shift(1)
    )


    valid = (
        df["price_ret_30m"].notna()
        &
        df["oi_change_30m"].notna()
        &
        df["oi_q10"].notna()
        &
        df["oi_q90"].notna()
    )


    # ========================================================
    # FOUR ECONOMIC STATES
    # ========================================================

    up_oi_surge = (
        valid
        &
        (
            df["price_ret_30m"] > 0
        )
        &
        (
            df["oi_change_30m"]
            >=
            df["oi_q90"]
        )
    )


    down_oi_surge = (
        valid
        &
        (
            df["price_ret_30m"] < 0
        )
        &
        (
            df["oi_change_30m"]
            >=
            df["oi_q90"]
        )
    )


    up_oi_flush = (
        valid
        &
        (
            df["price_ret_30m"] > 0
        )
        &
        (
            df["oi_change_30m"]
            <=
            df["oi_q10"]
        )
    )


    down_oi_flush = (
        valid
        &
        (
            df["price_ret_30m"] < 0
        )
        &
        (
            df["oi_change_30m"]
            <=
            df["oi_q10"]
        )
    )


    # ========================================================
    # FUTURE RETURNS
    #
    # Signal at t.
    # Entry Futures open t+1.
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

        "UP_OI_SURGE":
            up_oi_surge,

        "DOWN_OI_SURGE":
            down_oi_surge,

        "UP_OI_FLUSH":
            up_oi_flush,

        "DOWN_OI_FLUSH":
            down_oi_flush,
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

        mean_price_ret_30m=(
            "price_ret_30m",
            "mean",
        ),

        median_price_ret_30m=(
            "price_ret_30m",
            "median",
        ),

        mean_oi_change_30m=(
            "oi_change_30m",
            "mean",
        ),

        median_oi_change_30m=(
            "oi_change_30m",
            "median",
        ),
    )
)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    # Price up + OI increasing strongly
    "UP_SURGE_CONTINUE_LONG":
        (
            "UP_OI_SURGE",
            "LONG",
        ),

    "UP_SURGE_REVERSE_SHORT":
        (
            "UP_OI_SURGE",
            "SHORT",
        ),


    # Price down + OI increasing strongly
    "DOWN_SURGE_CONTINUE_SHORT":
        (
            "DOWN_OI_SURGE",
            "SHORT",
        ),

    "DOWN_SURGE_REVERSE_LONG":
        (
            "DOWN_OI_SURGE",
            "LONG",
        ),


    # Price up + OI collapsing
    "UP_FLUSH_CONTINUE_LONG":
        (
            "UP_OI_FLUSH",
            "LONG",
        ),

    "UP_FLUSH_REVERSE_SHORT":
        (
            "UP_OI_FLUSH",
            "SHORT",
        ),


    # Price down + OI collapsing
    "DOWN_FLUSH_CONTINUE_SHORT":
        (
            "DOWN_OI_FLUSH",
            "SHORT",
        ),

    "DOWN_FLUSH_REVERSE_LONG":
        (
            "DOWN_OI_FLUSH",
            "LONG",
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
                    )
                    .sum()
                ),

            "total_years":
                len(years),

            "worst_year_pf":
                years[
                    "profit_factor"
                ]
                .min(),

            "median_year_pf":
                years[
                    "profit_factor"
                ]
                .median(),


            "assets_pf_gt_1":
                int(
                    (
                        assets[
                            "profit_factor"
                        ]
                        >
                        1
                    )
                    .sum()
                ),

            "total_assets":
                len(assets),

            "worst_asset_pf":
                assets[
                    "profit_factor"
                ]
                .min(),

            "median_asset_pf":
                assets[
                    "profit_factor"
                ]
                .median(),


            "months_pf_gt_1":
                int(
                    (
                        months[
                            "profit_factor"
                        ]
                        >
                        1
                    )
                    .sum()
                ),

            "total_months":
                len(months),

            "median_month_pf":
                months[
                    "profit_factor"
                ]
                .median(),
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

    output = df.copy()

    columns = [
        "cost",
        "mean_return",
        "median_return",
        "trimmed_mean_5",
        "winsorized_mean_5",
        "win_rate",
        "q10",
        "q90",
        "mean_price_ret_30m",
        "median_price_ret_30m",
        "mean_oi_change_30m",
        "median_oi_change_30m",
    ]

    for column in columns:

        if column in output.columns:

            output[column] *= 100

    return output


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
    "EXPERIMENTO 45 — "
    "BRANCH 16 OPEN INTEREST REGIME"
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
    "open_interest_regime_events.csv",
    index=False,
)

counts.to_csv(
    RESULTS_DIR
    /
    "open_interest_regime_counts.csv",
    index=False,
)

anatomy.to_csv(
    RESULTS_DIR
    /
    "open_interest_regime_anatomy.csv",
    index=False,
)

global_results.to_csv(
    RESULTS_DIR
    /
    "open_interest_regime_global.csv",
    index=False,
)

by_year.to_csv(
    RESULTS_DIR
    /
    "open_interest_regime_by_year.csv",
    index=False,
)

by_asset.to_csv(
    RESULTS_DIR
    /
    "open_interest_regime_by_asset.csv",
    index=False,
)

monthly.to_csv(
    RESULTS_DIR
    /
    "open_interest_regime_monthly.csv",
    index=False,
)

stability.to_csv(
    RESULTS_DIR
    /
    "open_interest_regime_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
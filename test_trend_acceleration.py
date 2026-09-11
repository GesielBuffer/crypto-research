from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# EXPERIMENTO 39
# BRANCH 15 — TREND ACCELERATION / DECELERATION
#
# DEVELOPMENT:
# 2024-01 -> 2026-07
#
# Agosto:
# já observado -> fora
#
# Setembro:
# INTOCADO
#
# Signal:
# conhecido no close t
#
# Entry:
# open t+1
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
# MONTHS
# ============================================================

MONTH_STARTS = pd.date_range(
    "2024-01-01",
    "2026-07-01",
    freq="MS",
)

PERIODS = []

for start in MONTH_STARTS:

    end = start + pd.offsets.MonthBegin(1)

    PERIODS.append(
        (
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )
    )


# ============================================================
# HISTORICAL CONTEXT
# ============================================================

BARS_PER_DAY = 288

LOOKBACK = 7 * BARS_PER_DAY
MIN_PERIODS = 3 * BARS_PER_DAY

ACCEL_LOW_Q = 0.10
ACCEL_HIGH_Q = 0.90


# ============================================================
# HORIZONS
#
# Entry open t+1
# ============================================================

HORIZONS = [
    3,      # 15m
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
# LOAD
# ============================================================

def load_symbol(symbol):

    frames = []

    for start_date, end_date in PERIODS:

        path = (
            DATA_DIR
            /
            f"{symbol}_5m_{start_date}_{end_date}.csv"
        )

        if not path.exists():

            raise FileNotFoundError(
                f"Arquivo não encontrado: {path}"
            )

        df = pd.read_csv(path)

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
            "volume",
        ]:

            if column in df.columns:

                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

        frames.append(df)

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

    values = pd.Series(values).dropna()

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


def trimmed_mean(values, trim=0.05):

    values = np.asarray(
        pd.Series(values).dropna(),
        dtype=float,
    )

    if len(values) == 0:
        return np.nan

    values = np.sort(values)

    cut = int(
        len(values) * trim
    )

    if (
        cut == 0
        or
        len(values) <= 2 * cut
    ):
        return values.mean()

    return values[
        cut:-cut
    ].mean()


def winsorized_mean(values, limit=0.05):

    values = np.asarray(
        pd.Series(values).dropna(),
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

    return np.clip(
        values,
        low,
        high,
    ).mean()


def summarize(values):

    values = pd.Series(values).dropna()

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
        f"PROCESSANDO TREND ACCELERATION — {symbol}"
    )

    print("=" * 100)

    df = load_symbol(symbol)

    print(
        f"{symbol}: candles = {len(df)}"
    )


    # ========================================================
    # MULTI-HORIZON PAST RETURNS
    #
    # Tudo conhecido em t close.
    # ========================================================

    df["ret_15m"] = (
        df["close"]
        /
        df["close"].shift(3)
        -
        1
    )

    df["ret_60m"] = (
        df["close"]
        /
        df["close"].shift(12)
        -
        1
    )


    # ========================================================
    # RETURN VELOCITY
    #
    # Per 5m candle equivalent.
    # ========================================================

    df["pace_15m"] = (
        df["ret_15m"]
        /
        3.0
    )

    df["pace_60m"] = (
        df["ret_60m"]
        /
        12.0
    )


    # ========================================================
    # ACCELERATION
    # ========================================================

    df["acceleration"] = (
        df["pace_15m"]
        -
        df["pace_60m"]
    )


    # ========================================================
    # HISTORICAL ACCELERATION DISTRIBUTION
    #
    # Past only.
    # ========================================================

    df["accel_q10"] = (
        df["acceleration"]
        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )
        .quantile(
            ACCEL_LOW_Q
        )
        .shift(1)
    )

    df["accel_q90"] = (
        df["acceleration"]
        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )
        .quantile(
            ACCEL_HIGH_Q
        )
        .shift(1)
    )


    valid = (
        df["accel_q10"].notna()
        &
        df["accel_q90"].notna()
    )


    # ========================================================
    # STATES
    # ========================================================

    up_accel = (
        valid
        &
        (df["ret_60m"] > 0)
        &
        (
            df["acceleration"]
            >=
            df["accel_q90"]
        )
    )


    up_decel = (
        valid
        &
        (df["ret_60m"] > 0)
        &
        (
            df["acceleration"]
            <=
            df["accel_q10"]
        )
    )


    down_accel = (
        valid
        &
        (df["ret_60m"] < 0)
        &
        (
            df["acceleration"]
            <=
            df["accel_q10"]
        )
    )


    down_decel = (
        valid
        &
        (df["ret_60m"] < 0)
        &
        (
            df["acceleration"]
            >=
            df["accel_q90"]
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
    #
    # Counts one event per acceleration episode.
    # ========================================================

    masks = {

        "UP_ACCEL":
            up_accel,

        "UP_DECEL":
            up_decel,

        "DOWN_ACCEL":
            down_accel,

        "DOWN_DECEL":
            down_decel,
    }


    for event_name, raw_mask in masks.items():

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

        temp["event"] = event_name

        event_frames.append(temp)


# ============================================================
# CONCAT EVENTS
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

        mean_ret_15m=(
            "ret_15m",
            "mean",
        ),

        mean_ret_60m=(
            "ret_60m",
            "mean",
        ),

        mean_pace_15m=(
            "pace_15m",
            "mean",
        ),

        mean_pace_60m=(
            "pace_60m",
            "mean",
        ),

        mean_acceleration=(
            "acceleration",
            "mean",
        ),

        median_acceleration=(
            "acceleration",
            "median",
        ),
    )
)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    # --------------------------------------------------------
    # UP ACCELERATION
    # --------------------------------------------------------

    "UP_ACCEL_CONTINUE_LONG":
        (
            "UP_ACCEL",
            "LONG",
        ),

    "UP_ACCEL_REVERSE_SHORT":
        (
            "UP_ACCEL",
            "SHORT",
        ),


    # --------------------------------------------------------
    # UP DECELERATION
    # --------------------------------------------------------

    "UP_DECEL_REVERSE_SHORT":
        (
            "UP_DECEL",
            "SHORT",
        ),

    "UP_DECEL_CONTINUE_LONG":
        (
            "UP_DECEL",
            "LONG",
        ),


    # --------------------------------------------------------
    # DOWN ACCELERATION
    # --------------------------------------------------------

    "DOWN_ACCEL_CONTINUE_SHORT":
        (
            "DOWN_ACCEL",
            "SHORT",
        ),

    "DOWN_ACCEL_REVERSE_LONG":
        (
            "DOWN_ACCEL",
            "LONG",
        ),


    # --------------------------------------------------------
    # DOWN DECELERATION
    # --------------------------------------------------------

    "DOWN_DECEL_REVERSE_LONG":
        (
            "DOWN_DECEL",
            "LONG",
        ),

    "DOWN_DECEL_CONTINUE_SHORT":
        (
            "DOWN_DECEL",
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
                    gross - cost
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
                        returns - cost
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
                        returns - cost
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
                    return_column
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


        global_match = global_results[
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


        if global_match.empty:
            continue


        row = global_match.iloc[0]


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
                        assets["profit_factor"]
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
                        months["profit_factor"]
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
        "mean_ret_15m",
        "mean_ret_60m",
        "mean_pace_15m",
        "mean_pace_60m",
        "mean_acceleration",
        "median_acceleration",
    ]

    for column in columns:

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
    "EXPERIMENTO 39 — "
    "BRANCH 15 TREND ACCELERATION"
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
    .to_string(index=False)
)


# ============================================================
# GLOBAL BASE COST
# ============================================================

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
    base_global
    .to_string(index=False)
)


# ============================================================
# STABILITY
# ============================================================

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
    .to_string(index=False)
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
print("DISCOVERY GATE")
print("=" * 220)
print()


if passed.empty:

    print(
        "Nenhuma hipótese passou o gate básico."
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
        .to_string(index=False)
    )


# ============================================================
# SAVE
# ============================================================

events.to_csv(
    RESULTS_DIR
    /
    "trend_acceleration_events.csv",
    index=False,
)

counts.to_csv(
    RESULTS_DIR
    /
    "trend_acceleration_counts.csv",
    index=False,
)

anatomy.to_csv(
    RESULTS_DIR
    /
    "trend_acceleration_anatomy.csv",
    index=False,
)

global_results.to_csv(
    RESULTS_DIR
    /
    "trend_acceleration_global.csv",
    index=False,
)

by_year.to_csv(
    RESULTS_DIR
    /
    "trend_acceleration_by_year.csv",
    index=False,
)

by_asset.to_csv(
    RESULTS_DIR
    /
    "trend_acceleration_by_asset.csv",
    index=False,
)

monthly.to_csv(
    RESULTS_DIR
    /
    "trend_acceleration_monthly.csv",
    index=False,
)

stability.to_csv(
    RESULTS_DIR
    /
    "trend_acceleration_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
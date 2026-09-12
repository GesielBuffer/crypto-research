from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# EXPERIMENTO 44
# BRANCH 20 — SPOT / FUTURES TAKER FLOW DIVERGENCE
#
# DEVELOPMENT:
# Jan/2024 -> Jul/2026
#
# Agosto/2026:
# não usar
#
# Setembro/2026:
# intocado
#
# Signal conhecido no close t.
# Entrada Futures no open t+1.
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
# DEVELOPMENT MONTHS
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
# CONTEXT
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
# LOAD SPOT
# ============================================================

def load_spot(symbol):

    path = (
        DATA_DIR
        /
        (
            f"{symbol}_spot_5m_"
            f"2024-01-01_2026-08-01.csv"
        )
    )

    if not path.exists():

        raise FileNotFoundError(
            f"Cache Spot ausente: {path}\n"
            f"Execute primeiro o Exp 43."
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

    numeric_columns = [
        "spot_open",
        "spot_close",
        "spot_quote_volume",
        "spot_taker_buy_quote",
    ]

    for column in numeric_columns:

        if column not in df.columns:

            raise RuntimeError(
                f"{symbol}: coluna Spot ausente: "
                f"{column}"
            )

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    return (
        df
        .dropna(
            subset=[
                "open_time",
                "spot_close",
                "spot_quote_volume",
                "spot_taker_buy_quote",
            ]
        )
        .drop_duplicates(
            subset=["open_time"]
        )
        .sort_values("open_time")
        .reset_index(drop=True)
    )


# ============================================================
# LOAD FUTURES
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
            "close",
        ]:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )


        # ====================================================
        # Prefer quote-based flow.
        # ====================================================

        quote_candidates = [
            "quote_volume",
            "quote_asset_volume",
        ]

        taker_quote_candidates = [
            "taker_buy_quote",
            "taker_buy_quote_asset_volume",
        ]

        quote_col = next(
            (
                c
                for c in quote_candidates
                if c in df.columns
            ),
            None,
        )

        taker_quote_col = next(
            (
                c
                for c in taker_quote_candidates
                if c in df.columns
            ),
            None,
        )


        # ====================================================
        # Fallback base volume.
        # ====================================================

        if (
            quote_col is None
            or
            taker_quote_col is None
        ):

            if (
                "volume" not in df.columns
                or
                "taker_buy_base" not in df.columns
            ):

                raise RuntimeError(
                    f"{symbol}: dados de taker flow "
                    f"Futures ausentes."
                )

            df["flow_total"] = pd.to_numeric(
                df["volume"],
                errors="coerce",
            )

            df["flow_buy"] = pd.to_numeric(
                df["taker_buy_base"],
                errors="coerce",
            )

        else:

            df["flow_total"] = pd.to_numeric(
                df[quote_col],
                errors="coerce",
            )

            df["flow_buy"] = pd.to_numeric(
                df[taker_quote_col],
                errors="coerce",
            )


        frames.append(
            df[
                [
                    "open_time",
                    "open",
                    "close",
                    "flow_total",
                    "flow_buy",
                ]
            ]
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
                "flow_total",
                "flow_buy",
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
# BUILD EVENTS
# ============================================================

event_frames = []


for symbol in SYMBOLS:

    print()
    print("=" * 100)

    print(
        f"PROCESSANDO FLOW DIVERGENCE — "
        f"{symbol}"
    )

    print("=" * 100)


    futures = load_futures(
        symbol
    )

    spot = load_spot(
        symbol
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
        f"{symbol}: futures={len(futures)} "
        f"spot={len(spot)} "
        f"aligned={len(df)} "
        f"({coverage:.2%})"
    )


    if coverage < 0.95:

        raise RuntimeError(
            f"{symbol}: cobertura insuficiente."
        )


    # ========================================================
    # SPOT BUY SHARE
    # ========================================================

    df["spot_buy_share"] = np.where(
        df["spot_quote_volume"] > 0,

        (
            df["spot_taker_buy_quote"]
            /
            df["spot_quote_volume"]
        ),

        np.nan,
    )


    # ========================================================
    # FUTURES BUY SHARE
    # ========================================================

    df["fut_buy_share"] = np.where(
        df["flow_total"] > 0,

        (
            df["flow_buy"]
            /
            df["flow_total"]
        ),

        np.nan,
    )


    # ========================================================
    # IMBALANCE
    #
    # -1 = all aggressive sells
    # +1 = all aggressive buys
    # ========================================================

    df["spot_imbalance"] = (
        2
        *
        df["spot_buy_share"]
        -
        1
    )


    df["fut_imbalance"] = (
        2
        *
        df["fut_buy_share"]
        -
        1
    )


    # ========================================================
    # FLOW GAP
    #
    # positive = Spot more buy-aggressive
    # negative = Futures more buy-aggressive
    # ========================================================

    df["flow_gap"] = (
        df["spot_imbalance"]
        -
        df["fut_imbalance"]
    )


    # ========================================================
    # HISTORICAL THRESHOLDS
    # ========================================================

    df["gap_q10"] = (
        df["flow_gap"]
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
        df["flow_gap"]
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
        &
        df["spot_imbalance"].notna()
        &
        df["fut_imbalance"].notna()
    )


    # ========================================================
    # STATES
    # ========================================================

    spot_buy_leads = (
        valid
        &
        (
            df["flow_gap"]
            >=
            df["gap_q90"]
        )
    )


    spot_sell_leads = (
        valid
        &
        (
            df["flow_gap"]
            <=
            df["gap_q10"]
        )
    )


    spot_buy_fut_sell = (
        spot_buy_leads
        &
        (
            df["spot_imbalance"] > 0
        )
        &
        (
            df["fut_imbalance"] < 0
        )
    )


    spot_sell_fut_buy = (
        spot_sell_leads
        &
        (
            df["spot_imbalance"] < 0
        )
        &
        (
            df["fut_imbalance"] > 0
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
    # ========================================================

    raw_masks = {

        "SPOT_BUY_LEADS":
            spot_buy_leads,

        "SPOT_SELL_LEADS":
            spot_sell_leads,

        "SPOT_BUY_FUT_SELL":
            spot_buy_fut_sell,

        "SPOT_SELL_FUT_BUY":
            spot_sell_fut_buy,
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

        temp["event"] = event_name

        event_frames.append(
            temp
        )


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

        mean_spot_imbalance=(
            "spot_imbalance",
            "mean",
        ),

        mean_fut_imbalance=(
            "fut_imbalance",
            "mean",
        ),

        mean_flow_gap=(
            "flow_gap",
            "mean",
        ),

        median_flow_gap=(
            "flow_gap",
            "median",
        ),
    )
)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    "SPOT_BUY_CATCHUP_LONG":
        (
            "SPOT_BUY_LEADS",
            "LONG",
        ),

    "SPOT_BUY_REVERSE_SHORT":
        (
            "SPOT_BUY_LEADS",
            "SHORT",
        ),


    "SPOT_SELL_CATCHUP_SHORT":
        (
            "SPOT_SELL_LEADS",
            "SHORT",
        ),

    "SPOT_SELL_REVERSE_LONG":
        (
            "SPOT_SELL_LEADS",
            "LONG",
        ),


    "DISAGREE_BUY_CATCHUP_LONG":
        (
            "SPOT_BUY_FUT_SELL",
            "LONG",
        ),

    "DISAGREE_BUY_REVERSE_SHORT":
        (
            "SPOT_BUY_FUT_SELL",
            "SHORT",
        ),


    "DISAGREE_SELL_CATCHUP_SHORT":
        (
            "SPOT_SELL_FUT_BUY",
            "SHORT",
        ),

    "DISAGREE_SELL_REVERSE_LONG":
        (
            "SPOT_SELL_FUT_BUY",
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
# GATE
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
        "mean_spot_imbalance",
        "mean_fut_imbalance",
        "mean_flow_gap",
        "median_flow_gap",
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
    "EXPERIMENTO 44 — "
    "BRANCH 20 SPOT/FUTURES FLOW DIVERGENCE"
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
print("GLOBAL @ 0.06%")
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
    "spot_futures_flow_divergence_events.csv",
    index=False,
)

counts.to_csv(
    RESULTS_DIR
    /
    "spot_futures_flow_divergence_counts.csv",
    index=False,
)

anatomy.to_csv(
    RESULTS_DIR
    /
    "spot_futures_flow_divergence_anatomy.csv",
    index=False,
)

global_results.to_csv(
    RESULTS_DIR
    /
    "spot_futures_flow_divergence_global.csv",
    index=False,
)

by_year.to_csv(
    RESULTS_DIR
    /
    "spot_futures_flow_divergence_by_year.csv",
    index=False,
)

by_asset.to_csv(
    RESULTS_DIR
    /
    "spot_futures_flow_divergence_by_asset.csv",
    index=False,
)

monthly.to_csv(
    RESULTS_DIR
    /
    "spot_futures_flow_divergence_monthly.csv",
    index=False,
)

stability.to_csv(
    RESULTS_DIR
    /
    "spot_futures_flow_divergence_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
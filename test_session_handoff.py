from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# EXPERIMENTO 36
# BRANCH 13 — UTC SESSION HANDOFF
#
# DEVELOPMENT:
# 2024-01 -> 2026-07
#
# Agosto/2026:
# fora
#
# Setembro/2026:
# intocado
#
# EVENTOS:
#
# 00:00 UTC
# 08:00 UTC
# 16:00 UTC
#
# Antes do anchor:
# mede retorno dos 60 minutos anteriores.
#
# Somente movimentos com magnitude >= q75 histórico
# entram como eventos.
#
# PRE_UP:
# forte alta antes do anchor
#
# PRE_DOWN:
# forte queda antes do anchor
#
# Testamos:
#
# PRE_UP:
#   continuação LONG
#   reversão SHORT
#
# PRE_DOWN:
#   continuação SHORT
#   reversão LONG
#
# Signal:
# conhecido no fechamento do candle imediatamente
# anterior ao anchor.
#
# Entry:
# open do próprio anchor.
# ============================================================


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]


ANCHOR_HOURS = [
    0,
    8,
    16,
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
            start.strftime("%Y-%m"),
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


# ============================================================
# PRE-ANCHOR WINDOW
#
# 12 x 5m = 60m
# ============================================================

PRE_BARS = 12

SHOCK_QUANTILE = 0.75


# ============================================================
# FUTURE HORIZONS
#
# Anchor entry:
# 30m / 60m / 120m
# ============================================================

HORIZONS = [
    6,
    12,
    24,
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

MIN_SAMPLES = 300

TARGET_PF = 1.08

MIN_ASSETS_PF_GT_1 = 3


# ============================================================
# LOAD SYMBOL
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
            f"{symbol}_5m_{start_date}_{end_date}.csv"
        )


        if not path.exists():

            raise FileNotFoundError(
                f"Arquivo não encontrado: {path}"
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
            "volume",
        ]:

            if column in df.columns:

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


    df["hour"] = (
        df["open_time"]
        .dt.hour
    )


    df["minute"] = (
        df["open_time"]
        .dt.minute
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
# EVENTS
# ============================================================

event_frames = []


for symbol in SYMBOLS:


    print()

    print("=" * 100)

    print(
        f"PROCESSANDO SESSION HANDOFF — {symbol}"
    )

    print("=" * 100)


    df = load_symbol(
        symbol
    )


    print(
        f"{symbol}: candles = {len(df)}"
    )


    # ========================================================
    # PRE-ANCHOR 60M RETURN
    #
    # Para linha anchor t:
    #
    # open t-12
    # close t-1
    #
    # Portanto só utiliza candles completamente concluídos
    # antes da entrada.
    # ========================================================

    df["pre_60m_return"] = (
        df["close"]
        .shift(1)
        /
        df["open"]
        .shift(PRE_BARS)
        -
        1
    )


    df["pre_60m_abs"] = (
        df["pre_60m_return"]
        .abs()
    )


    # ========================================================
    # HISTORICAL SHOCK THRESHOLD
    #
    # Também usa passado.
    # ========================================================

    df["shock_threshold"] = (
        df["pre_60m_abs"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            SHOCK_QUANTILE
        )

        .shift(1)
    )


    # ========================================================
    # FIXED UTC ANCHORS
    # ========================================================

    anchor = (

        df["hour"]
        .isin(
            ANCHOR_HOURS
        )

        &

        (
            df["minute"]
            ==
            0
        )

    )


    shock = (
        df["pre_60m_abs"]
        >=
        df["shock_threshold"]
    )


    pre_up = (

        anchor

        &

        shock

        &

        (
            df["pre_60m_return"]
            >
            0
        )

    )


    pre_down = (

        anchor

        &

        shock

        &

        (
            df["pre_60m_return"]
            <
            0
        )

    )


    # ========================================================
    # ENTRY
    #
    # Entry = open do próprio anchor.
    #
    # O sinal já existe no close do candle anterior.
    # ========================================================

    entry = df["open"]


    # ========================================================
    # FUTURE RETURNS
    # ========================================================

    for horizon in HORIZONS:


        # Entry no open do anchor.
        #
        # horizon 6:
        #
        # anchor 08:00
        # candles:
        # 08:00
        # 08:05
        # 08:10
        # 08:15
        # 08:20
        # 08:25
        #
        # exit close 08:30

        exit_price = (
            df["close"]
            .shift(
                -(horizon - 1)
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
    # SAVE EVENTS
    # ========================================================

    masks = {

        "PRE_UP":
            pre_up,

        "PRE_DOWN":
            pre_down,

    }


    for event_name, mask in masks.items():


        temp = (
            df.loc[
                mask.fillna(False)
            ]
            .copy()
        )


        temp["event"] = event_name


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
# COUNTS BY ANCHOR
# ============================================================

anchor_counts = (

    events

    .groupby(
        [
            "event",
            "hour",
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

        mean_pre_return=(
            "pre_60m_return",
            "mean",
        ),

        median_pre_return=(
            "pre_60m_return",
            "median",
        ),

        mean_pre_abs=(
            "pre_60m_abs",
            "mean",
        ),

        median_pre_abs=(
            "pre_60m_abs",
            "median",
        ),

        mean_threshold=(
            "shock_threshold",
            "mean",
        ),

    )

)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    "PRE_UP_CONTINUE_LONG":
        (
            "PRE_UP",
            "LONG",
        ),

    "PRE_UP_REVERSE_SHORT":
        (
            "PRE_UP",
            "SHORT",
        ),

    "PRE_DOWN_CONTINUE_SHORT":
        (
            "PRE_DOWN",
            "SHORT",
        ),

    "PRE_DOWN_REVERSE_LONG":
        (
            "PRE_DOWN",
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

anchor_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "event"
        ]
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
                        gross_year - cost
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
                        gross_asset - cost
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


        # ====================================================
        # ANCHOR HOUR
        #
        # Diagnostic only.
        #
        # NÃO será usado para escolher um horário isolado
        # como estratégia.
        # ====================================================

        for hour, group in subset.groupby(
            "hour"
        ):


            gross_anchor = (
                group[
                    return_column
                ]
                .dropna()
            )


            anchor_rows.append({

                "hypothesis":
                    hypothesis,

                "minutes":
                    minutes,

                "hour":
                    hour,

                **summarize(
                    gross_anchor
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


by_anchor = pd.DataFrame(
    anchor_rows
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


        anchors = by_anchor[
            (
                by_anchor["hypothesis"]
                ==
                hypothesis
            )
            &
            (
                by_anchor["minutes"]
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


            "anchors_pf_gt_1":
                int(
                    (
                        anchors["profit_factor"]
                        >
                        1
                    ).sum()
                ),

            "total_anchors":
                len(anchors),

            "worst_anchor_pf":
                anchors[
                    "profit_factor"
                ].min(),

            "median_anchor_pf":
                anchors[
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
#
# Anchor stability is included:
# require at least 2 of 3 anchor hours > PF 1.
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

    &

    (
        stability["anchors_pf_gt_1"]
        >=
        2
    )

)


# ============================================================
# DISPLAY
# ============================================================

def percent_display(df):

    result = df.copy()


    for column in [
        "cost",
        "mean_return",
        "median_return",
        "trimmed_mean_5",
        "winsorized_mean_5",
        "win_rate",
        "q10",
        "q90",
        "mean_pre_return",
        "median_pre_return",
        "mean_pre_abs",
        "median_pre_abs",
        "mean_threshold",
    ]:

        if column in result.columns:

            result[
                column
            ] *= 100


    return result


global_display = percent_display(
    global_results
)


stability_display = percent_display(
    stability
)


anatomy_display = percent_display(
    anatomy
)


anchor_display = percent_display(
    by_anchor
)


pd.set_option(
    "display.max_columns",
    None,
)


pd.set_option(
    "display.width",
    440,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 220)

print(
    "EXPERIMENTO 36 — "
    "BRANCH 13 UTC SESSION HANDOFF"
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

print("ANCHOR COUNTS")

print()

print(
    anchor_counts.to_string(
        index=False
    )
)


print()

print("=" * 220)

print("EVENT ANATOMY")

print("=" * 220)

print()

print(
    anatomy_display.to_string(
        index=False
    )
)


# ============================================================
# GLOBAL @ BASE COST
# ============================================================

base_global = (

    global_display[
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
    base_global.to_string(
        index=False
    )
)


# ============================================================
# ANCHOR DIAGNOSTIC
# ============================================================

print()

print("=" * 220)

print(
    "BY UTC ANCHOR @ 0.06%"
)

print("=" * 220)

print()

print(
    anchor_display

    .sort_values(
        [
            "hypothesis",
            "minutes",
            "hour",
        ]
    )

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
    stability_display

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
                "anchors_pf_gt_1",
                "months_pf_gt_1",
            ]
        ]

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
    "session_handoff_events.csv",
    index=False,
)


counts.to_csv(
    RESULTS_DIR
    /
    "session_handoff_counts.csv",
    index=False,
)


anchor_counts.to_csv(
    RESULTS_DIR
    /
    "session_handoff_anchor_counts.csv",
    index=False,
)


anatomy.to_csv(
    RESULTS_DIR
    /
    "session_handoff_anatomy.csv",
    index=False,
)


global_results.to_csv(
    RESULTS_DIR
    /
    "session_handoff_global.csv",
    index=False,
)


by_year.to_csv(
    RESULTS_DIR
    /
    "session_handoff_by_year.csv",
    index=False,
)


by_asset.to_csv(
    RESULTS_DIR
    /
    "session_handoff_by_asset.csv",
    index=False,
)


by_anchor.to_csv(
    RESULTS_DIR
    /
    "session_handoff_by_anchor.csv",
    index=False,
)


monthly.to_csv(
    RESULTS_DIR
    /
    "session_handoff_monthly.csv",
    index=False,
)


stability.to_csv(
    RESULTS_DIR
    /
    "session_handoff_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# EXPERIMENTO 32
# BRANCH 09 — EFFORT VS RESULT
#
# DEVELOPMENT:
# 2024-01 -> 2026-07
#
# NÃO USAR:
# agosto/2026
# setembro/2026
#
# HIPÓTESE:
#
# esforço = volume relativo
# resultado = deslocamento absoluto do preço
#
# 1) HIGH EFFORT + LOW RESULT
#    possível absorção
#
# 2) HIGH EFFORT + HIGH RESULT
#    movimento eficiente
#
# 3) LOW EFFORT + HIGH RESULT
#    movimento frágil
#
# Entrada:
# OPEN t+1
#
# Saídas:
# 5m / 15m / 30m / 60m
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
# DEVELOPMENT
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
# ROLLING CONTEXT
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
# FIXED QUANTILES
#
# Nenhum tuning fino.
# ============================================================

VOLUME_LOW_Q = 0.25

VOLUME_HIGH_Q = 0.90

RESULT_LOW_Q = 0.25

RESULT_HIGH_Q = 0.90


# ============================================================
# HORIZONS
# ============================================================

HORIZONS = [
    1,    # 5m
    3,    # 15m
    6,    # 30m
    12,   # 60m
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
# LOAD CSV
# ============================================================

def load_csv(path):

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

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )


    return df


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
            (
                f"{symbol}_5m_"
                f"{start_date}_"
                f"{end_date}.csv"
            )
        )


        if not path.exists():

            raise FileNotFoundError(
                f"Arquivo não encontrado: {path}"
            )


        df = load_csv(
            path
        )


        frames.append(
            df
        )


    result = pd.concat(
        frames,
        ignore_index=True,
    )


    result = (
        result

        .dropna(
            subset=[
                "open_time",
                "open",
                "close",
                "volume",
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


    result["period"] = (
        result[
            "open_time"
        ]
        .dt.strftime(
            "%Y-%m"
        )
    )


    result["year"] = (
        result[
            "open_time"
        ]
        .dt.strftime(
            "%Y"
        )
    )


    return result


# ============================================================
# PROFIT FACTOR
# ============================================================

def profit_factor(values):

    values = (
        pd.Series(values)
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


    return gains / losses


# ============================================================
# TRIMMED MEAN
# ============================================================

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


# ============================================================
# WINSORIZED
# ============================================================

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


# ============================================================
# SUMMARY
# ============================================================

def summarize(values):

    values = (
        pd.Series(values)
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
        f"PROCESSANDO EFFORT VS RESULT — {symbol}"
    )

    print("=" * 100)


    df = load_symbol(
        symbol
    )


    print(
        f"{symbol}: candles = "
        f"{len(df)}"
    )


    # ========================================================
    # PRICE RESULT
    # ========================================================

    df["return_5m"] = (
        df["close"]
        /
        df["open"]
        -
        1
    )


    df["abs_return"] = (
        df[
            "return_5m"
        ]
        .abs()
    )


    # ========================================================
    # PAST VOLUME QUANTILES
    # ========================================================

    df["volume_q25"] = (
        df["volume"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            VOLUME_LOW_Q
        )

        .shift(1)
    )


    df["volume_q90"] = (
        df["volume"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            VOLUME_HIGH_Q
        )

        .shift(1)
    )


    # ========================================================
    # PAST PRICE RESULT QUANTILES
    # ========================================================

    df["result_q25"] = (
        df["abs_return"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            RESULT_LOW_Q
        )

        .shift(1)
    )


    df["result_q90"] = (
        df["abs_return"]

        .rolling(
            LOOKBACK,
            min_periods=MIN_PERIODS,
        )

        .quantile(
            RESULT_HIGH_Q
        )

        .shift(1)
    )


    # ========================================================
    # STATES
    # ========================================================

    high_effort = (
        df["volume"]
        >=
        df["volume_q90"]
    )


    low_effort = (
        df["volume"]
        <=
        df["volume_q25"]
    )


    low_result = (
        df["abs_return"]
        <=
        df["result_q25"]
    )


    high_result = (
        df["abs_return"]
        >=
        df["result_q90"]
    )


    up = (
        df["return_5m"]
        >
        0
    )


    down = (
        df["return_5m"]
        <
        0
    )


    # ========================================================
    # RAW EVENT FAMILIES
    #
    # ABSORPTION:
    # high effort + low result
    #
    # EFFICIENT:
    # high effort + high result
    #
    # FRAGILE:
    # low effort + high result
    # ========================================================

    masks = {

        "ABSORPTION_UP":
            (
                high_effort
                &
                low_result
                &
                up
            ),

        "ABSORPTION_DOWN":
            (
                high_effort
                &
                low_result
                &
                down
            ),

        "EFFICIENT_UP":
            (
                high_effort
                &
                high_result
                &
                up
            ),

        "EFFICIENT_DOWN":
            (
                high_effort
                &
                high_result
                &
                down
            ),

        "FRAGILE_UP":
            (
                low_effort
                &
                high_result
                &
                up
            ),

        "FRAGILE_DOWN":
            (
                low_effort
                &
                high_result
                &
                down
            ),

    }


    # ========================================================
    # FUTURE RETURNS
    # ========================================================

    entry_price = (
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
    # FIRST CROSSING
    #
    # Evita contar sequências consecutivas do mesmo estado.
    # Não há cooldown arbitrário.
    # ========================================================

    for state_name, raw_mask in masks.items():


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


        temp["symbol"] = symbol

        temp["state"] = state_name


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
            "state",
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
        "state",
        as_index=False,
    )

    .agg(

        samples=(
            "state",
            "size",
        ),

        mean_signal_return=(
            "return_5m",
            "mean",
        ),

        median_signal_return=(
            "return_5m",
            "median",
        ),

        mean_abs_return=(
            "abs_return",
            "mean",
        ),

        median_abs_return=(
            "abs_return",
            "median",
        ),

        mean_volume=(
            "volume",
            "mean",
        ),

    )

)


# ============================================================
# HYPOTHESES
#
# Cada fenômeno testa:
# - interpretação principal
# - controle oposto
#
# Isso evita concluir direção por construção.
# ============================================================

HYPOTHESES = {

    # --------------------------------------------------------
    # ABSORPTION
    # --------------------------------------------------------

    "ABS_UP_REVERSE_SHORT":
        (
            "ABSORPTION_UP",
            "SHORT",
        ),

    "ABS_UP_CONTINUE_LONG":
        (
            "ABSORPTION_UP",
            "LONG",
        ),

    "ABS_DOWN_REVERSE_LONG":
        (
            "ABSORPTION_DOWN",
            "LONG",
        ),

    "ABS_DOWN_CONTINUE_SHORT":
        (
            "ABSORPTION_DOWN",
            "SHORT",
        ),


    # --------------------------------------------------------
    # EFFICIENT MOVE
    # --------------------------------------------------------

    "EFF_UP_CONTINUE_LONG":
        (
            "EFFICIENT_UP",
            "LONG",
        ),

    "EFF_UP_REVERSE_SHORT":
        (
            "EFFICIENT_UP",
            "SHORT",
        ),

    "EFF_DOWN_CONTINUE_SHORT":
        (
            "EFFICIENT_DOWN",
            "SHORT",
        ),

    "EFF_DOWN_REVERSE_LONG":
        (
            "EFFICIENT_DOWN",
            "LONG",
        ),


    # --------------------------------------------------------
    # FRAGILE MOVE
    # --------------------------------------------------------

    "FRAG_UP_REVERSE_SHORT":
        (
            "FRAGILE_UP",
            "SHORT",
        ),

    "FRAG_UP_CONTINUE_LONG":
        (
            "FRAGILE_UP",
            "LONG",
        ),

    "FRAG_DOWN_REVERSE_LONG":
        (
            "FRAGILE_DOWN",
            "LONG",
        ),

    "FRAG_DOWN_CONTINUE_SHORT":
        (
            "FRAGILE_DOWN",
            "SHORT",
        ),

}


# ============================================================
# GENERIC ANALYSIS
# ============================================================

global_rows = []

year_rows = []

asset_rows = []

monthly_rows = []


for hypothesis, (
    state,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "state"
        ]
        ==
        state
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

                "state":
                    state,

                "side":
                    side,

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
        # MONTHLY
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
# STABILITY @ BASE COST
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
            global_match.iloc[0]
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
# AUTOMATIC GATE
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

def percent_display(df):

    output = df.copy()


    for column in [
        "cost",
        "mean_return",
        "median_return",
        "trimmed_mean_5",
        "winsorized_mean_5",
        "win_rate",
        "q10",
        "q90",
        "mean_signal_return",
        "median_signal_return",
        "mean_abs_return",
        "median_abs_return",
    ]:

        if column in output.columns:

            output[
                column
            ] *= 100


    return output


global_display = percent_display(
    global_results
)


stability_display = percent_display(
    stability
)


anatomy_display = percent_display(
    anatomy
)


pd.set_option(
    "display.max_columns",
    None,
)


pd.set_option(
    "display.width",
    420,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print("=" * 220)

print(
    "EXPERIMENTO 32 — "
    "BRANCH 09 EFFORT VS RESULT"
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
    anatomy_display.to_string(
        index=False
    )
)


print()

print("=" * 220)

print(
    "TOP GLOBAL RESULTS @ 0.06%"
)

print("=" * 220)

print()


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


print(
    base_global.to_string(
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
# PASSED
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
    / "effort_result_events.csv",
    index=False,
)


counts.to_csv(
    RESULTS_DIR
    / "effort_result_counts.csv",
    index=False,
)


anatomy.to_csv(
    RESULTS_DIR
    / "effort_result_anatomy.csv",
    index=False,
)


global_results.to_csv(
    RESULTS_DIR
    / "effort_result_global.csv",
    index=False,
)


by_year.to_csv(
    RESULTS_DIR
    / "effort_result_by_year.csv",
    index=False,
)


by_asset.to_csv(
    RESULTS_DIR
    / "effort_result_by_asset.csv",
    index=False,
)


monthly.to_csv(
    RESULTS_DIR
    / "effort_result_monthly.csv",
    index=False,
)


stability.to_csv(
    RESULTS_DIR
    / "effort_result_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
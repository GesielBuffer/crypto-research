from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

RESULTS_DIR = Path("results")

INPUT_FILE = (
    RESULTS_DIR
    / "extreme_impulse_events.csv"
)


HORIZONS = [
    6,   # 30 min
    12,  # 60 min
]


COSTS = [
    0.0000,
    0.0002,
    0.0004,
]


HYPOTHESES = {

    "DOWN_REVERSAL_LONG": {
        "event": "EXTREME_DOWN",
        "side": "LONG",
    },

    "UP_CONTINUATION_LONG": {
        "event": "EXTREME_UP",
        "side": "LONG",
    },

}


FEATURES = [

    "abs_return_z",

    "range_ratio",

    "volume_ratio_7d",

    "directional_close_extremity",

]


# ============================================================
# PROFIT FACTOR
# ============================================================

def profit_factor(returns):

    returns = (
        pd.Series(returns)
        .dropna()
    )


    if len(returns) == 0:
        return np.nan


    positive = (
        returns[
            returns > 0
        ]
        .sum()
    )


    negative = (
        returns[
            returns < 0
        ]
        .abs()
        .sum()
    )


    if negative == 0:

        if positive > 0:
            return np.inf

        return np.nan


    return (
        positive
        /
        negative
    )


# ============================================================
# SUMMARY
# ============================================================

def summarize(returns):

    returns = (
        pd.Series(returns)
        .dropna()
    )


    if len(returns) == 0:

        return {

            "samples": 0,

            "mean_return": np.nan,

            "median_return": np.nan,

            "win_rate": np.nan,

            "profit_factor": np.nan,

            "q10": np.nan,

            "q90": np.nan,

        }


    return {

        "samples":
            len(returns),

        "mean_return":
            returns.mean(),

        "median_return":
            returns.median(),

        "win_rate":
            (
                returns > 0
            ).mean(),

        "profit_factor":
            profit_factor(
                returns
            ),

        "q10":
            returns.quantile(
                0.10
            ),

        "q90":
            returns.quantile(
                0.90
            ),

    }


# ============================================================
# LOAD
# ============================================================

events = pd.read_csv(
    INPUT_FILE
)


# ============================================================
# FEATURE ENGINEERING
#
# Nenhuma informação futura.
# ============================================================

events[
    "abs_return_z"
] = (

    events[
        "return_z"
    ]
    .abs()

)


# ============================================================
# FECHAMENTO DIRECIONAL
#
# 1 = fechou totalmente na direção do impulso
#
# DOWN:
# close perto da mínima -> próximo de 1
#
# UP:
# close perto da máxima -> próximo de 1
# ============================================================

events[
    "directional_close_extremity"
] = np.where(

    events[
        "event"
    ]
    ==
    "EXTREME_DOWN",

    1.0
    -
    events[
        "close_position"
    ],

    events[
        "close_position"
    ],

)


events = events.dropna(

    subset=(

        FEATURES

        +

        [
            "event",
            "symbol",
            "year",
            "future_long_6",
            "future_long_12",
        ]

    )

).copy()


print()

print(
    f"Eventos disponíveis: "
    f"{len(events)}"
)


# ============================================================
# QUARTIS
#
# IMPORTANTE:
#
# Criados separadamente para EXTREME_DOWN
# e EXTREME_UP.
#
# São diagnóstico.
# Não representam ainda regra de trading.
# ============================================================

for feature in FEATURES:


    bucket_column = (
        f"{feature}_quartile"
    )


    events[
        bucket_column
    ] = pd.NA


    for (
        event_name,
        group,
    ) in events.groupby(
        "event"
    ):


        values = group[
            feature
        ]


        codes = pd.qcut(

            values,

            q=4,

            labels=False,

            duplicates="drop",

        )


        labels = codes.map(

            lambda x:

                (
                    f"Q{int(x) + 1}"

                    if pd.notna(x)

                    else np.nan
                )

        )


        events.loc[

            group.index,

            bucket_column

        ] = labels


# ============================================================
# BASELINES
# ============================================================

baseline_rows = []


for (
    hypothesis,
    config,
) in HYPOTHESES.items():


    subset = events[

        events[
            "event"
        ]
        ==
        config[
            "event"
        ]

    ]


    for horizon in HORIZONS:


        gross = subset[
            f"future_long_{horizon}"
        ]


        for cost in COSTS:


            stats = summarize(
                gross - cost
            )


            baseline_rows.append({

                "hypothesis":
                    hypothesis,

                "event":
                    config[
                        "event"
                    ],

                "horizon":
                    horizon,

                "minutes":
                    horizon * 5,

                "cost":
                    cost,

                **stats,

            })


baseline = pd.DataFrame(
    baseline_rows
)


# ============================================================
# GLOBAL BUCKET ANALYSIS
# ============================================================

bucket_rows = []


for (
    hypothesis,
    config,
) in HYPOTHESES.items():


    event_name = config[
        "event"
    ]


    subset_event = events[

        events[
            "event"
        ]
        ==
        event_name

    ]


    for horizon in HORIZONS:


        return_column = (
            f"future_long_{horizon}"
        )


        for feature in FEATURES:


            bucket_column = (
                f"{feature}_quartile"
            )


            for bucket in [

                "Q1",
                "Q2",
                "Q3",
                "Q4",

            ]:


                subset = subset_event[

                    subset_event[
                        bucket_column
                    ]
                    ==
                    bucket

                ]


                if subset.empty:
                    continue


                gross = subset[
                    return_column
                ]


                for cost in COSTS:


                    stats = summarize(
                        gross - cost
                    )


                    base_row = baseline[

                        (
                            baseline[
                                "hypothesis"
                            ]
                            ==
                            hypothesis
                        )

                        &

                        (
                            baseline[
                                "horizon"
                            ]
                            ==
                            horizon
                        )

                        &

                        (
                            baseline[
                                "cost"
                            ]
                            ==
                            cost
                        )

                    ].iloc[0]


                    bucket_rows.append({

                        "hypothesis":
                            hypothesis,

                        "event":
                            event_name,

                        "horizon":
                            horizon,

                        "minutes":
                            horizon * 5,

                        "feature":
                            feature,

                        "bucket":
                            bucket,

                        "cost":
                            cost,

                        "feature_min":
                            subset[
                                feature
                            ].min(),

                        "feature_median":
                            subset[
                                feature
                            ].median(),

                        "feature_max":
                            subset[
                                feature
                            ].max(),

                        **stats,

                        "baseline_mean_return":
                            base_row[
                                "mean_return"
                            ],

                        "baseline_profit_factor":
                            base_row[
                                "profit_factor"
                            ],

                        "mean_return_delta":
                            stats[
                                "mean_return"
                            ]
                            -
                            base_row[
                                "mean_return"
                            ],

                        "pf_delta":
                            stats[
                                "profit_factor"
                            ]
                            -
                            base_row[
                                "profit_factor"
                            ],

                    })


buckets = pd.DataFrame(
    bucket_rows
)


# ============================================================
# CORRELATIONS
#
# Relação contínua:
# feature vs retorno futuro
# ============================================================

correlation_rows = []


for (
    hypothesis,
    config,
) in HYPOTHESES.items():


    subset = events[

        events[
            "event"
        ]
        ==
        config[
            "event"
        ]

    ]


    for horizon in HORIZONS:


        return_column = (
            f"future_long_{horizon}"
        )


        for feature in FEATURES:


            valid = subset[

                [
                    feature,
                    return_column,
                ]

            ].dropna()


            pearson = (

                valid[
                    feature
                ]

                .corr(

                    valid[
                        return_column
                    ]

                )

            )


            spearman = (

                valid[
                    feature
                ]

                .rank()

                .corr(

                    valid[
                        return_column
                    ]

                    .rank()

                )

            )


            correlation_rows.append({

                "hypothesis":
                    hypothesis,

                "horizon":
                    horizon,

                "minutes":
                    horizon * 5,

                "feature":
                    feature,

                "samples":
                    len(valid),

                "pearson":
                    pearson,

                "spearman":
                    spearman,

            })


correlations = pd.DataFrame(
    correlation_rows
)


# ============================================================
# YEAR × BUCKET
# ============================================================

year_rows = []


for (
    hypothesis,
    config,
) in HYPOTHESES.items():


    subset_event = events[

        events[
            "event"
        ]
        ==
        config[
            "event"
        ]

    ]


    for horizon in HORIZONS:


        return_column = (
            f"future_long_{horizon}"
        )


        for feature in FEATURES:


            bucket_column = (
                f"{feature}_quartile"
            )


            for (
                year,
                bucket,
            ), group in subset_event.groupby(

                [
                    "year",
                    bucket_column,
                ],

                observed=True,

            ):


                for cost in COSTS:


                    stats = summarize(

                        group[
                            return_column
                        ]

                        -
                        cost

                    )


                    year_rows.append({

                        "hypothesis":
                            hypothesis,

                        "year":
                            str(year),

                        "horizon":
                            horizon,

                        "minutes":
                            horizon * 5,

                        "feature":
                            feature,

                        "bucket":
                            str(bucket),

                        "cost":
                            cost,

                        **stats,

                    })


year_buckets = pd.DataFrame(
    year_rows
)


# ============================================================
# ASSET × BUCKET
# ============================================================

asset_rows = []


for (
    hypothesis,
    config,
) in HYPOTHESES.items():


    subset_event = events[

        events[
            "event"
        ]
        ==
        config[
            "event"
        ]

    ]


    for horizon in HORIZONS:


        return_column = (
            f"future_long_{horizon}"
        )


        for feature in FEATURES:


            bucket_column = (
                f"{feature}_quartile"
            )


            for (
                symbol,
                bucket,
            ), group in subset_event.groupby(

                [
                    "symbol",
                    bucket_column,
                ],

                observed=True,

            ):


                for cost in COSTS:


                    stats = summarize(

                        group[
                            return_column
                        ]

                        -
                        cost

                    )


                    asset_rows.append({

                        "hypothesis":
                            hypothesis,

                        "symbol":
                            symbol,

                        "horizon":
                            horizon,

                        "minutes":
                            horizon * 5,

                        "feature":
                            feature,

                        "bucket":
                            str(bucket),

                        "cost":
                            cost,

                        **stats,

                    })


asset_buckets = pd.DataFrame(
    asset_rows
)


# ============================================================
# STABILITY SUMMARY
#
# Principal tabela para decisão.
#
# Custo = 0.04%
# ============================================================

TARGET_COST = 0.0004


global_cost = buckets[

    buckets[
        "cost"
    ]
    ==
    TARGET_COST

].copy()


year_cost = year_buckets[

    year_buckets[
        "cost"
    ]
    ==
    TARGET_COST

].copy()


asset_cost = asset_buckets[

    asset_buckets[
        "cost"
    ]
    ==
    TARGET_COST

].copy()


KEYS = [

    "hypothesis",

    "horizon",

    "minutes",

    "feature",

    "bucket",

]


year_stability = (

    year_cost

    .groupby(
        KEYS,
        as_index=False,
    )

    .agg(

        years=(
            "year",
            "nunique",
        ),

        years_pf_gt_1=(

            "profit_factor",

            lambda x:
                (
                    x > 1
                ).sum(),

        ),

        years_mean_gt_0=(

            "mean_return",

            lambda x:
                (
                    x > 0
                ).sum(),

        ),

        worst_year_pf=(
            "profit_factor",
            "min",
        ),

        median_year_pf=(
            "profit_factor",
            "median",
        ),

    )

)


asset_stability = (

    asset_cost

    .groupby(
        KEYS,
        as_index=False,
    )

    .agg(

        assets=(
            "symbol",
            "nunique",
        ),

        assets_pf_gt_1=(

            "profit_factor",

            lambda x:
                (
                    x > 1
                ).sum(),

        ),

        assets_mean_gt_0=(

            "mean_return",

            lambda x:
                (
                    x > 0
                ).sum(),

        ),

        worst_asset_pf=(
            "profit_factor",
            "min",
        ),

        median_asset_pf=(
            "profit_factor",
            "median",
        ),

    )

)


stability = (

    global_cost

    .merge(

        year_stability,

        on=KEYS,

        how="left",

    )

    .merge(

        asset_stability,

        on=KEYS,

        how="left",

    )

)


stability = (

    stability

    .sort_values(

        [

            "profit_factor",

            "years_pf_gt_1",

            "assets_pf_gt_1",

        ],

        ascending=[

            False,

            False,

            False,

        ],

    )

)


# ============================================================
# DISPLAY HELPERS
# ============================================================

def percent_display(
    df,
):

    output = df.copy()


    for column in [

        "cost",

        "mean_return",
        "median_return",

        "win_rate",

        "q10",
        "q90",

        "baseline_mean_return",

        "mean_return_delta",

    ]:

        if column in output.columns:

            output[
                column
            ] *= 100


    return output


baseline_display = percent_display(
    baseline
)


bucket_display = percent_display(
    buckets
)


stability_display = percent_display(
    stability
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
# OUTPUT 1
# ============================================================

print()

print("=" * 200)

print(
    "EXPERIMENTO 19 — "
    "PRICE-VOLUME DISLOCATION ANATOMY"
)

print("=" * 200)

print()


print(
    "BASELINES"
)

print()


print(

    baseline_display

    .sort_values(

        [
            "hypothesis",
            "cost",
            "horizon",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 2
# ============================================================

print()

print("=" * 200)

print(
    "CORRELAÇÕES CONTÍNUAS"
)

print("=" * 200)

print()


print(

    correlations

    .sort_values(

        [
            "hypothesis",
            "horizon",
            "feature",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 3
#
# BRUTO + 0.04%
# ============================================================

print()

print("=" * 200)

print(
    "QUARTIS — "
    "BRUTO E CUSTO 0.04%"
)

print("=" * 200)

print()


bucket_focus = bucket_display[

    bucket_display[
        "cost"
    ]
    .isin(
        [
            0.00,
            0.04,
        ]
    )

]


print(

    bucket_focus

    .sort_values(

        [
            "hypothesis",
            "horizon",
            "feature",
            "cost",
            "bucket",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 4
# ============================================================

print()

print("=" * 200)

print(
    "TOP 25 — "
    "ESTABILIDADE COM CUSTO 0.04%"
)

print("=" * 200)

print()


columns = [

    "hypothesis",

    "minutes",

    "feature",

    "bucket",

    "samples",

    "mean_return",

    "median_return",

    "profit_factor",

    "pf_delta",

    "years_pf_gt_1",

    "years_mean_gt_0",

    "worst_year_pf",

    "median_year_pf",

    "assets_pf_gt_1",

    "assets_mean_gt_0",

    "worst_asset_pf",

    "median_asset_pf",

]


print(

    stability_display[

        columns

    ]

    .head(25)

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

events.to_csv(

    RESULTS_DIR
    / "dislocation_events_with_quartiles.csv",

    index=False,

)


baseline.to_csv(

    RESULTS_DIR
    / "dislocation_baseline.csv",

    index=False,

)


correlations.to_csv(

    RESULTS_DIR
    / "dislocation_correlations.csv",

    index=False,

)


buckets.to_csv(

    RESULTS_DIR
    / "dislocation_buckets.csv",

    index=False,

)


year_buckets.to_csv(

    RESULTS_DIR
    / "dislocation_buckets_by_year.csv",

    index=False,

)


asset_buckets.to_csv(

    RESULTS_DIR
    / "dislocation_buckets_by_asset.csv",

    index=False,

)


stability.to_csv(

    RESULTS_DIR
    / "dislocation_stability.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
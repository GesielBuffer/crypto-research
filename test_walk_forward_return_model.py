from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge


# ============================================================
# CONFIG
# ============================================================

RESULTS_DIR = Path("results")

INPUT_FILE = (
    RESULTS_DIR
    / "slow_regime_events.csv"
)


SELECTION_QUANTILE = 0.70


COSTS = [
    0.0000,
    0.0004,
    0.0008,
]


# ============================================================
# MESMAS FEATURES DO EXPERIMENTO 12
# ============================================================

FEATURES = [

    "asset_ret_1d",
    "asset_ret_3d",
    "asset_ret_7d",
    "asset_ret_30d",

    "asset_rv_1d",
    "asset_rv_7d",

    "asset_price_vs_sma7d",
    "asset_sma1d_vs_7d",

    "market_mean_1d",
    "market_mean_3d",
    "market_mean_7d",
    "market_mean_30d",

    "market_rv_1d",
    "market_rv_7d",

    "breadth_down_7d",
    "breadth_down_30d",

    "dispersion_7d",

    "btc_ret_7d",
    "btc_ret_30d",

]


# ============================================================
# WALK FORWARD
# ============================================================

FOLDS = [

    {
        "name": "2024_H2",
        "train_end": "2024-07-01",
        "test_start": "2024-07-01",
        "test_end": "2025-01-01",
    },

    {
        "name": "2025_H1",
        "train_end": "2025-01-01",
        "test_start": "2025-01-01",
        "test_end": "2025-07-01",
    },

    {
        "name": "2025_H2",
        "train_end": "2025-07-01",
        "test_start": "2025-07-01",
        "test_end": "2026-01-01",
    },

    {
        "name": "2026_DEV",
        "train_end": "2026-01-01",
        "test_start": "2026-01-01",
        "test_end": "2026-08-01",
    },

]


# ============================================================
# PROFIT FACTOR
# ============================================================

def profit_factor(returns):

    returns = pd.Series(
        returns
    ).dropna()


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
# PERFORMANCE
# ============================================================

def performance(returns):

    returns = pd.Series(
        returns
    ).dropna()


    if len(returns) == 0:

        return {

            "samples": 0,

            "mean_return": np.nan,

            "median_return": np.nan,

            "win_rate": np.nan,

            "profit_factor": np.nan,

            "q90": np.nan,

            "q95": np.nan,

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

        "q90":
            returns.quantile(
                0.90
            ),

        "q95":
            returns.quantile(
                0.95
            ),

    }


# ============================================================
# LOAD
# ============================================================

events = pd.read_csv(
    INPUT_FILE
)


events[
    "open_time"
] = pd.to_datetime(

    events[
        "open_time"
    ],

    utc=True,

)


events = (

    events

    .dropna(

        subset=(

            FEATURES

            +

            [
                "future_return",
                "open_time",
                "symbol",
            ]

        )

    )

    .copy()

)


print()

print(
    f"Eventos disponíveis: "
    f"{len(events)}"
)


# ============================================================
# CONTAINERS
# ============================================================

diagnostic_rows = []

performance_rows = []

coefficient_rows = []

oos_frames = []


# ============================================================
# WALK FORWARD
# ============================================================

for fold in FOLDS:


    name = fold[
        "name"
    ]


    train_end = pd.Timestamp(
        fold["train_end"],
        tz="UTC",
    )


    test_start = pd.Timestamp(
        fold["test_start"],
        tz="UTC",
    )


    test_end = pd.Timestamp(
        fold["test_end"],
        tz="UTC",
    )


    # ========================================================
    # TRAIN
    # ========================================================

    train = events[

        events[
            "open_time"
        ]
        <
        train_end

    ].copy()


    # ========================================================
    # TEST
    # ========================================================

    test = events[

        (
            events[
                "open_time"
            ]
            >=
            test_start
        )

        &

        (
            events[
                "open_time"
            ]
            <
            test_end
        )

    ].copy()


    if (
        len(train) < 100
        or
        len(test) < 30
    ):

        print(
            f"Fold ignorado: {name}"
        )

        continue


    X_train = train[
        FEATURES
    ]


    y_train = train[
        "future_return"
    ]


    X_test = test[
        FEATURES
    ]


    y_test = test[
        "future_return"
    ]


    # ========================================================
    # RIDGE REGRESSION
    #
    # Sem tuning.
    # alpha fixo = 1.
    # ========================================================

    model = Pipeline(

        [

            (
                "scaler",

                StandardScaler(),

            ),

            (
                "model",

                Ridge(
                    alpha=1.0
                ),

            ),

        ]

    )


    model.fit(

        X_train,

        y_train,

    )


    # ========================================================
    # PREDIÇÕES
    # ========================================================

    train_pred = model.predict(
        X_train
    )


    test_pred = model.predict(
        X_test
    )


    # ========================================================
    # THRESHOLD DEFINIDO SOMENTE NO TRAIN
    #
    # Top 30% esperado pelo modelo.
    # ========================================================

    threshold = np.quantile(

        train_pred,

        SELECTION_QUANTILE,

    )


    selected = (

        test_pred
        >=
        threshold

    )


    # ========================================================
    # CORRELAÇÕES OOS
    # ========================================================

    prediction_series = pd.Series(

        test_pred,

        index=test.index,

    )


    pearson = (

        prediction_series

        .corr(
            y_test
        )

    )


    spearman = (

        prediction_series

        .rank()

        .corr(

            y_test
            .rank()

        )

    )


    # ========================================================
    # DIAGNÓSTICO
    # ========================================================

    diagnostic_rows.append({

        "fold":
            name,

        "train_samples":
            len(train),

        "test_samples":
            len(test),

        "train_mean_return":
            y_train.mean(),

        "test_mean_return":
            y_test.mean(),

        "pearson_pred_return":
            pearson,

        "spearman_pred_return":
            spearman,

        "threshold":
            threshold,

        "selection_rate":
            selected.mean(),

        "selected_samples":
            int(
                selected.sum()
            ),

        "mean_predicted_return":
            np.mean(
                test_pred
            ),

        "mean_pred_selected":
            np.mean(
                test_pred[
                    selected
                ]
            )
            if selected.sum() > 0
            else np.nan,

    })


    # ========================================================
    # TEST OOS
    # ========================================================

    test = test.copy()


    test[
        "predicted_return"
    ] = test_pred


    test[
        "ridge_selected"
    ] = selected


    test[
        "fold"
    ] = name


    oos_frames.append(
        test
    )


    # ========================================================
    # PERFORMANCE
    # ========================================================

    masks = [

        (
            "BASE",

            pd.Series(
                True,
                index=test.index,
            ),

        ),

        (
            "RIDGE_SELECTED",

            test[
                "ridge_selected"
            ],

        ),

    ]


    for (
        strategy,
        mask,
    ) in masks:


        gross = (

            test.loc[

                mask,

                "future_return",

            ]

            .dropna()

        )


        for cost in COSTS:


            returns = (

                gross
                -
                cost

            )


            performance_rows.append({

                "fold":
                    name,

                "strategy":
                    strategy,

                "cost":
                    cost,

                **performance(
                    returns
                ),

            })


    # ========================================================
    # COEFICIENTES
    #
    # Inputs padronizados.
    # ========================================================

    coefficients = (

        model

        .named_steps[
            "model"
        ]

        .coef_

    )


    for feature, coef in zip(

        FEATURES,

        coefficients,

    ):


        coefficient_rows.append({

            "fold":
                name,

            "feature":
                feature,

            "coefficient":
                coef,

        })


# ============================================================
# DATAFRAMES
# ============================================================

diagnostics = pd.DataFrame(
    diagnostic_rows
)


fold_performance = pd.DataFrame(
    performance_rows
)


coefficients = pd.DataFrame(
    coefficient_rows
)


oos = pd.concat(

    oos_frames,

    ignore_index=True,

)


# ============================================================
# POOLED OOS
# ============================================================

pooled_rows = []


for strategy, mask in [

    (
        "BASE",

        pd.Series(
            True,
            index=oos.index,
        ),

    ),

    (
        "RIDGE_SELECTED",

        oos[
            "ridge_selected"
        ],

    ),

]:


    gross = (

        oos.loc[

            mask,

            "future_return",

        ]

        .dropna()

    )


    for cost in COSTS:


        returns = (

            gross
            -
            cost

        )


        pooled_rows.append({

            "strategy":
                strategy,

            "cost":
                cost,

            **performance(
                returns
            ),

        })


pooled = pd.DataFrame(
    pooled_rows
)


# ============================================================
# OOS POR ATIVO
# ============================================================

asset_rows = []


for symbol in sorted(

    oos[
        "symbol"
    ]
    .unique()

):


    subset_symbol = oos[

        oos[
            "symbol"
        ]
        ==
        symbol

    ]


    for strategy, mask in [

        (
            "BASE",

            pd.Series(
                True,
                index=subset_symbol.index,
            ),

        ),

        (
            "RIDGE_SELECTED",

            subset_symbol[
                "ridge_selected"
            ],

        ),

    ]:


        returns = (

            subset_symbol.loc[

                mask,

                "future_return",

            ]

            .dropna()

        )


        asset_rows.append({

            "symbol":
                symbol,

            "strategy":
                strategy,

            **performance(
                returns
            ),

        })


asset_results = pd.DataFrame(
    asset_rows
)


# ============================================================
# COEFFICIENT STABILITY
# ============================================================

coef_summary = (

    coefficients

    .groupby(
        "feature",
        as_index=False,
    )

    .agg(

        folds=(
            "fold",
            "count",
        ),

        mean_coefficient=(
            "coefficient",
            "mean",
        ),

        median_coefficient=(
            "coefficient",
            "median",
        ),

        positive_sign_rate=(

            "coefficient",

            lambda x:
                (
                    x > 0
                )
                .mean(),

        ),

        mean_abs_coefficient=(

            "coefficient",

            lambda x:
                x.abs().mean(),

        ),

    )

)


coef_summary = (

    coef_summary

    .sort_values(

        "mean_abs_coefficient",

        ascending=False,

    )

)


# ============================================================
# DISPLAY
# ============================================================

diagnostic_display = (
    diagnostics.copy()
)


for column in [

    "train_mean_return",
    "test_mean_return",
    "threshold",
    "mean_predicted_return",
    "mean_pred_selected",

]:

    diagnostic_display[
        column
    ] *= 100


diagnostic_display[
    "selection_rate"
] *= 100


fold_display = (
    fold_performance.copy()
)


pooled_display = (
    pooled.copy()
)


asset_display = (
    asset_results.copy()
)


for df in [

    fold_display,
    pooled_display,
    asset_display,

]:

    for column in [

        "cost",
        "mean_return",
        "median_return",
        "win_rate",
        "q90",
        "q95",

    ]:

        if column in df.columns:

            df[
                column
            ] *= 100


coef_display = (
    coef_summary.copy()
)


coef_display[
    "positive_sign_rate"
] *= 100


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    280,
)


# ============================================================
# OUTPUT 1
# ============================================================

print()

print("=" * 190)

print(
    "EXPERIMENTO 13 — "
    "WALK-FORWARD RETURN MODEL"
)

print("=" * 190)

print()


print(

    diagnostic_display

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 2
# ============================================================

print()

print("=" * 190)

print(
    "PERFORMANCE OUT-OF-TIME "
    "POR FOLD"
)

print("=" * 190)

print()


print(

    fold_display

    .sort_values(

        [
            "fold",
            "strategy",
            "cost",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 3
# ============================================================

print()

print("=" * 190)

print(
    "PERFORMANCE POOLED "
    "100% WALK-FORWARD"
)

print("=" * 190)

print()


print(

    pooled_display

    .sort_values(

        [
            "strategy",
            "cost",
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

print("=" * 190)

print(
    "OOS POR ATIVO — "
    "CUSTO ZERO"
)

print("=" * 190)

print()


print(

    asset_display

    .sort_values(

        [
            "strategy",
            "symbol",
        ]

    )

    .to_string(
        index=False
    )

)


# ============================================================
# OUTPUT 5
# ============================================================

print()

print("=" * 190)

print(
    "ESTABILIDADE DOS COEFICIENTES "
    "RIDGE"
)

print("=" * 190)

print()


print(

    coef_display

    .head(15)

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

diagnostics.to_csv(

    RESULTS_DIR
    / "ridge_diagnostics.csv",

    index=False,

)


fold_performance.to_csv(

    RESULTS_DIR
    / "ridge_fold_performance.csv",

    index=False,

)


pooled.to_csv(

    RESULTS_DIR
    / "ridge_pooled_performance.csv",

    index=False,

)


asset_results.to_csv(

    RESULTS_DIR
    / "ridge_asset_performance.csv",

    index=False,

)


coef_summary.to_csv(

    RESULTS_DIR
    / "ridge_coefficients.csv",

    index=False,

)


oos.to_csv(

    RESULTS_DIR
    / "ridge_oos_predictions.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
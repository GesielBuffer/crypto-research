from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


# ============================================================
# CONFIG
# ============================================================

RESULTS_DIR = Path("results")

INPUT_FILE = (
    RESULTS_DIR
    / "slow_regime_events.csv"
)


# ============================================================
# IMPORTANTE
#
# Selecionamos aproximadamente os 30% dos sinais que o
# modelo considera melhores.
#
# O percentil é calculado SOMENTE NO TREINO.
# ============================================================

SELECTION_QUANTILE = 0.70


COSTS = [

    0.0000,   # bruto
    0.0004,   # 0.04%
    0.0008,   # 0.08%

]


# ============================================================
# FEATURES
#
# Todas conhecidas antes da entrada.
#
# NÃO usamos:
# - future_return
# - year
# - macro_regime
# - symbol
#
# no modelo.
#
# Queremos inicialmente estudar REGIME,
# não memorizar ativo.
# ============================================================

FEATURES = [

    # --------------------------------------------------------
    # PRÓPRIO ATIVO
    # --------------------------------------------------------

    "asset_ret_1d",
    "asset_ret_3d",
    "asset_ret_7d",
    "asset_ret_30d",

    "asset_rv_1d",
    "asset_rv_7d",

    "asset_price_vs_sma7d",
    "asset_sma1d_vs_7d",


    # --------------------------------------------------------
    # MERCADO
    # --------------------------------------------------------

    "market_mean_1d",
    "market_mean_3d",
    "market_mean_7d",
    "market_mean_30d",

    "market_rv_1d",
    "market_rv_7d",

    "breadth_down_7d",
    "breadth_down_30d",

    "dispersion_7d",


    # --------------------------------------------------------
    # BTC
    # --------------------------------------------------------

    "btc_ret_7d",
    "btc_ret_30d",

]


# ============================================================
# WALK-FORWARD FOLDS
# ============================================================

FOLDS = [

    {

        "name":
            "2024_H2",

        "train_end":
            "2024-07-01",

        "test_start":
            "2024-07-01",

        "test_end":
            "2025-01-01",

    },

    {

        "name":
            "2025_H1",

        "train_end":
            "2025-01-01",

        "test_start":
            "2025-01-01",

        "test_end":
            "2025-07-01",

    },

    {

        "name":
            "2025_H2",

        "train_end":
            "2025-07-01",

        "test_start":
            "2025-07-01",

        "test_end":
            "2026-01-01",

    },

    {

        "name":
            "2026_DEV",

        "train_end":
            "2026-01-01",

        "test_start":
            "2026-01-01",

        "test_end":
            "2026-08-01",

    },

]


# ============================================================
# SAFE PROFIT FACTOR
# ============================================================

def profit_factor(
    returns,
):

    returns = (

        pd.Series(
            returns
        )

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
# PERFORMANCE
# ============================================================

def calculate_performance(
    returns,
):

    returns = (

        pd.Series(
            returns
        )

        .dropna()

    )


    if len(returns) == 0:

        return {

            "samples":
                0,

            "mean_return":
                np.nan,

            "median_return":
                np.nan,

            "win_rate":
                np.nan,

            "profit_factor":
                np.nan,

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

    }


# ============================================================
# LOAD
# ============================================================

events = pd.read_csv(
    INPUT_FILE
)


events[
    "period_start"
] = pd.to_datetime(

    events[
        "period"
    ]

    +
    "-01"

)


# ============================================================
# REMOVE NAN
# ============================================================

required = (

    FEATURES

    +

    [
        "future_return",
        "period_start",
        "symbol",
    ]

)


events = (

    events

    .dropna(
        subset=required
    )

    .copy()

)


# ============================================================
# TARGET
#
# META-LABEL:
#
# 1 = trade terminou positivo em 60 min
# 0 = trade terminou <= 0
#
# IMPORTANTE:
# O modelo NÃO vai operar diretamente.
#
# Queremos testar se ele consegue RANQUEAR
# bons e maus sinais.
# ============================================================

events[
    "target"
] = (

    events[
        "future_return"
    ]

    >
    0

).astype(int)


print()

print(
    f"Eventos disponíveis: "
    f"{len(events)}"
)


# ============================================================
# OUTPUT CONTAINERS
# ============================================================

diagnostic_rows = []

performance_rows = []

coefficient_rows = []

oos_frames = []


# ============================================================
# WALK FORWARD
# ============================================================

for fold in FOLDS:


    fold_name = (
        fold[
            "name"
        ]
    )


    train_end = pd.Timestamp(
        fold[
            "train_end"
        ]
    )


    test_start = pd.Timestamp(
        fold[
            "test_start"
        ]
    )


    test_end = pd.Timestamp(
        fold[
            "test_end"
        ]
    )


    # ========================================================
    # TRAIN
    # ========================================================

    train = events[

        events[
            "period_start"
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
                "period_start"
            ]
            >=
            test_start
        )

        &

        (
            events[
                "period_start"
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
            f"Fold ignorado: "
            f"{fold_name}"
        )

        continue


    # ========================================================
    # X / Y
    # ========================================================

    X_train = train[
        FEATURES
    ]


    y_train = train[
        "target"
    ]


    X_test = test[
        FEATURES
    ]


    y_test = test[
        "target"
    ]


    # ========================================================
    # MODELO
    #
    # Simples:
    #
    # scaler
    # +
    # logistic regression L2
    #
    # Sem otimização de hiperparâmetros.
    # ========================================================

    model = Pipeline(

        [

            (
                "scaler",

                StandardScaler(),

            ),

            (
                "model",

                LogisticRegression(

                    penalty="l2",

                    C=1.0,

                    max_iter=2000,

                    solver="lbfgs",

                ),

            ),

        ]

    )


    model.fit(

        X_train,

        y_train,

    )


    # ========================================================
    # PROBABILIDADES
    # ========================================================

    train_probability = (

        model

        .predict_proba(
            X_train
        )

        [:, 1]

    )


    test_probability = (

        model

        .predict_proba(
            X_test
        )

        [:, 1]

    )


    # ========================================================
    # THRESHOLD SOMENTE PELO TREINO
    #
    # Seleciona aproximadamente top 30%.
    # ========================================================

    threshold = np.quantile(

        train_probability,

        SELECTION_QUANTILE,

    )


    selected = (

        test_probability
        >=
        threshold

    )


    # ========================================================
    # AUC
    # ========================================================

    if (
        y_test.nunique()
        >
        1
    ):

        auc = roc_auc_score(

            y_test,

            test_probability,

        )

    else:

        auc = np.nan


    # ========================================================
    # SPEARMAN:
    #
    # Probabilidade prevista
    # vs retorno financeiro real.
    # ========================================================

    probability_series = pd.Series(

        test_probability,

        index=test.index,

    )


    spearman = (

        probability_series

        .rank()

        .corr(

            test[
                "future_return"
            ]

            .rank()

        )

    )


    # ========================================================
    # DIAGNÓSTICO DO FOLD
    # ========================================================

    diagnostic_rows.append({

        "fold":
            fold_name,

        "train_samples":
            len(train),

        "test_samples":
            len(test),

        "train_win_rate":
            y_train.mean(),

        "test_win_rate":
            y_test.mean(),

        "auc":
            auc,

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

    })


    # ========================================================
    # PERFORMANCE
    #
    # BASE
    # vs
    # META_SELECTED
    # ========================================================

    test = test.copy()


    test[
        "predicted_probability"
    ] = test_probability


    test[
        "meta_selected"
    ] = selected


    test[
        "fold"
    ] = fold_name


    oos_frames.append(
        test
    )


    for strategy_name, mask in [

        (
            "BASE",

            pd.Series(

                True,

                index=test.index,

            ),

        ),

        (
            "META_SELECTED",

            test[
                "meta_selected"
            ],

        ),

    ]:


        gross_returns = (

            test.loc[

                mask,

                "future_return",

            ]

            .dropna()

        )


        for cost in COSTS:


            net_returns = (

                gross_returns

                -

                cost

            )


            stats = calculate_performance(

                net_returns

            )


            performance_rows.append({

                "fold":
                    fold_name,

                "strategy":
                    strategy_name,

                "cost":
                    cost,

                **stats,

            })


    # ========================================================
    # COEFICIENTES
    #
    # Como usamos StandardScaler,
    # podemos comparar magnitudes aproximadamente.
    # ========================================================

    coefficients = (

        model

        .named_steps[
            "model"
        ]

        .coef_[0]

    )


    for (
        feature,
        coefficient,
    ) in zip(

        FEATURES,

        coefficients,

    ):


        coefficient_rows.append({

            "fold":
                fold_name,

            "feature":
                feature,

            "coefficient":
                coefficient,

        })


# ============================================================
# DATAFRAMES
# ============================================================

diagnostics = pd.DataFrame(
    diagnostic_rows
)


performance = pd.DataFrame(
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
#
# Cada observação aqui foi prevista por um
# modelo treinado SOMENTE no passado.
# ============================================================

pooled_rows = []


for strategy_name, mask in [

    (
        "BASE",

        pd.Series(

            True,

            index=oos.index,

        ),

    ),

    (
        "META_SELECTED",

        oos[
            "meta_selected"
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
                strategy_name,

            "cost":
                cost,

            **calculate_performance(
                returns
            ),

        })


pooled = pd.DataFrame(
    pooled_rows
)


# ============================================================
# PERFORMANCE POR ATIVO
#
# Apenas OOS bruto.
# ============================================================

asset_rows = []


for symbol in sorted(

    oos[
        "symbol"
    ]
    .unique()

):


    for strategy_name, selection_column in [

        (
            "BASE",
            None,
        ),

        (
            "META_SELECTED",
            "meta_selected",
        ),

    ]:


        subset = oos[

            oos[
                "symbol"
            ]
            ==
            symbol

        ].copy()


        if (
            selection_column
            is not None
        ):

            subset = subset[

                subset[
                    selection_column
                ]

            ]


        returns = (

            subset[
                "future_return"
            ]

            .dropna()

        )


        asset_rows.append({

            "symbol":
                symbol,

            "strategy":
                strategy_name,

            **calculate_performance(
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
# DISPLAY HELPERS
# ============================================================

diagnostic_display = (
    diagnostics.copy()
)


for column in [

    "train_win_rate",
    "test_win_rate",
    "selection_rate",

]:

    diagnostic_display[
        column
    ] *= 100


performance_display = (
    performance.copy()
)


for column in [

    "cost",
    "mean_return",
    "median_return",
    "win_rate",

]:

    performance_display[
        column
    ] *= 100


pooled_display = (
    pooled.copy()
)


for column in [

    "cost",
    "mean_return",
    "median_return",
    "win_rate",

]:

    pooled_display[
        column
    ] *= 100


asset_display = (
    asset_results.copy()
)


for column in [

    "mean_return",
    "median_return",
    "win_rate",

]:

    asset_display[
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
    260,
)


# ============================================================
# OUTPUT 1
# ============================================================

print()

print("=" * 180)

print(
    "EXPERIMENTO 12 — "
    "WALK-FORWARD META-MODEL"
)

print("=" * 180)

print()


print(
    diagnostic_display.to_string(
        index=False
    )
)


# ============================================================
# OUTPUT 2
# ============================================================

print()

print("=" * 180)

print(
    "PERFORMANCE OUT-OF-TIME "
    "POR FOLD"
)

print("=" * 180)

print()


print(

    performance_display

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

print("=" * 180)

print(
    "PERFORMANCE POOLED "
    "100% WALK-FORWARD"
)

print("=" * 180)

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

print("=" * 180)

print(
    "OOS POR ATIVO — "
    "CUSTO ZERO"
)

print("=" * 180)

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

print("=" * 180)

print(
    "ESTABILIDADE DOS COEFICIENTES"
)

print("=" * 180)

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
    / "meta_model_diagnostics.csv",

    index=False,

)


performance.to_csv(

    RESULTS_DIR
    / "meta_model_fold_performance.csv",

    index=False,

)


pooled.to_csv(

    RESULTS_DIR
    / "meta_model_pooled_performance.csv",

    index=False,

)


asset_results.to_csv(

    RESULTS_DIR
    / "meta_model_asset_performance.csv",

    index=False,

)


coef_summary.to_csv(

    RESULTS_DIR
    / "meta_model_coefficients.csv",

    index=False,

)


oos.to_csv(

    RESULTS_DIR
    / "meta_model_oos_predictions.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
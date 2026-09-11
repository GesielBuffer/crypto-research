from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import (
    fetch_klines,
    save_csv,
    load_csv,
)

from research.indicators import (
    add_all_indicators,
)

from research.features import (
    add_all_features,
)

from research.targets import (
    add_future_targets,
)

from research.validation import (
    run_validation,
)


# ============================================================
# CONFIGURAÇÕES
# ============================================================

SYMBOLS = [

    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",

]


INTERVAL = "5m"


# ============================================================
# OUT-OF-SAMPLE
# ============================================================
#
# Janeiro NÃO entra.
#
# Janeiro foi usado para descoberta.
#
# Agora testaremos períodos que ainda não
# foram utilizados para desenvolver a ideia.
#
# ============================================================

PERIODS = [

    (
        "2026-02",
        "2026-02-01",
        "2026-03-01",
    ),

    (
        "2026-03",
        "2026-03-01",
        "2026-04-01",
    ),

    (
        "2026-04",
        "2026-04-01",
        "2026-05-01",
    ),

    (
        "2026-05",
        "2026-05-01",
        "2026-06-01",
    ),

    (
        "2026-06",
        "2026-06-01",
        "2026-07-01",
    ),

    (
        "2026-07",
        "2026-07-01",
        "2026-08-01",
    ),

]


# ============================================================
# MESMOS HORIZONTES
# ============================================================

HORIZONS = [

    1,
    3,
    6,
    12,

]


# ============================================================
# MESMO CUSTO
# ============================================================

ROUND_TRIP_COST = 0.0008


# ============================================================
# DIRETÓRIOS
# ============================================================

DATA_DIR = Path(
    "data"
)

RESULTS_DIR = Path(
    "results"
)


DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# CARREGAR OU BAIXAR HISTÓRICO
# ============================================================

def load_or_download(
    symbol,
    interval,
    start_date,
    end_date,
):

    filename = (

        f"{symbol}_"
        f"{interval}_"
        f"{start_date}_"
        f"{end_date}.csv"

    )

    path = (
        DATA_DIR
        / filename
    )


    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if path.exists():

        print(
            f"📁 Cache: "
            f"{symbol} "
            f"{start_date}"
        )

        return load_csv(
            path
        )


    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    print(
        f"🌐 Baixando: "
        f"{symbol} "
        f"{start_date}"
    )


    df = fetch_klines(

        symbol,

        interval,

        start_date,

        end_date,

    )


    save_csv(
        df,
        path,
    )


    return df


# ============================================================
# RESULTADOS
# ============================================================

all_results = []


# ============================================================
# LOOP PRINCIPAL
# ============================================================

for symbol in SYMBOLS:

    print()

    print(
        "=" * 100
    )

    print(
        f"ATIVO: {symbol}"
    )

    print(
        "=" * 100
    )


    for (
        period_name,
        start_date,
        end_date,
    ) in PERIODS:


        df = load_or_download(

            symbol,

            INTERVAL,

            start_date,

            end_date,

        )


        print(
            f"   {period_name}: "
            f"{len(df)} candles"
        )


        # ====================================================
        # INDICADORES
        # ====================================================

        df = add_all_indicators(
            df
        )


        # ====================================================
        # FEATURES
        # ====================================================

        df = add_all_features(
            df
        )


        # ====================================================
        # TARGETS
        # ====================================================

        df = add_future_targets(

            df,

            HORIZONS,

        )


        # ====================================================
        # VALIDAÇÃO
        # ====================================================

        result = run_validation(

            df=df,

            horizons=HORIZONS,

            cost=ROUND_TRIP_COST,

        )


        result.insert(
            0,
            "symbol",
            symbol,
        )


        result.insert(
            1,
            "period",
            period_name,
        )


        all_results.append(
            result
        )


# ============================================================
# CONCATENA
# ============================================================

results_df = pd.concat(

    all_results,

    ignore_index=True,

)


# ============================================================
# SALVA RESULTADO DETALHADO
# ============================================================

detailed_file = (

    RESULTS_DIR
    / "multi_asset_validation_detailed.csv"

)


results_df.to_csv(

    detailed_file,

    index=False,

)


# ============================================================
# PREPARA AGREGAÇÃO
# ============================================================

summary_source = (
    results_df.copy()
)


# PF infinito pode atrapalhar mediana/agregação.

summary_source[
    "profit_factor_clean"
] = (

    summary_source[
        "profit_factor"
    ]
    .replace(
        [
            np.inf,
            -np.inf,
        ],
        np.nan,
    )

)


# ============================================================
# ROBUSTEZ ENTRE JANELAS
# ============================================================

summary_df = (

    summary_source

    .groupby(

        [
            "strategy",
            "side",
            "horizon",
            "sample_mode",
        ],

        as_index=False,

    )

    .agg(

        windows=(
            "period",
            "count",
        ),

        total_samples=(
            "samples",
            "sum",
        ),

        profitable_windows=(

            "mean_return",

            lambda x: int(
                (x > 0).sum()
            ),

        ),

        positive_window_rate=(

            "mean_return",

            lambda x: (
                x > 0
            ).mean(),

        ),

        pf_above_1_rate=(

            "profit_factor_clean",

            lambda x: (
                x > 1
            ).mean(),

        ),

        median_profit_factor=(

            "profit_factor_clean",

            "median",

        ),

        median_mean_return=(

            "mean_return",

            "median",

        ),

        worst_mean_return=(

            "mean_return",

            "min",

        ),

        best_mean_return=(

            "mean_return",

            "max",

        ),

        median_win_rate=(

            "win_rate",

            "median",

        ),

    )

)


# ============================================================
# SALVA RESUMO
# ============================================================

summary_file = (

    RESULTS_DIR
    / "multi_asset_validation_summary.csv"

)


summary_df.to_csv(

    summary_file,

    index=False,

)


# ============================================================
# DISPLAY
# ============================================================

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    250,
)


# ============================================================
# FOCO PRINCIPAL:
# 60 MINUTOS + NÃO SOBREPOSTO
# ============================================================

focus = summary_df[

    (
        summary_df["horizon"]
        == 12
    )

    &

    (
        summary_df["sample_mode"]
        == "NON_OVERLAP"
    )

].copy()


# ============================================================
# CONVERTE PARA EXIBIÇÃO
# ============================================================

focus[
    "positive_window_rate"
] *= 100


focus[
    "pf_above_1_rate"
] *= 100


focus[
    "median_mean_return"
] *= 100


focus[
    "worst_mean_return"
] *= 100


focus[
    "best_mean_return"
] *= 100


focus[
    "median_win_rate"
] *= 100


focus = focus.sort_values(

    [
        "positive_window_rate",
        "median_profit_factor",
    ],

    ascending=[
        False,
        False,
    ],

)


print()

print(
    "=" * 180
)

print(
    "VALIDAÇÃO OUT-OF-SAMPLE"
)

print(
    "4 ATIVOS | 6 MESES | 5m | "
    "HORIZONTE 60 MIN | "
    "SINAIS NÃO SOBREPOSTOS"
)

print(
    "=" * 180
)

print()


columns = [

    "strategy",

    "side",

    "windows",

    "total_samples",

    "profitable_windows",

    "positive_window_rate",

    "pf_above_1_rate",

    "median_profit_factor",

    "median_mean_return",

    "median_win_rate",

    "worst_mean_return",

    "best_mean_return",

]


print(

    focus[
        columns
    ].to_string(
        index=False
    )

)


# ============================================================
# PERFIL DO NOSSO PRINCIPAL CANDIDATO
# ============================================================

candidate = summary_df[

    (
        summary_df["strategy"]
        ==
        "SHORT_EMA_MACD_ADX_VOLUME"
    )

    &

    (
        summary_df["sample_mode"]
        ==
        "NON_OVERLAP"
    )

].copy()


candidate[
    "positive_window_rate"
] *= 100


candidate[
    "pf_above_1_rate"
] *= 100


candidate[
    "median_mean_return"
] *= 100


candidate[
    "median_win_rate"
] *= 100


candidate = candidate.sort_values(
    "horizon"
)


print()

print(
    "=" * 180
)

print(
    "PERFIL POR HORIZONTE — "
    "SHORT_EMA_MACD_ADX_VOLUME"
)

print(
    "=" * 180
)

print()


candidate_columns = [

    "horizon",

    "windows",

    "total_samples",

    "positive_window_rate",

    "pf_above_1_rate",

    "median_profit_factor",

    "median_mean_return",

    "median_win_rate",

]


print(

    candidate[
        candidate_columns
    ].to_string(
        index=False
    )

)


# ============================================================
# ARQUIVOS
# ============================================================

print()

print(
    "=" * 100
)

print(
    "ARQUIVOS GERADOS"
)

print(
    "=" * 100
)

print(
    detailed_file
)

print(
    summary_file
)
import numpy as np
import pandas as pd

from .statistics import analyze_condition


# ============================================================
# SINAIS NÃO SOBREPOSTOS
# ============================================================

def non_overlapping_mask(
    mask: pd.Series,
    horizon: int,
) -> pd.Series:

    """
    Seleciona um sinal e bloqueia novos sinais
    enquanto aquela operação hipotética ainda
    estaria aberta.

    Exemplo:
    horizonte 12 candles

    sinal em t
        ↓
    entrada t+1
        ↓
    saída t+12

    Outro sinal só será considerado depois
    desse movimento.
    """

    mask = (
        mask
        .fillna(False)
        .astype(bool)
    )

    selected = np.zeros(
        len(mask),
        dtype=bool,
    )

    next_allowed = 0

    values = mask.to_numpy()

    for i, is_signal in enumerate(values):

        if not is_signal:
            continue

        if i < next_allowed:
            continue

        selected[i] = True

        next_allowed = (
            i + horizon
        )

    return pd.Series(
        selected,
        index=mask.index,
    )


# ============================================================
# REGRAS DO EXPERIMENTO
# ============================================================

def build_experiments(
    df: pd.DataFrame,
) -> dict:

    # --------------------------------------------------------
    # LONG
    # --------------------------------------------------------

    ema_bull = (
        (df["ema_9"] > df["ema_21"])
        &
        (df["ema_21"] > df["ema_35"])
    )

    macd_bull = (
        df["macd_hist"] > 0
    )

    # --------------------------------------------------------
    # SHORT
    # --------------------------------------------------------

    ema_bear = (
        (df["ema_9"] < df["ema_21"])
        &
        (df["ema_21"] < df["ema_35"])
    )

    macd_bear = (
        df["macd_hist"] < 0
    )

    # --------------------------------------------------------
    # FORÇA
    # --------------------------------------------------------

    adx_strong = (
        df["adx"] >= 25
    )

    volume_strong = (
        df["volume_ratio"] >= 1.5
    )

    # Mantemos exatamente a regra anterior.
    score_bear = (
        df["directional_score"] <= -4
    )

    # --------------------------------------------------------
    # EXPERIMENTOS
    # --------------------------------------------------------

    experiments = {

        "SHORT_EMA": (
            ema_bear,
            "SHORT",
        ),

        "SHORT_EMA_MACD": (
            ema_bear
            & macd_bear,
            "SHORT",
        ),

        "SHORT_EMA_MACD_ADX": (
            ema_bear
            & macd_bear
            & adx_strong,
            "SHORT",
        ),

        "SHORT_EMA_MACD_ADX_VOLUME": (
            ema_bear
            & macd_bear
            & adx_strong
            & volume_strong,
            "SHORT",
        ),

        "SHORT_SCORE_4_ADX_VOLUME": (
            score_bear
            & adx_strong
            & volume_strong,
            "SHORT",
        ),

        # Controle LONG
        "LONG_EMA_MACD_ADX_VOLUME": (
            ema_bull
            & macd_bull
            & adx_strong
            & volume_strong,
            "LONG",
        ),
    }

    return experiments


# ============================================================
# EXECUTA EXPERIMENTO EM UM DATASET
# ============================================================

def run_validation(
    df: pd.DataFrame,
    horizons,
    cost,
) -> pd.DataFrame:

    experiments = (
        build_experiments(df)
    )

    results = []

    for strategy, (
        original_mask,
        side,
    ) in experiments.items():

        for horizon in horizons:

            # ================================================
            # 1. SINAIS BRUTOS
            # ================================================

            stats_raw = analyze_condition(

                df=df,

                mask=original_mask,

                side=side,

                horizon=horizon,

                cost=cost,

            )

            results.append({

                "strategy": strategy,

                "side": side,

                "horizon": horizon,

                "sample_mode": "RAW",

                **stats_raw,

            })

            # ================================================
            # 2. SINAIS NÃO SOBREPOSTOS
            # ================================================

            clean_mask = (
                non_overlapping_mask(
                    original_mask,
                    horizon,
                )
            )

            stats_clean = analyze_condition(

                df=df,

                mask=clean_mask,

                side=side,

                horizon=horizon,

                cost=cost,

            )

            results.append({

                "strategy": strategy,

                "side": side,

                "horizon": horizon,

                "sample_mode": "NON_OVERLAP",

                **stats_clean,

            })

    return pd.DataFrame(
        results
    )
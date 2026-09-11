import numpy as np
import pandas as pd


# ============================================================
# RETORNOS FUTUROS EXECUTÁVEIS
# ============================================================

def add_future_targets(
    df: pd.DataFrame,
    horizons=(1, 3, 6, 12),
) -> pd.DataFrame:

    df = df.copy()

    # O sinal é conhecido somente depois
    # do fechamento do candle atual.
    #
    # Por isso a entrada acontece
    # no OPEN do próximo candle.

    df["future_entry"] = (
        df["open"].shift(-1)
    )

    for horizon in horizons:

        future_exit = (
            df["close"].shift(-horizon)
        )

        # Retorno caso comprássemos
        df[f"future_long_{horizon}"] = (
            future_exit
            / df["future_entry"]
            - 1
        )

        # Retorno caso vendêssemos
        df[f"future_short_{horizon}"] = (
            df["future_entry"]
            / future_exit
            - 1
        )

    return df
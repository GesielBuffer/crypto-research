import numpy as np
import pandas as pd


# ============================================================
# PROFIT FACTOR
# ============================================================

def calculate_profit_factor(
    returns: pd.Series,
) -> float:

    returns = returns.dropna()

    gains = returns[
        returns > 0
    ].sum()

    losses = abs(
        returns[
            returns < 0
        ].sum()
    )

    if losses == 0:

        if gains > 0:
            return float("inf")

        return 0.0

    return float(
        gains / losses
    )


# ============================================================
# ANALISAR UMA CONDIÇÃO
# ============================================================

def analyze_condition(
    df: pd.DataFrame,
    mask: pd.Series,
    side: str,
    horizon: int,
    cost: float = 0.0,
) -> dict:

    side = side.upper()

    if side == "LONG":

        column = (
            f"future_long_{horizon}"
        )

    elif side == "SHORT":

        column = (
            f"future_short_{horizon}"
        )

    else:

        raise ValueError(
            "side deve ser LONG ou SHORT"
        )

    returns = (
        df.loc[
            mask,
            column,
        ]
        .dropna()
    )

    # --------------------------------------------
    # RETORNO APÓS CUSTOS
    # --------------------------------------------

    net_returns = (
        returns - cost
    )

    if len(net_returns) == 0:

        return {
            "samples": 0,
            "win_rate": np.nan,
            "mean_return": np.nan,
            "median_return": np.nan,
            "profit_factor": np.nan,
            "best_trade": np.nan,
            "worst_trade": np.nan,
        }

    return {

        "samples": len(
            net_returns
        ),

        "win_rate": (
            net_returns > 0
        ).mean(),

        "mean_return": (
            net_returns.mean()
        ),

        "median_return": (
            net_returns.median()
        ),

        "profit_factor": (
            calculate_profit_factor(
                net_returns
            )
        ),

        "best_trade": (
            net_returns.max()
        ),

        "worst_trade": (
            net_returns.min()
        ),

    }
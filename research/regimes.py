import pandas as pd


# ============================================================
# REGIMES DINÂMICOS
# ============================================================

def build_regimes(
    df: pd.DataFrame,
) -> dict:

    regimes = {}


    # ========================================================
    # ADX
    # ========================================================

    regimes["ADX_RISING"] = (
        df["adx_change"] > 0
    )

    regimes["ADX_FALLING"] = (
        df["adx_change"] <= 0
    )


    # ========================================================
    # TENDÊNCIA / EMAs
    #
    # Para SHORT:
    #
    # EMA9 - EMA21 normalmente é negativo.
    #
    # Se ficar ainda mais negativo:
    # tendência bearish está se expandindo.
    # ========================================================

    regimes["BEAR_SPREAD_WIDENING"] = (
        df["trend_velocity"] < 0
    )

    regimes["BEAR_SPREAD_NARROWING"] = (
        df["trend_velocity"] >= 0
    )


    # ========================================================
    # ACELERAÇÃO DA TENDÊNCIA
    # ========================================================

    regimes["BEAR_ACCELERATION"] = (
        df["trend_acceleration"] < 0
    )

    regimes["BEAR_DECELERATION"] = (
        df["trend_acceleration"] >= 0
    )


    # ========================================================
    # VOLATILIDADE
    # ========================================================

    regimes["ATR_EXPANDING"] = (
        df["atr_expansion"] > 1
    )

    regimes["ATR_CONTRACTING"] = (
        df["atr_expansion"] <= 1
    )


    # ========================================================
    # VOLUME
    # ========================================================

    regimes["VOLUME_ACCELERATING"] = (
        df["volume_ratio_change"] > 0
    )

    regimes["VOLUME_DECELERATING"] = (
        df["volume_ratio_change"] <= 0
    )


    # ========================================================
    # PRESSÃO DO CANDLE
    #
    # close_position:
    #
    # 0.0 = fechamento na mínima
    # 1.0 = fechamento na máxima
    # ========================================================

    regimes["BEAR_CANDLE_PRESSURE"] = (
        df["close_position"] <= 0.35
    )

    regimes["BULL_CANDLE_PRESSURE"] = (
        df["close_position"] >= 0.65
    )


    # ========================================================
    # ADX + DI
    # ========================================================

    regimes["BEAR_DI_DOMINANCE"] = (
        df["di_strength"] < 0
    )


    # ========================================================
    # COMBINAÇÃO DINÂMICA EXPERIMENTAL
    #
    # Não é ainda nosso indicador.
    # É apenas uma hipótese para pesquisa.
    # ========================================================

    regimes["DYNAMIC_BEAR_CONFIRMATION"] = (

        (df["adx_change"] > 0)

        &

        (df["trend_velocity"] < 0)

        &

        (df["atr_expansion"] > 1)

    )


    return regimes
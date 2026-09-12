from pathlib import Path

import numpy as np
import pandas as pd

from research.binance_data import load_csv
from research.indicators import add_all_indicators
from research.features import add_all_features
from research.targets import add_future_targets
from research.statistics import calculate_profit_factor
from research.validation import non_overlapping_mask


# ============================================================
# CONFIG
# ============================================================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]


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


INTERVAL = "5m"

HORIZON = 12


DATA_DIR = Path("data")

RESULTS_DIR = Path("results")

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# CARREGA SÉRIE CONTÍNUA
# ============================================================

def load_continuous_symbol(
    symbol,
):

    frames = []

    for (
        period,
        start_date,
        end_date,
    ) in PERIODS:

        filename = (
            f"{symbol}_"
            f"{INTERVAL}_"
            f"{start_date}_"
            f"{end_date}.csv"
        )

        path = (
            DATA_DIR
            / filename
        )

        if not path.exists():

            print(
                f"Arquivo ausente: {path}"
            )

            continue

        temp = load_csv(
            path
        )

        temp["period"] = period

        frames.append(
            temp
        )

    if not frames:

        return None

    df = pd.concat(
        frames,
        ignore_index=True,
    )

    df = (
        df
        .drop_duplicates(
            subset=["open_time"]
        )
        .sort_values(
            "open_time"
        )
        .reset_index(
            drop=True
        )
    )

    return df


# ============================================================
# CONSTRÓI TIMEFRAME 1H
#
# Barra rotulada 01:00 contém:
# 00:00 ... 00:55
#
# Portanto ela só é usada depois
# de estar completamente fechada.
# ============================================================

def build_1h_features(
    df,
    prefix,
):

    temp = df.copy()

    temp["open_time"] = pd.to_datetime(
        temp["open_time"],
        utc=True,
    )

    temp = (
        temp
        .set_index("open_time")
        .sort_index()
    )

    aggregation = {

        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",

    }

    # Campos opcionais
    if "quote_volume" in temp.columns:
        aggregation["quote_volume"] = "sum"

    if "trades" in temp.columns:
        aggregation["trades"] = "sum"


    hourly = (

        temp

        .resample(
            "1h",
            closed="left",
            label="right",
        )

        .agg(
            aggregation
        )

        .dropna(
            subset=[
                "open",
                "high",
                "low",
                "close",
            ]
        )

        .reset_index()

    )


    # ========================================================
    # INDICADORES 1H
    # ========================================================

    hourly = add_all_indicators(
        hourly
    )

    hourly = add_all_features(
        hourly
    )


    # ========================================================
    # RETORNOS SUPERIORES
    # ========================================================

    hourly["return_24"] = (
        hourly["close"]
        .pct_change(24)
    )


    # ========================================================
    # REGIME 1H
    # ========================================================

    hourly["ema_bear"] = (

        (hourly["ema_9"] < hourly["ema_21"])

        &

        (hourly["ema_21"] < hourly["ema_35"])

    )


    hourly["ema_bull"] = (

        (hourly["ema_9"] > hourly["ema_21"])

        &

        (hourly["ema_21"] > hourly["ema_35"])

    )


    # ========================================================
    # A open_time agora representa o FINAL
    # da barra agregada.
    # ========================================================

    hourly = hourly.rename(

        columns={
            "open_time": "htf_end"
        }

    )


    columns = [

        "htf_end",

        "ema_bear",
        "ema_bull",

        "macd_hist",

        "adx",
        "adx_change",

        "atr_expansion",

        "di_strength",

        "trend_velocity",
        "trend_acceleration",

        "return_3",
        "return_6",
        "return_12",
        "return_24",

    ]


    hourly = hourly[
        columns
    ].copy()


    rename = {

        column:
            f"{prefix}_{column}"

        for column in columns

        if column != "htf_end"

    }


    hourly = hourly.rename(
        columns=rename
    )


    return hourly


# ============================================================
# PREPARA TODAS AS SÉRIES
# ============================================================

market_data = {}

hourly_data = {}


for symbol in SYMBOLS:

    print()

    print(
        "=" * 100
    )

    print(
        f"PREPARANDO {symbol}"
    )

    print(
        "=" * 100
    )


    raw = load_continuous_symbol(
        symbol
    )


    if raw is None:

        continue


    market_data[
        symbol
    ] = raw


    hourly_data[
        symbol
    ] = build_1h_features(

        raw,

        prefix="asset1h",

    )


# ============================================================
# BTC REGIME
# ============================================================

btc_hourly = build_1h_features(

    market_data["BTCUSDT"],

    prefix="btc1h",

)


# ============================================================
# EVENTOS
# ============================================================

all_events = []


for symbol in SYMBOLS:

    print(
        f"Analisando eventos: {symbol}"
    )


    df = market_data[
        symbol
    ].copy()


    # ========================================================
    # INDICADORES 5M
    # ========================================================

    df = add_all_indicators(
        df
    )


    df = add_all_features(
        df
    )


    df = add_future_targets(

        df,

        [HORIZON],

    )


    # ========================================================
    # SINAL BASE
    # ========================================================

    base_short = (

        (df["ema_9"] < df["ema_21"])

        &

        (df["ema_21"] < df["ema_35"])

        &

        (df["macd_hist"] < 0)

        &

        (df["adx"] >= 25)

        &

        (df["volume_ratio"] >= 1.5)

    )


    # ========================================================
    # NON OVERLAP
    # ========================================================

    mask = non_overlapping_mask(

        base_short,

        HORIZON,

    )


    events = df.loc[
        mask
    ].copy()


    # ========================================================
    # ATR CANDIDATO
    # ========================================================

    events = events[

        (events["atr_expansion"] >= 0.80)

        &

        (events["atr_expansion"] < 1.00)

    ].copy()


    # ========================================================
    # MOMENTO EM QUE O SINAL É CONHECIDO
    #
    # candle open_time 10:00
    # fecha aproximadamente 10:05
    # sinal conhecido em 10:05
    # ========================================================

    events["signal_time"] = (

        pd.to_datetime(
            events["open_time"],
            utc=True,
        )

        +

        pd.Timedelta(
            minutes=5
        )

    )


    # ========================================================
    # MERGE 1H DO PRÓPRIO ATIVO
    # ========================================================

    asset_htf = hourly_data[
        symbol
    ].copy()


    events = pd.merge_asof(

        events.sort_values(
            "signal_time"
        ),

        asset_htf.sort_values(
            "htf_end"
        ),

        left_on="signal_time",

        right_on="htf_end",

        direction="backward",

    )


    events = events.rename(

        columns={
            "htf_end":
                "asset1h_end"
        }

    )


    # ========================================================
    # MERGE REGIME BTC
    # ========================================================

    btc = btc_hourly.copy()


    events = pd.merge_asof(

        events.sort_values(
            "signal_time"
        ),

        btc.sort_values(
            "htf_end"
        ),

        left_on="signal_time",

        right_on="htf_end",

        direction="backward",

    )


    events = events.rename(

        columns={
            "htf_end":
                "btc1h_end"
        }

    )


    # ========================================================
    # TARGET
    # ========================================================

    events["future_return"] = (

        events[
            f"future_short_{HORIZON}"
        ]

    )


    events["symbol"] = symbol


    events["regime_group"] = np.where(

        events["period"]
        ==
        "2026-07",

        "JULY",

        "FEB_JUN",

    )


    all_events.append(
        events
    )


# ============================================================
# CONSOLIDA
# ============================================================

events_df = pd.concat(

    all_events,

    ignore_index=True,

)


events_df = events_df.dropna(

    subset=[
        "future_return",
    ]

)


# ============================================================
# PERFORMANCE
# ============================================================

def summarize(
    data,
):

    returns = (

        data[
            "future_return"
        ]

        .dropna()

    )


    if len(returns) == 0:

        return {

            "samples": 0,

            "mean_return": np.nan,

            "median_return": np.nan,

            "win_rate": np.nan,

            "profit_factor": np.nan,

        }


    return {

        "samples":
            len(returns),

        "mean_return":
            returns.mean(),

        "median_return":
            returns.median(),

        "win_rate":
            (returns > 0).mean(),

        "profit_factor":
            calculate_profit_factor(
                returns
            ),

    }


# ============================================================
# ESTADOS DE TIMEFRAME SUPERIOR
# ============================================================

states = {

    # --------------------------------------------------------
    # ATIVO 1H
    # --------------------------------------------------------

    "ASSET_1H_BEAR":

        events_df[
            "asset1h_ema_bear"
        ] == True,


    "ASSET_1H_NOT_BEAR":

        events_df[
            "asset1h_ema_bear"
        ] != True,


    "ASSET_6H_DOWN":

        events_df[
            "asset1h_return_6"
        ] < 0,


    "ASSET_6H_UP":

        events_df[
            "asset1h_return_6"
        ] >= 0,


    "ASSET_12H_DOWN":

        events_df[
            "asset1h_return_12"
        ] < 0,


    "ASSET_12H_UP":

        events_df[
            "asset1h_return_12"
        ] >= 0,


    "ASSET_24H_DOWN":

        events_df[
            "asset1h_return_24"
        ] < 0,


    "ASSET_24H_UP":

        events_df[
            "asset1h_return_24"
        ] >= 0,


    "ASSET_1H_MACD_BEAR":

        events_df[
            "asset1h_macd_hist"
        ] < 0,


    "ASSET_1H_MACD_BULL":

        events_df[
            "asset1h_macd_hist"
        ] >= 0,


    # --------------------------------------------------------
    # BTC
    # --------------------------------------------------------

    "BTC_1H_BEAR":

        events_df[
            "btc1h_ema_bear"
        ] == True,


    "BTC_1H_NOT_BEAR":

        events_df[
            "btc1h_ema_bear"
        ] != True,


    "BTC_6H_DOWN":

        events_df[
            "btc1h_return_6"
        ] < 0,


    "BTC_6H_UP":

        events_df[
            "btc1h_return_6"
        ] >= 0,


    "BTC_24H_DOWN":

        events_df[
            "btc1h_return_24"
        ] < 0,


    "BTC_24H_UP":

        events_df[
            "btc1h_return_24"
        ] >= 0,


    # --------------------------------------------------------
    # CONFLUÊNCIA
    # --------------------------------------------------------

    "ASSET_BEAR_AND_BTC_BEAR":

        (
            events_df[
                "asset1h_ema_bear"
            ] == True
        )

        &

        (
            events_df[
                "btc1h_ema_bear"
            ] == True
        ),


    "ASSET_24H_DOWN_AND_BTC_24H_DOWN":

        (
            events_df[
                "asset1h_return_24"
            ] < 0
        )

        &

        (
            events_df[
                "btc1h_return_24"
            ] < 0
        ),

}


# ============================================================
# PERFORMANCE POR ESTADO
# ============================================================

rows = []


# BASELINE
for group in [
    "FEB_JUN",
    "JULY",
]:

    subset = events_df[

        events_df[
            "regime_group"
        ]
        ==
        group

    ]

    stats = summarize(
        subset
    )

    rows.append({

        "state":
            "BASE",

        "regime_group":
            group,

        **stats,

    })


# ESTADOS
for (
    state_name,
    state_mask,
) in states.items():


    for group in [

        "FEB_JUN",
        "JULY",

    ]:


        subset = events_df[

            state_mask

            &

            (
                events_df[
                    "regime_group"
                ]
                ==
                group
            )

        ]


        stats = summarize(
            subset
        )


        rows.append({

            "state":
                state_name,

            "regime_group":
                group,

            **stats,

        })


results = pd.DataFrame(
    rows
)


# ============================================================
# MUDANÇA DE DISTRIBUIÇÃO 1H
# ============================================================

HTF_FEATURES = [

    "asset1h_macd_hist",
    "asset1h_adx",
    "asset1h_adx_change",
    "asset1h_atr_expansion",
    "asset1h_di_strength",
    "asset1h_trend_velocity",
    "asset1h_trend_acceleration",
    "asset1h_return_3",
    "asset1h_return_6",
    "asset1h_return_12",
    "asset1h_return_24",

    "btc1h_macd_hist",
    "btc1h_adx",
    "btc1h_adx_change",
    "btc1h_atr_expansion",
    "btc1h_di_strength",
    "btc1h_trend_velocity",
    "btc1h_trend_acceleration",
    "btc1h_return_3",
    "btc1h_return_6",
    "btc1h_return_12",
    "btc1h_return_24",

]


shift_rows = []


for feature in HTF_FEATURES:

    pre = events_df.loc[

        events_df[
            "regime_group"
        ]
        ==
        "FEB_JUN",

        feature,

    ].dropna()


    july = events_df.loc[

        events_df[
            "regime_group"
        ]
        ==
        "JULY",

        feature,

    ].dropna()


    if len(pre) == 0 or len(july) == 0:

        continue


    q25 = pre.quantile(
        0.25
    )

    q75 = pre.quantile(
        0.75
    )

    iqr = (
        q75 - q25
    )


    pre_median = (
        pre.median()
    )

    july_median = (
        july.median()
    )


    robust_shift = (

        (
            july_median
            -
            pre_median
        )

        /

        iqr

        if iqr != 0

        else np.nan

    )


    shift_rows.append({

        "feature":
            feature,

        "pre_median":
            pre_median,

        "july_median":
            july_median,

        "robust_shift":
            robust_shift,

    })


shift_df = pd.DataFrame(
    shift_rows
)


shift_df[
    "abs_shift"
] = (

    shift_df[
        "robust_shift"
    ]
    .abs()

)


shift_df = (

    shift_df

    .sort_values(

        "abs_shift",

        ascending=False,

    )

)


# ============================================================
# DISPLAY
# ============================================================

display = results.copy()


for column in [

    "mean_return",
    "median_return",
    "win_rate",

]:

    display[column] *= 100


pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    250,
)


print()

print(
    "=" * 170
)

print(
    "EXPERIMENTO 7 — "
    "HIGHER TIMEFRAME / MARKET REGIME"
)

print(
    "=" * 170
)

print()


print(

    display

    .sort_values(

        [
            "state",
            "regime_group",
        ]

    )

    .to_string(
        index=False
    )

)


print()

print(
    "=" * 170
)

print(
    "MAIORES MUDANÇAS DE REGIME 1H "
    "EM JULHO"
)

print(
    "=" * 170
)

print()


print(

    shift_df

    .head(20)

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

events_df.to_csv(

    RESULTS_DIR
    / "htf_regime_events.csv",

    index=False,

)


results.to_csv(

    RESULTS_DIR
    / "htf_regime_performance.csv",

    index=False,

)


shift_df.to_csv(

    RESULTS_DIR
    / "htf_regime_shift.csv",

    index=False,

)


print()

print(
    "Arquivos salvos em results/"
)
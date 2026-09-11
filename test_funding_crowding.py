from pathlib import Path
import time

import numpy as np
import pandas as pd
import requests


# ============================================================
# EXPERIMENTO 31
# BRANCH 08 — POST-FUNDING CROWDING
#
# DEVELOPMENT:
# 2024-01-01 -> 2026-08-01
#
# Isso significa:
# Jan/2024 até Jul/2026.
#
# AGOSTO/2026:
# já observado -> NÃO USAR.
#
# SETEMBRO/2026:
# permanece INTOCADO.
#
# HIPÓTESE:
#
# HIGH FUNDING:
#   crowding comprador
#   testar SHORT pós-settlement
#
# LOW FUNDING:
#   crowding vendedor
#   testar LONG pós-settlement
#
# Também testamos controles opostos.
#
# IMPORTANTE:
# entrada somente após o funding já ter sido liquidado.
# ============================================================


# ============================================================
# SYMBOLS
# ============================================================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
]


# ============================================================
# PATHS
# ============================================================

DATA_DIR = Path("data")

RESULTS_DIR = Path("results")


DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# DEVELOPMENT PERIOD
# ============================================================

DEV_START = pd.Timestamp(
    "2024-01-01 00:00:00",
    tz="UTC",
)


DEV_END = pd.Timestamp(
    "2026-08-01 00:00:00",
    tz="UTC",
)


# ============================================================
# MONTHLY 5M PRICE FILES
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
# FUNDING EVENT DEFINITION
#
# ~3 fundings por dia normalmente.
#
# 270 observações:
# aproximadamente 90 dias.
#
# 90 observações mínimas:
# aproximadamente 30 dias.
#
# Não assumimos horário fixo de funding.
# ============================================================

FUNDING_LOOKBACK = 270

FUNDING_MIN_PERIODS = 90


LOW_QUANTILE = 0.05

HIGH_QUANTILE = 0.95


# ============================================================
# FUTURE PRICE WINDOWS
#
# 5m candles:
#
# 6  = 30m
# 12 = 60m
# 48 = 4h
# ============================================================

HORIZONS = [
    6,
    12,
    48,
]


BAR_MINUTES = 5


# ============================================================
# COST MODEL
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

MIN_SAMPLES = 300

TARGET_PF = 1.08

MIN_ASSETS_PF_GT_1 = 3


# ============================================================
# BINANCE PUBLIC FUNDING ENDPOINT
# ============================================================

FUNDING_URL = (
    "https://fapi.binance.com"
    "/fapi/v1/fundingRate"
)


# ============================================================
# LOCAL CSV LOADER
#
# Torna o script independente do pacote research.
# ============================================================

def load_csv(path):

    df = pd.read_csv(
        path
    )


    if "open_time" in df.columns:

        df["open_time"] = pd.to_datetime(
            df["open_time"],
            format="mixed",
            utc=True,
            errors="coerce",
        )


    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trades",
        "taker_buy_base",
        "taker_buy_quote",
    ]


    for column in numeric_columns:

        if column in df.columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )


    return df


# ============================================================
# TIMESTAMP -> MILLISECONDS
# ============================================================

def timestamp_ms(ts):

    return int(
        ts.timestamp()
        *
        1000
    )


# ============================================================
# COST COLUMN
# ============================================================

def cost_column(cost):

    bps = int(
        round(
            cost
            *
            10000
        )
    )

    return (
        f"net_{bps}bps"
    )


# ============================================================
# DOWNLOAD FUNDING HISTORY
# ============================================================

def download_funding(
    symbol,
    start,
    end,
):

    print(
        f"{symbol}: baixando funding history..."
    )


    start_ms = timestamp_ms(
        start
    )


    # end exclusive
    end_ms = (
        timestamp_ms(
            end
        )
        -
        1
    )


    current = start_ms

    rows = []


    while current <= end_ms:


        params = {
            "symbol": symbol,
            "startTime": current,
            "endTime": end_ms,
            "limit": 1000,
        }


        response = requests.get(
            FUNDING_URL,
            params=params,
            timeout=30,
        )


        response.raise_for_status()


        batch = response.json()


        if not batch:
            break


        rows.extend(
            batch
        )


        last_time = int(
            batch[-1][
                "fundingTime"
            ]
        )


        next_start = (
            last_time
            +
            1
        )


        if next_start <= current:

            raise RuntimeError(
                f"{symbol}: paginação "
                f"de funding travada em "
                f"{current}"
            )


        current = next_start


        time.sleep(
            0.10
        )


        if len(batch) < 1000:
            break


    if not rows:

        raise RuntimeError(
            f"{symbol}: nenhum funding obtido."
        )


    df = pd.DataFrame(
        rows
    )


    # ========================================================
    # TIMESTAMP
    # ========================================================

    df["fundingTime"] = pd.to_datetime(
        df["fundingTime"],
        unit="ms",
        utc=True,
        errors="coerce",
    )


    # ========================================================
    # RATE
    # ========================================================

    df["fundingRate"] = pd.to_numeric(
        df["fundingRate"],
        errors="coerce",
    )


    if "markPrice" in df.columns:

        df["markPrice"] = pd.to_numeric(
            df["markPrice"],
            errors="coerce",
        )


    # ========================================================
    # CLEAN
    # ========================================================

    df = (
        df

        .dropna(
            subset=[
                "fundingTime",
                "fundingRate",
            ]
        )

        .drop_duplicates(
            subset=[
                "fundingTime",
            ]
        )

        .sort_values(
            "fundingTime"
        )

        .reset_index(
            drop=True
        )
    )


    df = df[
        (
            df[
                "fundingTime"
            ]
            >=
            start
        )
        &
        (
            df[
                "fundingTime"
            ]
            <
            end
        )
    ].copy()


    return df


# ============================================================
# LOAD / DOWNLOAD FUNDING
# ============================================================

def load_funding(symbol):

    path = (
        DATA_DIR
        /
        (
            f"{symbol}_funding_"
            "2024-01-01_"
            "2026-08-01.csv"
        )
    )


    # ========================================================
    # LOCAL OR DOWNLOAD
    # ========================================================

    if path.exists():

        print(
            f"{symbol}: funding local encontrado."
        )


        df = pd.read_csv(
            path
        )


    else:

        df = download_funding(
            symbol,
            DEV_START,
            DEV_END,
        )


        df.to_csv(
            path,
            index=False,
        )


        print(
            f"{symbol}: funding salvo em "
            f"{path}"
        )


    # ========================================================
    # REQUIRED COLUMNS
    # ========================================================

    required = [
        "fundingTime",
        "fundingRate",
    ]


    missing = [
        column
        for column in required
        if column not in df.columns
    ]


    if missing:

        raise RuntimeError(
            f"{symbol}: colunas ausentes "
            f"no funding CSV: {missing}"
        )


    # ========================================================
    # DATETIME
    #
    # CRITICAL FIX:
    #
    # O CSV pode ter timestamps como:
    #
    # 2024-01-01 08:00:00+00:00
    #
    # e:
    #
    # 2024-01-05 00:00:00.001000+00:00
    #
    # format="mixed" aceita ambos.
    # ========================================================

    df["fundingTime"] = pd.to_datetime(
        df["fundingTime"],
        format="mixed",
        utc=True,
        errors="coerce",
    )


    # ========================================================
    # RATE
    # ========================================================

    df["fundingRate"] = pd.to_numeric(
        df["fundingRate"],
        errors="coerce",
    )


    if "markPrice" in df.columns:

        df["markPrice"] = pd.to_numeric(
            df["markPrice"],
            errors="coerce",
        )


    # ========================================================
    # INVALID
    # ========================================================

    invalid_time = int(
        df[
            "fundingTime"
        ]
        .isna()
        .sum()
    )


    invalid_rate = int(
        df[
            "fundingRate"
        ]
        .isna()
        .sum()
    )


    if invalid_time:

        print(
            f"{symbol}: ATENÇÃO — "
            f"{invalid_time} fundingTime inválidos."
        )


    if invalid_rate:

        print(
            f"{symbol}: ATENÇÃO — "
            f"{invalid_rate} fundingRate inválidos."
        )


    # ========================================================
    # CLEAN
    # ========================================================

    df = (
        df

        .dropna(
            subset=[
                "fundingTime",
                "fundingRate",
            ]
        )

        .drop_duplicates(
            subset=[
                "fundingTime",
            ]
        )

        .sort_values(
            "fundingTime"
        )

        .reset_index(
            drop=True
        )
    )


    # ========================================================
    # DEVELOPMENT ONLY
    # ========================================================

    df = df[
        (
            df[
                "fundingTime"
            ]
            >=
            DEV_START
        )
        &
        (
            df[
                "fundingTime"
            ]
            <
            DEV_END
        )
    ].copy()


    df = df.reset_index(
        drop=True
    )


    # ========================================================
    # SANITY
    # ========================================================

    print(
        f"{symbol}: funding carregados = "
        f"{len(df)}"
    )


    if not df.empty:

        print(
            f"{symbol}: primeiro funding = "
            f"{df['fundingTime'].iloc[0]}"
        )


        print(
            f"{symbol}: último funding = "
            f"{df['fundingTime'].iloc[-1]}"
        )


        print(
            f"{symbol}: funding min = "
            f"{df['fundingRate'].min():.8f}"
        )


        print(
            f"{symbol}: funding median = "
            f"{df['fundingRate'].median():.8f}"
        )


        print(
            f"{symbol}: funding max = "
            f"{df['fundingRate'].max():.8f}"
        )


    return df


# ============================================================
# LOAD PRICE HISTORY
# ============================================================

def load_price(symbol):

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
                f"Arquivo de preço ausente: "
                f"{path}"
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


    # ========================================================
    # DATETIME AGAIN FOR SAFETY
    # ========================================================

    result["open_time"] = pd.to_datetime(
        result["open_time"],
        format="mixed",
        utc=True,
        errors="coerce",
    )


    # ========================================================
    # NUMERIC
    # ========================================================

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:

        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )


    # ========================================================
    # CLEAN
    # ========================================================

    result = (
        result

        .dropna(
            subset=[
                "open_time",
                "open",
                "close",
            ]
        )

        .drop_duplicates(
            subset=[
                "open_time",
            ]
        )

        .sort_values(
            "open_time"
        )

        .reset_index(
            drop=True
        )
    )


    result = result[
        (
            result[
                "open_time"
            ]
            >=
            DEV_START
        )
        &
        (
            result[
                "open_time"
            ]
            <
            DEV_END
        )
    ].copy()


    result = result.reset_index(
        drop=True
    )


    return result


# ============================================================
# PROFIT FACTOR
# ============================================================

def profit_factor(returns):

    values = (
        pd.Series(
            returns
        )
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


    return (
        gains
        /
        losses
    )


# ============================================================
# TRIMMED MEAN
# ============================================================

def trimmed_mean(
    returns,
    trim=0.05,
):

    values = np.asarray(
        pd.Series(
            returns
        )
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
# WINSORIZED MEAN
# ============================================================

def winsorized_mean(
    returns,
    limit=0.05,
):

    values = np.asarray(
        pd.Series(
            returns
        )
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

def summarize(returns):

    values = (
        pd.Series(
            returns
        )
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
            trimmed_mean(
                values
            ),

        "winsorized_mean_5":
            winsorized_mean(
                values
            ),

        "win_rate":
            (
                values > 0
            ).mean(),

        "profit_factor":
            profit_factor(
                values
            ),

        "q10":
            values.quantile(
                0.10
            ),

        "q90":
            values.quantile(
                0.90
            ),

    }


# ============================================================
# BUILD FUNDING EVENTS
# ============================================================

event_frames = []


for symbol in SYMBOLS:


    print()

    print(
        "=" * 100
    )

    print(
        f"PROCESSANDO FUNDING — {symbol}"
    )

    print(
        "=" * 100
    )


    funding = load_funding(
        symbol
    )


    price = load_price(
        symbol
    )


    print(
        f"{symbol}: funding records = "
        f"{len(funding)}"
    )


    print(
        f"{symbol}: price candles = "
        f"{len(price)}"
    )


    # ========================================================
    # NEXT FUNDING TIME
    # ========================================================

    funding[
        "next_funding_time"
    ] = (
        funding[
            "fundingTime"
        ]
        .shift(-1)
    )


    # ========================================================
    # ROLLING FUNDING MEAN
    # ========================================================

    funding[
        "funding_mean"
    ] = (
        funding[
            "fundingRate"
        ]

        .rolling(
            FUNDING_LOOKBACK,
            min_periods=FUNDING_MIN_PERIODS,
        )

        .mean()

        .shift(1)
    )


    # ========================================================
    # ROLLING FUNDING STD
    # ========================================================

    funding[
        "funding_std"
    ] = (
        funding[
            "fundingRate"
        ]

        .rolling(
            FUNDING_LOOKBACK,
            min_periods=FUNDING_MIN_PERIODS,
        )

        .std()

        .shift(1)
    )


    # ========================================================
    # Q05
    # ========================================================

    funding[
        "funding_q05"
    ] = (
        funding[
            "fundingRate"
        ]

        .rolling(
            FUNDING_LOOKBACK,
            min_periods=FUNDING_MIN_PERIODS,
        )

        .quantile(
            LOW_QUANTILE
        )

        .shift(1)
    )


    # ========================================================
    # Q95
    # ========================================================

    funding[
        "funding_q95"
    ] = (
        funding[
            "fundingRate"
        ]

        .rolling(
            FUNDING_LOOKBACK,
            min_periods=FUNDING_MIN_PERIODS,
        )

        .quantile(
            HIGH_QUANTILE
        )

        .shift(1)
    )


    # ========================================================
    # FUNDING Z
    # ========================================================

    funding[
        "funding_z"
    ] = np.where(

        (
            funding[
                "funding_std"
            ].notna()
        )

        &

        (
            funding[
                "funding_std"
            ]
            >
            0
        ),

        (
            funding[
                "fundingRate"
            ]
            -
            funding[
                "funding_mean"
            ]
        )
        /
        funding[
            "funding_std"
        ],

        np.nan,

    )


    # ========================================================
    # VALID CONTEXT
    # ========================================================

    valid_context = (

        funding[
            "funding_q05"
        ].notna()

        &

        funding[
            "funding_q95"
        ].notna()

    )


    print(
        f"{symbol}: contextos válidos = "
        f"{int(valid_context.sum())}"
    )


    # ========================================================
    # HIGH FUNDING
    # ========================================================

    high_funding = (

        valid_context

        &

        (
            funding[
                "fundingRate"
            ]
            >=
            funding[
                "funding_q95"
            ]
        )

    )


    # ========================================================
    # LOW FUNDING
    # ========================================================

    low_funding = (

        valid_context

        &

        (
            funding[
                "fundingRate"
            ]
            <=
            funding[
                "funding_q05"
            ]
        )

    )


    high_count = int(
        high_funding.sum()
    )


    low_count = int(
        low_funding.sum()
    )


    print(
        f"{symbol}: HIGH_FUNDING = "
        f"{high_count}"
    )


    print(
        f"{symbol}: LOW_FUNDING  = "
        f"{low_count}"
    )


    if (
        high_count == 0
        and
        low_count == 0
    ):

        raise RuntimeError(
            f"{symbol}: nenhum funding "
            f"extremo encontrado."
        )


    # ========================================================
    # PRICE SANITY
    # ========================================================

    price[
        "open_time"
    ] = pd.to_datetime(
        price[
            "open_time"
        ],
        format="mixed",
        utc=True,
        errors="coerce",
    )


    price = (
        price

        .dropna(
            subset=[
                "open_time",
                "open",
                "close",
            ]
        )

        .sort_values(
            "open_time"
        )

        .drop_duplicates(
            subset=[
                "open_time",
            ]
        )

        .reset_index(
            drop=True
        )
    )


    price_time_index = pd.DatetimeIndex(
    price["open_time"]
    )


    price_open = (
        price[
            "open"
        ]
        .to_numpy(
            dtype=float
        )
    )


    price_close = (
        price[
            "close"
        ]
        .to_numpy(
            dtype=float
        )
    )


    print(
        f"{symbol}: primeiro candle = "
        f"{price['open_time'].iloc[0]}"
    )


    print(
        f"{symbol}: último candle = "
        f"{price['open_time'].iloc[-1]}"
    )


    # ========================================================
    # MASKS
    # ========================================================

    masks = {

        "HIGH_FUNDING":
            high_funding,

        "LOW_FUNDING":
            low_funding,

    }


    symbol_events_created = 0


    # ========================================================
    # PROCESS FUNDING EVENTS
    # ========================================================

    for event_name, mask in masks.items():


        subset = (
            funding.loc[
                mask
            ]
            .copy()
        )


        print(
            f"{symbol}: construindo "
            f"{event_name}: "
            f"{len(subset)} candidatos"
        )


        event_created = 0

        no_entry = 0

        invalid_entry_price = 0

        no_valid_horizon = 0


        for _, event in subset.iterrows():


            funding_time = pd.Timestamp(
                event[
                    "fundingTime"
                ]
            )

            # =================================================
            # ENTRY
            #
            # Primeiro candle estritamente depois do funding.
            #
            # funding:
            # 08:00:00
            #
            # entry:
            # 08:05:00
            # =================================================

            entry_idx = int(
                price_time_index.searchsorted(
                    funding_time,
                    side="right",
                )
            )


            if entry_idx >= len(price):

                no_entry += 1
                continue


            entry_time = (
                price[
                    "open_time"
                ]
                .iloc[
                    entry_idx
                ]
            )


            entry_price = float(
                price_open[
                    entry_idx
                ]
            )


            if (
                not np.isfinite(
                    entry_price
                )
                or
                entry_price <= 0
            ):

                invalid_entry_price += 1
                continue


            # =================================================
            # LOOKAHEAD CHECK
            # =================================================

            if (
                entry_time
                <=
                funding_time
            ):

                raise RuntimeError(
                    f"LOOKAHEAD {symbol}: "
                    f"funding={funding_time}, "
                    f"entry={entry_time}"
                )


            # =================================================
            # BASE EVENT RECORD
            # =================================================

            record = {

                "symbol":
                    symbol,

                "event":
                    event_name,

                "funding_time":
                    funding_time,

                "next_funding_time":
                    event[
                        "next_funding_time"
                    ],

                "entry_time":
                    entry_time,

                "entry_price":
                    entry_price,

                "funding_rate":
                    float(
                        event[
                            "fundingRate"
                        ]
                    ),

                "funding_q05":
                    float(
                        event[
                            "funding_q05"
                        ]
                    ),

                "funding_q95":
                    float(
                        event[
                            "funding_q95"
                        ]
                    ),

                "funding_mean":
                    event[
                        "funding_mean"
                    ],

                "funding_std":
                    event[
                        "funding_std"
                    ],

                "funding_z":
                    event[
                        "funding_z"
                    ],

                "year":
                    funding_time.strftime(
                        "%Y"
                    ),

                "period":
                    funding_time.strftime(
                        "%Y-%m"
                    ),

            }


            valid_event = False


            # =================================================
            # FUTURE HORIZONS
            # =================================================

            for horizon in HORIZONS:


                long_col = (
                    f"future_long_{horizon}"
                )


                short_col = (
                    f"future_short_{horizon}"
                )


                # =================================================
                # Example:
                #
                # Entry 08:05
                #
                # horizon 6:
                #
                # candles:
                # 08:05
                # 08:10
                # 08:15
                # 08:20
                # 08:25
                # 08:30
                #
                # Exit close = 08:35
                #
                # 30 minutos.
                # =================================================

                exit_idx = (
                    entry_idx
                    +
                    horizon
                    -
                    1
                )


                if exit_idx >= len(price):

                    record[
                        long_col
                    ] = np.nan

                    record[
                        short_col
                    ] = np.nan

                    continue


                exit_open_time = (
                    price[
                        "open_time"
                    ]
                    .iloc[
                        exit_idx
                    ]
                )


                exit_time = (
                    exit_open_time
                    +
                    pd.Timedelta(
                        minutes=BAR_MINUTES
                    )
                )


                # =================================================
                # DEVELOPMENT BOUNDARY
                # =================================================

                if (
                    exit_time
                    >
                    DEV_END
                ):

                    record[
                        long_col
                    ] = np.nan

                    record[
                        short_col
                    ] = np.nan

                    continue


                # =================================================
                # DO NOT CROSS NEXT FUNDING
                # =================================================

                next_funding = (
                    event[
                        "next_funding_time"
                    ]
                )


                if pd.notna(
                    next_funding
                ):


                    next_funding = pd.Timestamp(
                        next_funding
                    )


                    if (
                        exit_time
                        >=
                        next_funding
                    ):

                        record[
                            long_col
                        ] = np.nan

                        record[
                            short_col
                        ] = np.nan

                        continue


                # =================================================
                # EXIT PRICE
                # =================================================

                exit_price = float(
                    price_close[
                        exit_idx
                    ]
                )


                if (
                    not np.isfinite(
                        exit_price
                    )
                    or
                    exit_price <= 0
                ):

                    record[
                        long_col
                    ] = np.nan

                    record[
                        short_col
                    ] = np.nan

                    continue


                # =================================================
                # LONG PNL
                # =================================================

                long_return = (
                    exit_price
                    /
                    entry_price
                    -
                    1.0
                )


                # =================================================
                # SHORT PNL
                #
                # Linear USDT Futures approximation
                # =================================================

                short_return = (
                    1.0
                    -
                    exit_price
                    /
                    entry_price
                )


                record[
                    long_col
                ] = long_return


                record[
                    short_col
                ] = short_return


                valid_event = True


            # =================================================
            # SAVE
            # =================================================

            if valid_event:


                event_frames.append(
                    record
                )


                event_created += 1


                symbol_events_created += 1


            else:

                no_valid_horizon += 1


        # ====================================================
        # EVENT SANITY
        # ====================================================

        print(
            f"{symbol} {event_name}: "
            f"criados={event_created}, "
            f"sem_entry={no_entry}, "
            f"entry_invalida={invalid_entry_price}, "
            f"sem_horizonte={no_valid_horizon}"
        )


    print(
        f"{symbol}: TOTAL EVENTOS CRIADOS = "
        f"{symbol_events_created}"
    )


# ============================================================
# FINAL EVENT SANITY
# ============================================================

print()

print(
    "=" * 100
)

print(
    "SANITY — EVENTOS FUNDING"
)

print(
    "=" * 100
)


print(
    f"Total event_frames = "
    f"{len(event_frames)}"
)


if not event_frames:

    raise RuntimeError(
        "Nenhum evento de funding foi criado. "
        "Veja os sanity checks acima."
    )


# ============================================================
# EVENT DATAFRAME
# ============================================================

events = pd.DataFrame(
    event_frames
)


# ============================================================
# DATETIME PARSING
#
# format=mixed evita erro com timestamps
# com microssegundos.
# ============================================================

events[
    "funding_time"
] = pd.to_datetime(
    events[
        "funding_time"
    ],
    format="mixed",
    utc=True,
    errors="coerce",
)


events[
    "entry_time"
] = pd.to_datetime(
    events[
        "entry_time"
    ],
    format="mixed",
    utc=True,
    errors="coerce",
)


events[
    "next_funding_time"
] = pd.to_datetime(
    events[
        "next_funding_time"
    ],
    format="mixed",
    utc=True,
    errors="coerce",
)


events = (
    events

    .dropna(
        subset=[
            "funding_time",
            "entry_time",
        ]
    )

    .sort_values(
        [
            "funding_time",
            "symbol",
        ]
    )

    .reset_index(
        drop=True
    )
)


# ============================================================
# LOOKAHEAD SANITY
# ============================================================

if (
    events[
        "funding_time"
    ]
    >=
    DEV_END
).any():

    raise RuntimeError(
        "CONTAMINAÇÃO: funding "
        "após julho/2026 encontrado."
    )


if (
    events[
        "entry_time"
    ]
    <=
    events[
        "funding_time"
    ]
).any():

    raise RuntimeError(
        "LOOKAHEAD: alguma entrada ocorreu "
        "antes ou no mesmo instante do funding."
    )


# ============================================================
# EVENT COUNTS
# ============================================================

counts = (

    events

    .groupby(
        [
            "event",
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
# FUNDING ANATOMY
# ============================================================

anatomy = (

    events

    .groupby(
        "event",
        as_index=False,
    )

    .agg(

        samples=(
            "event",
            "size",
        ),

        mean_funding_rate=(
            "funding_rate",
            "mean",
        ),

        median_funding_rate=(
            "funding_rate",
            "median",
        ),

        mean_funding_z=(
            "funding_z",
            "mean",
        ),

        median_funding_z=(
            "funding_z",
            "median",
        ),

        min_funding_rate=(
            "funding_rate",
            "min",
        ),

        max_funding_rate=(
            "funding_rate",
            "max",
        ),

    )

)


# ============================================================
# HYPOTHESES
# ============================================================

HYPOTHESES = {

    # ========================================================
    # CONTRARIAN / CROWDING
    # ========================================================

    "HIGH_FUNDING_SHORT":
        (
            "HIGH_FUNDING",
            "SHORT",
        ),

    "LOW_FUNDING_LONG":
        (
            "LOW_FUNDING",
            "LONG",
        ),


    # ========================================================
    # CONTROLS
    # ========================================================

    "HIGH_FUNDING_LONG":
        (
            "HIGH_FUNDING",
            "LONG",
        ),

    "LOW_FUNDING_SHORT":
        (
            "LOW_FUNDING",
            "SHORT",
        ),

}


# ============================================================
# GLOBAL RESULTS
# ============================================================

global_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "event"
        ]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        gross = (
            subset[
                return_column
            ]
            .dropna()
        )


        for cost in COSTS:


            returns = (
                gross
                -
                cost
            )


            global_rows.append({

                "hypothesis":
                    hypothesis,

                "minutes":
                    horizon
                    *
                    BAR_MINUTES,

                "cost":
                    cost,

                **summarize(
                    returns
                ),

            })


global_results = pd.DataFrame(
    global_rows
)


# ============================================================
# BY YEAR
# ============================================================

year_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "event"
        ]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for year, group in subset.groupby(
            "year"
        ):


            gross = (
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
                        horizon
                        *
                        BAR_MINUTES,

                    "year":
                        year,

                    "cost":
                        cost,

                    **summarize(
                        gross
                        -
                        cost
                    ),

                })


by_year = pd.DataFrame(
    year_rows
)


# ============================================================
# BY ASSET
# ============================================================

asset_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "event"
        ]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for symbol, group in subset.groupby(
            "symbol"
        ):


            gross = (
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
                        horizon
                        *
                        BAR_MINUTES,

                    "symbol":
                        symbol,

                    "cost":
                        cost,

                    **summarize(
                        gross
                        -
                        cost
                    ),

                })


by_asset = pd.DataFrame(
    asset_rows
)


# ============================================================
# MONTHLY @ BASE COST
# ============================================================

monthly_rows = []


for hypothesis, (
    event_name,
    side,
) in HYPOTHESES.items():


    subset = events[
        events[
            "event"
        ]
        ==
        event_name
    ]


    for horizon in HORIZONS:


        if side == "LONG":

            return_column = (
                f"future_long_{horizon}"
            )

        else:

            return_column = (
                f"future_short_{horizon}"
            )


        for period, group in subset.groupby(
            "period"
        ):


            gross = (
                group[
                    return_column
                ]
                .dropna()
            )


            monthly_rows.append({

                "hypothesis":
                    hypothesis,

                "minutes":
                    horizon
                    *
                    BAR_MINUTES,

                "period":
                    period,

                **summarize(
                    gross
                    -
                    BASE_COST
                ),

            })


monthly = pd.DataFrame(
    monthly_rows
)


# ============================================================
# STABILITY @ 0.06%
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
                len(
                    years
                ),

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
                len(
                    assets
                ),

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
                len(
                    months
                ),

            "median_month_pf":
                months[
                    "profit_factor"
                ].median(),

        })


stability = pd.DataFrame(
    stability_rows
)


# ============================================================
# DISCOVERY GATE
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
# DISPLAY HELPER
# ============================================================

def percent_display(df):

    result = df.copy()


    columns = [

        "cost",

        "mean_return",
        "median_return",

        "trimmed_mean_5",
        "winsorized_mean_5",

        "win_rate",

        "q10",
        "q90",

        "mean_funding_rate",
        "median_funding_rate",

        "min_funding_rate",
        "max_funding_rate",

    ]


    for column in columns:

        if column in result.columns:

            result[
                column
            ] *= 100


    return result


anatomy_display = percent_display(
    anatomy
)


global_display = percent_display(
    global_results
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
    400,
)


# ============================================================
# OUTPUT
# ============================================================

print()

print(
    "=" * 220
)

print(
    "EXPERIMENTO 31 — "
    "BRANCH 08 POST-FUNDING CROWDING"
)

print(
    "=" * 220
)

print()


# ============================================================
# COUNTS
# ============================================================

print(
    "EVENT COUNTS"
)

print()


print(
    counts.to_string(
        index=False
    )
)


# ============================================================
# ANATOMY
# ============================================================

print()

print(
    "=" * 220
)

print(
    "FUNDING ANATOMY"
)

print(
    "=" * 220
)

print()


print(
    anatomy_display.to_string(
        index=False
    )
)


# ============================================================
# GLOBAL
# ============================================================

print()

print(
    "=" * 220
)

print(
    "GLOBAL HYPOTHESES"
)

print(
    "=" * 220
)

print()


print(

    global_display

    .sort_values(
        [
            "hypothesis",
            "minutes",
            "cost",
        ]
    )

    .to_string(
        index=False
    )

)


# ============================================================
# STABILITY
# ============================================================

print()

print(
    "=" * 220
)

print(
    "STABILITY @ 0.06%"
)

print(
    "=" * 220
)

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
# DISCOVERY GATE
# ============================================================

print()

print(
    "=" * 220
)

print(
    "DISCOVERY GATE"
)

print(
    "=" * 220
)

print()


passed = stability[
    stability[
        "basic_discovery_gate"
    ]
].copy()


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

        .to_string(
            index=False
        )
    )


# ============================================================
# SAVE RESULTS
# ============================================================

events.to_csv(
    RESULTS_DIR
    / "funding_crowding_events.csv",
    index=False,
)


counts.to_csv(
    RESULTS_DIR
    / "funding_crowding_counts.csv",
    index=False,
)


anatomy.to_csv(
    RESULTS_DIR
    / "funding_crowding_anatomy.csv",
    index=False,
)


global_results.to_csv(
    RESULTS_DIR
    / "funding_crowding_global.csv",
    index=False,
)


by_year.to_csv(
    RESULTS_DIR
    / "funding_crowding_by_year.csv",
    index=False,
)


by_asset.to_csv(
    RESULTS_DIR
    / "funding_crowding_by_asset.csv",
    index=False,
)


monthly.to_csv(
    RESULTS_DIR
    / "funding_crowding_monthly.csv",
    index=False,
)


stability.to_csv(
    RESULTS_DIR
    / "funding_crowding_stability.csv",
    index=False,
)


print()

print(
    "Arquivos salvos em results/"
)
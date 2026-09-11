import time

from datetime import datetime, timezone

from pathlib import Path

import requests
import pandas as pd


BASE_URL = "https://fapi.binance.com"

KLINE_URL = (
    BASE_URL +
    "/fapi/v1/klines"
)


COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_base",
    "taker_buy_quote",
    "ignore",
]


def date_to_ms(date_string: str) -> int:

    dt = datetime.strptime(
        date_string,
        "%Y-%m-%d",
    )

    dt = dt.replace(
        tzinfo=timezone.utc
    )

    return int(
        dt.timestamp() * 1000
    )


def fetch_klines(
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:

    start_ms = date_to_ms(
        start_date
    )

    end_ms = date_to_ms(
        end_date
    )

    rows = []

    cursor = start_ms


    while cursor < end_ms:

        params = {

            "symbol": symbol,

            "interval": interval,

            "limit": 1500,

            "startTime": cursor,

            "endTime": end_ms,

        }


        response = requests.get(

            KLINE_URL,

            params=params,

            timeout=20,

        )


        response.raise_for_status()


        batch = response.json()


        if not batch:

            break


        rows.extend(batch)


        last_open_time = int(
            batch[-1][0]
        )


        next_cursor = (
            last_open_time + 1
        )


        if next_cursor <= cursor:

            break


        cursor = next_cursor


        if len(batch) < 1500:

            break


        time.sleep(0.15)


    df = pd.DataFrame(
        rows,
        columns=COLUMNS,
    )


    if df.empty:

        return df


    numeric_columns = [

        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",

    ]


    for column in numeric_columns:

        df[column] = pd.to_numeric(

            df[column],

            errors="coerce",

        )


    df["open_time"] = pd.to_datetime(

        df["open_time"],

        unit="ms",

        utc=True,

    )


    df["close_time"] = pd.to_datetime(

        df["close_time"],

        unit="ms",

        utc=True,

    )


    df = df.drop_duplicates(
        subset=["open_time"]
    )


    df = df.sort_values(
        "open_time"
    )


    df = df.reset_index(
        drop=True
    )


    # Remove candle ainda aberta.

    now = pd.Timestamp.now(
        tz="UTC"
    )


    df = df[
        df["close_time"] <= now
    ].copy()


    return df


def save_csv(
    df: pd.DataFrame,
    path: Path,
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        path,
        index=False,
    )


def load_csv(
    path: Path,
) -> pd.DataFrame:

    df = pd.read_csv(

        path,

        parse_dates=[
            "open_time",
            "close_time",
        ],

    )


    return (
        df
        .sort_values("open_time")
        .reset_index(drop=True)
    )
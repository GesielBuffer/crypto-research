from research.binance_data import fetch_klines
from research.indicators import add_all_indicators


df = fetch_klines(
    "BTCUSDT",
    "5m",
    "2026-01-01",
    "2026-01-02",
)


df = add_all_indicators(df)


columns = [
    "open_time",
    "close",
    "ema_9",
    "ema_21",
    "ema_35",
    "macd",
    "macd_signal",
    "macd_hist",
    "rsi",
    "atr",
    "plus_di",
    "minus_di",
    "adx",
    "volume",
    "volume_ratio",
]


print(
    df[columns].tail(10)
)
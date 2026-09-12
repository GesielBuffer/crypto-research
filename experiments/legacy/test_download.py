from research.binance_data import fetch_klines


df = fetch_klines(
    "BTCUSDT",
    "5m",
    "2026-01-01",
    "2026-01-02",
)


print(df.head())

print()

print(
    "Quantidade de candles:",
    len(df)
)
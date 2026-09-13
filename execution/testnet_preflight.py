"""Read-only Binance USD-M Testnet preflight. It never submits or cancels orders."""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv

from execution.binance_testnet import BinanceUsdMTestnetExchange
from execution.config import RuntimeConfig


def main() -> int:
    load_dotenv()
    config = RuntimeConfig.from_mapping(os.environ)
    if config.mode != "testnet":
        print(json.dumps({
            "testnet_ready": False,
            "blockers": ["BOT_MODE_is_not_testnet"],
        }, indent=2))
        return 2
    exchange = BinanceUsdMTestnetExchange(
        config.binance_api_key,
        config.binance_api_secret,
    )
    blockers = exchange.preflight_blockers()
    print(json.dumps({
        "testnet_ready": not blockers,
        "blockers": blockers,
    }, indent=2))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())

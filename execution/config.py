from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


def _boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return normalized == "true"


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str
    approved_strategy_id: str
    real_trading_enabled: bool
    binance_api_key: str = ""
    binance_api_secret: str = ""

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "RuntimeConfig":
        mode = values.get("BOT_MODE", "paper").strip().lower()
        if mode not in {"paper", "testnet"}:
            raise ValueError("BOT_MODE must be paper or testnet; live is not supported")
        real_enabled = _boolean(
            values.get("REAL_TRADING_ENABLED", "false"), "REAL_TRADING_ENABLED"
        )
        if real_enabled:
            raise ValueError("real trading cannot be enabled by environment variable")
        config = cls(
            mode=mode,
            approved_strategy_id=values.get("APPROVED_STRATEGY_ID", "").strip(),
            real_trading_enabled=real_enabled,
            binance_api_key=values.get("BINANCE_TESTNET_API_KEY", ""),
            binance_api_secret=values.get("BINANCE_TESTNET_API_SECRET", ""),
        )
        if mode == "testnet" and (
            not config.binance_api_key or not config.binance_api_secret
        ):
            raise ValueError("testnet mode requires Binance testnet credentials")
        return config

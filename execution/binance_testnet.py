"""USD-M Futures adapter that is structurally restricted to Binance Testnet."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode

import requests

from execution.models import (
    Fill,
    OrderIntent,
    ProtectionReceipt,
    Side,
    child_order_id,
)
from execution.risk import RiskSnapshot


TESTNET_BASE_URL = "https://testnet.binancefuture.com"


class BinanceApiError(RuntimeError):
    def __init__(self, status_code: int, code: int | None, message: str):
        super().__init__(f"Binance API error {status_code}/{code}: {message}")
        self.status_code = status_code
        self.code = code


class BinanceUsdMTestnetExchange:
    """Signed REST gateway with no configurable production hostname."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        session=None,
        base_url: str = TESTNET_BASE_URL,
        clock_ms=None,
        kill_switch=None,
    ) -> None:
        if base_url.rstrip("/") != TESTNET_BASE_URL:
            raise ValueError("only Binance USD-M Testnet is allowed")
        if not api_key or not api_secret:
            raise ValueError("testnet API credentials are required")
        self.api_key = api_key
        self._secret = api_secret.encode("utf-8")
        self.session = session or requests.Session()
        self.base_url = TESTNET_BASE_URL
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self.kill_switch = kill_switch or (lambda: False)

    def _signed_request(self, method: str, path: str, params: dict | None = None):
        payload = dict(params or {})
        payload["recvWindow"] = 5000
        payload["timestamp"] = self.clock_ms()
        query = urlencode(payload)
        payload["signature"] = hmac.new(
            self._secret, query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        response = self.session.request(
            method,
            self.base_url + path,
            params=payload,
            headers={"X-MBX-APIKEY": self.api_key},
            timeout=10,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise BinanceApiError(response.status_code, None, "invalid JSON response") from exc
        if response.status_code >= 400:
            raise BinanceApiError(
                response.status_code,
                body.get("code") if isinstance(body, dict) else None,
                body.get("msg", "request failed") if isinstance(body, dict) else "request failed",
            )
        return body

    @staticmethod
    def _fill_from_response(body: dict) -> Fill | None:
        quantity = Decimal(str(body.get("executedQty", "0")))
        if quantity <= 0:
            return None
        price = Decimal(str(body.get("avgPrice", "0")))
        if price <= 0:
            raise ValueError("filled testnet order has no average price")
        timestamp = int(body.get("updateTime", body.get("time", 0)))
        return Fill(
            client_order_id=body["clientOrderId"],
            symbol=body["symbol"],
            side=Side(body["side"]),
            quantity=quantity,
            price=price,
            filled_at=datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc),
        )

    def find_fill(self, intent: OrderIntent) -> Fill | None:
        try:
            body = self._signed_request(
                "GET",
                "/fapi/v1/order",
                {"symbol": intent.symbol, "origClientOrderId": intent.client_order_id},
            )
        except BinanceApiError as exc:
            if exc.code == -2013:
                return None
            raise
        return self._fill_from_response(body)

    def find_protection(self, intent: OrderIntent) -> ProtectionReceipt | None:
        orders = self._signed_request(
            "GET", "/fapi/v1/openAlgoOrders", {"symbol": intent.symbol}
        )
        open_ids = {row.get("clientAlgoId") for row in orders}
        stop_id = child_order_id(intent.client_order_id, "sl")
        take_profit_id = child_order_id(intent.client_order_id, "tp")
        if stop_id in open_ids and take_profit_id in open_ids:
            return ProtectionReceipt(intent.client_order_id, stop_id, take_profit_id)
        return None

    def submit_protection(
        self, intent: OrderIntent, entry_fill: Fill
    ) -> ProtectionReceipt:
        existing = self.find_protection(intent)
        if existing is not None:
            return existing
        exit_side = entry_fill.side.opposite.value
        stop_id = child_order_id(intent.client_order_id, "sl")
        take_profit_id = child_order_id(intent.client_order_id, "tp")
        common = {
            "algoType": "CONDITIONAL",
            "symbol": intent.symbol,
            "side": exit_side,
            "closePosition": "true",
            "workingType": "MARK_PRICE",
            "priceProtect": "TRUE",
        }
        stop = self._signed_request(
            "POST",
            "/fapi/v1/algoOrder",
            {
                **common,
                "type": "STOP_MARKET",
                "triggerPrice": str(intent.protection.stop_loss_price),
                "clientAlgoId": stop_id,
            },
        )
        take_profit = self._signed_request(
            "POST",
            "/fapi/v1/algoOrder",
            {
                **common,
                "type": "TAKE_PROFIT_MARKET",
                "triggerPrice": str(intent.protection.take_profit_price),
                "clientAlgoId": take_profit_id,
            },
        )
        if (
            stop.get("clientAlgoId") != stop_id
            or take_profit.get("clientAlgoId") != take_profit_id
        ):
            raise RuntimeError("testnet did not confirm both protection orders")
        return ProtectionReceipt(intent.client_order_id, stop_id, take_profit_id)

    def emergency_close(self, intent: OrderIntent, entry_fill: Fill) -> Fill:
        exit_id = child_order_id(intent.client_order_id, "exit")
        emergency_intent = OrderIntent(
            strategy_id=intent.strategy_id,
            symbol=intent.symbol,
            side=entry_fill.side.opposite,
            quantity=entry_fill.quantity,
            reference_price=entry_fill.price,
            leverage=intent.leverage,
            client_order_id=exit_id,
            market_data_time=intent.market_data_time,
            protection=intent.protection,
        )
        existing = self.find_fill(emergency_intent)
        if existing is None:
            body = self._signed_request(
                "POST",
                "/fapi/v1/order",
                {
                    "symbol": intent.symbol,
                    "side": entry_fill.side.opposite.value,
                    "type": "MARKET",
                    "quantity": str(entry_fill.quantity),
                    "reduceOnly": "true",
                    "newClientOrderId": exit_id,
                    "newOrderRespType": "RESULT",
                },
            )
            existing = self._fill_from_response(body)
            if existing is None:
                raise RuntimeError("testnet emergency close did not return an execution")
        self._signed_request(
            "DELETE", "/fapi/v1/algoOpenOrders", {"symbol": intent.symbol}
        )
        return existing

    def find_emergency_exit(self, intent: OrderIntent) -> Fill | None:
        exit_intent = OrderIntent(
            strategy_id=intent.strategy_id,
            symbol=intent.symbol,
            side=intent.side.opposite,
            quantity=intent.quantity,
            reference_price=intent.reference_price,
            leverage=intent.leverage,
            client_order_id=child_order_id(intent.client_order_id, "exit"),
            market_data_time=intent.market_data_time,
            protection=intent.protection,
        )
        return self.find_fill(exit_intent)

    def submit_market(self, intent: OrderIntent) -> Fill:
        body = self._signed_request(
            "POST",
            "/fapi/v1/order",
            {
                "symbol": intent.symbol,
                "side": intent.side.value,
                "type": "MARKET",
                "quantity": str(intent.quantity),
                "newClientOrderId": intent.client_order_id,
                "newOrderRespType": "RESULT",
            },
        )
        fill = self._fill_from_response(body)
        if fill is None:
            raise RuntimeError("testnet market order did not return an execution")
        return fill

    def snapshot(self) -> RiskSnapshot:
        positions = self._signed_request("GET", "/fapi/v3/positionRisk")
        start_of_day = datetime.fromtimestamp(
            self.clock_ms() / 1000, tz=timezone.utc
        ).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        income = self._signed_request(
            "GET",
            "/fapi/v1/income",
            {"startTime": int(start_of_day.timestamp() * 1000), "limit": 1000},
        )
        return RiskSnapshot(
            open_symbols=frozenset(
                row["symbol"]
                for row in positions
                if Decimal(str(row.get("positionAmt", "0"))) != 0
            ),
            realized_pnl_today=sum(
                (Decimal(str(row.get("income", "0"))) for row in income),
                Decimal("0"),
            ),
            kill_switch=bool(self.kill_switch()),
        )

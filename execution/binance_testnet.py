"""USD-M Futures adapter that is structurally restricted to Binance Testnet."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from urllib.parse import urlencode

import requests

from execution.models import (
    Fill,
    MarkPrice,
    OrderIntent,
    ProtectionReceipt,
    Side,
    child_order_id,
)
from execution.risk import RiskSnapshot


TESTNET_BASE_URL = "https://testnet.binancefuture.com"


@dataclass(frozen=True)
class PriceFilter:
    minimum: Decimal
    maximum: Decimal
    tick_size: Decimal


@dataclass(frozen=True)
class QuantityFilter:
    minimum: Decimal
    maximum: Decimal
    step_size: Decimal


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
        self._price_filters: dict[str, PriceFilter] = {}
        self._quantity_filters: dict[str, QuantityFilter] = {}
        self._symbol_rows: dict[str, dict] = {}

    def _public_request(self, path: str, params: dict | None = None):
        response = self.session.request(
            "GET",
            self.base_url + path,
            params=dict(params or {}),
            timeout=10,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise BinanceApiError(
                response.status_code, None, "invalid JSON response"
            ) from exc
        if response.status_code >= 400:
            raise BinanceApiError(
                response.status_code,
                body.get("code") if isinstance(body, dict) else None,
                body.get("msg", "request failed")
                if isinstance(body, dict)
                else "request failed",
            )
        return body

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

    def get_mark_price(self, symbol: str) -> MarkPrice:
        body = self._public_request(
            "/fapi/v1/premiumIndex", {"symbol": symbol}
        )
        if not isinstance(body, dict):
            raise RuntimeError("testnet returned an invalid mark price response")
        if body.get("symbol") != symbol:
            raise RuntimeError("testnet returned mark price for another symbol")
        price = Decimal(str(body.get("markPrice", "0")))
        timestamp = int(body.get("time", 0))
        if not price.is_finite() or price <= 0 or timestamp <= 0:
            raise RuntimeError("testnet returned an invalid mark price")
        return MarkPrice(
            symbol=symbol,
            price=price,
            observed_at=datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc),
        )

    def _symbol_row(self, symbol: str) -> dict:
        cached = self._symbol_rows.get(symbol)
        if cached is not None:
            return cached
        body = self._public_request("/fapi/v1/exchangeInfo")
        if not isinstance(body, dict):
            raise RuntimeError("testnet returned invalid exchange information")
        self._symbol_rows.update(
            {
                row["symbol"]: row
                for row in body.get("symbols", [])
                if isinstance(row, dict) and row.get("symbol")
            }
        )
        symbol_row = self._symbol_rows.get(symbol)
        if symbol_row is None or symbol_row.get("status") != "TRADING":
            raise RuntimeError(f"{symbol} is not available for Testnet trading")
        return symbol_row

    def refresh_symbol_rules(self, symbol: str) -> None:
        self._symbol_rows.pop(symbol, None)
        self._price_filters.pop(symbol, None)
        self._quantity_filters.pop(symbol, None)
        self._symbol_row(symbol)

    def price_filter(self, symbol: str) -> PriceFilter:
        cached = self._price_filters.get(symbol)
        if cached is not None:
            return cached
        symbol_row = self._symbol_row(symbol)
        filter_row = next(
            (
                row
                for row in symbol_row.get("filters", [])
                if row.get("filterType") == "PRICE_FILTER"
            ),
            None,
        )
        if filter_row is None:
            raise RuntimeError(f"{symbol} has no PRICE_FILTER")
        price_filter = PriceFilter(
            minimum=Decimal(str(filter_row.get("minPrice", "0"))),
            maximum=Decimal(str(filter_row.get("maxPrice", "0"))),
            tick_size=Decimal(str(filter_row.get("tickSize", "0"))),
        )
        if (
            price_filter.minimum < 0
            or price_filter.maximum <= price_filter.minimum
            or price_filter.tick_size <= 0
        ):
            raise RuntimeError(f"{symbol} has an invalid PRICE_FILTER")
        self._price_filters[symbol] = price_filter
        return price_filter

    def quantity_filter(self, symbol: str) -> QuantityFilter:
        cached = self._quantity_filters.get(symbol)
        if cached is not None:
            return cached
        symbol_row = self._symbol_row(symbol)
        filters = symbol_row.get("filters", [])
        filter_row = next(
            (row for row in filters if row.get("filterType") == "MARKET_LOT_SIZE"),
            None,
        )
        if filter_row is None or Decimal(str(filter_row.get("stepSize", "0"))) <= 0:
            filter_row = next(
                (row for row in filters if row.get("filterType") == "LOT_SIZE"),
                None,
            )
        if filter_row is None:
            raise RuntimeError(f"{symbol} has no market quantity filter")
        quantity_filter = QuantityFilter(
            minimum=Decimal(str(filter_row.get("minQty", "0"))),
            maximum=Decimal(str(filter_row.get("maxQty", "0"))),
            step_size=Decimal(str(filter_row.get("stepSize", "0"))),
        )
        if (
            quantity_filter.minimum < 0
            or quantity_filter.maximum <= quantity_filter.minimum
            or quantity_filter.step_size <= 0
        ):
            raise RuntimeError(f"{symbol} has an invalid quantity filter")
        self._quantity_filters[symbol] = quantity_filter
        return quantity_filter

    def validate_market_quantity(self, symbol: str, quantity: Decimal) -> None:
        if not quantity.is_finite():
            raise RuntimeError("quantity violates the symbol market lot filter")
        quantity_filter = self.quantity_filter(symbol)
        steps = (quantity - quantity_filter.minimum) / quantity_filter.step_size
        if (
            not quantity_filter.minimum <= quantity <= quantity_filter.maximum
            or steps != steps.to_integral_value()
        ):
            raise RuntimeError("quantity violates the symbol market lot filter")

    def validate_trigger_price(self, symbol: str, price: Decimal) -> None:
        if not price.is_finite():
            raise RuntimeError("trigger price violates the symbol price filter")
        price_filter = self.price_filter(symbol)
        steps = (price - price_filter.minimum) / price_filter.tick_size
        if (
            not price_filter.minimum <= price <= price_filter.maximum
            or steps != steps.to_integral_value()
        ):
            raise RuntimeError("trigger price violates the symbol price filter")

    def normalize_stop_price(
        self, intent: OrderIntent, requested_price: Decimal
    ) -> Decimal:
        if not requested_price.is_finite():
            raise RuntimeError("requested stop price must be finite")
        price_filter = self.price_filter(intent.symbol)
        rounding = ROUND_FLOOR if intent.side is Side.BUY else ROUND_CEILING
        steps = (
            (requested_price - price_filter.minimum) / price_filter.tick_size
        ).to_integral_value(rounding=rounding)
        normalized = price_filter.minimum + steps * price_filter.tick_size
        if not price_filter.minimum <= normalized <= price_filter.maximum:
            raise RuntimeError("normalized stop is outside the symbol price filter")
        return normalized

    def find_protection(self, intent: OrderIntent) -> ProtectionReceipt | None:
        orders = self._signed_request(
            "GET", "/fapi/v1/openAlgoOrders", {"symbol": intent.symbol}
        )
        stop_id = child_order_id(intent.client_order_id, "sl")
        break_even_id = child_order_id(intent.client_order_id, "be")
        take_profit_id = child_order_id(intent.client_order_id, "tp")
        by_id = {row.get("clientAlgoId"): row for row in orders}
        # Prefer the original while both exist so reconciliation retries finish
        # cancelling it instead of silently accepting duplicate close triggers.
        active_stop_id = (
            stop_id
            if stop_id in by_id
            else break_even_id
            if break_even_id in by_id
            else None
        )
        if active_stop_id is not None and take_profit_id in by_id:
            stop_price = Decimal(
                str(
                    by_id[active_stop_id].get(
                        "triggerPrice",
                        intent.protection.stop_loss_price,
                    )
                )
            )
            take_profit_price = Decimal(
                str(
                    by_id[take_profit_id].get(
                        "triggerPrice",
                        intent.protection.take_profit_price,
                    )
                )
            )
            return ProtectionReceipt(
                intent.client_order_id,
                active_stop_id,
                take_profit_id,
                stop_price,
                take_profit_price,
            )
        return None

    def submit_protection(
        self, intent: OrderIntent, entry_fill: Fill
    ) -> ProtectionReceipt:
        existing = self.find_protection(intent)
        if existing is not None:
            return existing
        self.validate_trigger_price(intent.symbol, intent.protection.stop_loss_price)
        self.validate_trigger_price(intent.symbol, intent.protection.take_profit_price)
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
        return ProtectionReceipt(
            intent.client_order_id,
            stop_id,
            take_profit_id,
            intent.protection.stop_loss_price,
            intent.protection.take_profit_price,
        )

    def replace_stop(
        self,
        intent: OrderIntent,
        entry_fill: Fill,
        current: ProtectionReceipt,
        new_stop_price: Decimal,
    ) -> ProtectionReceipt:
        """Create and confirm the safer stop before cancelling the old one."""
        self.refresh_symbol_rules(intent.symbol)
        normalized_stop_price = self.normalize_stop_price(intent, new_stop_price)
        if intent.side is Side.BUY and normalized_stop_price <= current.stop_price:
            raise RuntimeError("normalized long stop does not improve protection")
        if intent.side is Side.SELL and normalized_stop_price >= current.stop_price:
            raise RuntimeError("normalized short stop does not improve protection")
        orders = self._signed_request(
            "GET", "/fapi/v1/openAlgoOrders", {"symbol": intent.symbol}
        )
        by_id = {row.get("clientAlgoId"): row for row in orders}
        old_stop_id = child_order_id(intent.client_order_id, "sl")
        break_even_id = child_order_id(intent.client_order_id, "be")
        take_profit_id = child_order_id(intent.client_order_id, "tp")
        if take_profit_id not in by_id or not (
            old_stop_id in by_id or break_even_id in by_id
        ):
            raise RuntimeError("current protection is not fully open")

        if break_even_id not in by_id:
            created = self._signed_request(
                "POST",
                "/fapi/v1/algoOrder",
                {
                    "algoType": "CONDITIONAL",
                    "symbol": intent.symbol,
                    "side": entry_fill.side.opposite.value,
                    "type": "STOP_MARKET",
                    "triggerPrice": str(normalized_stop_price),
                    "closePosition": "true",
                    "workingType": "MARK_PRICE",
                    "priceProtect": "TRUE",
                    "clientAlgoId": break_even_id,
                },
            )
            if created.get("clientAlgoId") != break_even_id:
                raise RuntimeError("testnet did not confirm the break-even stop")

        confirmed = self._signed_request(
            "GET", "/fapi/v1/openAlgoOrders", {"symbol": intent.symbol}
        )
        confirmed_by_id = {row.get("clientAlgoId"): row for row in confirmed}
        confirmed_ids = set(confirmed_by_id)
        if not {break_even_id, take_profit_id}.issubset(confirmed_ids):
            raise RuntimeError("new stop was not visible before cancellation")
        confirmed_stop_price = Decimal(
            str(confirmed_by_id[break_even_id].get("triggerPrice", "0"))
        )
        if confirmed_stop_price != normalized_stop_price:
            raise RuntimeError("new stop price does not match the requested price")

        if old_stop_id in confirmed_ids:
            self._signed_request(
                "DELETE",
                "/fapi/v1/algoOrder",
                {"symbol": intent.symbol, "clientAlgoId": old_stop_id},
            )

        final_orders = self._signed_request(
            "GET", "/fapi/v1/openAlgoOrders", {"symbol": intent.symbol}
        )
        final_ids = {row.get("clientAlgoId") for row in final_orders}
        if not {break_even_id, take_profit_id}.issubset(final_ids):
            raise RuntimeError("break-even protection is incomplete after replacement")
        if old_stop_id in final_ids:
            raise RuntimeError("old stop cancellation is unresolved")
        return ProtectionReceipt(
            intent.client_order_id,
            break_even_id,
            take_profit_id,
            normalized_stop_price,
            current.take_profit_price,
        )

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
        self.refresh_symbol_rules(intent.symbol)
        self.validate_market_quantity(intent.symbol, intent.quantity)
        self.validate_trigger_price(intent.symbol, intent.protection.stop_loss_price)
        self.validate_trigger_price(intent.symbol, intent.protection.take_profit_price)
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

    def preflight_blockers(self) -> list[str]:
        """Read-only account checks required before a Testnet execution trial."""
        blockers = []
        position_mode = self._signed_request("GET", "/fapi/v1/positionSide/dual")
        if bool(position_mode.get("dualSidePosition")):
            blockers.append("account_is_not_in_one_way_mode")
        positions = self._signed_request("GET", "/fapi/v3/positionRisk")
        if any(Decimal(str(row.get("positionAmt", "0"))) != 0 for row in positions):
            blockers.append("account_has_open_positions")
        orders = self._signed_request("GET", "/fapi/v1/openOrders")
        if orders:
            blockers.append("account_has_open_orders")
        algo_orders = self._signed_request("GET", "/fapi/v1/openAlgoOrders")
        if algo_orders:
            blockers.append("account_has_open_algo_orders")
        if self.kill_switch():
            blockers.append("kill_switch_is_active")
        return blockers

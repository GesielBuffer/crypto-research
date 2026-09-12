import hashlib
import hmac
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode

from execution.binance_testnet import (
    BinanceUsdMTestnetExchange,
    TESTNET_BASE_URL,
)
from execution.models import OrderIntent, Side


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def intent():
    return OrderIntent(
        strategy_id="approved-v1",
        symbol="BTCUSDT",
        side=Side.BUY,
        quantity=Decimal("0.001"),
        reference_price=Decimal("50000"),
        leverage=1,
        client_order_id="apv1-BTC-20260912T000000Z",
        market_data_time=datetime(2026, 9, 12, tzinfo=timezone.utc),
    )


class BinanceTestnetTests(unittest.TestCase):
    def test_production_hostname_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Testnet"):
            BinanceUsdMTestnetExchange(
                "key", "secret", base_url="https://fapi.binance.com"
            )

    def test_market_order_is_signed_and_testnet_only(self):
        body = {
            "clientOrderId": intent().client_order_id,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "executedQty": "0.001",
            "avgPrice": "50001.5",
            "updateTime": 1789161600000,
        }
        session = FakeSession([FakeResponse(200, body)])
        exchange = BinanceUsdMTestnetExchange(
            "key", "secret", session=session, clock_ms=lambda: 1234567890
        )
        fill = exchange.submit_market(intent())
        method, url, kwargs = session.calls[0]
        self.assertEqual((method, url), ("POST", TESTNET_BASE_URL + "/fapi/v1/order"))
        self.assertEqual(kwargs["headers"], {"X-MBX-APIKEY": "key"})
        unsigned = dict(kwargs["params"])
        signature = unsigned.pop("signature")
        expected = hmac.new(
            b"secret", urlencode(unsigned).encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(signature, expected)
        self.assertEqual(fill.price, Decimal("50001.5"))

    def test_unknown_order_returns_none_for_reconciliation(self):
        session = FakeSession([FakeResponse(400, {"code": -2013, "msg": "Order does not exist"})])
        exchange = BinanceUsdMTestnetExchange(
            "key", "secret", session=session, clock_ms=lambda: 1234567890
        )
        self.assertIsNone(exchange.find_fill(intent()))

    def test_snapshot_includes_positions_income_and_kill_switch(self):
        session = FakeSession([
            FakeResponse(200, [
                {"symbol": "BTCUSDT", "positionAmt": "0.001"},
                {"symbol": "ETHUSDT", "positionAmt": "0"},
            ]),
            FakeResponse(200, [{"income": "-2.50"}, {"income": "0.25"}]),
        ])
        exchange = BinanceUsdMTestnetExchange(
            "key", "secret", session=session, kill_switch=lambda: True
        )
        snapshot = exchange.snapshot()
        self.assertEqual(snapshot.open_symbols, frozenset({"BTCUSDT"}))
        self.assertEqual(snapshot.realized_pnl_today, Decimal("-2.25"))
        self.assertTrue(snapshot.kill_switch)

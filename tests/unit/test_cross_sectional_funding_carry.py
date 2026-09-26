import unittest

import pandas as pd

from research.experiments.cross_sectional_funding_carry import (
    fetch_funding,
    funding_between,
    period_return,
    trailing_funding_matrix,
)


class CrossSectionalFundingCarryTests(unittest.TestCase):
    def test_fetch_accepts_api_symbol_field(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return [{"symbol": "BTCUSDT", "fundingTime": 1704067200000, "fundingRate": "0.0001"}]

        import unittest.mock
        protocol = {"data": {
            "start": "2024-01-01",
            "discovery_end": "2024-01-02",
            "funding_endpoint": "https://example.invalid/funding",
        }}
        with unittest.mock.patch("research.experiments.cross_sectional_funding_carry.requests.get", return_value=Response()):
            frame = fetch_funding("BTCUSDT", protocol)
        self.assertEqual(frame.iloc[0]["symbol"], "BTCUSDT")
        self.assertAlmostEqual(frame.iloc[0]["fundingRate"], 0.0001)

    def test_positive_funding_is_received_by_short_and_paid_by_long(self):
        weights = pd.Series({"LONG": 0.5, "SHORT": -0.5})
        entry = pd.Series({"LONG": 100.0, "SHORT": 100.0})
        exit_prices = entry.copy()
        funding = pd.Series({"LONG": 0.001, "SHORT": 0.003})
        total, price, carry = period_return(weights, entry, exit_prices, funding)
        self.assertAlmostEqual(price, 0.0)
        self.assertAlmostEqual(carry, 0.001)
        self.assertAlmostEqual(total, 0.001)

    def test_funding_window_excludes_observation_and_includes_exit(self):
        times = pd.date_range("2026-01-01", periods=4, freq="8h", tz="UTC")
        frame = pd.DataFrame({"fundingTime": times, "fundingRate": [1.0, 2.0, 3.0, 4.0]})
        self.assertEqual(funding_between(frame, times[0], times[2]), 5.0)

    def test_mixed_fractional_funding_timestamps_are_supported(self):
        values = pd.to_datetime(
            ["2024-01-01 00:00:00+00:00", "2024-01-05 00:00:00.001000+00:00"],
            utc=True,
            format="mixed",
        )
        self.assertEqual(values[1].microsecond, 1000)

    def test_trailing_matrix_uses_only_current_and_past_records(self):
        times = pd.date_range("2026-01-01", periods=4, freq="8h", tz="UTC")
        funding = {
            "A": pd.DataFrame({"fundingTime": times, "fundingRate": [1.0, 1.0, 10.0, 99.0]}),
            "B": pd.DataFrame({"fundingTime": times, "fundingRate": [2.0, 2.0, 2.0, 2.0]}),
        }
        matrix = trailing_funding_matrix(funding, 2)
        self.assertEqual(matrix.loc[times[1], "A"], 1.0)
        self.assertEqual(matrix.loc[times[2], "A"], 5.5)


if __name__ == "__main__":
    unittest.main()

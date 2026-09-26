import unittest

import pandas as pd

from research.experiments.delta_neutral_carry import simulate_symbol


class DeltaNeutralCarryTests(unittest.TestCase):
    def test_entry_is_strictly_after_known_funding_and_accounting_is_explicit(self):
        times = pd.date_range("2026-01-01", periods=145, freq="5min", tz="UTC")
        prices = pd.DataFrame({
            "open_time": times,
            "perp_open": [101.0] * len(times),
            "spot_open": [100.0] * len(times),
        })
        funding_times = pd.date_range("2026-01-01", periods=3, freq="4h", tz="UTC")
        funding = pd.DataFrame({
            "fundingTime": funding_times,
            "fundingRate": [0.001, 0.002, 0.003],
        })
        trades = simulate_symbol(
            prices,
            funding,
            trailing_records=1,
            annualization_periods=100,
            min_annualized_funding=0.05,
            hold_funding_periods=1,
            max_entry_basis=0.02,
        )
        self.assertEqual(trades.iloc[0]["entry_time"], funding_times[0] + pd.Timedelta(minutes=5))
        self.assertEqual(trades.iloc[0]["exit_time"], funding_times[1] + pd.Timedelta(minutes=5))
        self.assertAlmostEqual(trades.iloc[0]["realized_funding"], 0.002)
        self.assertAlmostEqual(trades.iloc[0]["gross_return"], 0.001)

    def test_negative_observed_funding_never_opens_inverse_carry(self):
        times = pd.date_range("2026-01-01", periods=145, freq="5min", tz="UTC")
        prices = pd.DataFrame({
            "open_time": times,
            "perp_open": [100.0] * len(times),
            "spot_open": [100.0] * len(times),
        })
        funding = pd.DataFrame({
            "fundingTime": pd.date_range("2026-01-01", periods=3, freq="4h", tz="UTC"),
            "fundingRate": [-0.001, -0.001, -0.001],
        })
        trades = simulate_symbol(
            prices,
            funding,
            trailing_records=1,
            annualization_periods=100,
            min_annualized_funding=0.05,
            hold_funding_periods=1,
            max_entry_basis=0.02,
        )
        self.assertTrue(trades.empty)

    def test_future_funding_is_not_used_for_entry_threshold(self):
        times = pd.date_range("2026-01-01", periods=145, freq="5min", tz="UTC")
        prices = pd.DataFrame({
            "open_time": times,
            "perp_open": [100.0] * len(times),
            "spot_open": [100.0] * len(times),
        })
        funding = pd.DataFrame({
            "fundingTime": pd.date_range("2026-01-01", periods=3, freq="4h", tz="UTC"),
            "fundingRate": [0.0001, 0.5, 0.5],
        })
        trades = simulate_symbol(
            prices,
            funding,
            trailing_records=1,
            annualization_periods=100,
            min_annualized_funding=0.02,
            hold_funding_periods=1,
            max_entry_basis=0.02,
        )
        self.assertEqual(trades.iloc[0]["observation_time"], funding.iloc[1]["fundingTime"])


if __name__ == "__main__":
    unittest.main()

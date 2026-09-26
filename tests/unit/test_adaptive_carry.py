import unittest

import pandas as pd

from research.experiments.adaptive_carry import simulate_adaptive_symbol


class AdaptiveCarryTests(unittest.TestCase):
    def test_threshold_uses_history_before_current_observation(self):
        funding_times = pd.date_range("2026-01-01", periods=7, freq="4h", tz="UTC")
        funding = pd.DataFrame({
            "fundingTime": funding_times,
            "fundingRate": [0.001, 0.001, 0.001, 0.010, 0.001, 0.001, 0.001],
        })
        times = pd.date_range("2026-01-01", periods=400, freq="5min", tz="UTC")
        prices = pd.DataFrame({
            "open_time": times,
            "perp_open": [101.0] * len(times),
            "spot_open": [100.0] * len(times),
        })
        trades = simulate_adaptive_symbol(
            prices,
            funding,
            trailing_records=1,
            percentile_history_records=3,
            entry_percentile=0.75,
            hold_funding_periods=1,
            max_entry_basis=0.02,
        )
        self.assertEqual(trades.iloc[0]["observation_time"], funding_times[3])
        self.assertAlmostEqual(trades.iloc[0]["historical_threshold"], 0.001)
        self.assertEqual(trades.iloc[0]["entry_time"], funding_times[3] + pd.Timedelta(minutes=5))

    def test_negative_current_funding_is_rejected_even_above_negative_history(self):
        funding_times = pd.date_range("2026-01-01", periods=7, freq="4h", tz="UTC")
        funding = pd.DataFrame({
            "fundingTime": funding_times,
            "fundingRate": [-0.01, -0.01, -0.01, -0.001, -0.01, -0.01, -0.01],
        })
        times = pd.date_range("2026-01-01", periods=400, freq="5min", tz="UTC")
        prices = pd.DataFrame({
            "open_time": times,
            "perp_open": [100.0] * len(times),
            "spot_open": [100.0] * len(times),
        })
        trades = simulate_adaptive_symbol(
            prices,
            funding,
            trailing_records=1,
            percentile_history_records=3,
            entry_percentile=0.75,
            hold_funding_periods=1,
            max_entry_basis=0.02,
        )
        self.assertTrue(trades.empty)


if __name__ == "__main__":
    unittest.main()

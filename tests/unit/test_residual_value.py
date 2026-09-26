import json
import unittest
from pathlib import Path

import pandas as pd

from research.experiments.residual_value import residual_scores, simulate


class ResidualValueTests(unittest.TestCase):
    def test_frozen_discovery_result_keeps_holdout_closed(self):
        path = Path(__file__).parents[2] / "results" / "residual_value_v1_decision.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["decision"], "FAIL_DISCOVERY")
        self.assertEqual(report["passing_parameter_sets"], 0)
        self.assertIsNone(report["selected"])
        self.assertEqual(report["holdout_status"], "UNOPENED")

    def test_exact_factor_multiple_has_zero_residual(self):
        index = pd.date_range("2024-01-01", periods=400, freq="4h", tz="UTC")
        btc = pd.Series(100.0 * (1.001 ** pd.Series(range(len(index)), index=index)), index=index)
        closes = pd.DataFrame({"BTCUSDT": btc, "DOUBLE": 50.0 * (btc / 100.0) ** 2}, index=index)
        scores, betas = residual_scores(closes, index[-1], market_factor="BTCUSDT", beta_window_days=28, residual_lookback_days=1)
        self.assertAlmostEqual(scores["BTCUSDT"], 0.0, places=12)
        self.assertAlmostEqual(betas["BTCUSDT"], 1.0, places=12)

    def test_future_change_cannot_change_first_period(self):
        index = pd.date_range("2024-01-01", "2024-04-10", freq="4h", tz="UTC")
        symbols = ["BTCUSDT"] + [f"S{i:02d}" for i in range(15)]
        closes = pd.DataFrame({s: 100 + i + pd.Series(range(len(index)), index=index) * (i + 1) / 1000 for i, s in enumerate(symbols)}, index=index)
        opens = closes.copy()
        first, _ = simulate(closes, opens, market_factor="BTCUSDT", beta_window_days=28, residual_lookback_days=1, rebalance_days=1)
        changed = closes.copy()
        changed.loc[changed.index >= pd.Timestamp("2024-04-03", tz="UTC"), "S00"] *= 100
        second, _ = simulate(changed, opens, market_factor="BTCUSDT", beta_window_days=28, residual_lookback_days=1, rebalance_days=1)
        pd.testing.assert_series_equal(first.iloc[0], second.iloc[0])


if __name__ == "__main__":
    unittest.main()

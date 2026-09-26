import json
import unittest
from pathlib import Path

import pandas as pd

from research.experiments.slow_trend import _capped_signed_weights, simulate


class SlowTrendTests(unittest.TestCase):
    def test_frozen_discovery_result_keeps_holdout_closed(self):
        path = Path(__file__).parents[2] / "results" / "slow_trend_v1_decision.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["decision"], "FAIL_DISCOVERY")
        self.assertEqual(report["passing_parameter_sets"], 0)
        self.assertIsNone(report["selected"])
        self.assertEqual(report["holdout_status"], "UNOPENED")

    def test_signed_weights_respect_cap_and_gross(self):
        raw = pd.Series({f"S{i}": (-1 if i % 2 else 1) / (i + 1) for i in range(16)})
        weights = _capped_signed_weights(raw, gross=1.0, cap=0.10)
        self.assertAlmostEqual(weights.abs().sum(), 1.0)
        self.assertLessEqual(weights.abs().max(), 0.10)

    def test_sparse_signals_hold_cash_instead_of_breaking_cap(self):
        raw = pd.Series({"A": 1.0, "B": -0.5, "C": 0.25})
        weights = _capped_signed_weights(raw, gross=1.0, cap=0.10)
        self.assertAlmostEqual(weights.abs().sum(), 0.30)
        self.assertTrue((weights.abs() <= 0.10).all())

    def test_future_change_cannot_change_first_period(self):
        index = pd.date_range("2024-01-01", "2024-04-10", freq="4h", tz="UTC")
        symbols = [f"S{i:02d}" for i in range(16)]
        closes = pd.DataFrame({s: 100 + i + pd.Series(range(len(index)), index=index) * (i + 1) / 1000 for i, s in enumerate(symbols)}, index=index)
        opens = closes.copy()
        first, _ = simulate(closes, opens, speeds=[7, 28], rebalance_days=1, weight_cap=0.10)
        changed = closes.copy()
        changed.loc[changed.index >= pd.Timestamp("2024-04-03", tz="UTC"), "S00"] *= 100
        second, _ = simulate(changed, opens, speeds=[7, 28], rebalance_days=1, weight_cap=0.10)
        pd.testing.assert_series_equal(first.iloc[0], second.iloc[0])


if __name__ == "__main__":
    unittest.main()

import math
import unittest
from pathlib import Path

import pandas as pd

from research.backtest import CostModel, apply_costs
from research.metrics import summarize_returns


ROOT = Path(__file__).resolve().parents[2]


class CostModelTests(unittest.TestCase):
    def test_components_are_additive_and_input_is_unchanged(self):
        gross = pd.Series([0.01, -0.02], name="gross_return")
        net = apply_costs(gross, CostModel(0.0004, 0.0001, 0.0002))

        pd.testing.assert_series_equal(
            net,
            pd.Series([0.0093, -0.0207], name="net_return"),
        )
        self.assertEqual(gross.name, "gross_return")

    def test_negative_cost_is_rejected(self):
        with self.assertRaises(ValueError):
            CostModel(slippage=-0.0001)


class FrozenC2RegressionTests(unittest.TestCase):
    def _assert_frozen_summary(self, trades_file, summary_file, cost):
        trades = pd.read_csv(ROOT / "results" / trades_file)
        frozen = pd.read_csv(ROOT / "results" / summary_file)
        expected = frozen.loc[frozen["cost"].sub(cost).abs().idxmin()]

        actual = summarize_returns(
            apply_costs(trades["gross_return"], CostModel(fees=cost))
        )

        for key in ("samples", "mean_return", "median_return", "win_rate", "profit_factor"):
            self.assertTrue(
                math.isclose(actual[key], expected[key], rel_tol=1e-12, abs_tol=1e-12),
                f"{key}: {actual[key]} != {expected[key]}",
            )

    def test_canonical_development_baseline(self):
        self._assert_frozen_summary(
            "c2_canonical_trades.csv", "c2_canonical_summary.csv", 0.0006
        )

    def test_august_holdout_baseline(self):
        self._assert_frozen_summary(
            "c2_august_holdout_trades.csv", "c2_august_holdout_global.csv", 0.0006
        )


if __name__ == "__main__":
    unittest.main()

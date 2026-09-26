import json
import unittest
from pathlib import Path

import pandas as pd

from research.experiments.cross_sectional_funding_carry_v2 import (
    block_bootstrap_mean,
    hysteresis_membership,
)


class CrossSectionalFundingCarryV2Tests(unittest.TestCase):
    def test_frozen_v2_preserves_original_rejection(self):
        path = Path(__file__).parents[2] / "results" / "cross_sectional_funding_carry_v2_decision.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["decision"], "REJECT")
        self.assertEqual(report["holdout_status"], "UNOPENED")
        self.assertIn("symbol_breadth", report["research_reasons"])

    def test_hysteresis_retains_positions_until_median_cross(self):
        ranking = pd.Series({f"S{i:02d}": float(i) for i in range(16)})
        longs, shorts = hysteresis_membership(
            ranking,
            {"S06", "S12"},
            {"S03", "S09"},
            entry_fraction=0.25,
            exit_boundary=0.50,
        )
        self.assertIn("S06", longs)
        self.assertNotIn("S12", longs)
        self.assertIn("S09", shorts)
        self.assertNotIn("S03", shorts)
        self.assertTrue(set(ranking.head(4).index).issubset(longs))
        self.assertTrue(set(ranking.tail(4).index).issubset(shorts))

    def test_block_bootstrap_is_deterministic_and_detects_positive_series(self):
        returns = pd.Series([0.001, 0.002, -0.0001] * 30)
        first = block_bootstrap_mean(returns, resamples=200, block_periods=7, seed=42)
        second = block_bootstrap_mean(returns, resamples=200, block_periods=7, seed=42)
        self.assertEqual(first, second)
        self.assertGreater(first["probability_positive"], 0.95)


if __name__ == "__main__":
    unittest.main()

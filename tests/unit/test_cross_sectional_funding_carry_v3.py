import json
import unittest
from pathlib import Path

import pandas as pd

from research.experiments.cross_sectional_funding_carry_v3 import summarize_window


class CrossSectionalFundingCarryV3Tests(unittest.TestCase):
    def test_frozen_holdout_result_is_fail_and_cannot_promote(self):
        path = Path(__file__).parents[2] / "results" / "cross_sectional_funding_carry_v3_decision.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["decision"], "FAIL")
        self.assertEqual(report["holdout_status"], "OPENED_ONCE")
        self.assertEqual(report["promotion_effect"], "NONE")
        self.assertIn("base_profit_factor", report["reasons"])

    def test_window_is_end_exclusive_and_cost_uses_turnover(self):
        periods = pd.DataFrame({
            "entry_time": pd.to_datetime(["2026-09-01T04:00:00Z", "2026-09-26T00:00:00Z"]),
            "exit_time": pd.to_datetime(["2026-09-02T04:00:00Z", "2026-09-27T00:00:00Z"]),
            "gross_return": [0.01, 1.0],
            "turnover": [2.0, 0.0],
            "price_component": [0.009, 1.0],
            "funding_component": [0.001, 0.0],
        })
        result = summarize_window(periods, "2026-09-01", "2026-09-26", [0.001])[0]
        self.assertEqual(result["samples"], 1)
        self.assertAlmostEqual(result["mean_return"], 0.009)


if __name__ == "__main__":
    unittest.main()

import unittest

import pandas as pd

from research.experiments.cross_exchange_funding_replication import (
    _okx_month_chunks,
    coverage_ratio,
    decide_venue,
)


class CrossExchangeFundingReplicationTests(unittest.TestCase):
    def test_price_coverage_counts_expected_four_hour_bars(self):
        frame = pd.DataFrame({"open_time": pd.date_range("2024-01-01", periods=6, freq="4h", tz="UTC")})
        self.assertEqual(coverage_ratio(frame, "open_time", "2024-01-01", "2024-01-02", expected_frequency="4h"), 1.0)

    def test_temporal_coverage_rejects_late_listing(self):
        frame = pd.DataFrame({"fundingTime": pd.date_range("2024-07-01", "2024-12-31", freq="8h", tz="UTC")})
        self.assertLess(coverage_ratio(frame, "fundingTime", "2024-01-01", "2025-01-01"), 0.95)

    def test_okx_catalog_queries_stay_below_ten_month_limit(self):
        chunks = _okx_month_chunks("2024-01-01", "2026-10-01")
        self.assertGreater(len(chunks), 1)
        for begin, end in chunks:
            self.assertLessEqual(pd.Timestamp(end, unit="ms", tz="UTC"), pd.Timestamp(begin, unit="ms", tz="UTC") + pd.DateOffset(months=9))

    def test_decision_requires_every_registered_gate(self):
        rows = []
        for segment, samples in (("2024", 250), ("2025", 250), ("2026", 200), ("full", 700)):
            for cost, pf in ((0.0006, 1.2), (0.0014, 1.05)):
                rows.append({"segment": segment, "cost": cost, "samples": samples, "profit_factor": pf, "max_compounded_drawdown": 0.10})
        protocol = {"strategy": {"round_trip_costs": [0.0006, 0.0014]}, "evaluation": {
            "minimum_periods_per_full_year": 200, "minimum_periods_2026_partial": 180,
            "base_cost_min_profit_factor_each_segment": 1.0,
            "base_cost_min_profit_factor_full_period": 1.1,
            "stress_cost_min_profit_factor_full_period": 1.0,
            "max_full_period_drawdown": 0.15,
        }}
        self.assertTrue(decide_venue(pd.DataFrame(rows), protocol)["passed"])
        rows[0]["profit_factor"] = 0.99
        result = decide_venue(pd.DataFrame(rows), protocol)
        self.assertFalse(result["passed"])
        self.assertIn("2024_base_profit_factor", result["reasons"])


if __name__ == "__main__":
    unittest.main()

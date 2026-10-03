import unittest

import pandas as pd

from execution.shadow_funding import advance_state, funding_matrix


class ShadowFundingTests(unittest.TestCase):
    def setUp(self):
        self.protocol = {"experiment": {"strategy_version": "V4"}, "strategy": {
            "trailing_funding_records": 3,
            "rebalance_funding_periods": 3,
            "entry_fraction": 0.25,
            "exit_boundary": 0.50,
        }}

    def test_matrix_uses_only_common_settled_timestamps(self):
        times = pd.date_range("2026-10-01", periods=5, freq="8h", tz="UTC")
        frames = {
            "A": pd.DataFrame({"fundingTime": times, "fundingRate": range(5)}),
            "B": pd.DataFrame({"fundingTime": times.delete(0), "fundingRate": range(4)}),
        }
        matrix = funding_matrix(frames, 3)
        self.assertEqual(list(matrix.index), list(times[3:]))

    def test_initial_observation_creates_balanced_quartiles(self):
        times = pd.date_range("2026-10-01", periods=2, freq="8h", tz="UTC")
        matrix = pd.DataFrame(
            [{f"S{i:02d}": float(i) for i in range(16)} for _ in times],
            index=times,
        )
        state, changed = advance_state(matrix, {}, self.protocol)
        self.assertTrue(changed)
        self.assertEqual(len(state["longs"]), 4)
        self.assertEqual(len(state["shorts"]), 4)
        self.assertEqual(state["last_rebalance_time"], times[-1].isoformat())

    def test_existing_state_waits_for_three_new_settlements(self):
        times = pd.date_range("2026-10-01", periods=4, freq="8h", tz="UTC")
        matrix = pd.DataFrame(
            [{f"S{i:02d}": float(i) for i in range(16)} for _ in times],
            index=times,
        )
        previous = {"last_rebalance_time": times[1].isoformat(), "longs": ["S00"], "shorts": ["S15"]}
        state, changed = advance_state(matrix, previous, self.protocol)
        self.assertFalse(changed)
        self.assertEqual(state["last_rebalance_time"], times[1].isoformat())


if __name__ == "__main__":
    unittest.main()

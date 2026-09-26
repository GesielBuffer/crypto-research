import json
import unittest
from pathlib import Path

import pandas as pd

from research.experiments.hourly_breakout import (
    build_signal,
    max_compounded_drawdown,
    resample_hourly,
    simulate_atr_exits,
)


class HourlyBreakoutTests(unittest.TestCase):
    def test_frozen_result_rejects_every_parameter_set(self):
        root = Path(__file__).resolve().parents[2]
        decision = json.loads(
            (root / "results" / "hourly_breakout_v1_decision.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(decision["decision"], "FAIL")
        self.assertEqual(decision["tested_parameter_sets"], 8)
        self.assertEqual(decision["passing_parameter_sets"], 0)
        self.assertIsNone(decision["selected"])

    def test_resample_keeps_only_complete_hours(self):
        times = pd.date_range("2026-01-01", periods=23, freq="5min", tz="UTC")
        bars = pd.DataFrame({
            "open_time": times,
            "open": range(23),
            "high": [value + 2 for value in range(23)],
            "low": [value - 1 for value in range(23)],
            "close": [value + 1 for value in range(23)],
            "volume": [1] * 23,
        })
        hourly = resample_hourly(bars)
        self.assertEqual(len(hourly), 1)
        self.assertEqual(hourly.iloc[0]["open"], 0)
        self.assertEqual(hourly.iloc[0]["close"], 12)

    def test_signal_uses_prior_range_and_future_changes_do_not_leak(self):
        size = 650
        bars = pd.DataFrame({
            "high": [100.0] * size,
            "low": [90.0] * size,
            "close": [95.0] * size,
            "atr": [2.0] * size,
            "ema_200": [94.0] * size,
        })
        bars.loc[610, ["high", "close"]] = [102.0, 101.0]
        original = build_signal(
            bars,
            breakout_window=24,
            trend_ema_span=200,
            side="long",
            min_atr_fraction=0.002,
            max_atr_fraction=0.04,
        )
        changed = bars.copy()
        changed.loc[620:, ["high", "low", "close", "ema_200"]] = 1_000_000
        after = build_signal(
            changed,
            breakout_window=24,
            trend_ema_span=200,
            side="long",
            min_atr_fraction=0.002,
            max_atr_fraction=0.04,
        )
        self.assertTrue(original.iloc[610])
        pd.testing.assert_series_equal(original.iloc[:620], after.iloc[:620])

    def test_entry_is_next_open_and_same_bar_stop_wins(self):
        times = pd.date_range("2026-01-01", periods=5, freq="1h", tz="UTC")
        bars = pd.DataFrame({
            "open_time": times,
            "open": [100.0] * 5,
            "high": [100.0, 106.0, 100.0, 100.0, 100.0],
            "low": [100.0, 97.0, 100.0, 100.0, 100.0],
            "close": [100.0] * 5,
            "atr": [2.0] * 5,
        })
        signals = pd.Series([True, False, False, False, False])
        trades = simulate_atr_exits(
            bars,
            signals,
            side="long",
            stop_atr_multiple=1.0,
            reward_r_multiple=2.5,
            max_hold_bars=3,
        )
        self.assertEqual(trades.iloc[0]["entry_time"], times[1])
        self.assertEqual(trades.iloc[0]["exit_reason"], "stop_loss")
        self.assertEqual(trades.iloc[0]["exit_price"], 98.0)

    def test_short_return_uses_linear_usdm_convention(self):
        times = pd.date_range("2026-01-01", periods=5, freq="1h", tz="UTC")
        bars = pd.DataFrame({
            "open_time": times,
            "open": [100.0] * 5,
            "high": [100.0] * 5,
            "low": [100.0, 94.0, 100.0, 100.0, 100.0],
            "close": [100.0] * 5,
            "atr": [2.0] * 5,
        })
        trades = simulate_atr_exits(
            bars,
            pd.Series([True, False, False, False, False]),
            side="short",
            stop_atr_multiple=1.0,
            reward_r_multiple=2.5,
            max_hold_bars=3,
        )
        self.assertAlmostEqual(trades.iloc[0]["gross_return"], 0.05)

    def test_compounded_drawdown(self):
        value = max_compounded_drawdown(pd.Series([0.10, -0.20, 0.05]))
        self.assertAlmostEqual(value, 0.20)


if __name__ == "__main__":
    unittest.main()

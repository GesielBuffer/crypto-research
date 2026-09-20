import math
import unittest
from pathlib import Path

import pandas as pd

from research.backtest import (
    CostModel,
    FixedHorizonConfig,
    IntrabarExitConfig,
    apply_costs,
    simulate_fixed_horizon,
    simulate_intrabar_exits,
)
from research.metrics import summarize_returns
from research.signals import C2SignalConfig, build_c2_signals


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


class FixedHorizonTests(unittest.TestCase):
    def setUp(self):
        self.bars = pd.DataFrame({
            "open_time": pd.date_range("2026-01-01", periods=7, freq="5min", tz="UTC"),
            "open": [100, 101, 102, 103, 104, 105, 106],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5],
        })

    def test_entry_is_next_open_and_exit_is_future_close(self):
        signals = pd.Series([True, False, False, False, False, False, False])
        trades = simulate_fixed_horizon(
            self.bars,
            signals,
            FixedHorizonConfig(hold_bars=3, costs=CostModel(fees=0.0006)),
        )

        trade = trades.iloc[0]
        self.assertEqual(trade.entry_position, 1)
        self.assertEqual(trade.exit_position, 3)
        self.assertEqual(trade.entry_price, 101.0)
        self.assertEqual(trade.exit_price, 103.5)
        self.assertAlmostEqual(trade.gross_return, 103.5 / 101 - 1)
        self.assertAlmostEqual(trade.net_return, trade.gross_return - 0.0006)

    def test_short_return_has_inverse_direction(self):
        signals = pd.Series([True, False, False, False, False, False, False])
        trades = simulate_fixed_horizon(
            self.bars, signals, FixedHorizonConfig(side="short", hold_bars=2)
        )
        self.assertAlmostEqual(trades.iloc[0].gross_return, -(102.5 / 101 - 1))

    def test_inverse_short_convention_reproduces_legacy_targets(self):
        signals = pd.Series([True, False, False, False, False, False, False])
        trades = simulate_fixed_horizon(
            self.bars,
            signals,
            FixedHorizonConfig(
                side="short", hold_bars=2, short_return_convention="inverse"
            ),
        )
        self.assertAlmostEqual(trades.iloc[0].gross_return, 101 / 102.5 - 1)

    def test_single_position_rejects_only_overlapping_signals(self):
        signals = pd.Series([True, True, False, True, False, False, False])
        trades = simulate_fixed_horizon(
            self.bars, signals, FixedHorizonConfig(hold_bars=3)
        )
        self.assertEqual(trades.signal_position.tolist(), [0, 3])

    def test_allow_policy_keeps_overlapping_signals(self):
        signals = pd.Series([True, True, False, False, False, False, False])
        trades = simulate_fixed_horizon(
            self.bars,
            signals,
            FixedHorizonConfig(hold_bars=3, overlap="allow"),
        )
        self.assertEqual(trades.signal_position.tolist(), [0, 1])

    def test_incomplete_last_trade_is_dropped(self):
        signals = pd.Series([False, False, False, False, False, True, True])
        trades = simulate_fixed_horizon(
            self.bars, signals, FixedHorizonConfig(hold_bars=2)
        )
        self.assertTrue(trades.empty)

    def test_same_candle_entry_is_rejected(self):
        with self.assertRaises(ValueError):
            FixedHorizonConfig(entry_delay_bars=0)


class IntrabarExitTests(unittest.TestCase):
    def bars(self, rows):
        return pd.DataFrame({
            "open_time": pd.date_range(
                "2026-01-01", periods=len(rows), freq="5min", tz="UTC"
            ),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
        })

    def signal(self, length, *positions):
        values = [False] * length
        for position in positions:
            values[position] = True
        return pd.Series(values)

    def config(self, **overrides):
        values = {
            "hold_bars": 4,
            "stop_loss_fraction": 0.05,
            "take_profit_fraction": 0.15,
            "costs": CostModel(fees=0.0006),
        }
        values.update(overrides)
        return IntrabarExitConfig(**values)

    def test_stop_wins_when_stop_and_target_touch_in_same_candle(self):
        bars = self.bars([
            (100, 101, 99, 100),
            (100, 116, 94, 105),
            (105, 106, 104, 105),
            (105, 106, 104, 105),
            (105, 106, 104, 105),
            (105, 106, 104, 105),
        ])
        trade = simulate_intrabar_exits(
            bars, self.signal(len(bars), 0), self.config()
        ).iloc[0]
        self.assertEqual(trade.exit_reason, "stop_loss")
        self.assertEqual(trade.exit_price, 95.0)
        self.assertEqual(trade.exit_position, 1)

    def test_stop_gap_uses_bar_open_instead_of_ideal_stop_price(self):
        bars = self.bars([
            (100, 101, 99, 100),
            (100, 102, 99, 101),
            (93, 96, 92, 95),
            (95, 96, 94, 95),
            (95, 96, 94, 95),
            (95, 96, 94, 95),
        ])
        trade = simulate_intrabar_exits(
            bars, self.signal(len(bars), 0), self.config()
        ).iloc[0]
        self.assertEqual(trade.exit_reason, "stop_loss")
        self.assertEqual(trade.exit_price, 93.0)

    def test_take_profit_exits_at_predefined_level(self):
        bars = self.bars([
            (100, 101, 99, 100),
            (100, 116, 99, 115),
            (115, 116, 114, 115),
            (115, 116, 114, 115),
            (115, 116, 114, 115),
            (115, 116, 114, 115),
        ])
        trade = simulate_intrabar_exits(
            bars, self.signal(len(bars), 0), self.config()
        ).iloc[0]
        self.assertEqual(trade.exit_reason, "take_profit")
        self.assertAlmostEqual(trade.exit_price, 115.0)

    def test_break_even_activation_only_changes_stop_on_next_candle(self):
        bars = self.bars([
            (100, 101, 99, 100),
            (100, 106, 99, 105),
            (101, 102, 99, 100),
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 101, 99, 100),
        ])
        trade = simulate_intrabar_exits(
            bars,
            self.signal(len(bars), 0),
            self.config(break_even_activation_r_multiple=1.0),
        ).iloc[0]
        self.assertTrue(trade.break_even_activated)
        self.assertEqual(trade.activation_position, 1)
        self.assertEqual(trade.exit_position, 2)
        self.assertEqual(trade.exit_reason, "break_even")
        self.assertEqual(trade.exit_price, 100.0)

    def test_short_break_even_is_symmetric(self):
        bars = self.bars([
            (100, 101, 99, 100),
            (100, 101, 94, 95),
            (99, 101, 98, 100),
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 101, 99, 100),
        ])
        trade = simulate_intrabar_exits(
            bars,
            self.signal(len(bars), 0),
            self.config(side="short", break_even_activation_r_multiple=1.0),
        ).iloc[0]
        self.assertEqual(trade.exit_reason, "break_even")
        self.assertEqual(trade.exit_price, 100.0)
        self.assertEqual(trade.gross_return, 0.0)

    def test_horizon_exit_and_cost_are_reported(self):
        bars = self.bars([
            (100, 101, 99, 100),
            (100, 102, 99, 101),
            (101, 103, 100, 102),
            (102, 104, 101, 103),
            (103, 105, 102, 104),
            (104, 106, 103, 105),
        ])
        trade = simulate_intrabar_exits(
            bars, self.signal(len(bars), 0), self.config()
        ).iloc[0]
        self.assertEqual(trade.exit_reason, "horizon")
        self.assertEqual(trade.exit_price, 104.0)
        self.assertAlmostEqual(trade.net_return, 0.04 - 0.0006)

    def test_early_exit_allows_a_later_non_overlapping_signal(self):
        bars = self.bars([
            (100, 101, 99, 100),
            (100, 101, 94, 95),
            (100, 101, 99, 100),
            (100, 102, 99, 101),
            (101, 103, 100, 102),
            (102, 104, 101, 103),
            (103, 105, 102, 104),
        ])
        trades = simulate_intrabar_exits(
            bars,
            self.signal(len(bars), 0, 2),
            self.config(hold_bars=3),
        )
        self.assertEqual(trades.signal_position.tolist(), [0, 2])

    def test_invalid_ohlc_range_is_rejected(self):
        bars = self.bars([
            (100, 99, 98, 100),
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 101, 99, 100),
        ])
        with self.assertRaisesRegex(ValueError, "invalid price range"):
            simulate_intrabar_exits(
                bars, self.signal(len(bars), 0), self.config()
            )


class C2SignalTests(unittest.TestCase):
    def test_future_candles_cannot_change_past_features_or_signals(self):
        bars = pd.DataFrame({
            "open": [100.0] * 10,
            "close": [100.0, 101.0, 99.0, 102.0, 100.0, 104.0, 100.0, 99.0, 101.0, 100.0],
        })
        config = C2SignalConfig(
            lookback=4,
            min_periods=3,
            extreme_quantile=0.75,
            z_threshold=1.0,
            fresh_lookback_bars=2,
        )
        original = build_c2_signals(bars, config)
        changed = bars.copy()
        changed.loc[7:, "close"] = [500.0, 1.0, 700.0]
        recalculated = build_c2_signals(changed, config)

        pd.testing.assert_frame_equal(original.loc[:6], recalculated.loc[:6])

    def test_current_candle_is_excluded_from_threshold_and_freshness(self):
        bars = pd.DataFrame({
            "open": [100.0] * 6,
            "close": [100.0, 101.0, 99.0, 100.5, 110.0, 111.0],
        })
        features = build_c2_signals(
            bars,
            C2SignalConfig(
                lookback=4,
                min_periods=3,
                extreme_quantile=0.75,
                z_threshold=1.0,
                fresh_lookback_bars=2,
            ),
        )
        self.assertTrue(features.loc[4, "signal"])
        self.assertEqual(features.loc[4, "prior_extreme_count"], 0)
        self.assertFalse(features.loc[5, "signal"])
        self.assertEqual(features.loc[5, "prior_extreme_count"], 1)


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

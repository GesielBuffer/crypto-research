import unittest
from pathlib import Path

import pandas as pd

from research.backtest import CostModel, FixedHorizonConfig, simulate_fixed_horizon
from research.binance_data import load_csv
from research.regression import replay_frozen_trades
from research.signals import build_c2_signals


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"


class C2TradeReplayTests(unittest.TestCase):
    def _assert_trade_replay(self, filename, signal_column):
        frozen = pd.read_csv(ROOT / "results" / filename)
        actual = replay_frozen_trades(
            frozen,
            DATA_DIR,
            FixedHorizonConfig(
                side="long",
                entry_delay_bars=1,
                hold_bars=6,
                overlap="single_position",
                costs=CostModel(fees=0.0006),
            ),
            signal_time_column=signal_column,
        )
        expected = frozen.copy()
        expected[signal_column] = pd.to_datetime(expected[signal_column], utc=True)
        expected = expected.sort_values([signal_column, "symbol"], ignore_index=True)

        self.assertEqual(len(actual), len(expected))
        self.assertEqual(actual.symbol.tolist(), expected.symbol.tolist())
        pd.testing.assert_series_equal(
            actual.signal_time, expected[signal_column], check_names=False
        )
        pd.testing.assert_series_equal(
            actual.entry_price, expected.entry_price, check_names=False, rtol=1e-12
        )
        pd.testing.assert_series_equal(
            actual.gross_return, expected.gross_return, check_names=False, rtol=1e-12
        )

    def test_development_trades_match_candle_replay(self):
        self._assert_trade_replay("c2_canonical_trades.csv", "signal_time")

    def test_august_holdout_trades_match_candle_replay(self):
        self._assert_trade_replay("c2_august_holdout_trades.csv", "open_time")

    def _load_months(self, symbol, periods):
        frames = []
        for period in periods:
            start = pd.Timestamp(f"{period}-01")
            end = start + pd.offsets.MonthBegin(1)
            path = DATA_DIR / (
                f"{symbol}_5m_{start:%Y-%m-%d}_{end:%Y-%m-%d}.csv"
            )
            frames.append(load_csv(path))
        return pd.concat(frames, ignore_index=True).drop_duplicates("open_time")

    def _assert_generated_signals(self, filename, signal_column, warmup_period=None):
        frozen = pd.read_csv(ROOT / "results" / filename)
        frozen[signal_column] = pd.to_datetime(frozen[signal_column], utc=True)
        actual_frames = []
        for symbol, expected_symbol in frozen.groupby("symbol"):
            periods = sorted(expected_symbol[signal_column].dt.strftime("%Y-%m").unique())
            if warmup_period and warmup_period not in periods:
                periods.insert(0, warmup_period)
            bars = self._load_months(symbol, periods)
            features = build_c2_signals(bars)
            config = FixedHorizonConfig(
                side="long",
                entry_delay_bars=1,
                hold_bars=6,
                overlap="single_position",
                costs=CostModel(fees=0.0006),
            )
            actual = simulate_fixed_horizon(bars, features["signal"], config)
            actual.insert(0, "symbol", symbol)
            if warmup_period:
                holdout_start = frozen[signal_column].dt.floor("D").min()
                actual = actual[actual["signal_time"] >= holdout_start]
            actual_frames.append(actual)

        actual = pd.concat(actual_frames, ignore_index=True).sort_values(
            ["signal_time", "symbol"], ignore_index=True
        )
        expected = frozen.sort_values([signal_column, "symbol"], ignore_index=True)
        self.assertEqual(len(actual), len(expected))
        pd.testing.assert_series_equal(
            actual.signal_time, expected[signal_column], check_names=False
        )
        pd.testing.assert_series_equal(
            actual.gross_return, expected.gross_return, check_names=False, rtol=1e-12
        )

    def test_frozen_development_signals_are_regenerated_without_lookahead(self):
        self._assert_generated_signals("c2_canonical_trades.csv", "signal_time")

    def test_frozen_holdout_signals_are_regenerated_with_july_warmup(self):
        self._assert_generated_signals(
            "c2_august_holdout_trades.csv", "open_time", warmup_period="2026-07"
        )


if __name__ == "__main__":
    unittest.main()

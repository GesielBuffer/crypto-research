import unittest
from pathlib import Path

import pandas as pd

from research.backtest import CostModel, FixedHorizonConfig
from research.regression import replay_frozen_trades


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


if __name__ == "__main__":
    unittest.main()

import unittest

import pandas as pd

from research.experiments.cross_sectional_momentum import (
    _capped_inverse_vol,
    select_universe,
    simulate,
)


class CrossSectionalMomentumTests(unittest.TestCase):
    def test_inverse_vol_weights_respect_cap_and_gross(self):
        vol = pd.Series({"A": 0.1, "B": 0.2, "C": 0.3, "D": 0.4})
        weights = _capped_inverse_vol(vol, gross=0.5, cap=0.15)
        self.assertAlmostEqual(weights.sum(), 0.5)
        self.assertLessEqual(weights.max(), 0.15)

    def test_signal_does_not_change_when_future_prices_change(self):
        index = pd.date_range("2024-01-01", "2024-04-10", freq="4h", tz="UTC")
        symbols = [f"S{i:02d}" for i in range(16)]
        closes = pd.DataFrame({s: 100 + i + pd.Series(range(len(index)), index=index) * (i + 1) / 1000 for i, s in enumerate(symbols)}, index=index)
        opens = closes.copy()
        first, _ = simulate(closes, opens, lookback_days=7, rebalance_days=1, skip_hours=24, long_fraction=0.25, short_fraction=0.25)
        changed = closes.copy()
        changed.loc[changed.index >= pd.Timestamp("2024-04-03", tz="UTC"), "S00"] *= 100
        second, _ = simulate(changed, opens, lookback_days=7, rebalance_days=1, skip_hours=24, long_fraction=0.25, short_fraction=0.25)
        pd.testing.assert_series_equal(first.iloc[0], second.iloc[0])

    def test_universe_selection_uses_formation_liquidity_only(self):
        index = pd.date_range("2024-01-01", "2024-04-01", freq="4h", inclusive="left", tz="UTC")
        frames = {}
        symbols = [f"S{i:02d}" for i in range(17)]
        for i, symbol in enumerate(symbols):
            frames[symbol] = pd.DataFrame({"open_time": index, "quote_volume": float(i + 1)})
        protocol = {"universe": {"formation_start": "2024-01-01", "formation_end": "2024-04-01", "minimum_daily_coverage": 0.9}}
        selected, ranking = select_universe(frames, protocol)
        self.assertNotIn("S00", selected)
        self.assertEqual(len(selected), 16)
        self.assertTrue(ranking.loc[ranking["symbol"] == "S16", "selected"].item())


if __name__ == "__main__":
    unittest.main()

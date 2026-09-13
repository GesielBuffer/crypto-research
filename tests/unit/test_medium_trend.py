import unittest

import pandas as pd

from research.experiments.medium_trend import build_event_signal


class MediumTrendTests(unittest.TestCase):
    def bars(self):
        size = 700
        frame = pd.DataFrame({
            "ema_24": [90.0] * size,
            "ema_96": [100.0 + index / 100 for index in range(size)],
            "adx": [30.0] * size,
            "plus_di": [35.0] * size,
            "minus_di": [10.0] * size,
        })
        frame.loc[400:, "ema_24"] = 110.0
        return frame

    def test_signal_occurs_only_on_first_regime_bar(self):
        signal = build_event_signal(
            self.bars(), fast_span=24, slow_span=96, adx_threshold=25, side="long"
        )
        self.assertEqual(signal[signal].index.tolist(), [400])

    def test_future_changes_do_not_change_past_signal(self):
        original = self.bars()
        changed = original.copy()
        changed.loc[500:, ["ema_24", "ema_96", "adx", "plus_di", "minus_di"]] = 0
        before = build_event_signal(
            original, fast_span=24, slow_span=96, adx_threshold=25, side="long"
        )
        after = build_event_signal(
            changed, fast_span=24, slow_span=96, adx_threshold=25, side="long"
        )
        pd.testing.assert_series_equal(before.loc[:499], after.loc[:499])

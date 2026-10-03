import unittest
from pathlib import Path
import tempfile
import json

from research.experiments.september_month_close import load_protocol


class SeptemberMonthCloseTests(unittest.TestCase):
    def test_frozen_month_close_cannot_change_holdout_fail(self):
        path = Path(__file__).parents[2] / "results" / "september_2026_month_close.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["formal_holdout_decision"], "FAIL")
        self.assertEqual(report["effect"], "DIAGNOSTIC_ONLY")
        self.assertLess(report["full_month"][0]["profit_factor"], 1.0)

    def test_protocol_cannot_change_frozen_holdout_decision(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.toml"
            path.write_text(
                '[experiment]\nstatus="PREREGISTERED_DIAGNOSTIC"\n'
                '[decision]\nformal_holdout_decision="PASS"\neffect="DIAGNOSTIC_ONLY"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "cannot replace"):
                load_protocol(path)


if __name__ == "__main__":
    unittest.main()

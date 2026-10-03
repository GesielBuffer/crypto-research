import unittest
from pathlib import Path
import tempfile

from research.experiments.september_month_close import load_protocol


class SeptemberMonthCloseTests(unittest.TestCase):
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

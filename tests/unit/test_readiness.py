import unittest

from execution.readiness import REQUIRED_LIVE_GATES, live_blockers


class ReadinessTests(unittest.TestCase):
    def test_real_trading_is_blocked_by_default(self):
        document = {
            "deployment": {"mode": "paper", "real_trading_enabled": False},
            "gates": {},
        }
        blockers = live_blockers(document)
        self.assertTrue(set(REQUIRED_LIVE_GATES).issubset(blockers))
        self.assertIn("real_trading_is_disabled", blockers)

    def test_all_gates_are_required_for_live(self):
        document = {
            "deployment": {"mode": "live", "real_trading_enabled": True},
            "gates": {gate: True for gate in REQUIRED_LIVE_GATES},
        }
        self.assertEqual(live_blockers(document), [])

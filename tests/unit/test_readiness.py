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
            "deployment": {
                "mode": "live",
                "real_trading_enabled": True,
                "approved_strategy_id": "approved-v1",
            },
            "gates": {gate: True for gate in REQUIRED_LIVE_GATES},
            "evidence": {
                "current_holdout_decision": "PASS",
                "paper_report_sha256": "abc",
                "testnet_report_sha256": "def",
                "failure_recovery_report_sha256": "ghi",
                "human_approval_ref": "approval-1",
            },
        }
        self.assertEqual(live_blockers(document), [])

    def test_boolean_gates_without_evidence_remain_blocked(self):
        document = {
            "deployment": {"mode": "live", "real_trading_enabled": True},
            "gates": {gate: True for gate in REQUIRED_LIVE_GATES},
            "evidence": {"current_holdout_decision": "FAIL"},
        }
        blockers = live_blockers(document)
        self.assertIn("approved_strategy_id_is_missing", blockers)
        self.assertIn("holdout_evidence_is_not_pass", blockers)
        self.assertIn("paper_report_sha256_is_missing", blockers)
        self.assertIn("failure_recovery_report_sha256_is_missing", blockers)

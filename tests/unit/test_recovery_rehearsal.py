import unittest
from datetime import datetime, timezone

from execution.recovery_rehearsal import run_rehearsal


class RecoveryRehearsalTests(unittest.TestCase):
    def test_all_scenarios_pass_without_duplicate_entry(self):
        generated_at = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)

        report = run_rehearsal(
            generated_at=generated_at,
            implementation_commit="abc123",
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["scenario_count"], 5)
        self.assertEqual(report["duplicate_entry_submissions"], 0)
        self.assertEqual(report["implementation_commit"], "abc123")
        self.assertEqual(
            {scenario["actual_status"] for scenario in report["scenarios"]},
            {"protected", "closed", "unresolved", "divergence"},
        )


if __name__ == "__main__":
    unittest.main()

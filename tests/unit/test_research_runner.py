import unittest

from research.run_research import load_registry, run_experiment


class ResearchRunnerTests(unittest.TestCase):
    def test_registry_contains_frozen_development_and_holdout(self):
        registry = load_registry()
        self.assertIn("c2_development_replay", registry)
        self.assertIn("c2_august_holdout_replay", registry)
        self.assertEqual(registry["c2_august_holdout_replay"]["expected_decision"], "FAIL")

    def test_unknown_experiment_is_rejected(self):
        with self.assertRaises(ValueError):
            run_experiment("does_not_exist", write_report=False)

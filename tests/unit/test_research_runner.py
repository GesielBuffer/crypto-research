import unittest

from research.run_research import load_registry, run_experiment, validate_experiment_spec


class ResearchRunnerTests(unittest.TestCase):
    def setUp(self):
        self.valid_spec = load_registry()["c2_development_replay"].copy()

    def test_registry_contains_frozen_development_and_holdout(self):
        registry = load_registry()
        self.assertIn("c2_development_replay", registry)
        self.assertIn("c2_august_holdout_replay", registry)
        self.assertIn("trend_short_cost_sensitivity", registry)
        self.assertEqual(registry["c2_august_holdout_replay"]["expected_decision"], "FAIL")

    def test_unknown_experiment_is_rejected(self):
        with self.assertRaises(ValueError):
            run_experiment("does_not_exist", write_report=False)

    def test_registry_rejects_missing_required_field(self):
        del self.valid_spec["cost"]
        with self.assertRaisesRegex(ValueError, "missing fields.*cost"):
            validate_experiment_spec("invalid", self.valid_spec)

    def test_registry_rejects_same_candle_entry(self):
        self.valid_spec["entry_delay_bars"] = 0
        with self.assertRaisesRegex(ValueError, "t\\+1"):
            validate_experiment_spec("invalid", self.valid_spec)

    def test_registry_rejects_paths_outside_repository(self):
        self.valid_spec["trades_file"] = "../secret.csv"
        with self.assertRaisesRegex(ValueError, "inside the repository"):
            validate_experiment_spec("invalid", self.valid_spec)

    def test_registry_rejects_evaluation_outside_data_period(self):
        self.valid_spec["evaluation_end"] = "2027-01-01"
        with self.assertRaisesRegex(ValueError, "inside the data period"):
            validate_experiment_spec("invalid", self.valid_spec)

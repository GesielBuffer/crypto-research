import unittest
from pathlib import Path

import pandas as pd

from research.experiments.c2_exit_policy import decide, load_protocol


ROOT = Path(__file__).resolve().parents[2]


class C2ExitPolicyTests(unittest.TestCase):
    def setUp(self):
        self.protocol = load_protocol(ROOT / "experiments" / "c2_exit_policy_v1.toml")

    def test_protocol_is_preregistered_and_excludes_opened_holdout(self):
        self.assertEqual(self.protocol["experiment"]["status"], "PREREGISTERED")
        self.assertEqual(self.protocol["splits"]["confirmation_end"], "2026-08-01")
        self.assertEqual(
            self.protocol["decision"]["production_effect"],
            "NONE; C2 remains rejected and a future strategy still requires a fresh untouched holdout.",
        )

    def frames(self):
        summary = []
        assets = []
        for split in ("validation", "confirmation"):
            for cost in (0.0006, 0.001):
                for policy, activation, mean, profit_factor, q10 in (
                    ("no_break_even", None, 0.001, 1.10, -0.01),
                    ("break_even_1r", 1.0, 0.0011, 1.20, -0.009),
                ):
                    common = {
                        "stop_loss_fraction": 0.01,
                        "take_profit_r_multiple": 2.0,
                        "policy": policy,
                        "activation_r_multiple": activation,
                        "split": split,
                        "cost": cost,
                    }
                    summary.append({
                        **common,
                        "mean_return": mean,
                        "profit_factor": profit_factor,
                        "q10": q10,
                    })
                    for symbol in self.protocol["data"]["symbols"]:
                        assets.append({
                            **common,
                            "symbol": symbol,
                            "profit_factor": profit_factor,
                        })
        return pd.DataFrame(summary), pd.DataFrame(assets)

    def test_decision_accepts_only_a_rule_that_clears_every_pairwise_gate(self):
        summary, assets = self.frames()
        decision = decide(self.protocol, summary, assets)
        self.assertEqual(decision["decision"], "PASS_EXPLORATORY")
        self.assertEqual(decision["passing_break_even_rules"], 1)
        self.assertEqual(decision["production_effect"], "NONE")

        mask = (
            (summary["policy"] == "break_even_1r")
            & (summary["split"] == "validation")
            & (summary["cost"] == 0.001)
        )
        summary.loc[mask, "mean_return"] = -0.01
        failed = decide(self.protocol, summary, assets)
        self.assertEqual(failed["decision"], "FAIL")
        self.assertEqual(failed["passing_break_even_rules"], 0)


if __name__ == "__main__":
    unittest.main()

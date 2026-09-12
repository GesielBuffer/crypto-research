"""Compatibility entry point for the migrated cost-sensitivity experiment."""

from __future__ import annotations

import json

from research.run_research import run_experiment


EXPERIMENT_ID = "trend_short_cost_sensitivity"


def main() -> int:
    report = run_experiment(EXPERIMENT_ID)
    print(json.dumps({
        "experiment_id": report["experiment_id"],
        "status": report["status"],
        "expected_decision": report["expected_decision"],
        "metrics": report["metrics"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import tomllib
from pathlib import Path


REQUIRED_LIVE_GATES = (
    "strategy_approved",
    "fresh_holdout_passed",
    "paper_trading_passed",
    "testnet_passed",
    "failure_recovery_tested",
    "order_reconciliation_tested",
    "kill_switch_tested",
)


def load_readiness(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def live_blockers(document: dict) -> list[str]:
    deployment = document.get("deployment", {})
    gates = document.get("gates", {})
    blockers = [gate for gate in REQUIRED_LIVE_GATES if not gates.get(gate, False)]
    if deployment.get("mode") != "live":
        blockers.append("deployment_mode_is_not_live")
    if not deployment.get("real_trading_enabled", False):
        blockers.append("real_trading_is_disabled")
    return blockers

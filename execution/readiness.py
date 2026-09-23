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
    "position_protection_tested",
    "emergency_close_tested",
    "live_adapter_reviewed",
    "human_live_approval",
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
    evidence = document.get("evidence", {})
    if gates.get("strategy_approved") and not deployment.get("approved_strategy_id"):
        blockers.append("approved_strategy_id_is_missing")
    if gates.get("fresh_holdout_passed") and evidence.get("current_holdout_decision") != "PASS":
        blockers.append("holdout_evidence_is_not_pass")
    for gate, field in (
        ("paper_trading_passed", "paper_report_sha256"),
        ("testnet_passed", "testnet_report_sha256"),
        ("failure_recovery_tested", "failure_recovery_report_sha256"),
        ("human_live_approval", "human_approval_ref"),
    ):
        if gates.get(gate) and not evidence.get(field):
            blockers.append(f"{field}_is_missing")
    return blockers

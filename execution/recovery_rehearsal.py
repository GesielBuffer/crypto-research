"""Run a credential-free restart recovery rehearsal and write JSON evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from execution.journal import JsonlOrderJournal
from execution.models import Fill, OrderIntent, PositionProtection, Side
from execution.paper import PaperExchange
from execution.recovery import JournalRecovery
from execution.risk import RiskEngine, RiskLimits
from execution.service import TradingService
from research.config import BASE_DIR


DEFAULT_OUTPUT = BASE_DIR / "results" / "operational_recovery_rehearsal.json"
STRATEGY_ID = "recovery-rehearsal-v1"
OBSERVED_AT = datetime(2026, 9, 23, tzinfo=timezone.utc)


class CountingPaperExchange(PaperExchange):
    def __init__(self) -> None:
        super().__init__()
        self.entry_submissions = 0

    def submit_market(self, intent: OrderIntent) -> Fill:
        self.entry_submissions += 1
        return super().submit_market(intent)


def _intent(suffix: str) -> OrderIntent:
    return OrderIntent(
        strategy_id=STRATEGY_ID,
        symbol="BTCUSDT",
        side=Side.BUY,
        quantity=Decimal("0.001"),
        reference_price=Decimal("50000"),
        leverage=1,
        client_order_id=f"recovery-{suffix}",
        market_data_time=OBSERVED_AT,
        protection=PositionProtection(
            stop_loss_price=Decimal("49500"),
            take_profit_price=Decimal("51000"),
        ),
    )


def _runtime(directory: Path) -> tuple[CountingPaperExchange, JsonlOrderJournal, TradingService]:
    exchange = CountingPaperExchange()
    journal = JsonlOrderJournal(directory / "orders.jsonl")
    risk = RiskEngine(RiskLimits(approved_strategies=frozenset({STRATEGY_ID})))
    return exchange, journal, TradingService(exchange, risk, journal)


def _result(
    name: str,
    expected_status: str,
    exchange: CountingPaperExchange,
    journal: JsonlOrderJournal,
    service: TradingService,
) -> dict:
    exchange.entry_submissions = 0
    report = JournalRecovery(service, journal).recover()
    actual_status = report.items[0].status
    no_duplicate_entry = exchange.entry_submissions == 0
    return {
        "name": name,
        "expected_status": expected_status,
        "actual_status": actual_status,
        "recovery_entry_submissions": exchange.entry_submissions,
        "passed": actual_status == expected_status and no_duplicate_entry,
    }


def run_rehearsal(*, generated_at: datetime, implementation_commit: str) -> dict:
    scenarios = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)

        exchange, journal, service = _runtime(root / "accepted")
        order = _intent("accepted")
        journal.record_intent(order)
        exchange.submit_market(order)
        scenarios.append(
            _result("response_lost_after_accept", "protected", exchange, journal, service)
        )

        exchange, journal, service = _runtime(root / "protected")
        order = _intent("protected")
        service.execute(order, now=OBSERVED_AT)
        scenarios.append(
            _result("already_protected_restart", "protected", exchange, journal, service)
        )

        exchange, journal, service = _runtime(root / "closed")
        order = _intent("closed")
        fill = exchange.submit_market(order)
        journal.record_intent(order)
        journal.record_fill(fill)
        exchange.simulate_protection_fill(order)
        scenarios.append(
            _result("exchange_side_close", "closed", exchange, journal, service)
        )

        exchange, journal, service = _runtime(root / "unresolved")
        journal.record_intent(_intent("unresolved"))
        scenarios.append(
            _result("unresolved_submission", "unresolved", exchange, journal, service)
        )

        exchange, journal, service = _runtime(root / "divergence")
        order = _intent("divergence")
        journal.record_intent(order)
        journal.record_fill(Fill.from_intent(order))
        scenarios.append(
            _result("journal_exchange_divergence", "divergence", exchange, journal, service)
        )

    return {
        "schema_version": 1,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "implementation_commit": implementation_commit,
        "environment": "deterministic-paper-no-network-no-credentials",
        "passed": all(scenario["passed"] for scenario in scenarios),
        "scenario_count": len(scenarios),
        "duplicate_entry_submissions": sum(
            scenario["recovery_entry_submissions"] for scenario in scenarios
        ),
        "scenarios": scenarios,
    }


def _git_commit() -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={BASE_DIR.as_posix()}",
            "rev-parse",
            "HEAD",
        ],
        cwd=BASE_DIR,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run_rehearsal(
        generated_at=datetime.now(timezone.utc),
        implementation_commit=_git_commit(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

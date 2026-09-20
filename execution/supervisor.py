from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import requests

from execution.models import OrderIntent, ProtectionReceipt
from execution.service import TradingService


class SupervisorUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SupervisorConfig:
    poll_interval_seconds: float = 1.0
    initial_backoff_seconds: float = 1.0
    maximum_backoff_seconds: float = 30.0
    max_consecutive_failures: int = 3

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self.initial_backoff_seconds <= 0:
            raise ValueError("initial_backoff_seconds must be positive")
        if self.maximum_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("maximum_backoff_seconds must cover initial backoff")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be at least one")


@dataclass(frozen=True)
class SupervisorResult:
    cycles: int
    transient_failures: int
    reason: str
    protection: ProtectionReceipt | None = None


class PositionSupervisor:
    """Supervise one protected position without creating an entry order."""

    RETRYABLE_ERRORS = (
        ConnectionError,
        TimeoutError,
        requests.exceptions.RequestException,
    )

    def __init__(
        self,
        service: TradingService,
        config: SupervisorConfig | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.service = service
        self.config = config or SupervisorConfig()
        self.sleeper = sleeper
        self.clock = clock

    def run(
        self,
        intent: OrderIntent,
        *,
        should_stop: Callable[[], bool],
        max_cycles: int | None = None,
    ) -> SupervisorResult:
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("max_cycles must be at least one")
        if not intent.protection.break_even.enabled:
            return SupervisorResult(0, 0, "policy_disabled")

        cycles = 0
        total_failures = 0
        consecutive_failures = 0
        while not should_stop():
            try:
                protection = self.service.supervise_position(
                    intent, now=self.clock()
                )
            except self.RETRYABLE_ERRORS as exc:
                total_failures += 1
                consecutive_failures += 1
                if consecutive_failures >= self.config.max_consecutive_failures:
                    raise SupervisorUnavailable(
                        "market supervision exceeded the transient failure limit"
                    ) from exc
                delay = min(
                    self.config.initial_backoff_seconds
                    * (2 ** (consecutive_failures - 1)),
                    self.config.maximum_backoff_seconds,
                )
                self.sleeper(delay)
                continue

            cycles += 1
            consecutive_failures = 0
            if protection is not None:
                return SupervisorResult(
                    cycles,
                    total_failures,
                    "protection_adjusted",
                    protection,
                )
            if max_cycles is not None and cycles >= max_cycles:
                return SupervisorResult(cycles, total_failures, "cycle_limit")
            self.sleeper(self.config.poll_interval_seconds)

        return SupervisorResult(cycles, total_failures, "stop_requested")

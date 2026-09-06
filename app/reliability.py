"""Lesson 10 - reliability boundaries around external services (Bedrock).

Two small, dependency-free primitives:

- ``retry_call``: bounded exponential-backoff retry for transient failures.
- ``CircuitBreaker``: stops hammering a failing dependency by "opening" after a
  threshold of consecutive failures, then probing again after a cooldown.

Both accept injected ``sleep`` / ``clock`` callables so they are fully
deterministic under test. They wrap the Bedrock call in app/cli.py; the
deterministic solver / resilience layers never fail transiently and are not
wrapped.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a call is attempted while the circuit is open."""


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.2,
    max_delay: float = 5.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Call ``fn`` up to ``attempts`` times with exponential backoff.

    Re-raises the last exception if every attempt fails. ``sleep`` is injectable
    for tests (defaults to ``time.sleep``).
    """

    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    sleeper = sleep if sleep is not None else time.sleep
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt == attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning("retry %d/%d after error: %s (sleeping %.2fs)", attempt, attempts, exc, delay)
            sleeper(delay)
    assert last_exc is not None  # loop always sets it before breaking
    raise last_exc


@dataclass
class CircuitBreaker:
    """A minimal three-state circuit breaker (closed -> open -> half_open).

    - ``closed``: calls pass through; consecutive failures are counted.
    - ``open``: calls fail fast with ``CircuitBreakerOpenError`` until
      ``reset_timeout`` elapses.
    - ``half_open``: the next call is a probe; success closes the circuit,
      failure re-opens it.
    """

    failure_threshold: int = 3
    reset_timeout: float = 30.0
    clock: Callable[[], float] | None = None

    _failures: int = field(default=0, init=False)
    _state: str = field(default="closed", init=False)
    _opened_at: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.clock is None:
            self.clock = time.monotonic

    @property
    def state(self) -> str:
        """Current state, lazily transitioning open -> half_open after cooldown."""

        if self._state == "open" and self._opened_at is not None:
            assert self.clock is not None
            if self.clock() - self._opened_at >= self.reset_timeout:
                self._state = "half_open"
        return self._state

    def call(self, fn: Callable[[], T]) -> T:
        """Run ``fn`` through the breaker, updating state on success/failure."""

        if self.state == "open":
            raise CircuitBreakerOpenError("circuit is open; refusing call")
        try:
            result = fn()
        except Exception:
            self._on_failure()
            raise
        self._on_success()
        return result

    def _on_success(self) -> None:
        self._failures = 0
        self._state = "closed"
        self._opened_at = None

    def _on_failure(self) -> None:
        assert self.clock is not None
        self._failures += 1
        if self._state == "half_open" or self._failures >= self.failure_threshold:
            self._state = "open"
            self._opened_at = self.clock()

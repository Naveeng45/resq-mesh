from __future__ import annotations

import unittest

from app.reliability import CircuitBreaker, CircuitBreakerOpenError, retry_call


class RetryCallTest(unittest.TestCase):
    def test_succeeds_after_transient_failures(self) -> None:
        attempts = {"n": 0}
        delays: list[float] = []

        def flaky() -> str:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("transient")
            return "ok"

        result = retry_call(flaky, attempts=3, base_delay=0.1, sleep=delays.append)
        self.assertEqual(result, "ok")
        self.assertEqual(attempts["n"], 3)
        self.assertEqual(delays, [0.1, 0.2])  # exponential backoff between attempts

    def test_raises_after_exhausting_attempts(self) -> None:
        def always_fail() -> None:
            raise RuntimeError("nope")

        with self.assertRaises(RuntimeError):
            retry_call(always_fail, attempts=2, sleep=lambda _: None)

    def test_does_not_retry_unlisted_exceptions(self) -> None:
        calls = {"n": 0}

        def boom() -> None:
            calls["n"] += 1
            raise KeyError("unexpected")

        with self.assertRaises(KeyError):
            retry_call(boom, attempts=3, retry_on=(RuntimeError,), sleep=lambda _: None)
        self.assertEqual(calls["n"], 1)


class CircuitBreakerTest(unittest.TestCase):
    def test_opens_after_threshold_then_fails_fast(self) -> None:
        clock = {"t": 0.0}
        breaker = CircuitBreaker(failure_threshold=2, reset_timeout=10.0, clock=lambda: clock["t"])

        for _ in range(2):
            with self.assertRaises(RuntimeError):
                breaker.call(self._fail)
        self.assertEqual(breaker.state, "open")

        with self.assertRaises(CircuitBreakerOpenError):
            breaker.call(lambda: "should not run")

    def test_half_open_probe_closes_on_success(self) -> None:
        clock = {"t": 0.0}
        breaker = CircuitBreaker(failure_threshold=1, reset_timeout=5.0, clock=lambda: clock["t"])

        with self.assertRaises(RuntimeError):
            breaker.call(self._fail)
        self.assertEqual(breaker.state, "open")

        clock["t"] = 5.0  # cooldown elapsed -> half_open on next state read
        self.assertEqual(breaker.state, "half_open")

        self.assertEqual(breaker.call(lambda: "recovered"), "recovered")
        self.assertEqual(breaker.state, "closed")

    def test_half_open_probe_reopens_on_failure(self) -> None:
        clock = {"t": 0.0}
        breaker = CircuitBreaker(failure_threshold=1, reset_timeout=5.0, clock=lambda: clock["t"])

        with self.assertRaises(RuntimeError):
            breaker.call(self._fail)
        clock["t"] = 5.0
        self.assertEqual(breaker.state, "half_open")

        with self.assertRaises(RuntimeError):
            breaker.call(self._fail)
        self.assertEqual(breaker.state, "open")

    @staticmethod
    def _fail() -> None:
        raise RuntimeError("dependency down")


if __name__ == "__main__":
    unittest.main()

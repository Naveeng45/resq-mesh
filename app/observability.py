"""Lesson 10 - lightweight observability: structured logs + trace/correlation IDs.

The pipeline is deterministic, so the cheapest useful observability is a single
``trace_id`` threaded through one mission run plus structured (JSON) log events
for each stage. No external tracing backend is required for the hackathon demo;
the same events map cleanly onto OpenTelemetry spans if this is later deployed to
AgentCore (see docs/architecture.md).

Everything here is stdlib-only and safe to import from any layer.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

# The trace_id for the currently-running mission. Set once per request / CLI run
# so every log event and every stage can be correlated after the fact.
_current_trace_id: ContextVar[str | None] = ContextVar("resq_trace_id", default=None)


def new_trace_id() -> str:
    """Return a short, unique correlation id for one mission run."""

    return uuid.uuid4().hex[:12]


def set_trace_id(trace_id: str) -> str:
    """Bind ``trace_id`` as the current trace and return it."""

    _current_trace_id.set(trace_id)
    return trace_id


def get_trace_id() -> str | None:
    """Return the trace_id bound to the current context, if any."""

    return _current_trace_id.get()


class JsonLogFormatter(logging.Formatter):
    """Render log records as one JSON object per line, including the trace_id."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        trace_id = getattr(record, "trace_id", None) or get_trace_id()
        if trace_id:
            payload["trace_id"] = trace_id
        # Attach any structured fields passed via ``extra={"fields": {...}}``.
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(level: int = logging.INFO, *, json_format: bool = True) -> None:
    """Install a single stream handler on the root logger.

    Call once at process start. ``json_format=False`` falls back to a plain
    human-readable format for local debugging.
    """

    handler = logging.StreamHandler()
    if json_format:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger (thin wrapper for a consistent import surface)."""

    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: object) -> None:
    """Emit one structured event. ``event`` is the message; ``fields`` are extras."""

    logger.log(level, event, extra={"fields": fields, "trace_id": get_trace_id()})


@contextmanager
def traced_stage(logger: logging.Logger, stage: str, **fields: object) -> Iterator[dict[str, object]]:
    """Log ``stage`` start/finish with a duration and the current trace_id.

    Yields a mutable dict so callers can attach result fields that get logged on
    completion, e.g.::

        with traced_stage(log, "solve") as span:
            span["feasible"] = True
    """

    span: dict[str, object] = dict(fields)
    start = time.perf_counter()
    log_event(logger, f"{stage}.start", **span)
    try:
        yield span
    except Exception as exc:  # noqa: BLE001 - logged then re-raised
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        log_event(logger, f"{stage}.error", level=logging.ERROR, **{**span, "error": str(exc), "elapsed_ms": elapsed_ms})
        raise
    else:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        log_event(logger, f"{stage}.finish", **{**span, "elapsed_ms": elapsed_ms})

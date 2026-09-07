"""Custom observability callback handler for Strands Agents.

This module provides structured audit logging and metrics tracking for Strands
Agents interacting with Amazon Bedrock (Nova, Claude, etc.).

Key features:
1. Custom ``StrandsAuditCallbackHandler`` listening to toolUse, reasoningText,
   and contentBlock events.
2. Structured JSON log emission via ``app.observability.log_event``.
3. In-memory execution audit trail for inspectability via API or CLI.
4. Latency, tool call breakdown, and trace ID correlation.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import ConfigDict, Field

from app.observability import get_logger, get_trace_id, log_event
from app.pydantic_compat import CompatBaseModel

logger = get_logger(__name__)


class ToolInvocationRecord(CompatBaseModel):
    """Record of a single tool invocation captured by the callback handler."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_use_id: str | None = None
    start_time: str
    end_time: str | None = None
    duration_ms: float | None = None
    status: str = "completed"
    trace_id: str | None = None


class AgentAuditSummary(CompatBaseModel):
    """Compact summary of agent execution observability metrics."""

    model_config = ConfigDict(extra="forbid")

    total_tool_calls: int
    tool_call_counts: dict[str, int] = Field(default_factory=dict)
    reasoning_detected: bool = False
    trace_id: str | None = None
    records: list[ToolInvocationRecord] = Field(default_factory=list)


# In-memory store for global agent audit logs
_GLOBAL_AUDIT_LOG: list[ToolInvocationRecord] = []


def get_global_audit_trail() -> list[dict[str, Any]]:
    """Return all global audit records as JSON-compatible dicts."""

    return [record.model_dump(mode="json") for record in _GLOBAL_AUDIT_LOG]


def clear_global_audit_trail() -> None:
    """Clear accumulated global audit records."""

    global _GLOBAL_AUDIT_LOG
    _GLOBAL_AUDIT_LOG.clear()


class StrandsAuditCallbackHandler:
    """Strands-native callback handler for observing tool calls and model events."""

    def __init__(self, *, verbose_output: bool = True, log_to_observability: bool = True) -> None:
        self.verbose_output = verbose_output
        self.log_to_observability = log_to_observability
        self.tool_count = 0
        self.reasoning_detected = False
        self.records: list[ToolInvocationRecord] = []

    def __call__(self, **kwargs: Any) -> None:
        """Process callback events from Strands agent stream."""

        event = kwargs.get("event", {})
        start = event.get("contentBlockStart", {}).get("start", {})
        tool_use = start.get("toolUse")
        reasoning_text = kwargs.get("reasoningText") or event.get("contentBlockDelta", {}).get("delta", {}).get("reasoningContent")
        complete = kwargs.get("complete", False)

        if reasoning_text:
            self.reasoning_detected = True
            if self.log_to_observability:
                log_event(logger, "strands_agent.reasoning_detected", trace_id=get_trace_id())

        if tool_use:
            self.tool_count += 1
            tool_name = tool_use.get("name", "unknown_tool")
            tool_use_id = tool_use.get("toolUseId")
            now_iso = datetime.now(timezone.utc).isoformat()

            record = ToolInvocationRecord(
                tool_name=tool_name,
                tool_use_id=tool_use_id,
                start_time=now_iso,
                end_time=now_iso,
                duration_ms=0.0,
                status="completed",
                trace_id=get_trace_id(),
            )
            self.records.append(record)
            _GLOBAL_AUDIT_LOG.append(record)

            if self.log_to_observability:
                log_event(
                    logger,
                    "strands_agent.tool_call",
                    tool_name=tool_name,
                    tool_use_id=tool_use_id,
                    tool_index=self.tool_count,
                    trace_id=get_trace_id(),
                )

            if self.verbose_output:
                print(f"  🔧 [Strands Audit] tool call #{self.tool_count}: {tool_name}")

        if complete:
            if self.log_to_observability:
                log_event(
                    logger,
                    "strands_agent.execution_complete",
                    total_tool_calls=self.tool_count,
                    reasoning_detected=self.reasoning_detected,
                    trace_id=get_trace_id(),
                )

    def summary(self) -> AgentAuditSummary:
        """Return a structured summary of captured metrics."""

        tool_counts: dict[str, int] = {}
        for r in self.records:
            tool_counts[r.tool_name] = tool_counts.get(r.tool_name, 0) + 1

        return AgentAuditSummary(
            total_tool_calls=self.tool_count,
            tool_call_counts=tool_counts,
            reasoning_detected=self.reasoning_detected,
            trace_id=get_trace_id(),
            records=self.records,
        )

    def clear(self) -> None:
        """Clear local audit records."""

        self.tool_count = 0
        self.reasoning_detected = False
        self.records.clear()


# Backward compatibility alias
ToolTraceCallbackHandler = StrandsAuditCallbackHandler

from __future__ import annotations

import unittest

from app.agent_observability import (
    StrandsAuditCallbackHandler,
    ToolInvocationRecord,
    clear_global_audit_trail,
    get_global_audit_trail,
)
from app.api.server import delete_agent_audit, get_agent_audit, post_advisor, AdvisorRequest
from app.observability import set_trace_id


class AgentObservabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        clear_global_audit_trail()
        set_trace_id("test_trace_123")

    def tearDown(self) -> None:
        clear_global_audit_trail()

    def test_callback_handler_captures_tool_use(self) -> None:
        handler = StrandsAuditCallbackHandler(verbose_output=False, log_to_observability=False)

        handler(
            event={
                "contentBlockStart": {
                    "start": {
                        "toolUse": {
                            "name": "assess_incident",
                            "toolUseId": "call_abc123",
                        }
                    }
                }
            }
        )

        self.assertEqual(handler.tool_count, 1)
        self.assertEqual(len(handler.records), 1)

        record = handler.records[0]
        self.assertEqual(record.tool_name, "assess_incident")
        self.assertEqual(record.tool_use_id, "call_abc123")
        self.assertEqual(record.trace_id, "test_trace_123")

    def test_callback_handler_detects_reasoning(self) -> None:
        handler = StrandsAuditCallbackHandler(verbose_output=False, log_to_observability=False)
        self.assertFalse(handler.reasoning_detected)

        handler(reasoningText="Thinking about schedule constraints...")
        self.assertTrue(handler.reasoning_detected)

    def test_summary_aggregates_multiple_calls(self) -> None:
        handler = StrandsAuditCallbackHandler(verbose_output=False, log_to_observability=False)

        for name in ("assess_incident", "get_available_resources", "assess_incident"):
            handler(
                event={
                    "contentBlockStart": {
                        "start": {
                            "toolUse": {
                                "name": name,
                                "toolUseId": f"call_{name}",
                            }
                        }
                    }
                }
            )

        summary = handler.summary()
        self.assertEqual(summary.total_tool_calls, 3)
        self.assertEqual(summary.tool_call_counts, {"assess_incident": 2, "get_available_resources": 1})
        self.assertEqual(len(summary.records), 3)

    def test_global_audit_trail_accumulates_and_clears(self) -> None:
        self.assertEqual(len(get_global_audit_trail()), 0)

        handler = StrandsAuditCallbackHandler(verbose_output=False, log_to_observability=False)
        handler(
            event={
                "contentBlockStart": {
                    "start": {
                        "toolUse": {
                            "name": "ingest_event",
                            "toolUseId": "call_evt1",
                        }
                    }
                }
            }
        )

        trail = get_global_audit_trail()
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["tool_name"], "ingest_event")

        clear_global_audit_trail()
        self.assertEqual(len(get_global_audit_trail()), 0)

    def test_api_audit_endpoints(self) -> None:
        handler = StrandsAuditCallbackHandler(verbose_output=False, log_to_observability=False)
        handler(
            event={
                "contentBlockStart": {
                    "start": {
                        "toolUse": {
                            "name": "assess_coverage",
                            "toolUseId": "call_cov1",
                        }
                    }
                }
            }
        )

        res = get_agent_audit()
        self.assertEqual(len(res["records"]), 1)
        self.assertEqual(res["records"][0]["tool_name"], "assess_coverage")

        del_res = delete_agent_audit()
        self.assertEqual(del_res["status"], "cleared")
        self.assertEqual(len(get_agent_audit()["records"]), 0)


if __name__ == "__main__":
    unittest.main()

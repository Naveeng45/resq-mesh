from __future__ import annotations

import json
import logging
import unittest

from app.observability import (
    JsonLogFormatter,
    get_trace_id,
    log_event,
    new_trace_id,
    set_trace_id,
    traced_stage,
)


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class ObservabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test.observability")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.handler = _ListHandler()
        self.logger.addHandler(self.handler)

    def tearDown(self) -> None:
        self.logger.removeHandler(self.handler)

    def test_trace_id_is_short_unique_and_bindable(self) -> None:
        first = new_trace_id()
        second = new_trace_id()
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 12)

        set_trace_id(first)
        self.assertEqual(get_trace_id(), first)

    def test_json_formatter_emits_trace_id_and_fields(self) -> None:
        set_trace_id("trace123")
        log_event(self.logger, "solve.finish", feasible=True, count=2)

        record = self.handler.records[-1]
        payload = json.loads(JsonLogFormatter().format(record))
        self.assertEqual(payload["msg"], "solve.finish")
        self.assertEqual(payload["trace_id"], "trace123")
        self.assertTrue(payload["feasible"])
        self.assertEqual(payload["count"], 2)

    def test_traced_stage_logs_start_and_finish_with_duration(self) -> None:
        with traced_stage(self.logger, "solve") as span:
            span["feasible"] = True

        messages = [record.getMessage() for record in self.handler.records]
        self.assertIn("solve.start", messages)
        self.assertIn("solve.finish", messages)
        finish = next(r for r in self.handler.records if r.getMessage() == "solve.finish")
        self.assertIn("elapsed_ms", finish.fields)  # type: ignore[attr-defined]
        self.assertTrue(finish.fields["feasible"])  # type: ignore[attr-defined]

    def test_traced_stage_logs_error_and_reraises(self) -> None:
        with self.assertRaises(ValueError):
            with traced_stage(self.logger, "solve"):
                raise ValueError("boom")

        error_records = [r for r in self.handler.records if r.getMessage() == "solve.error"]
        self.assertEqual(len(error_records), 1)
        self.assertEqual(error_records[0].fields["error"], "boom")  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()

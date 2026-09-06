from __future__ import annotations

import unittest

from app.eval import load_scenarios, run_golden_eval


class GoldenEvalTest(unittest.TestCase):
    def test_all_golden_scenarios_pass(self) -> None:
        report = run_golden_eval()
        failures = [f"{r.id}: {r.mismatches}" for r in report.results if not r.passed]
        self.assertEqual(report.failed, 0, msg=f"golden regressions: {failures}")
        self.assertEqual(report.pass_rate, 1.0)

    def test_golden_file_covers_every_verdict_branch(self) -> None:
        verdicts = {s["expected"]["verdict"] for s in load_scenarios()}
        self.assertEqual(
            verdicts,
            {
                "ready to deploy",
                "ready but fragile",
                "no feasible coalition",
                "needs more facts",
                "needs human review",
            },
        )


if __name__ == "__main__":
    unittest.main()

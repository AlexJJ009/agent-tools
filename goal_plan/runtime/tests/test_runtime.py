from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from goal_plan_runtime.cli import append_jsonl, init_goal, plan_hash, replay_runtime, validate_plan


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_goal(self) -> Path:
        goal = self.root / "goal-one"
        init_goal(argparse.Namespace(goal_dir=str(goal), title="Goal One", actor="main"))
        return goal

    def test_init_creates_isolated_append_only_goal_directory(self) -> None:
        goal = self.create_goal()
        self.assertEqual(
            {path.name for path in goal.iterdir()},
            {"acceptance.md", "findings.jsonl", "plan.md", "reviews", "runtime.jsonl"},
        )
        first = json.loads((goal / "runtime.jsonl").read_text().splitlines()[0])
        self.assertEqual(first["event"], "PLAN_CREATED")
        self.assertEqual(first["seq"], 1)

    def test_plan_template_passes_validation(self) -> None:
        goal = self.create_goal()
        self.assertEqual(validate_plan(goal / "plan.md"), [])

    def test_runtime_rejects_implementation_before_ready_review(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "runtime.jsonl", {"event": "MILESTONE_STARTED", "milestone": "M1"})
        _, errors = replay_runtime(goal)
        self.assertTrue(any("before READY" in error for error in errors))

    def test_runtime_accepts_plan_amendment_bound_to_current_hash(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        plan.write_text(plan.read_text() + "\nAmended detail.\n")
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "PLAN_AMENDED",
                "plan_version": 2,
                "plan_sha256": plan_hash(plan),
            },
        )

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["plan_status"], "UNREVIEWED")
        self.assertEqual(state["plan_version"], 2)

    def test_runtime_rejects_plan_amendment_with_stale_hash(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        plan.write_text(plan.read_text() + "\nAmended detail.\n")
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "PLAN_AMENDED",
                "plan_version": 2,
                "plan_sha256": "stale",
            },
        )

        _, errors = replay_runtime(goal)

        self.assertTrue(any("plan hash does not match" in error for error in errors))

    def test_runtime_requires_convergence_review_after_two_fix_rounds(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_OPENED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CLASSIFIED", "finding_id": "F-01", "classification": "IN_SCOPE"},
        )
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_FIX_PROPOSED", "finding_id": "F-01"})
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_FIX_PROPOSED", "finding_id": "F-01"})
        _, errors = replay_runtime(goal)
        self.assertTrue(any("convergence review required" in error for error in errors))

    def test_runtime_rejects_self_acceptance(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "reviewer"},
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "ACCEPTANCE_COMPLETED",
                "plan_version": 1,
                "verdict": "PASS",
                "reviewer": "main",
                "implementer": "main",
            },
        )
        _, errors = replay_runtime(goal)
        self.assertTrue(any("cannot self-review" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

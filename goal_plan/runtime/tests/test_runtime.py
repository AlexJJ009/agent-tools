from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from goal_plan_runtime.cli import (
    append_jsonl,
    init_goal,
    plan_hash,
    replay_runtime,
    setup_identity,
    validate_plan,
)


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

    def test_runtime_rejects_ready_plan_with_open_contradiction(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_OPENED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CLASSIFIED", "finding_id": "F-01", "classification": "CONTRADICTION"},
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "reviewer"},
        )

        _, errors = replay_runtime(goal)

        self.assertTrue(any("plan must return to review" in error for error in errors))

    def test_runtime_allows_ready_plan_after_contradiction_is_closed(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_OPENED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CLASSIFIED", "finding_id": "F-01", "classification": "CONTRADICTION"},
        )
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_CLOSED", "finding_id": "F-01"})
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "reviewer"},
        )

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["open_findings"]["F-01"]["status"], "CLOSED")

    def test_plan_rejects_numeric_budget_without_feasibility_probe(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        text = plan.read_text().replace(
            "- Then describe the observable result.",
            "- Then p95 latency stays below 15 ms.",
        )
        plan.write_text(text)
        errors = validate_plan(plan)
        self.assertTrue(any("feasibility probe" in error for error in errors))

    def test_plan_accepts_numeric_budget_with_feasibility_probe(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        text = plan.read_text().replace(
            "- Then describe the observable result.",
            "- Then p95 latency stays below 15 ms.",
        )
        text = text.replace(
            "- None: no acceptance criterion declares an absolute numeric performance or resource budget.",
            "- AC-01: `redis-cli --latency` on target host measured 6.2 ms raw round-trip; budget 15 ms = floor + margin.",
        )
        plan.write_text(text)
        self.assertEqual(validate_plan(plan), [])

    def test_plan_rejects_missing_progression_classes(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        plan.write_text(plan.read_text().replace("AUTO_ADVANCE", "AUTOMATIC"))
        errors = validate_plan(plan)
        self.assertTrue(any("Progression Policy missing class: AUTO_ADVANCE" in error for error in errors))

    def test_runtime_blocks_milestone_while_user_decision_pending(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "reviewer"},
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "USER_DECISION_REQUESTED", "decision_id": "D-01", "summary": "disk below gate"},
        )
        append_jsonl(goal / "runtime.jsonl", {"event": "MILESTONE_STARTED", "milestone": "M1"})
        _, errors = replay_runtime(goal)
        self.assertTrue(any("user decision pending: D-01" in error for error in errors))

    def test_runtime_allows_milestone_after_user_decision_recorded(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "reviewer"},
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "USER_DECISION_REQUESTED", "decision_id": "D-01", "summary": "disk below gate"},
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "USER_DECISION_RECORDED", "decision_id": "D-01", "decision": "user authorized cleanup"},
        )
        append_jsonl(goal / "runtime.jsonl", {"event": "MILESTONE_STARTED", "milestone": "M1"})
        state, errors = replay_runtime(goal)
        self.assertEqual(errors, [])
        self.assertEqual(state["pending_user_decisions"], [])

    def test_runtime_rejects_unmatched_decision_recorded(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "USER_DECISION_RECORDED", "decision_id": "D-99"},
        )
        _, errors = replay_runtime(goal)
        self.assertTrue(any("no pending user decision" in error for error in errors))

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


class SetupIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name) / "repo"
        self.repo.mkdir()
        self.git("init")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def git(self, *args: str, expect_failure: bool = False) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args], capture_output=True, text=True
        )
        if expect_failure:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def run_setup(self, agent: str = "claude", goal_dir: str | None = None) -> None:
        setup_identity(argparse.Namespace(repo_dir=str(self.repo), agent=agent, goal_dir=goal_dir))

    def commit(self, message: str, *, expect_failure: bool = False) -> subprocess.CompletedProcess:
        (self.repo / "file.txt").write_text(message, encoding="utf-8")
        self.git("add", "file.txt")
        return self.git("commit", "-m", message, expect_failure=expect_failure)

    def test_sets_repo_local_agent_identity(self) -> None:
        self.run_setup("claude")
        self.assertEqual(self.git("config", "user.name").stdout.strip(), "Claude")
        self.assertEqual(self.git("config", "user.email").stdout.strip(), "noreply@anthropic.com")

    def test_guard_rejects_non_goal_author_and_accepts_agent_identity(self) -> None:
        self.run_setup("codex")
        self.commit("agent identity passes")
        self.git("config", "user.email", "someone@example.com")
        rejected = self.commit("hand-typed identity", expect_failure=True)
        self.assertIn("allowed goal identities", rejected.stderr)
        self.assertIn("setup-identity", rejected.stderr)

    def test_guard_rejects_committer_outside_allowlist(self) -> None:
        self.run_setup("claude")
        (self.repo / "file.txt").write_text("committer check", encoding="utf-8")
        self.git("add", "file.txt")
        result = subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-m", "committer check"],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "GIT_COMMITTER_NAME": "Someone",
                "GIT_COMMITTER_EMAIL": "someone@example.com",
            },
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("committer 'someone@example.com'", result.stderr)

    def test_refuses_to_overwrite_unrelated_pre_commit_hook(self) -> None:
        hooks = self.repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        (hooks / "pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_setup()

    def test_respects_core_hooks_path(self) -> None:
        self.git("config", "core.hooksPath", ".githooks")
        self.run_setup()
        self.assertTrue((self.repo / ".githooks" / "pre-commit").exists())
        self.assertTrue((self.repo / ".githooks" / "goal-allowed-emails.txt").exists())

    def test_is_idempotent(self) -> None:
        self.run_setup()
        self.run_setup()
        self.commit("still commits after rerun")

    def test_goal_dir_declaration_makes_guard_drift_a_validation_error(self) -> None:
        goal = Path(self.temp_dir.name) / "goal"
        init_goal(argparse.Namespace(goal_dir=str(goal), title="Guarded Goal", actor="main"))
        self.run_setup("claude", goal_dir=str(goal))
        _, errors = replay_runtime(goal)
        self.assertEqual(errors, [])
        (self.repo / ".git" / "hooks" / "pre-commit").unlink()
        _, errors = replay_runtime(goal)
        self.assertTrue(any("guard hook missing" in error for error in errors))

    def test_undeclared_goal_is_not_checked_for_guard(self) -> None:
        goal = Path(self.temp_dir.name) / "goal"
        init_goal(argparse.Namespace(goal_dir=str(goal), title="Plain Goal", actor="main"))
        _, errors = replay_runtime(goal)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

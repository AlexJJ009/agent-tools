from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from goal_plan_runtime.cli import (
    append_event,
    append_jsonl,
    build_reviewer_prompt,
    init_goal,
    plan_hash,
    replay_runtime,
    setup_identity,
    validate_plan,
)


LEGACY_EVENT = "TOKENROUTER_LOCAL_REPLACEMENT_AUTHORIZATION_CONSUMED"
LEGACY_DECISION = "D-M3-V14-TOKENROUTER-LOCAL-CANDIDATE-V15-01"
SYNTHETIC_OIDS = {
    "base": "1" * 40,
    "old_first": "2" * 40,
    "old_head": "3" * 40,
    "new_head": "4" * 40,
    "candidate_commit": "5" * 40,
    "report_commit": "6" * 40,
    "verifier_blob": "7" * 40,
    "fixture_blob": "8" * 40,
}


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.goal_count = 0

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_goal(self) -> Path:
        self.goal_count += 1
        goal = self.root / ("goal-one" if self.goal_count == 1 else f"goal-{self.goal_count}")
        init_goal(argparse.Namespace(goal_dir=str(goal), title="Goal One", actor="main"))
        return goal

    def write_runtime(self, goal: Path, records: list[dict[str, object]]) -> None:
        (goal / "runtime.jsonl").write_text(
            "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records),
            encoding="utf-8",
        )

    def legacy_goal(self) -> tuple[Path, list[dict[str, object]]]:
        goal = self.create_goal()
        plan_sha256 = plan_hash(goal / "plan.md")
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "PLAN_REVIEWED",
                "plan_version": 1,
                "plan_sha256_reviewed": plan_sha256,
                "verdict": "READY",
                "reviewer": "reviewer",
            },
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "USER_DECISION_REQUESTED",
                "decision_id": LEGACY_DECISION,
                "summary": "synthetic historical authorization",
            },
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "USER_DECISION_RECORDED",
                "decision_id": LEGACY_DECISION,
                "actor": "user",
                "decision": "AUTHORIZED",
                "source": "synthetic user message",
            },
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": LEGACY_EVENT,
                "plan_version": 1,
                "plan_sha256": plan_sha256,
                "repository": "AlexJJ009/tokenrouter",
                "branch": "fix/trusted-review-failure-fence",
                **SYNTHETIC_OIDS,
                "objects_sha256": "9" * 64,
                "decision_id": LEGACY_DECISION,
                "time": "2026-01-02T03:04:05.123456Z",
            },
        )
        records = [json.loads(line) for line in (goal / "runtime.jsonl").read_text().splitlines()]
        return goal, records

    def assert_legacy_rejected(self, goal: Path) -> list[str]:
        _, errors = replay_runtime(goal)
        self.assertTrue(errors, "mutated legacy ledger unexpectedly replayed")
        return errors

    def assert_append_rejected_unchanged(
        self,
        *,
        ledger: str,
        event: str,
        data: str,
    ) -> None:
        goal = self.create_goal()
        paths = (goal / "runtime.jsonl", goal / "findings.jsonl")
        before = {path: (path.read_bytes(), path.stat().st_size) for path in paths}
        with self.assertRaises(ValueError):
            append_event(argparse.Namespace(
                goal_dir=str(goal),
                event=event,
                ledger=ledger,
                data=data,
            ))
        for path in paths:
            self.assertEqual(path.read_bytes(), before[path][0])
            self.assertEqual(path.stat().st_size, before[path][1])

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

    def test_append_event_binds_plan_amendment_to_current_hash(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        plan.write_text(plan.read_text() + "\nAmended detail.\n")

        append_event(
            argparse.Namespace(
                goal_dir=str(goal),
                event="PLAN_AMENDED",
                ledger="runtime",
                data='{"plan_version":2}',
            )
        )

        latest = json.loads((goal / "runtime.jsonl").read_text().splitlines()[-1])
        self.assertEqual(latest["plan_sha256"], plan_hash(plan))

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

    def test_runtime_accepts_applied_fix_evidence_without_new_fix_round(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_OPENED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CLASSIFIED", "finding_id": "F-01", "classification": "IN_SCOPE"},
        )
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_FIX_PROPOSED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_FIX_APPLIED", "finding_id": "F-01", "evidence": "validated"},
        )

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["open_findings"]["F-01"]["review_fix_rounds"], 1)

    def test_findings_correction_suppresses_invalid_event(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_OPENED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CLASSIFIED", "finding_id": "F-01", "classification": "IN_SCOPE"},
        )
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_RESOLVED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CORRECTED", "finding_id": "F-01", "corrects_seq": 3},
        )
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_CLOSED", "finding_id": "F-01"})

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["open_findings"]["F-01"]["status"], "CLOSED")

    def test_findings_correction_does_not_collide_with_runtime_sequence(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "runtime.jsonl", {"event": "MILESTONE_STARTED", "milestone": "M1"})
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_OPENED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CLASSIFIED", "finding_id": "F-01", "classification": "IN_SCOPE"},
        )
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_RESOLVED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CORRECTED", "finding_id": "F-01", "corrects_seq": 3},
        )

        _, errors = replay_runtime(goal)

        self.assertTrue(any("before READY" in error for error in errors))
        self.assertFalse(any("unknown event 'FINDING_RESOLVED'" in error for error in errors))

    def test_convergence_prompt_is_available_when_convergence_review_is_required(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_OPENED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CLASSIFIED", "finding_id": "F-01", "classification": "IN_SCOPE"},
        )
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_FIX_PROPOSED", "finding_id": "F-01"})
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_FIX_PROPOSED", "finding_id": "F-01"})
        output = goal / "reviews" / "convergence.md"

        result = build_reviewer_prompt(
            argparse.Namespace(
                goal_dir=str(goal),
                review_type="Convergence Review",
                milestone=None,
                base_commit=None,
                candidate_commit=None,
                applicable_acs=None,
                verification_commands=None,
                focus="",
                focus_file=None,
                output=str(output),
            )
        )

        self.assertEqual(result, 0)
        self.assertIn("Convergence Review", output.read_text())

    def test_plan_reentry_prompt_is_available_for_open_contradiction(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "runtime.jsonl", {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "reviewer"})
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_OPENED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CLASSIFIED", "finding_id": "F-01", "classification": "CONTRADICTION"},
        )
        output = goal / "reviews" / "reentry.md"

        result = build_reviewer_prompt(
            argparse.Namespace(
                goal_dir=str(goal),
                review_type="Plan Re-entry Review",
                milestone=None,
                base_commit=None,
                candidate_commit=None,
                applicable_acs=None,
                verification_commands=None,
                focus="",
                focus_file=None,
                output=str(output),
            )
        )

        self.assertEqual(result, 0)
        self.assertIn("Plan Re-entry Review", output.read_text())

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

    def test_plan_rejects_missing_default_authorization(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        plan.write_text(plan.read_text().replace("DEFAULT_AUTHORIZED", "ASK_BY_DEFAULT"))

        errors = validate_plan(plan)

        self.assertTrue(any("Authorization Policy missing rule: DEFAULT_AUTHORIZED" in error for error in errors))

    def test_legacy_plan_without_authorization_policy_remains_valid(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        text = plan.read_text()
        text = text.replace(
            text[text.index("## Authorization Policy"):text.index("## Runtime Contract")],
            "",
        )
        text = text.replace("- Authorization policy version: `2`\n", "")
        plan.write_text(text)

        self.assertEqual(validate_plan(plan), [])

    def test_plan_rejects_invalid_milestone_authorization_override(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        plan.write_text(
            plan.read_text().replace(
                "Milestone overrides: `None`.",
                "Milestone overrides: `M2: ASK_EACH_TIME`.",
            )
        )

        errors = validate_plan(plan)

        self.assertTrue(
            any("Authorization Policy invalid milestone override: ASK_EACH_TIME" in error for error in errors)
        )

    def test_new_plan_requires_authorization_policy(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        text = plan.read_text()
        text = text.replace(
            text[text.index("## Authorization Policy"):text.index("## Runtime Contract")],
            "",
        )
        plan.write_text(text)

        errors = validate_plan(plan)

        self.assertIn("missing section: Authorization Policy", errors)

    def test_plan_accepts_multiline_lowercase_milestone_overrides(self) -> None:
        goal = self.create_goal()
        plan = goal / "plan.md"
        plan.write_text(
            plan.read_text().replace(
                "Milestone overrides: `None`.",
                "Milestone overrides:\n  - M2: hold\n  - M3: authorized",
            )
        )

        self.assertEqual(validate_plan(plan), [])

    def test_plan_template_separates_risk_notice_from_user_decision(self) -> None:
        goal = self.create_goal()
        plan_text = (goal / "plan.md").read_text()

        self.assertIn("Silence about authorization means authorized", plan_text)
        self.assertIn("A risk notice is evidence and communication, not a permission request", plan_text)
        self.assertIn("PREAUTHORIZED_STOP_ACTION", plan_text)
        self.assertIn("Do not treat a risk notice", plan_text)

    def test_runtime_blocks_milestone_while_user_decision_pending(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "reviewer"},
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "USER_DECISION_REQUESTED",
                "authorization_policy_version": 2,
                "decision_id": "D-01",
                "stop_category": "deletion",
                "target": "exact disposable artifact",
                "operation": "delete artifact",
                "risk": "data loss",
                "decision_needed": "approve deletion",
            },
        )
        append_jsonl(goal / "runtime.jsonl", {"event": "MILESTONE_STARTED", "milestone": "M1"})
        _, errors = replay_runtime(goal)
        self.assertTrue(any("user decision pending: D-01" in error for error in errors))

    def test_runtime_rejects_new_unclassified_user_decision(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "USER_DECISION_REQUESTED",
                "authorization_policy_version": 2,
                "decision_id": "D-01",
                "summary": "disk below gate",
            },
        )

        _, errors = replay_runtime(goal)

        self.assertTrue(any("missing stop_category" in error for error in errors))

    def test_plan_v2_upgrade_keeps_historical_decision_requests_replayable(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "USER_DECISION_REQUESTED", "decision_id": "D-LEGACY", "summary": "historical gate"},
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "USER_DECISION_RECORDED", "decision_id": "D-LEGACY", "decision": "approved"},
        )

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["pending_user_decisions"], [])

    def test_runtime_rejects_user_decision_outside_stop_classes(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "USER_DECISION_REQUESTED",
                "authorization_policy_version": 2,
                "decision_id": "D-01",
                "stop_category": "routine_risk",
                "target": "fixture",
                "operation": "rerun test",
                "risk": "test may fail",
                "decision_needed": "approve rerun",
            },
        )

        _, errors = replay_runtime(goal)

        self.assertTrue(any("invalid stop_category 'routine_risk'" in error for error in errors))

    def test_runtime_risk_notice_is_recorded_without_blocking(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "reviewer"},
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "RISK_NOTICE_RECORDED",
                "target": "private fast-forward push",
                "risk": "remote state changes",
                "mitigation": "exact SHA and normal revert",
            },
        )
        append_jsonl(goal / "runtime.jsonl", {"event": "MILESTONE_STARTED", "milestone": "M1"})

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["pending_user_decisions"], [])

    def test_runtime_allows_milestone_after_user_decision_recorded(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "reviewer"},
        )
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "USER_DECISION_REQUESTED",
                "authorization_policy_version": 2,
                "decision_id": "D-01",
                "stop_category": "deletion",
                "target": "exact disposable artifact",
                "operation": "delete artifact",
                "risk": "data loss",
                "decision_needed": "approve deletion",
            },
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

    def test_runtime_accepts_closed_ac_change_after_fresh_ready_review(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_OPENED", "finding_id": "F-01"})
        append_jsonl(
            goal / "findings.jsonl",
            {"event": "FINDING_CLASSIFIED", "finding_id": "F-01", "classification": "AC_CHANGE"},
        )
        append_jsonl(goal / "findings.jsonl", {"event": "FINDING_CLOSED", "finding_id": "F-01"})
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "reviewer"},
        )

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["plan_status"], "READY")

    def test_runtime_accepts_milestone_review_event(self) -> None:
        goal = self.create_goal()
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_REVIEWED", "plan_version": 1, "verdict": "READY", "reviewer": "plan-reviewer"},
        )
        append_jsonl(goal / "runtime.jsonl", {"event": "MILESTONE_STARTED", "milestone": "Milestone 1"})
        append_jsonl(
            goal / "runtime.jsonl",
            {
                "event": "MILESTONE_REVIEWED",
                "milestone": "Milestone 1",
                "verdict": "FAIL",
                "reviewer": "milestone-reviewer",
                "implementer": "main",
            },
        )

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["latest_review"]["event"], "MILESTONE_REVIEWED")

    def test_legacy_consumption_replays_with_exact_public_schema(self) -> None:
        goal, records = self.legacy_goal()

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["plan_status"], "READY")
        legacy = records[-1]
        self.assertEqual(
            set(legacy),
            {
                "event", "plan_version", "plan_sha256", "repository", "branch",
                "base", "old_first", "old_head", "new_head", "candidate_commit",
                "report_commit", "verifier_blob", "fixture_blob", "objects_sha256",
                "decision_id", "seq", "time",
            },
        )

    def test_legacy_consumption_rejects_schema_type_time_hash_and_subject_mutations(self) -> None:
        mutations = {
            "missing-key": lambda row: row.pop("fixture_blob"),
            "extra-key": lambda row: row.update({"extra": "forbidden"}),
            "bool-plan-version": lambda row: row.update({"plan_version": True}),
            "zero-plan-version": lambda row: row.update({"plan_version": 0}),
            "string-plan-version": lambda row: row.update({"plan_version": "1"}),
            "bool-sequence": lambda row: row.update({"seq": True}),
            "non-string-time": lambda row: row.update({"time": 1}),
            "offset-time": lambda row: row.update({"time": "2026-01-02T03:04:05+00:00"}),
            "lowercase-z": lambda row: row.update({"time": "2026-01-02T03:04:05z"}),
            "missing-seconds": lambda row: row.update({"time": "2026-01-02T03:04Z"}),
            "empty-fraction": lambda row: row.update({"time": "2026-01-02T03:04:05.Z"}),
            "naive-time": lambda row: row.update({"time": "2026-01-02T03:04:05"}),
            "invalid-time": lambda row: row.update({"time": "2026-02-30T03:04:05Z"}),
            "uppercase-oid": lambda row: row.update({"base": "A" * 40}),
            "short-oid": lambda row: row.update({"old_head": "3" * 39}),
            "non-string-oid": lambda row: row.update({"new_head": 4}),
            "uppercase-sha256": lambda row: row.update({"plan_sha256": "A" * 64}),
            "short-sha256": lambda row: row.update({"objects_sha256": "9" * 63}),
            "repository": lambda row: row.update({"repository": "example.invalid/repository"}),
            "branch": lambda row: row.update({"branch": "fix/synthetic-other"}),
            "decision-id": lambda row: row.update({"decision_id": "D-SYNTHETIC-OTHER"}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                goal, records = self.legacy_goal()
                mutate(records[-1])
                self.write_runtime(goal, records)
                self.assert_legacy_rejected(goal)

    def test_legacy_consumption_rejects_wrong_event_spelling(self) -> None:
        goal, records = self.legacy_goal()
        records[-1]["event"] = LEGACY_EVENT + "_TYPO"
        self.write_runtime(goal, records)

        errors = self.assert_legacy_rejected(goal)

        self.assertTrue(any("unknown event" in error for error in errors))

    def test_legacy_consumption_validates_raw_physical_records_before_corrections(self) -> None:
        for label, raw_seq in (("bool", True), ("gap", 9), ("duplicate", 4)):
            with self.subTest(label=label):
                goal, records = self.legacy_goal()
                records.append({"event": "HISTORICAL_TYPO", "seq": raw_seq, "time": None})
                records.append({
                    "event": "EVENT_CORRECTED",
                    "corrects_seq": raw_seq,
                    "seq": 7,
                    "time": "2026-01-02T03:04:07Z",
                })
                self.write_runtime(goal, records)

                errors = self.assert_legacy_rejected(goal)

                self.assertTrue(any("expected physical seq 6" in error for error in errors))
                self.assertTrue(any("missing physical time" in error for error in errors))

    def test_legacy_consumption_rejects_blank_physical_line_before_corrections(self) -> None:
        goal, records = self.legacy_goal()
        lines = [json.dumps(record, sort_keys=True, separators=(",", ":")) for record in records]
        (goal / "runtime.jsonl").write_text("\n".join([lines[0], "", *lines[1:]]) + "\n")

        errors = self.assert_legacy_rejected(goal)

        self.assertTrue(any("blank physical line" in error for error in errors))

    def test_legacy_consumption_rejects_bool_correction_target_before_snapshot(self) -> None:
        goal, records = self.legacy_goal()
        records.insert(1, {
            "event": "PLAN_AMENDED",
            "plan_version": 1,
            "plan_sha256": records[0]["plan_sha256"],
            "time": "2026-01-02T03:04:01Z",
        })
        records.insert(-1, {
            "event": "EVENT_CORRECTED",
            "corrects_seq": True,
            "time": "2026-01-02T03:04:04Z",
        })
        for seq, record in enumerate(records, 1):
            record["seq"] = seq
        self.write_runtime(goal, records)

        errors = self.assert_legacy_rejected(goal)

        self.assertTrue(any("correction target is missing" in error for error in errors))

    def test_no_legacy_event_preserves_0_2_correction_before_sequence_behavior(self) -> None:
        goal = self.create_goal()
        records = [json.loads(line) for line in (goal / "runtime.jsonl").read_text().splitlines()]
        records.extend([
            {"event": "HISTORICAL_TYPO", "seq": 0, "time": None},
            {
                "event": "EVENT_CORRECTED",
                "corrects_seq": 0,
                "seq": 3,
                "time": "2026-01-02T03:04:07Z",
            },
        ])
        self.write_runtime(goal, records)

        _, errors = replay_runtime(goal)

        self.assertEqual(errors, [])

    def test_legacy_consumption_requires_one_physical_event_even_if_duplicate_is_corrected(self) -> None:
        goal, records = self.legacy_goal()
        duplicate = dict(records[-1], seq=6, time="2026-01-02T03:04:06Z")
        records.extend([
            duplicate,
            {
                "event": "EVENT_CORRECTED",
                "corrects_seq": 6,
                "seq": 7,
                "time": "2026-01-02T03:04:07Z",
            },
        ])
        self.write_runtime(goal, records)

        self.assert_legacy_rejected(goal)

    def test_legacy_consumption_is_permanently_non_correctable(self) -> None:
        for corrected_correction in (False, True):
            with self.subTest(corrected_correction=corrected_correction):
                goal, records = self.legacy_goal()
                records.append({
                    "event": "EVENT_CORRECTED",
                    "corrects_seq": 5,
                    "seq": 6,
                    "time": "2026-01-02T03:04:06Z",
                })
                if corrected_correction:
                    records.append({
                        "event": "EVENT_CORRECTED",
                        "corrects_seq": 6,
                        "seq": 7,
                        "time": "2026-01-02T03:04:07Z",
                    })
                self.write_runtime(goal, records)
                self.assert_legacy_rejected(goal)

    def test_legacy_consumption_binds_event_time_plan_and_latest_ready_review(self) -> None:
        mutations = {
            "event-plan-version": lambda rows: rows[-1].update({"plan_version": 2}),
            "event-plan-hash": lambda rows: rows[-1].update({"plan_sha256": "a" * 64}),
            "review-not-ready": lambda rows: rows[1].update({"verdict": "NOT_READY"}),
            "review-plan-version": lambda rows: rows[1].update({"plan_version": 2}),
            "review-plan-hash": lambda rows: rows[1].update({"plan_sha256_reviewed": "a" * 64}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                goal, records = self.legacy_goal()
                mutate(records)
                self.write_runtime(goal, records)
                self.assert_legacy_rejected(goal)

        for label, later_review in (
            ("later-not-ready", {"verdict": "NOT_READY"}),
            ("later-stale-version", {"verdict": "READY", "plan_version": 2}),
            ("later-stale-hash", {"verdict": "READY", "plan_sha256_reviewed": "a" * 64}),
        ):
            with self.subTest(label=label):
                goal, records = self.legacy_goal()
                review = dict(records[1], **later_review)
                records.insert(2, review)
                for seq, record in enumerate(records, 1):
                    record["seq"] = seq
                self.write_runtime(goal, records)
                self.assert_legacy_rejected(goal)

        for label, remove_index in (("missing-plan", 0), ("missing-review", 1)):
            with self.subTest(label=label):
                goal, records = self.legacy_goal()
                records.pop(remove_index)
                for seq, record in enumerate(records, 1):
                    record["seq"] = seq
                self.write_runtime(goal, records)
                self.assert_legacy_rejected(goal)

    def test_legacy_consumption_requires_prior_user_authorization(self) -> None:
        mutations = {
            "record-non-user": lambda rows: rows[3].update({"actor": "agent"}),
            "record-not-authorized": lambda rows: rows[3].update({"decision": "DENIED"}),
            "record-empty-source": lambda rows: rows[3].update({"source": ""}),
            "record-whitespace-source": lambda rows: rows[3].update({"source": " \t "}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                goal, records = self.legacy_goal()
                mutate(records)
                self.write_runtime(goal, records)
                self.assert_legacy_rejected(goal)

    def test_legacy_consumption_rejects_missing_duplicate_and_reordered_authorization(self) -> None:
        def resequence(records: list[dict[str, object]]) -> None:
            for seq, record in enumerate(records, 1):
                record["seq"] = seq

        for label in (
            "missing-request", "missing-record", "duplicate-request", "duplicate-record",
            "record-before-request",
        ):
            with self.subTest(label=label):
                goal, records = self.legacy_goal()
                if label == "missing-request":
                    records.pop(2)
                elif label == "missing-record":
                    records.pop(3)
                elif label == "duplicate-request":
                    records.insert(3, dict(records[2]))
                elif label == "duplicate-record":
                    records.insert(4, dict(records[3]))
                else:
                    records[2], records[3] = records[3], records[2]
                resequence(records)
                self.write_runtime(goal, records)
                self.assert_legacy_rejected(goal)

    def test_legacy_consumption_rejects_prefix_correction_of_required_review(self) -> None:
        goal, records = self.legacy_goal()
        records.insert(4, {
            "event": "EVENT_CORRECTED",
            "corrects_seq": 2,
            "time": "2026-01-02T03:04:04Z",
        })
        for seq, record in enumerate(records, 1):
            record["seq"] = seq
        self.write_runtime(goal, records)

        self.assert_legacy_rejected(goal)

    def test_suffix_correction_cannot_retroactively_remove_event_time_review(self) -> None:
        goal, _ = self.legacy_goal()
        append_jsonl(goal / "runtime.jsonl", {"event": "EVENT_CORRECTED", "corrects_seq": 2})

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["plan_status"], "UNREVIEWED")

    def test_suffix_correction_of_correction_cannot_change_event_time_prefix(self) -> None:
        goal, records = self.legacy_goal()
        records.insert(2, {
            "event": "EVENT_CORRECTED",
            "corrects_seq": 2,
            "time": "2026-01-02T03:04:02Z",
        })
        records.insert(3, {
            "event": "EVENT_CORRECTED",
            "corrects_seq": 3,
            "time": "2026-01-02T03:04:03Z",
        })
        for seq, record in enumerate(records, 1):
            record["seq"] = seq
        records.append({
            "event": "EVENT_CORRECTED",
            "corrects_seq": 4,
            "seq": 8,
            "time": "2026-01-02T03:04:08Z",
        })
        self.write_runtime(goal, records)

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["plan_status"], "READY")

    def test_later_plan_amendment_does_not_invalidate_legacy_consumption(self) -> None:
        goal, _ = self.legacy_goal()
        plan = goal / "plan.md"
        plan.write_text(plan.read_text() + "\nSynthetic later amendment.\n")
        append_jsonl(
            goal / "runtime.jsonl",
            {"event": "PLAN_AMENDED", "plan_version": 2, "plan_sha256": plan_hash(plan)},
        )

        state, errors = replay_runtime(goal)

        self.assertEqual(errors, [])
        self.assertEqual(state["plan_version"], 2)

    def test_corrected_historical_unknown_event_remains_replayable(self) -> None:
        goal = self.create_goal()
        append_jsonl(goal / "runtime.jsonl", {"event": "HISTORICAL_TYPO"})
        append_jsonl(goal / "runtime.jsonl", {"event": "EVENT_CORRECTED", "corrects_seq": 2})

        _, errors = replay_runtime(goal)

        self.assertEqual(errors, [])

    def test_append_event_rejects_unknown_and_cross_ledger_before_write(self) -> None:
        cases = (
            ("runtime", "RUNTIME_UNKNOWN", {}),
            ("findings", "FINDINGS_UNKNOWN", {}),
            ("runtime", "FINDING_OPENED", {"finding_id": "F-SYNTHETIC"}),
            ("findings", "RISK_NOTICE_RECORDED", {"target": "fixture", "risk": "none", "mitigation": "none"}),
        )
        for ledger, event, data in cases:
            with self.subTest(ledger=ledger, event=event, data=bool(data)):
                self.assert_append_rejected_unchanged(
                    ledger=ledger,
                    event=event,
                    data=json.dumps(data),
                )

    def test_append_event_rejects_replay_only_legacy_before_parsing_or_write(self) -> None:
        for label, data in (
            ("empty", "{}"),
            ("partial", json.dumps({"plan_version": 1, **SYNTHETIC_OIDS})),
            ("malformed-json", "{"),
        ):
            with self.subTest(label=label):
                self.assert_append_rejected_unchanged(
                    ledger="runtime",
                    event=LEGACY_EVENT,
                    data=data,
                )

    def test_append_event_still_allows_known_events_on_their_own_ledgers(self) -> None:
        goal = self.create_goal()
        append_event(argparse.Namespace(
            goal_dir=str(goal),
            event="RISK_NOTICE_RECORDED",
            ledger="runtime",
            data=json.dumps({"target": "fixture", "risk": "synthetic", "mitigation": "none"}),
        ))
        append_event(argparse.Namespace(
            goal_dir=str(goal),
            event="FINDING_OPENED",
            ledger="findings",
            data=json.dumps({"finding_id": "F-SYNTHETIC"}),
        ))

        runtime = [json.loads(line) for line in (goal / "runtime.jsonl").read_text().splitlines()]
        findings = [json.loads(line) for line in (goal / "findings.jsonl").read_text().splitlines()]
        self.assertEqual(runtime[-1]["event"], "RISK_NOTICE_RECORDED")
        self.assertEqual(findings[-1]["event"], "FINDING_OPENED")


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

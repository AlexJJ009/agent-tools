from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from linear_workflow_runtime.cli import main
from linear_workflow_runtime.migration import build_goal_plan_migration


PLAN = """# Ship Widget

- Goal ID: `ship-widget`
- Plan version: `1`
- Plan status: `READY`

## Outcome

Ship a deterministic widget command.

## Scope

### Included

- Add the command.

### Excluded

- Do not deploy it.

## Acceptance Criteria

### AC-01 - JSON output

- Given a configured repository,
- When the command runs,
- Then it emits stable JSON.

## Milestones

1. Define the widget contract.
2. Implement the widget command.
3. Document the widget command.

## Progression Policy

- AUTO_ADVANCE: old authorization must never migrate.

## Deferred Follow-ups

- Deployment remains out of scope.
"""


class GoalPlanMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.goal = Path(self.temp.name) / "ship-widget"
        self.goal.mkdir()
        (self.goal / "plan.md").write_text(PLAN, encoding="utf-8")
        self._write_jsonl(
            "runtime.jsonl",
            [
                {"event": "PLAN_CREATED", "seq": 1},
                {"event": "MILESTONE_COMPLETED", "milestone": "M1", "seq": 2},
                {
                    "event": "LEGACY_AUTHORIZATION",
                    "repository": "AlexJJ009/agent-tools",
                    "secret": "do-not-copy-ledger-body",
                    "seq": 3,
                },
            ],
        )
        self._write_jsonl(
            "findings.jsonl",
            [
                {"event": "FINDING_OPENED", "finding_id": "F-1", "summary": "Fix stable ordering"},
                {"event": "FINDING_CLASSIFIED", "finding_id": "F-1", "classification": "IN_SCOPE"},
                {"event": "FINDING_OPENED", "finding_id": "F-2", "summary": "Future deployment"},
                {"event": "FINDING_CLASSIFIED", "finding_id": "F-2", "classification": "DEFERRED"},
            ],
        )
        (self.goal / "acceptance.md").write_text(
            "# Goal Acceptance\n\n- Status: `PENDING REVIEW`\n- Reviewer: `unassigned`\n",
            encoding="utf-8",
        )
        reviews = self.goal / "reviews"
        reviews.mkdir()
        (reviews / "prompt.md").write_text("do-not-copy-review-body", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_jsonl(self, name: str, records: list[dict[str, object]]) -> None:
        (self.goal / name).write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )

    def snapshot(self) -> dict[str, bytes]:
        return {
            str(path.relative_to(self.goal)): path.read_bytes()
            for path in self.goal.rglob("*")
            if path.is_file()
        }

    def test_dry_run_is_deterministic_and_zero_write(self) -> None:
        before = self.snapshot()
        first = build_goal_plan_migration(self.goal)
        second = build_goal_plan_migration(self.goal)
        self.assertEqual(first, second)
        self.assertEqual(before, self.snapshot())
        self.assertEqual("dry-run", first["mode"])
        self.assertEqual([], first["external_writes"])
        self.assertEqual("waiting_for_human_review", first["approval_boundary"])

    def test_maps_prd_active_work_dag_and_batch_without_guessing_risk(self) -> None:
        proposal = build_goal_plan_migration(self.goal)
        self.assertEqual("Ship a deterministic widget command.", proposal["prd_proposal"]["outcome"])
        titles = [item["title"] for item in proposal["issue_proposals"]]
        self.assertEqual(
            ["Implement the widget command.", "Document the widget command.", "Fix stable ordering"],
            titles,
        )
        self.assertNotIn("Future deployment", titles)
        self.assertEqual(1, len(proposal["dag"]))
        self.assertIsNone(proposal["delivery_batch_proposals"][0]["risk_profile"])
        self.assertTrue(any("risk profile" in item for item in proposal["clarifications"]))

    def test_output_contains_references_not_ledger_prompt_or_legacy_authorization(self) -> None:
        rendered = json.dumps(build_goal_plan_migration(self.goal), sort_keys=True)
        self.assertIn("runtime.jsonl", rendered)
        self.assertIn("findings.jsonl", rendered)
        self.assertIn("acceptance.md", rendered)
        self.assertNotIn("do-not-copy-ledger-body", rendered)
        self.assertNotIn("do-not-copy-review-body", rendered)
        self.assertNotIn("AUTO_ADVANCE", rendered)
        self.assertNotIn("LEGACY_AUTHORIZATION", rendered)

    def test_missing_and_malformed_fields_produce_warnings_without_fabrication(self) -> None:
        (self.goal / "plan.md").write_text(
            "# Incomplete\n\n## Outcome\n\nTBD\n\n## Scope\n\n### Included\n\nTODO\n",
            encoding="utf-8",
        )
        (self.goal / "findings.jsonl").write_text("not-json\n", encoding="utf-8")
        proposal = build_goal_plan_migration(self.goal)
        self.assertTrue(proposal["warnings"])
        self.assertTrue(proposal["clarifications"])
        self.assertEqual([], proposal["issue_proposals"])
        self.assertNotIn("deployment", json.dumps(proposal).lower())

    def test_cli_emits_normalized_json_and_has_no_apply_path(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["migrate", "goal-plan", str(self.goal), "--dry-run"])
        self.assertEqual(0, code)
        self.assertEqual(build_goal_plan_migration(self.goal), json.loads(output.getvalue()))
        default_output = io.StringIO()
        with contextlib.redirect_stdout(default_output):
            default_code = main(["migrate", "goal-plan", str(self.goal)])
        self.assertEqual(0, default_code)
        self.assertEqual("dry-run", json.loads(default_output.getvalue())["mode"])
        help_text = io.StringIO()
        with contextlib.redirect_stdout(help_text), self.assertRaises(SystemExit) as raised:
            main(["migrate", "goal-plan", "--help"])
        self.assertEqual(0, raised.exception.code)
        self.assertNotIn("apply", help_text.getvalue().lower())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as rejected:
            main(["migrate", "goal-plan", str(self.goal), "--apply"])
        self.assertEqual(2, rejected.exception.code)


if __name__ == "__main__":
    unittest.main()

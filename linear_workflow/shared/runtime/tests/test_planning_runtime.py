from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from typing import Any, Mapping, Sequence

from linear_workflow_runtime.contracts import load_json
from linear_workflow_runtime.gateways import (
    GatewayFailure,
    GitHubIssue,
    LinearIssue,
    LinearPlanningObject,
    normalize_github_issue,
    normalize_linear_issue,
)
from linear_workflow_runtime.planning import (
    PlanningFailure,
    PlanningRuntime,
    PreviewApproval,
)

from test_planning_batch_validators import FIXTURES


class FakeLinearGateway:
    def __init__(self) -> None:
        self.by_key: dict[str, LinearIssue] = {}
        self.by_id: dict[str, LinearIssue] = {}
        self.planning_objects: dict[tuple[str, str], LinearPlanningObject] = {}
        self.relations: dict[str, tuple[str, str, tuple[str, ...]]] = {}
        self.matches: list[LinearIssue] = []
        self.write_count = 0
        self.linear_issue_write_count = 0
        self.planning_write_count = 0
        self.relation_write_count = 0
        self.last_timeout: int | None = None

    def find_by_proposal_key(self, proposal_key: str) -> LinearIssue | None:
        return self.by_key.get(proposal_key)

    def find_planning_object(
        self, object_type: str, proposal_key: str
    ) -> LinearPlanningObject | None:
        return self.planning_objects.get((object_type, proposal_key))

    def upsert_planning_object(
        self, object_type: str, proposal_key: str, payload: Mapping[str, Any]
    ) -> LinearPlanningObject:
        self.write_count += 1
        self.planning_write_count += 1
        key = (object_type, proposal_key)
        planned = self.planning_objects.get(key)
        if planned is None:
            sequence = 700 if object_type == "prd" else 710 + len(self.planning_objects)
            planned = LinearPlanningObject(
                f"DRAGAI-{sequence}", object_type, proposal_key
            )
            self.planning_objects[key] = planned
        return planned

    def upsert_linear_only(
        self, proposal_key: str, payload: Mapping[str, Any]
    ) -> LinearIssue:
        self.write_count += 1
        self.linear_issue_write_count += 1
        issue = self.by_key.get(proposal_key)
        if issue is None:
            issue = LinearIssue("DRAGAI-900", "DragAI", None, None, proposal_key)
            self.by_key[proposal_key] = issue
            self.by_id[issue.id] = issue
        return issue

    def find_sync_matches(
        self, github_url: str, expected_team: str, timeout_seconds: int
    ) -> Sequence[LinearIssue]:
        self.last_timeout = timeout_seconds
        return list(self.matches)

    def get_issue(self, issue_id: str) -> LinearIssue:
        return self.by_id[issue_id]

    def bind_synced_issue(
        self, issue_id: str, proposal_key: str, payload: Mapping[str, Any]
    ) -> LinearIssue:
        self.write_count += 1
        self.linear_issue_write_count += 1
        issue = self.by_id.get(issue_id) or next(
            item for item in self.matches if item.id == issue_id
        )
        bound = LinearIssue(
            issue.id,
            issue.team,
            issue.repository_full_name,
            issue.github_url,
            proposal_key,
            issue.duplicate_of,
        )
        self.by_id[bound.id] = bound
        self.by_key[proposal_key] = bound
        return bound

    def reconcile_issue_relations(
        self,
        issue_id: str,
        *,
        project_id: str,
        batch_id: str,
        dependency_issue_ids: Sequence[str],
    ) -> None:
        self.write_count += 1
        self.relation_write_count += 1
        self.relations[issue_id] = (
            project_id,
            batch_id,
            tuple(dependency_issue_ids),
        )


class FakeGitHubGateway:
    def __init__(self) -> None:
        self.by_key: dict[tuple[str, str], GitHubIssue] = {}
        self.create_count = 0
        self.update_count = 0

    def find_by_proposal_key(
        self, repository_full_name: str, proposal_key: str
    ) -> GitHubIssue | None:
        return self.by_key.get((repository_full_name, proposal_key))

    def create_issue(
        self,
        repository_full_name: str,
        title: str,
        body: str,
        proposal_key: str,
    ) -> GitHubIssue:
        self.create_count += 1
        issue = GitHubIssue(
            f"{repository_full_name}#100",
            f"https://github.com/{repository_full_name}/issues/100",
            repository_full_name,
            proposal_key,
            title,
            body,
        )
        self.by_key[(repository_full_name, proposal_key)] = issue
        return issue

    def update_issue(
        self,
        issue: GitHubIssue,
        title: str,
        body: str,
        proposal_key: str,
    ) -> GitHubIssue:
        self.update_count += 1
        updated = GitHubIssue(
            issue.reference,
            issue.url,
            issue.repository_full_name,
            proposal_key,
            title,
            body,
        )
        self.by_key[(issue.repository_full_name, proposal_key)] = updated
        return updated


class PlanningRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.linear = FakeLinearGateway()
        self.github = FakeGitHubGateway()
        self.runtime = PlanningRuntime(
            self.linear, self.github, workflow_version="0.2.0", sync_timeout_seconds=7
        )
        self.plan = load_json(FIXTURES / "good/prd.json")
        self.plan["workflow_version"] = "0.2.0"
        self.plan["issues"][0]["github_issue"] = None
        self.drafts = {
            "DRAGAI-67": {
                "project_url": "https://linear.app/example/project/example",
                "repository_full_name": "AlexJJ009/agent-tools",
                "base_branch": "main",
                "outcome": "Deliver the planned behavior.",
                "acceptance": "The behavior is covered by tests.",
                "verification": "Run the targeted unit tests.",
            }
        }

    def preview(self):
        return self.runtime.preview(
            self.plan,
            project_id="project:linear-workflow-v1",
            expected_team="DragAI",
            repository_inspections={
                "AlexJJ009/agent-tools": ["AGENTS.md", "linear_workflow/shared/runtime/"]
            },
            github_drafts=self.drafts,
        )

    def add_sync_match(self, issue_id: str = "DRAGAI-901") -> LinearIssue:
        operation = self.issue_operation(self.preview())
        url = "https://github.com/AlexJJ009/agent-tools/issues/100"
        issue = LinearIssue(
            issue_id,
            "DragAI",
            "AlexJJ009/agent-tools",
            url,
            operation.proposal_key,
        )
        self.linear.matches = [issue]
        self.linear.by_id[issue.id] = issue
        return issue

    @staticmethod
    def issue_operation(preview):
        return next(
            operation
            for operation in preview.operations
            if operation.object_type == "issue"
        )

    @staticmethod
    def github_mapping(result):
        return next(mapping for mapping in result if mapping.github_issue is not None)

    def test_preview_is_deterministic_and_performs_no_writes(self) -> None:
        first = self.preview()
        second = self.preview()
        self.assertEqual(first, second)
        self.assertTrue(first.as_dict()["dry_run"])
        self.assertEqual("create_github", self.issue_operation(first).action)
        self.assertEqual(
            ["prd", "batch", "issue", "relations"],
            [operation.object_type for operation in first.operations],
        )
        self.assertEqual(0, self.github.create_count)
        self.assertEqual(0, self.linear.write_count)

    def test_new_github_item_can_be_previewed_before_number_is_known(self) -> None:
        self.assertIsNone(self.plan["issues"][0]["github_issue"])
        preview = self.preview()
        self.assertEqual("create_github", self.issue_operation(preview).action)
        self.assertEqual(0, self.github.create_count)
        self.add_sync_match()
        result = self.runtime.apply(
            preview, PreviewApproval(preview.preview_id, "GongxunLi")
        )
        self.assertEqual(
            "AlexJJ009/agent-tools#100", self.github_mapping(result).github_issue
        )

    def test_exact_identifiable_approval_is_required(self) -> None:
        preview = self.preview()
        for approval in (
            PreviewApproval("wrong", "GongxunLi"),
            PreviewApproval(preview.preview_id, ""),
        ):
            with self.subTest(approval=approval), self.assertRaises(PlanningFailure) as caught:
                self.runtime.apply(preview, approval)
            self.assertEqual("approval_required", caught.exception.code)
        self.assertEqual(0, self.github.create_count)
        self.assertEqual(0, self.linear.write_count)

    def test_preview_payload_is_snapshotted_and_forgery_fails_before_writes(self) -> None:
        preview = self.preview()
        self.plan["issues"][0]["title"] = "mutated after preview"
        issue_operation = self.issue_operation(preview)
        detached_payload = issue_operation.payload
        detached_payload["issue"]["title"] = "also mutated"
        self.assertEqual("Establish contracts", issue_operation.payload["issue"]["title"])

        forged_payload = issue_operation.payload
        forged_payload["issue"]["title"] = "forged write"
        forged_operation = replace(
            issue_operation,
            payload_json=json.dumps(
                forged_payload, sort_keys=True, separators=(",", ":")
            ),
        )
        forged_preview = replace(
            preview,
            operations=tuple(
                forged_operation if operation is issue_operation else operation
                for operation in preview.operations
            ),
        )
        with self.assertRaises(PlanningFailure) as caught:
            self.runtime.apply(
                forged_preview,
                PreviewApproval(preview.preview_id, "GongxunLi"),
            )
        self.assertEqual("preview_integrity", caught.exception.code)
        self.assertEqual(0, self.github.create_count)
        self.assertEqual(0, self.linear.write_count)

    def test_apply_rejects_complete_plan_when_non_issue_operation_is_missing(self) -> None:
        preview = self.preview()
        operations = tuple(
            operation for operation in preview.operations if operation.object_type != "batch"
        )
        body = {
            "workflow_version": preview.workflow_version,
            "plan_id": preview.plan_id,
            "project_id": preview.project_id,
            "expected_team": preview.expected_team,
            "sync_timeout_seconds": preview.sync_timeout_seconds,
            "operations": [operation.as_dict() for operation in operations],
        }
        incomplete = replace(
            preview,
            preview_id=self.runtime._preview_id(body),
            operations=operations,
        )
        with self.assertRaises(PlanningFailure) as caught:
            self.runtime.apply(
                incomplete,
                PreviewApproval(incomplete.preview_id, "GongxunLi"),
            )
        self.assertEqual("preview_incomplete", caught.exception.code)
        self.assertEqual(0, self.linear.write_count)

    def test_approved_preview_is_idempotent(self) -> None:
        preview = self.preview()
        self.add_sync_match()
        approval = PreviewApproval(preview.preview_id, "GongxunLi")
        first = self.runtime.apply(preview, approval)
        second = self.runtime.apply(preview, approval)
        self.assertEqual(
            self.github_mapping(first).linear_issue_id,
            self.github_mapping(second).linear_issue_id,
        )
        self.assertEqual(1, self.github.create_count)
        self.assertEqual(7, self.linear.last_timeout)
        self.assertEqual(2, len(self.linear.planning_objects))
        self.assertEqual(1, len(self.linear.relations))

    def test_missing_sync_fails_closed_without_parallel_linear_issue(self) -> None:
        preview = self.preview()
        with self.assertRaises(PlanningFailure) as caught:
            self.runtime.apply(
                preview, PreviewApproval(preview.preview_id, "GongxunLi")
            )
        self.assertEqual("issue_sync_missing", caught.exception.code)
        self.assertEqual(1, self.github.create_count)
        self.assertEqual(0, self.linear.linear_issue_write_count)
        self.assertEqual(0, self.linear.relation_write_count)

    def test_revised_preview_updates_issue_after_create_then_sync_missing(self) -> None:
        first = self.preview()
        with self.assertRaises(PlanningFailure):
            self.runtime.apply(first, PreviewApproval(first.preview_id, "GongxunLi"))
        self.assertEqual(1, self.github.create_count)

        self.plan["issues"][0]["title"] = "Revised approved title"
        self.drafts["DRAGAI-67"]["outcome"] = "Revised approved outcome."
        revised = self.preview()
        revised_issue = self.issue_operation(revised)
        self.assertEqual("update_github", revised_issue.action)
        self.add_sync_match()
        result = self.runtime.apply(
            revised, PreviewApproval(revised.preview_id, "GongxunLi")
        )
        stored = self.github.find_by_proposal_key(
            "AlexJJ009/agent-tools", revised_issue.proposal_key
        )
        assert stored is not None
        self.assertEqual(1, self.github.create_count)
        self.assertEqual(1, self.github.update_count)
        self.assertEqual("Revised approved title", stored.title)
        self.assertIn("Revised approved outcome.", stored.body)
        self.assertEqual("DRAGAI-901", self.github_mapping(result).linear_issue_id)

    def test_wrong_repo_and_multiple_canonical_matches_fail_closed(self) -> None:
        preview = self.preview()
        operation = self.issue_operation(preview)
        url = "https://github.com/AlexJJ009/agent-tools/issues/100"
        wrong = LinearIssue(
            "DRAGAI-901", "DragAI", "Other/repo", url, operation.proposal_key
        )
        self.linear.matches = [wrong]
        with self.assertRaises(PlanningFailure) as caught:
            self.runtime.apply(
                preview, PreviewApproval(preview.preview_id, "GongxunLi")
            )
        self.assertEqual("wrong_repository", caught.exception.code)

        one = LinearIssue(
            "DRAGAI-901",
            "DragAI",
            "AlexJJ009/agent-tools",
            url,
            operation.proposal_key,
        )
        two = LinearIssue(
            "DRAGAI-902",
            "DragAI",
            "AlexJJ009/agent-tools",
            url,
            operation.proposal_key,
        )
        self.linear.matches = [one, two]
        with self.assertRaises(PlanningFailure) as caught:
            self.runtime.apply(
                preview, PreviewApproval(preview.preview_id, "GongxunLi")
            )
        self.assertEqual("multiple_sync_matches", caught.exception.code)

    def test_duplicate_of_target_wins_even_when_duplicate_is_only_match(self) -> None:
        preview = self.preview()
        operation = self.issue_operation(preview)
        url = "https://github.com/AlexJJ009/agent-tools/issues/100"
        canonical = LinearIssue(
            "DRAGAI-800",
            "DragAI",
            "AlexJJ009/agent-tools",
            url,
            operation.proposal_key,
        )
        duplicate = LinearIssue(
            "DRAGAI-801",
            "DragAI",
            "AlexJJ009/agent-tools",
            url,
            operation.proposal_key,
            duplicate_of="DRAGAI-800",
        )
        self.linear.by_id[canonical.id] = canonical
        self.linear.matches = [duplicate]
        result = self.runtime.apply(
            preview, PreviewApproval(preview.preview_id, "GongxunLi")
        )
        self.assertEqual("DRAGAI-800", self.github_mapping(result).linear_issue_id)

    def test_duplicate_canonical_target_identity_conflicts_fail_closed(self) -> None:
        preview = self.preview()
        operation = self.issue_operation(preview)
        url = "https://github.com/AlexJJ009/agent-tools/issues/100"
        duplicate = LinearIssue(
            "DRAGAI-801",
            "DragAI",
            "AlexJJ009/agent-tools",
            url,
            operation.proposal_key,
            duplicate_of="DRAGAI-800",
        )
        self.linear.matches = [duplicate]
        cases = {
            "wrong repo": LinearIssue(
                "DRAGAI-800", "DragAI", "Other/repo", url, operation.proposal_key
            ),
            "wrong url": LinearIssue(
                "DRAGAI-800",
                "DragAI",
                "AlexJJ009/agent-tools",
                "https://github.com/AlexJJ009/agent-tools/issues/99",
                operation.proposal_key,
            ),
            "wrong team": LinearIssue(
                "DRAGAI-800",
                "OtherTeam",
                "AlexJJ009/agent-tools",
                url,
                operation.proposal_key,
            ),
            "wrong proposal": LinearIssue(
                "DRAGAI-800",
                "DragAI",
                "AlexJJ009/agent-tools",
                url,
                "linear-workflow:different",
            ),
            "chained duplicate": LinearIssue(
                "DRAGAI-800",
                "DragAI",
                "AlexJJ009/agent-tools",
                url,
                operation.proposal_key,
                duplicate_of="DRAGAI-700",
            ),
        }
        for name, canonical in cases.items():
            with self.subTest(name=name):
                self.linear.by_id[canonical.id] = canonical
                with self.assertRaises(PlanningFailure):
                    self.runtime.apply(
                        preview, PreviewApproval(preview.preview_id, "GongxunLi")
                    )

    def test_repository_inspection_and_draft_identity_are_enforced(self) -> None:
        with self.assertRaises(PlanningFailure) as caught:
            self.runtime.preview(
                self.plan,
                project_id="project:linear-workflow-v1",
                expected_team="DragAI",
                repository_inspections={},
                github_drafts=self.drafts,
            )
        self.assertEqual("repository_not_inspected", caught.exception.code)
        wrong = copy.deepcopy(self.drafts)
        wrong["DRAGAI-67"]["repository_full_name"] = "Other/repo"
        with self.assertRaises(PlanningFailure) as caught:
            self.runtime.preview(
                self.plan,
                project_id="project:linear-workflow-v1",
                expected_team="DragAI",
                repository_inspections={"AlexJJ009/agent-tools": ["AGENTS.md"]},
                github_drafts=wrong,
            )
        self.assertEqual("wrong_repository", caught.exception.code)


class GatewayNormalizationTests(unittest.TestCase):
    def test_mcp_and_api_projections_normalize_to_the_same_linear_fact(self) -> None:
        projection = {
            "id": "DRAGAI-70",
            "team": "DragAI",
            "repository_full_name": "AlexJJ009/agent-tools",
            "github_url": "https://github.com/AlexJJ009/agent-tools/issues/6",
            "proposal_key": "linear-workflow:dragai-70:abc",
            "duplicate_of": None,
        }
        self.assertEqual(normalize_linear_issue(projection), normalize_linear_issue(dict(projection)))

    def test_raw_gateway_failures_are_typed(self) -> None:
        with self.assertRaises(GatewayFailure) as caught:
            normalize_linear_issue({"id": "DRAGAI-70"})
        self.assertEqual("invalid_response", caught.exception.kind)
        github = normalize_github_issue(
            {
                "repository_full_name": "AlexJJ009/agent-tools",
                "number": 6,
                "url": "https://github.com/AlexJJ009/agent-tools/issues/6",
                "proposal_key": "linear-workflow:dragai-70:abc",
                "title": "Implement Planning runtime",
                "body": "Approved issue body",
            }
        )
        self.assertEqual("AlexJJ009/agent-tools#6", github.reference)


if __name__ == "__main__":
    unittest.main()

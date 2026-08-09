from __future__ import annotations

import copy
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .gateways import GitHubGateway, GitHubIssue, LinearGateway, LinearIssue
from .validators import validate_plan


class PlanningFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PreviewOperation:
    proposal_key: str
    object_type: str
    object_id: str
    destination: str
    action: str
    repository_full_name: str | None
    payload_json: str
    github_body: str | None = None

    @classmethod
    def create(
        cls,
        proposal_key: str,
        object_type: str,
        object_id: str,
        destination: str,
        action: str,
        repository_full_name: str | None,
        payload: Mapping[str, Any],
        github_body: str | None = None,
    ) -> PreviewOperation:
        return cls(
            proposal_key,
            object_type,
            object_id,
            destination,
            action,
            repository_full_name,
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            github_body,
        )

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_key": self.proposal_key,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "destination": self.destination,
            "action": self.action,
            "repository_full_name": self.repository_full_name,
            "payload": self.payload,
            "github_body": self.github_body,
        }


@dataclass(frozen=True)
class PlanningPreview:
    preview_id: str
    workflow_version: str
    plan_id: str
    project_id: str
    expected_team: str
    sync_timeout_seconds: int
    operations: tuple[PreviewOperation, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "preview_id": self.preview_id,
            "workflow_version": self.workflow_version,
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "expected_team": self.expected_team,
            "sync_timeout_seconds": self.sync_timeout_seconds,
            "dry_run": True,
            "operations": [operation.as_dict() for operation in self.operations],
        }


@dataclass(frozen=True)
class PreviewApproval:
    preview_id: str
    approved_by: str


@dataclass(frozen=True)
class AppliedMapping:
    proposal_key: str
    linear_issue_id: str
    github_issue: str | None
    created_github: bool


class PlanningRuntime:
    def __init__(
        self,
        linear: LinearGateway,
        github: GitHubGateway,
        *,
        workflow_version: str,
        sync_timeout_seconds: int = 60,
    ) -> None:
        if sync_timeout_seconds <= 0:
            raise ValueError("sync_timeout_seconds must be positive")
        self._linear = linear
        self._github = github
        self._workflow_version = workflow_version
        self._sync_timeout_seconds = sync_timeout_seconds

    def preview(
        self,
        plan: Mapping[str, Any],
        *,
        project_id: str,
        expected_team: str,
        repository_inspections: Mapping[str, Sequence[str]],
        github_drafts: Mapping[str, Mapping[str, Any]],
    ) -> PlanningPreview:
        normalized_plan = dict(plan)
        validation_plan = copy.deepcopy(normalized_plan)
        used_references = {
            issue["github_issue"]
            for issue in validation_plan.get("issues", [])
            if issue.get("github_issue") is not None
        }
        synthetic_number = 900_000_000
        for issue in validation_plan.get("issues", []):
            if issue.get("destination") != "github_to_linear" or issue.get("github_issue") is not None:
                continue
            repository = issue.get("repository_full_name")
            while f"{repository}#{synthetic_number}" in used_references:
                synthetic_number += 1
            issue["github_issue"] = f"{repository}#{synthetic_number}"
            used_references.add(issue["github_issue"])
            synthetic_number += 1
        violations = validate_plan(validation_plan)
        if violations:
            rendered = "; ".join(violation.render() for violation in violations)
            raise PlanningFailure("invalid_plan", rendered)
        if normalized_plan["workflow_version"] != self._workflow_version:
            raise PlanningFailure(
                "version_mismatch",
                "plan workflow_version does not match the running Planning runtime",
            )

        operations: list[PreviewOperation] = []
        prd_key = self._object_proposal_key(normalized_plan["id"], "prd", normalized_plan["id"])
        existing_prd = self._linear.find_planning_object("prd", prd_key)
        operations.append(
            PreviewOperation.create(
                prd_key,
                "prd",
                normalized_plan["id"],
                "linear_only",
                "update_prd" if existing_prd else "create_prd",
                None,
                {"project_id": project_id, "plan": normalized_plan},
            )
        )
        for batch in normalized_plan["batches"]:
            batch_key = self._object_proposal_key(normalized_plan["id"], "batch", batch["id"])
            existing_batch = self._linear.find_planning_object("batch", batch_key)
            operations.append(
                PreviewOperation.create(
                    batch_key,
                    "batch",
                    batch["id"],
                    "linear_only",
                    "update_batch" if existing_batch else "create_batch",
                    None,
                    {"project_id": project_id, "batch": batch},
                )
            )
        batch_by_issue = {
            issue_id: batch["id"]
            for batch in normalized_plan["batches"]
            for issue_id in batch["included_issues"]
        }
        for issue in normalized_plan["issues"]:
            repository = issue["repository_full_name"]
            if repository is not None and not repository_inspections.get(repository):
                raise PlanningFailure(
                    "repository_not_inspected",
                    f"{issue['id']}: reliable decomposition requires inspected repository {repository}",
                )
            proposal_key = self._proposal_key(normalized_plan["id"], issue)
            prior_github = self._github.find_any_by_proposal_key(proposal_key)
            payload = {
                "workflow_version": self._workflow_version,
                "plan_id": normalized_plan["id"],
                "source_session": normalized_plan["source_session"],
                "issue": dict(issue),
                "batch_id": batch_by_issue[issue["id"]],
            }
            if issue["destination"] == "linear_only":
                if prior_github is not None:
                    raise PlanningFailure(
                        "destination_conflict",
                        f"{issue['id']}: an external GitHub write already exists for this logical item; resolve its sync/cleanup before changing destination",
                    )
                existing = self._linear.find_by_proposal_key(proposal_key)
                action = "update_linear" if existing else "create_linear"
                operations.append(
                    PreviewOperation.create(
                        proposal_key,
                        "issue",
                        issue["id"],
                        "linear_only",
                        action,
                        None,
                        payload,
                    )
                )
                continue

            draft = github_drafts.get(issue["id"])
            if draft is None:
                raise PlanningFailure(
                    "github_draft_missing",
                    f"{issue['id']}: github_to_linear item requires an approved GitHub draft",
                )
            github_body = self._github_body(issue, draft, normalized_plan["id"])
            existing = prior_github
            if existing is not None:
                self._assert_github_identity(existing, repository, proposal_key)
            expected_title = str(issue["title"])
            if existing is None:
                action = "create_github"
            elif existing.title == expected_title and existing.body == github_body:
                action = "reuse_github_unchanged"
            else:
                action = "update_github"
            operations.append(
                PreviewOperation.create(
                    proposal_key,
                    "issue",
                    issue["id"],
                    "github_to_linear",
                    action,
                    repository,
                    payload,
                    github_body,
                )
            )

        for issue in normalized_plan["issues"]:
            relation_key = self._object_proposal_key(
                normalized_plan["id"], "relations", issue["id"]
            )
            operations.append(
                PreviewOperation.create(
                    relation_key,
                    "relations",
                    issue["id"],
                    "linear_only",
                    "reconcile_relations",
                    issue["repository_full_name"],
                    {
                        "project_id": project_id,
                        "issue_id": issue["id"],
                        "batch_id": batch_by_issue[issue["id"]],
                        "dependency_issue_ids": issue["dependencies"],
                    },
                )
            )

        preview_body = {
            "workflow_version": self._workflow_version,
            "plan_id": normalized_plan["id"],
            "project_id": project_id,
            "expected_team": expected_team,
            "sync_timeout_seconds": self._sync_timeout_seconds,
            "operations": [operation.as_dict() for operation in operations],
        }
        preview_id = self._preview_id(preview_body)
        return PlanningPreview(
            preview_id,
            self._workflow_version,
            normalized_plan["id"],
            project_id,
            expected_team,
            self._sync_timeout_seconds,
            tuple(operations),
        )

    def apply(
        self, preview: PlanningPreview, approval: PreviewApproval
    ) -> tuple[AppliedMapping, ...]:
        current_preview_id = self._preview_id(
            {
                "workflow_version": preview.workflow_version,
                "plan_id": preview.plan_id,
                "project_id": preview.project_id,
                "expected_team": preview.expected_team,
                "sync_timeout_seconds": preview.sync_timeout_seconds,
                "operations": [operation.as_dict() for operation in preview.operations],
            }
        )
        if not hmac.compare_digest(current_preview_id, preview.preview_id):
            raise PlanningFailure(
                "preview_integrity",
                "preview content changed after its approval identity was computed",
            )
        self._validate_preview_inventory(preview)
        if approval.preview_id != preview.preview_id or not approval.approved_by.strip():
            raise PlanningFailure(
                "approval_required",
                "external writes require an identifiable approval of the exact current preview",
            )
        mappings: list[AppliedMapping] = []
        batch_ids: dict[str, str] = {}
        issue_ids: dict[str, str] = {}
        for operation in preview.operations:
            payload = operation.payload
            if operation.object_type in {"prd", "batch"}:
                planned = self._linear.upsert_planning_object(
                    operation.object_type, operation.proposal_key, payload
                )
                if operation.object_type == "batch":
                    batch_ids[operation.object_id] = planned.id
                mappings.append(
                    AppliedMapping(operation.proposal_key, planned.id, None, False)
                )
                continue
            if operation.object_type == "relations":
                try:
                    resolved_issue = issue_ids[operation.object_id]
                    resolved_batch = batch_ids[str(payload["batch_id"])]
                    resolved_dependencies = [
                        issue_ids[str(issue_id)]
                        for issue_id in payload["dependency_issue_ids"]
                    ]
                except KeyError as error:
                    raise PlanningFailure(
                        "preview_incomplete",
                        f"relation operation cannot resolve approved object {error.args[0]}",
                    ) from error
                self._linear.reconcile_issue_relations(
                    resolved_issue,
                    project_id=preview.project_id,
                    batch_id=resolved_batch,
                    dependency_issue_ids=resolved_dependencies,
                )
                mappings.append(
                    AppliedMapping(
                        operation.proposal_key, resolved_issue, None, False
                    )
                )
                continue
            if operation.object_type != "issue":
                raise PlanningFailure(
                    "preview_incomplete",
                    f"unknown preview operation type {operation.object_type}",
                )
            if operation.destination == "linear_only":
                issue = self._linear.upsert_linear_only(
                    operation.proposal_key, payload
                )
                issue_ids[operation.object_id] = issue.id
                mappings.append(
                    AppliedMapping(operation.proposal_key, issue.id, None, False)
                )
                continue

            repository = operation.repository_full_name
            assert repository is not None and operation.github_body is not None
            github_issue = self._github.find_any_by_proposal_key(
                operation.proposal_key
            )
            if github_issue is not None:
                self._assert_github_identity(
                    github_issue, repository, operation.proposal_key
                )
            created = github_issue is None
            title = str(payload["issue"]["title"])
            if github_issue is None:
                github_issue = self._github.create_issue(
                    repository,
                    title,
                    operation.github_body,
                    operation.proposal_key,
                )
            elif github_issue.title != title or github_issue.body != operation.github_body:
                github_issue = self._github.update_issue(
                    github_issue,
                    title,
                    operation.github_body,
                    operation.proposal_key,
                )
            self._assert_github_identity(
                github_issue, repository, operation.proposal_key
            )
            if github_issue.title != title or github_issue.body != operation.github_body:
                raise PlanningFailure(
                    "github_update_failed",
                    "GitHub Issue content does not match the exact approved preview",
                )
            matches = self._linear.find_sync_matches(
                github_issue.url,
                preview.expected_team,
                preview.sync_timeout_seconds,
            )
            synced = self._select_canonical_sync(
                matches,
                github_issue,
                preview.expected_team,
            )
            bound = self._linear.bind_synced_issue(
                synced.id, operation.proposal_key, payload
            )
            issue_ids[operation.object_id] = bound.id
            mappings.append(
                AppliedMapping(
                    operation.proposal_key,
                    bound.id,
                    github_issue.reference,
                    created,
                )
            )
        return tuple(mappings)

    @staticmethod
    def _preview_id(value: Mapping[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _validate_preview_inventory(preview: PlanningPreview) -> None:
        prd_operations = [
            operation for operation in preview.operations if operation.object_type == "prd"
        ]
        if len(prd_operations) != 1:
            raise PlanningFailure(
                "preview_incomplete", "preview must contain exactly one PRD operation"
            )
        plan = prd_operations[0].payload.get("plan")
        if not isinstance(plan, dict):
            raise PlanningFailure(
                "preview_incomplete", "PRD operation does not contain the normalized plan"
            )
        expected = (
            [("prd", str(plan.get("id")))]
            + [("batch", str(batch["id"])) for batch in plan.get("batches", [])]
            + [("issue", str(issue["id"])) for issue in plan.get("issues", [])]
            + [("relations", str(issue["id"])) for issue in plan.get("issues", [])]
        )
        actual = [
            (operation.object_type, operation.object_id)
            for operation in preview.operations
        ]
        if actual != expected:
            raise PlanningFailure(
                "preview_incomplete",
                "preview must explicitly cover PRD, Batches, Issues, and DAG relations in order",
            )

    @staticmethod
    def _proposal_key(plan_id: str, issue: Mapping[str, Any]) -> str:
        identity = {
            "plan_id": plan_id,
            "issue_id": issue["id"],
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:24]
        return f"linear-workflow:{issue['id'].lower()}:{digest}"

    @staticmethod
    def _object_proposal_key(plan_id: str, object_type: str, object_id: str) -> str:
        digest = hashlib.sha256(
            f"{plan_id}\0{object_type}\0{object_id}".encode()
        ).hexdigest()[:24]
        return f"linear-workflow:{object_type}:{digest}"

    @staticmethod
    def _github_body(
        issue: Mapping[str, Any], draft: Mapping[str, Any], plan_id: str
    ) -> str:
        required = ("project_url", "base_branch", "outcome", "acceptance", "verification")
        missing = [field for field in required if not draft.get(field)]
        if missing:
            raise PlanningFailure(
                "github_draft_incomplete",
                f"{issue['id']}: GitHub draft is missing {', '.join(missing)}",
            )
        if draft.get("repository_full_name") != issue["repository_full_name"]:
            raise PlanningFailure(
                "wrong_repository",
                f"{issue['id']}: GitHub draft repository differs from the approved destination",
            )
        return (
            f"Linear Project: {draft['project_url']}\n"
            f"Planning contract: {plan_id}\n"
            f"Repository: {issue['repository_full_name']}\n"
            f"Planned base branch: {draft['base_branch']}\n\n"
            f"## Outcome\n\n{draft['outcome']}\n\n"
            f"## Acceptance criteria\n\n{draft['acceptance']}\n\n"
            f"## Verification\n\n{draft['verification']}"
        )

    @staticmethod
    def _assert_github_identity(
        issue: GitHubIssue, expected_repository: str, proposal_key: str
    ) -> None:
        if issue.repository_full_name != expected_repository:
            raise PlanningFailure(
                "wrong_repository",
                "GitHub issue repository differs from the approved full repository name",
            )
        if issue.proposal_key != proposal_key:
            raise PlanningFailure(
                "proposal_key_mismatch",
                "GitHub issue does not carry the approved stable proposal key",
            )

    def _select_canonical_sync(
        self,
        matches: Sequence[LinearIssue],
        github_issue: GitHubIssue,
        expected_team: str,
    ) -> LinearIssue:
        if not matches:
            raise PlanningFailure(
                "issue_sync_missing",
                f"Blocked: issue sync missing for {github_issue.url} in {expected_team}",
            )
        canonical: dict[str, LinearIssue] = {}
        for match in matches:
            self._assert_linear_sync_identity(
                match, github_issue, expected_team, allow_duplicate=True
            )
            canonical_id = match.duplicate_of or match.id
            resolved = (
                self._linear.get_issue(canonical_id)
                if match.duplicate_of is not None
                else match
            )
            self._assert_linear_sync_identity(
                resolved, github_issue, expected_team, allow_duplicate=False
            )
            canonical[canonical_id] = resolved
        if len(canonical) != 1:
            raise PlanningFailure(
                "multiple_sync_matches",
                f"GitHub issue {github_issue.url} maps to multiple canonical Linear issues",
            )
        return next(iter(canonical.values()))

    @staticmethod
    def _assert_linear_sync_identity(
        issue: LinearIssue,
        github_issue: GitHubIssue,
        expected_team: str,
        *,
        allow_duplicate: bool,
    ) -> None:
        if issue.team != expected_team:
            raise PlanningFailure(
                "wrong_team",
                f"synced Linear issue {issue.id} belongs to {issue.team}, not {expected_team}",
            )
        if (
            issue.repository_full_name != github_issue.repository_full_name
            or issue.github_url != github_issue.url
        ):
            raise PlanningFailure(
                "wrong_repository",
                f"synced Linear issue {issue.id} does not match the approved GitHub URL/repository",
            )
        if issue.proposal_key not in {None, github_issue.proposal_key}:
            raise PlanningFailure(
                "proposal_key_mismatch",
                f"synced Linear issue {issue.id} belongs to a different approved proposal",
            )
        if not allow_duplicate and issue.duplicate_of is not None:
            raise PlanningFailure(
                "duplicate_target_invalid",
                f"canonical duplicate target {issue.id} is itself a duplicate",
            )

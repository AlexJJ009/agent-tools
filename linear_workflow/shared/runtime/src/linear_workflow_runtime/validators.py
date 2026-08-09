from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from .contracts import Violation, validate_schema


PLACEHOLDER = re.compile(r"(?:\bTBD\b|\bTODO\b|replace-me|待定|\{[^{}]+\})", re.IGNORECASE)

PLAN_BLOCKING_RULES = {
    "LW-PLN-001",  # placeholder
    "LW-PLN-002",  # approved PRD with blocking questions
    "LW-PLN-003",  # destination contract
    "LW-PLN-004",  # dependency target
    "LW-PLN-005",  # DAG cycle
    "LW-PLN-006",  # duplicate work item
    "LW-PLN-007",  # Batch membership
}
BATCH_BLOCKING_RULES = {
    "LW-BAT-001",  # Ready admission
    "LW-BAT-002",  # branch identity
    "LW-BAT-003",  # scope drift
    "LW-BAT-004",  # cross-repo risk
    "LW-BAT-005",  # High cross-repo evidence shape
}
PR_BLOCKING_RULES = {
    "LW-PR-001",  # PR identity / current head
    "LW-PR-002",  # required check presence
    "LW-PR-003",  # required check result
    "LW-PR-004",  # required check candidate binding
    "LW-PR-005",  # commit subject / candidate membership
    "LW-PR-006",  # current independent review verdict
    "LW-PR-007",  # append-only verdict history
    "LW-PR-008",  # verdict-only commit
    "LW-PR-009",  # reviewer context candidate
    "LW-PR-010",  # base policy authority
    "LW-PR-011",  # protected path risk lane
}

COMMIT_SUBJECT = re.compile(
    r"(?:feat|fix|refactor|test|docs|perf|build|ci|chore|revert)"
    r"\([A-Za-z0-9_.-]+\): [^\s].+"
)


def _violation(value: dict[str, Any], field: str, rule: str, message: str, fix: str) -> Violation:
    return Violation(str(value.get("id", "unknown")), field, rule, message, fix)


def _schema_violations(value: dict[str, Any], name: str) -> list[Violation]:
    return [
        _violation(value, error, "LW-SCHEMA", "contract does not match canonical schema", "correct the named field")
        for error in validate_schema(value, name)
    ]


def _strings(value: Any, path: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, str):
        found.append((path, value))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_strings(child, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, child in value.items():
            found.extend(_strings(child, f"{path}.{key}"))
    return found


def _has_cycle(issues: dict[str, dict[str, Any]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(issue_id: str) -> bool:
        if issue_id in visiting:
            return True
        if issue_id in visited:
            return False
        visiting.add(issue_id)
        for dependency in issues[issue_id].get("dependencies", []):
            if dependency in issues and visit(dependency):
                return True
        visiting.remove(issue_id)
        visited.add(issue_id)
        return False

    return any(visit(issue_id) for issue_id in issues)


def _path_allowed(path: str, permitted: list[str]) -> bool:
    normalized = PurePosixPath(path).as_posix()
    for entry in permitted:
        prefix = PurePosixPath(entry).as_posix().rstrip("/")
        if entry.endswith("/"):
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True
        elif normalized == prefix:
            return True
    return False


def load_gate_policy() -> dict[str, Any]:
    source = Path(__file__).resolve().parents[3] / "gate-policy.json"
    if source.is_file():
        return json.loads(source.read_text(encoding="utf-8"))
    packaged = resources.files("linear_workflow_runtime").joinpath("gate-policy.json")
    return json.loads(packaged.read_text(encoding="utf-8"))


def _path_matches_prefix(path: str, prefixes: list[str]) -> bool:
    normalized = PurePosixPath(path).as_posix()
    for prefix in prefixes:
        normalized_prefix = PurePosixPath(prefix).as_posix().rstrip("/")
        if prefix.endswith("/"):
            if normalized == normalized_prefix or normalized.startswith(normalized_prefix + "/"):
                return True
        elif normalized == normalized_prefix:
            return True
    return False


def validate_batch(batch: dict[str, Any], *, require_ready: bool = True) -> list[Violation]:
    errors = _schema_violations(batch, "batch")
    if errors:
        return errors
    if require_ready and batch["status"] != "Ready":
        errors.append(_violation(batch, "status", "LW-BAT-001", "only a Ready Batch can enter Delivery", "obtain human Ready admission"))
    expected = f"linear/{batch['id'].lower()}-"
    for index, work_ref in enumerate(batch["work_references"]):
        if not work_ref["working_branch"].startswith(expected):
            errors.append(_violation(batch, f"work_references[{index}].working_branch", "LW-BAT-002", f"Batch branch must start with {expected}", "use the client-independent Batch branch format"))
    for path in batch["changed_paths"]:
        if not _path_allowed(path, batch["permitted_paths"]):
            errors.append(_violation(batch, "changed_paths", "LW-BAT-003", f"undeclared path {path!r}", "remove the change or return to Planning for scope approval"))
    repositories = [item["repository_full_name"] for item in batch["work_references"]]
    if len(set(repositories)) > 1 and batch["risk_profile"] != "high":
        errors.append(_violation(batch, "work_references", "LW-BAT-004", "cross-repository Batch is not High risk", "split the Batch or obtain High-risk approval"))
    if len(set(repositories)) > 1 and batch["risk_profile"] == "high":
        complete_refs = all(item["candidate_sha"] and item["github_pull_request"] for item in batch["work_references"])
        if not complete_refs or not batch["integration_evidence"]:
            errors.append(_violation(batch, "integration_evidence", "LW-BAT-005", "High cross-repository release lacks per-repo PR/candidate or joint evidence", "bind every repo candidate and PR plus joint integration evidence"))
    return errors


def validate_plan(plan: dict[str, Any]) -> list[Violation]:
    errors = _schema_violations(plan, "prd")
    if errors:
        return errors
    for path, value in _strings({key: value for key, value in plan.items() if key not in {"issues", "batches"}}):
        if PLACEHOLDER.search(value):
            errors.append(_violation(plan, path, "LW-PLN-001", f"placeholder remains in required planning content: {value!r}", "replace it with an approved value"))
    if plan["status"] == "Approved" and plan["blocking_questions"]:
        errors.append(_violation(plan, "blocking_questions", "LW-PLN-002", "Approved PRD contains blocking questions", "resolve them or move the PRD out of Approved"))

    issues: dict[str, dict[str, Any]] = {}
    for index, issue in enumerate(plan["issues"]):
        schema_errors = _schema_violations(issue, "issue")
        if schema_errors:
            errors.extend(schema_errors)
            continue
        issue_id = issue["id"]
        issues[issue_id] = issue
        destination = issue["destination"]
        repo = issue["repository_full_name"]
        github_issue = issue["github_issue"]
        if (destination == "github_to_linear" and (not repo or not github_issue)) or (
            destination == "linear_only" and (repo is not None or github_issue is not None)
        ):
            errors.append(_violation(issue, "destination", "LW-PLN-003", "destination and GitHub mapping disagree", "provide full repo/Issue mapping only for github_to_linear"))
        if issue["duplicate_of"] is not None:
            errors.append(_violation(issue, "duplicate_of", "LW-PLN-006", "duplicate Issue cannot enter a new DAG or Batch", "use the canonical duplicate target"))
    known = set(issues)
    for issue in issues.values():
        for dependency in issue["dependencies"]:
            if dependency not in known:
                errors.append(_violation(issue, "dependencies", "LW-PLN-004", f"unknown dependency {dependency}", "reference a real work item in this proposal"))
    if issues and _has_cycle(issues):
        errors.append(_violation(plan, "issues.dependencies", "LW-PLN-005", "dependency graph contains a cycle", "remove the false dependency or split the work"))

    membership: dict[str, int] = {issue_id: 0 for issue_id in issues}
    for batch in plan["batches"]:
        errors.extend(validate_batch(batch, require_ready=False))
        for issue_id in batch.get("included_issues", []):
            if issue_id in membership:
                membership[issue_id] += 1
    for issue_id, count in membership.items():
        if count != 1:
            errors.append(_violation(issues[issue_id], "batch", "LW-PLN-007", f"Issue belongs to {count} proposed Batches", "assign it to exactly one unfinished Batch"))
    return errors


def validate_pr(evidence: dict[str, Any]) -> list[Violation]:
    errors = _schema_violations(evidence, "evidence")
    if errors:
        return errors
    for verdict in evidence["base_review_verdicts"] + evidence["review_verdicts"]:
        errors.extend(_schema_violations(verdict, "review-verdict"))
    if errors:
        return errors
    policy = load_gate_policy()
    candidate = evidence["candidate_sha"]
    pull_request = evidence["pull_request"]
    identity_mismatches = []
    if pull_request["repository_full_name"] != evidence["repository_full_name"]:
        identity_mismatches.append("repository")
    if pull_request["base_branch"] != evidence["base_branch"]:
        identity_mismatches.append("base branch")
    if pull_request["head_branch"] != evidence["working_branch"]:
        identity_mismatches.append("head branch")
    latest_artifact_commit = evidence["review_verdicts"][-1].get("artifact_commit")
    if pull_request["head_sha"] not in {candidate, latest_artifact_commit}:
        identity_mismatches.append("head SHA")
    if pull_request["draft"]:
        identity_mismatches.append("draft state")
    if identity_mismatches:
        errors.append(_violation(evidence, "pull_request", "LW-PR-001", f"PR identity mismatch: {', '.join(identity_mismatches)}", "use the declared repository/base/branch and current candidate or verdict-only tip"))

    checks = {check["name"]: check for check in evidence["required_checks"]}
    for name in policy["required_checks"]:
        check = checks.get(name)
        if check is None:
            errors.append(_violation(evidence, "required_checks", "LW-PR-002", f"required check {name!r} is absent", "run the exact base-policy required check"))
            continue
        if check["status"] != "success":
            errors.append(_violation(evidence, f"required_checks.{name}.status", "LW-PR-003", f"required check is {check['status']}", "wait for or rerun a successful check"))
        if check["sha"] != candidate:
            errors.append(_violation(evidence, f"required_checks.{name}.sha", "LW-PR-004", "required check is bound to a stale candidate", "run it on the current candidate SHA"))

    commit_shas = {commit["sha"] for commit in evidence["commits"]}
    bad_subjects = [commit["subject"] for commit in evidence["commits"] if not COMMIT_SUBJECT.fullmatch(commit["subject"]) or re.match(r"(?i)(?:WIP|fixup!|squash!)", commit["subject"])]
    if candidate not in commit_shas or bad_subjects:
        errors.append(_violation(evidence, "commits", "LW-PR-005", f"candidate absent or invalid commit subjects: {bad_subjects!r}", "include the candidate and clean WIP/fixup/squash or non-conventional subjects"))

    base_verdicts = evidence["base_review_verdicts"]
    verdicts = evidence["review_verdicts"]
    rounds = [item["round"] for item in verdicts]
    if (
        len(verdicts) <= len(base_verdicts)
        or verdicts[: len(base_verdicts)] != base_verdicts
        or rounds != sorted(set(rounds))
        or any(round_number <= 0 for round_number in rounds)
    ):
        errors.append(_violation(evidence, "review_verdicts", "LW-PR-007", "prior verdict artifacts were modified/deleted or no new round was appended", "preserve the exact base history and append one new artifact"))
    latest = verdicts[-1]
    latest_new_findings = [finding for finding in latest.get("findings", []) if finding.get("new")]
    if (
        latest.get("candidate_sha") != candidate
        or not latest.get("independent_context")
        or latest.get("verdict") != "approved"
        or latest_new_findings
    ):
        errors.append(_violation(evidence, "review_verdicts[-1]", "LW-PR-006", "latest review is stale, non-independent, unapproved, or contains new findings", "obtain an independent approved round with no new findings on the current candidate"))

    new_verdicts = verdicts[len(base_verdicts) :]
    expected_verdict_paths = {item.get("artifact_path") for item in new_verdicts}
    actual_verdict_paths = set(evidence["verdict_commit_changed_paths"])
    root = policy["verdict_artifact_root"]
    if (
        actual_verdict_paths != expected_verdict_paths
        or not actual_verdict_paths
        or any(not path.startswith(root) for path in actual_verdict_paths if isinstance(path, str))
    ):
        errors.append(_violation(evidence, "verdict_commit_changed_paths", "LW-PR-008", "verdict commit is missing, changes code, or writes outside the artifact root", "make an add-only verdict artifact commit"))
    if evidence["reviewer_context"]["candidate_sha"] != candidate:
        errors.append(_violation(evidence, "reviewer_context.candidate_sha", "LW-PR-009", "reviewer brief targets a stale candidate", "regenerate the context index for the current candidate"))
    if evidence["gate_policy_source"] != "base" or evidence["gate_policy_sha"] != evidence["base_sha"]:
        errors.append(_violation(evidence, "gate_policy_sha", "LW-PR-010", "gate policy is not bound to the declared base SHA", "load policy from the protected base revision"))
    protected = [path for path in evidence["changed_paths"] if _path_matches_prefix(path, policy["review_required_paths"])]
    if protected and evidence["risk_profile"] != "high":
        errors.append(_violation(evidence, "risk_profile", "LW-PR-011", f"gate-owned paths require High-risk review: {protected!r}", "use the High-risk review lane or remove the gate change"))
    return errors

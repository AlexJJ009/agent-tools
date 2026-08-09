from __future__ import annotations

import re
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
        prefix = PurePosixPath(entry).as_posix()
        if entry.endswith("/"):
            if normalized.startswith(prefix):
                return True
        elif normalized == prefix:
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

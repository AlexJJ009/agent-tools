from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from . import __version__


HEADING = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
ORDERED_ITEM = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")
META = re.compile(r"^\s*-\s*([^:]+):\s*`?(.+?)`?\s*$")
PLACEHOLDER = re.compile(r"(?:\breplace-me\b|\bTBD\b|\bTODO\b|待定)", re.IGNORECASE)
FORBIDDEN_OUTPUT = ("AUTO_ADVANCE", "reviewer prompt")


class MigrationError(ValueError):
    """A legacy Goal cannot be read safely enough to form a proposal."""


def _safe_text(text: str) -> str:
    return "\n".join(
        line for line in text.strip().splitlines()
        if not any(token.lower() in line.lower() for token in FORBIDDEN_OUTPUT)
    ).strip()


def _sections(markdown: str) -> dict[tuple[str, ...], str]:
    paths: list[str] = []
    content: dict[tuple[str, ...], list[str]] = {}
    for line in markdown.splitlines():
        match = HEADING.match(line)
        if match:
            level = len(match.group(1)) - 2
            paths = paths[:level]
            paths.append(match.group(2).strip())
            content.setdefault(tuple(paths), [])
        elif paths:
            content.setdefault(tuple(paths), []).append(line)
    return {path: _safe_text("\n".join(lines)) for path, lines in content.items()}


def _section(sections: dict[tuple[str, ...], str], *names: str) -> str | None:
    lowered = tuple(name.lower() for name in names)
    for path, text in sections.items():
        if tuple(part.lower() for part in path) == lowered:
            return text or None
    return None


def _metadata(plan: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in plan.splitlines():
        match = META.match(line)
        if match:
            result[match.group(1).strip().lower().replace(" ", "_")] = match.group(2).strip(" `")
    return result


def _read_jsonl(path: Path, warnings: list[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        warnings.append(f"Missing legacy artifact: {path.name}")
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            warnings.append(f"Malformed {path.name} line {line_number}: blank record")
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"Malformed {path.name} line {line_number}: invalid JSON")
            continue
        if not isinstance(value, dict):
            warnings.append(f"Malformed {path.name} line {line_number}: record is not an object")
            continue
        records.append(value)
    return records


def _artifact_reference(path: Path, record_count: int | None = None) -> dict[str, Any]:
    reference: dict[str, Any] = {"path": path.name}
    if path.is_file():
        reference["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if record_count is not None:
            reference["record_count"] = record_count
    else:
        reference["missing"] = True
    return reference


def _milestones(text: str | None) -> list[str]:
    if not text:
        return []
    return [match.group(1).strip() for line in text.splitlines() if (match := ORDERED_ITEM.match(line))]


def _completed_milestones(records: Iterable[dict[str, Any]]) -> set[str]:
    return {
        str(record["milestone"]).strip()
        for record in records
        if record.get("event") == "MILESTONE_COMPLETED" and record.get("milestone")
    }


def _open_in_scope_findings(
    records: Iterable[dict[str, Any]], warnings: list[str]
) -> list[tuple[str, str]]:
    state: dict[str, dict[str, Any]] = {}
    for record in records:
        finding_id = record.get("finding_id")
        if not isinstance(finding_id, str) or not finding_id:
            continue
        current = state.setdefault(
            finding_id,
            {"open": False, "classification": None, "summary": None},
        )
        event = record.get("event")
        if event in {"FINDING_OPENED", "FINDING_REOPENED"}:
            current["open"] = True
        elif event == "FINDING_CLOSED":
            current["open"] = False
        if event == "FINDING_CLASSIFIED":
            current["classification"] = record.get("classification")
        for field in ("summary", "title", "finding"):
            if isinstance(record.get(field), str) and record[field].strip():
                current["summary"] = _safe_text(record[field])
                break

    result: list[tuple[str, str]] = []
    for finding_id in sorted(state):
        item = state[finding_id]
        if not item["open"]:
            continue
        if item["classification"] != "IN_SCOPE":
            warnings.append(
                f"Open finding {finding_id} was not proposed because its current classification "
                "is not unambiguously IN_SCOPE"
            )
            continue
        summary = item["summary"] or f"Resolve legacy finding {finding_id}"
        result.append((finding_id, summary))
    return result


def _acceptance_items(sections: dict[tuple[str, ...], str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for path, body in sections.items():
        if len(path) == 2 and path[0].lower() == "acceptance criteria":
            value = _safe_text(body)
            if value:
                items.append({"title": path[1], "criteria": value})
    return items


def _unique_repository(runtime: Iterable[dict[str, Any]], warnings: list[str]) -> str | None:
    repositories = sorted({
        record["repository"]
        for record in runtime
        if isinstance(record.get("repository"), str)
        and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", record["repository"])
    })
    if len(repositories) == 1:
        return repositories[0]
    if not repositories:
        warnings.append("Repository is missing; choose the full owner/repository before approval")
    else:
        warnings.append(
            "Multiple historical repositories were observed; choose the still-applicable repository boundary"
        )
    return None


def _acceptance_status(text: str | None) -> str | None:
    if not text:
        return None
    for line in text.splitlines():
        match = META.match(line)
        if match and match.group(1).strip().lower() == "status":
            return match.group(2).strip(" `")
    return None


def build_goal_plan_migration(goal_dir: Path) -> dict[str, Any]:
    goal = goal_dir.resolve()
    if not goal.is_dir():
        raise MigrationError(f"legacy Goal directory does not exist: {goal}")
    warnings: list[str] = []
    clarifications: list[str] = []
    plan_path = goal / "plan.md"
    if not plan_path.is_file():
        raise MigrationError(f"missing required legacy plan: {plan_path}")
    plan = plan_path.read_text(encoding="utf-8")
    sections = _sections(plan)
    metadata = _metadata(plan)
    runtime_path = goal / "runtime.jsonl"
    findings_path = goal / "findings.jsonl"
    acceptance_path = goal / "acceptance.md"
    runtime = _read_jsonl(runtime_path, warnings)
    findings = _read_jsonl(findings_path, warnings)
    acceptance_text = (
        acceptance_path.read_text(encoding="utf-8") if acceptance_path.is_file() else None
    )
    if acceptance_text is None:
        warnings.append("Missing legacy artifact: acceptance.md")

    goal_id = metadata.get("goal_id") or goal.name
    title = next(
        (line.removeprefix("# ").strip() for line in plan.splitlines() if line.startswith("# ")),
        goal_id,
    )
    outcome = _section(sections, "Outcome")
    included = _section(sections, "Scope", "Included")
    excluded = _section(sections, "Scope", "Excluded")
    acceptance = _acceptance_items(sections)
    for field, value in (("outcome", outcome), ("scope.included", included), ("scope.excluded", excluded)):
        if not value or PLACEHOLDER.search(value):
            warnings.append(f"PRD {field} is missing or still contains a placeholder")
            clarifications.append(f"Provide the approved {field} before applying this proposal")
    if not acceptance or any(PLACEHOLDER.search(item["criteria"]) for item in acceptance):
        warnings.append("Product acceptance is missing or contains a placeholder")
        clarifications.append("Confirm the product acceptance criteria before approval")

    repository = _unique_repository(runtime, warnings)
    if repository is None:
        clarifications.append("Choose the full owner/repository for each proposed code Issue")

    milestones = _milestones(_section(sections, "Milestones"))
    completed = _completed_milestones(runtime)
    issue_proposals: list[dict[str, Any]] = []
    prior_key: str | None = None
    for index, milestone in enumerate(milestones, 1):
        if milestone in completed or f"M{index}" in completed:
            continue
        if PLACEHOLDER.search(milestone):
            warnings.append(f"Milestone {index} was not proposed because it is a placeholder")
            continue
        key = f"{goal_id}:milestone:{index}"
        issue_proposals.append({
            "proposal_key": key,
            "title": milestone,
            "outcome": milestone,
            "destination": None,
            "repository_full_name": repository,
            "dependencies": [prior_key] if prior_key else [],
            "acceptance": [],
            "source": {"artifact": "plan.md", "milestone": index},
        })
        prior_key = key

    for finding_id, summary in _open_in_scope_findings(findings, warnings):
        issue_proposals.append({
            "proposal_key": f"{goal_id}:finding:{finding_id}",
            "title": summary,
            "outcome": summary,
            "destination": None,
            "repository_full_name": repository,
            "dependencies": [],
            "acceptance": [],
            "source": {"artifact": "findings.jsonl", "finding_id": finding_id},
        })

    if issue_proposals:
        clarifications.append("Choose each Issue destination and add Issue-level acceptance before approval")
        clarifications.append("Choose the Delivery Batch risk profile; the legacy Goal does not define one")
    else:
        warnings.append("No unambiguously active work was found; no Issue or Delivery Batch is proposed")

    acceptance_status = _acceptance_status(acceptance_text)
    if acceptance_status in {None, "PENDING REVIEW", "unassigned"}:
        warnings.append("Historical acceptance is incomplete or unassigned")

    issue_keys = [item["proposal_key"] for item in issue_proposals]
    dag = [
        {"from": dependency, "to": item["proposal_key"]}
        for item in issue_proposals
        for dependency in item["dependencies"]
    ]
    batches = []
    if issue_keys:
        batches.append({
            "proposal_key": f"{goal_id}:batch:1",
            "title": f"Migration Batch | {title}",
            "included_issue_proposal_keys": issue_keys,
            "risk_profile": None,
            "full_ci_point": "after one exact candidate SHA is fixed",
            "status": "Backlog",
        })

    proposal = {
        "schema_version": 1,
        "workflow_version": __version__,
        "source": "goal-plan",
        "mode": "dry-run",
        "goal_reference": f"legacy-goal:{goal_id}",
        "project_proposal": {
            "proposal_key": f"{goal_id}:project",
            "title": title,
            "status": "Draft",
            "repository_full_name": repository,
        },
        "prd_proposal": {
            "proposal_key": f"{goal_id}:prd",
            "status": "Draft",
            "outcome": outcome,
            "scope": {"included": included, "excluded": excluded},
            "acceptance": acceptance,
        },
        "issue_proposals": issue_proposals,
        "dag": dag,
        "delivery_batch_proposals": batches,
        "archive_references": {
            "plan": _artifact_reference(plan_path),
            "runtime_ledger": _artifact_reference(runtime_path, len(runtime)),
            "findings_ledger": _artifact_reference(findings_path, len(findings)),
            "acceptance": {
                **_artifact_reference(acceptance_path),
                "status": acceptance_status,
            },
        },
        "warnings": sorted(set(warnings)),
        "clarifications": sorted(set(clarifications)),
        "approval_boundary": "waiting_for_human_review",
        "external_writes": [],
    }
    rendered = json.dumps(proposal, sort_keys=True)
    if any(token.lower() in rendered.lower() for token in FORBIDDEN_OUTPUT):
        raise MigrationError("legacy-only control text escaped the migration exclusion filter")
    return proposal

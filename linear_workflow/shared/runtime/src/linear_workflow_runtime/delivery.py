from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping

from .contracts import Violation, validate_schema
from .validators import validate_batch


class DeliveryAdmissionError(ValueError):
    """A Ready Batch cannot safely enter or continue Delivery."""


def _format_errors(errors: Iterable[Violation | str]) -> str:
    return "\n".join(error.render() if isinstance(error, Violation) else error for error in errors)


def topological_issue_order(
    batch: Mapping[str, Any],
    issues: Iterable[Mapping[str, Any]],
    *,
    completed_external_dependencies: Iterable[str] = (),
) -> tuple[str, ...]:
    """Return the deterministic included-Issue order or fail closed.

    Dependencies outside the Batch must be explicitly reported complete. This keeps
    Project context from silently becoming authorization for successor work.
    """

    batch_errors = validate_batch(dict(batch))
    if batch_errors:
        raise DeliveryAdmissionError(_format_errors(batch_errors))

    records: dict[str, Mapping[str, Any]] = {}
    schema_errors: list[str] = []
    for issue in issues:
        issue_id = str(issue.get("id", "unknown"))
        if issue_id in records:
            schema_errors.append(f"duplicate Issue ID: {issue_id}")
            continue
        errors = validate_schema(dict(issue), "issue")
        schema_errors.extend(f"{issue_id}: {error}" for error in errors)
        records[issue_id] = issue
    if schema_errors:
        raise DeliveryAdmissionError("\n".join(schema_errors))

    included = tuple(batch["included_issues"])
    if set(records) != set(included):
        unknown = sorted(set(included) - set(records))
        extra = sorted(set(records) - set(included))
        raise DeliveryAdmissionError(
            f"Batch/Issue identity mismatch; missing={unknown!r}, extra={extra!r}"
        )

    completed = set(completed_external_dependencies)
    indegree = {issue_id: 0 for issue_id in included}
    dependents: dict[str, list[str]] = {issue_id: [] for issue_id in included}
    for issue_id in included:
        for dependency in records[issue_id]["dependencies"]:
            if dependency in indegree:
                indegree[issue_id] += 1
                dependents[dependency].append(issue_id)
            elif dependency not in completed:
                raise DeliveryAdmissionError(
                    f"{issue_id} has incomplete external dependency {dependency}"
                )

    batch_position = {issue_id: index for index, issue_id in enumerate(included)}
    ready = sorted(
        (issue_id for issue_id, count in indegree.items() if count == 0),
        key=batch_position.__getitem__,
    )
    ordered: list[str] = []
    while ready:
        issue_id = ready.pop(0)
        ordered.append(issue_id)
        for dependent in sorted(dependents[issue_id], key=batch_position.__getitem__):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort(key=batch_position.__getitem__)
    if len(ordered) != len(included):
        raise DeliveryAdmissionError("included-Issue dependency graph contains a cycle")
    return tuple(ordered)


@dataclass(frozen=True)
class CandidateBinding:
    batch_id: str
    issue_ids: tuple[str, ...]
    repository_full_name: str
    branch: str
    base_sha: str
    candidate_sha: str | None = None
    full_ci_sha: str | None = None
    review_sha: str | None = None

    def bind_candidate(self, candidate_sha: str) -> "CandidateBinding":
        if len(candidate_sha) != 40 or any(char not in "0123456789abcdef" for char in candidate_sha):
            raise ValueError("candidate SHA must be 40 lowercase hexadecimal characters")
        if candidate_sha == self.candidate_sha:
            return self
        return replace(
            self,
            candidate_sha=candidate_sha,
            full_ci_sha=None,
            review_sha=None,
        )

    def record_full_ci(self, sha: str) -> "CandidateBinding":
        if sha != self.candidate_sha:
            raise ValueError("full CI evidence is not bound to the current candidate")
        return replace(self, full_ci_sha=sha)

    def record_review(self, sha: str) -> "CandidateBinding":
        if sha != self.candidate_sha:
            raise ValueError("review evidence is not bound to the current candidate")
        return replace(self, review_sha=sha)

    @property
    def candidate_gate_complete(self) -> bool:
        return (
            self.candidate_sha is not None
            and self.full_ci_sha == self.candidate_sha
            and self.review_sha == self.candidate_sha
        )

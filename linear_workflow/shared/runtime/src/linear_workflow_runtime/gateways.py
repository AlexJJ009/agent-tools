from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


class GatewayFailure(RuntimeError):
    """A typed external-system failure that callers must handle fail closed."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class LinearIssue:
    id: str
    team: str
    repository_full_name: str | None
    github_url: str | None
    proposal_key: str | None
    duplicate_of: str | None = None


@dataclass(frozen=True)
class GitHubIssue:
    reference: str
    url: str
    repository_full_name: str
    proposal_key: str


class LinearGateway(Protocol):
    """Normalized Linear facts and mutations, independent of MCP/API wire shapes."""

    def find_by_proposal_key(self, proposal_key: str) -> LinearIssue | None: ...

    def upsert_linear_only(
        self, proposal_key: str, payload: Mapping[str, Any]
    ) -> LinearIssue: ...

    def find_sync_matches(
        self, github_url: str, expected_team: str, timeout_seconds: int
    ) -> Sequence[LinearIssue]: ...

    def get_issue(self, issue_id: str) -> LinearIssue: ...

    def bind_synced_issue(
        self, issue_id: str, proposal_key: str, payload: Mapping[str, Any]
    ) -> LinearIssue: ...


class GitHubGateway(Protocol):
    """The minimal GitHub Issue interface used by Planning."""

    def find_by_proposal_key(
        self, repository_full_name: str, proposal_key: str
    ) -> GitHubIssue | None: ...

    def create_issue(
        self,
        repository_full_name: str,
        title: str,
        body: str,
        proposal_key: str,
    ) -> GitHubIssue: ...


def _optional_string(raw: Mapping[str, Any], field: str) -> str | None:
    value = raw.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise GatewayFailure("invalid_response", f"{field} must be a non-empty string or null")
    return value


def normalize_linear_issue(raw: Mapping[str, Any]) -> LinearIssue:
    """Normalize a gateway-owned projection, never persist the source response itself."""

    issue_id = raw.get("id")
    team = raw.get("team")
    if not isinstance(issue_id, str) or not issue_id:
        raise GatewayFailure("invalid_response", "Linear issue id is missing")
    if not isinstance(team, str) or not team:
        raise GatewayFailure("invalid_response", "Linear issue team is missing")
    return LinearIssue(
        id=issue_id,
        team=team,
        repository_full_name=_optional_string(raw, "repository_full_name"),
        github_url=_optional_string(raw, "github_url"),
        proposal_key=_optional_string(raw, "proposal_key"),
        duplicate_of=_optional_string(raw, "duplicate_of"),
    )


def normalize_github_issue(raw: Mapping[str, Any]) -> GitHubIssue:
    repository = raw.get("repository_full_name")
    number = raw.get("number")
    url = raw.get("url")
    proposal_key = raw.get("proposal_key")
    if not isinstance(repository, str) or "/" not in repository:
        raise GatewayFailure("invalid_response", "GitHub repository_full_name is invalid")
    if type(number) is not int or number <= 0:
        raise GatewayFailure("invalid_response", "GitHub issue number is invalid")
    if not isinstance(url, str) or not url:
        raise GatewayFailure("invalid_response", "GitHub issue URL is missing")
    if not isinstance(proposal_key, str) or not proposal_key:
        raise GatewayFailure("invalid_response", "GitHub proposal key is missing")
    return GitHubIssue(
        reference=f"{repository}#{number}",
        url=url,
        repository_full_name=repository,
        proposal_key=proposal_key,
    )

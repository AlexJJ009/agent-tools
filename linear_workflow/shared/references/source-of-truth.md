# Source-of-truth contract

| Artifact | Canonical location | Allowed replica |
| --- | --- | --- |
| Product problem, goals, scope, non-goals, product acceptance | Linear PRD Document | link and a short summary |
| Project status, Issue DAG, Batch membership and risk | Linear | IDs and links in commits/PRs |
| Code work item | GitHub/Linear native synced pair | Linear-only planning properties |
| Technical design, ADR, API/schema, migration and runbook | repository | Linear link and boundary summary |
| Code and tests | repository | none |
| PR, candidate SHA, CI and review | GitHub | Linear link and result summary |
| Runtime progress | Linear status/evidence | rebuildable local cache |
| Old Goal history | existing `docs/goals/` | archive link only |

Do not keep a second independently editable PRD in the repository. The schemas,
runtime, tests, and references under `linear_workflow/shared/` are the canonical
implementation contracts for every client adapter.

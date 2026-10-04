# Retire Linear Workflow

Date: 2026-09-30

Status: Accepted; amended 2026-10-03 (source removed)

## Context and Problem Statement

The user retired Linear Workflow from active use. Its planning and delivery
skills and installation defaults previously directed new tasks into Linear
Batches. Continuing to ship those entrypoints would route work into a workflow
the user no longer wants. An old approval or Ready Batch does not reactivate it.

The initial retirement kept the historical implementation for inspection,
while disabling execution. On 2026-10-03 the obsolete source, compatibility
tests, templates and guide were removed; Git history preserves that material.

## Considered Options

- Keep installing and advertising the workflow despite retirement.
- Disable entrypoints while retaining historical source in the active checkout.
- Remove the obsolete implementation and use Git history for reference.

## Decision Outcome

Linear Workflow is excluded from active use and installation. Its source,
schemas, validators, templates and compatibility tests are absent from the
current repository. Commits before removal remain available for historical
inspection; a new explicit decision is required to reintroduce the workflow.

Current contributions follow the authorized task scope and repository checks,
without mandatory Linear identities or a second checklist. The local Task
Runtime and unrelated Linear access remain available. Current validation policy
belongs in [CONTRIBUTING.md](../../CONTRIBUTING.md).

Installers remove verified stale client copies using
`config/retired-packages/linear-workflow.json`, which records fingerprints of
the last shipped copies. Existing runtime data under
`~/.local/share/linear-workflow` remains separate; source retirement does not
migrate or delete live task state.

### Consequences

- The active checkout no longer advertises or maintains the retired workflow.
- Historical rationale and implementation remain accessible in Git history.
- Fingerprinted cleanup removes known shipped copies without treating arbitrary
  user-modified files as disposable.
- Source changes do not prove every installed client was updated; deployment
  claims must identify the actual profiles checked.

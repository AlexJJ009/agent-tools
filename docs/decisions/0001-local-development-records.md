# Keep Development Records Local and System Documentation Maintained

Date: 2026-09-29

Status: Accepted

## Context and Problem Statement

Agent Tools contained migration PRDs, a canonical task checklist, a second
planning checklist, dated acceptance summaries, copied source baselines and
current usage instructions under adjacent documentation paths. These materials
serve different readers: a task handoff must recover unfinished work, whereas a
repository reader needs to use and maintain the implemented system. Historical
pass counts cannot establish that another host has been verified.

The user explicitly chose worktree-local development records and requested a
real cleanup of Agent Tools. This decision applies to this repository and its
record-generation defaults. It does not relocate production logs, external
caches, reusable tests or other projects.

## Considered Options

- Keep plans, status snapshots and current usage together in shared docs.
- Store private development records under one ignored local root and extract
  durable usage and architectural rationale into the repository.
- Build a common artifact-management service or a mandatory document pack.

These are the alternatives considered for this lifecycle change, not a claim
about undocumented choices made during earlier implementations.

## Decision Outcome

Use `docs/_local/tasks/<task-id>/`, `reports/<task-id>/` and
`scratch/<task-id>/` only when needed, excluded by the root `.gitignore`.
Preserve existing task identities and explicit continuation paths. Keep one
execution checklist per requirement; an agent may update observed status but
cannot relax user criteria or manufacture human acceptance. Ordinary fixes do
not require a PRD or persistent record.

Repository guides describe current interfaces and limitations. Handoffs link
those guides and record a recovery point. Significant rationale goes in MADR
records here. Before a meaningful stage commit or merge, state documentation
impact in an existing closing note or commit/PR description and update affected
instructions. Cleaner checks the current diff proportionately; an unchanged,
already-checked diff needs no repeated cleanup ceremony.

This keeps ownership understandable with Markdown, existing runtimes and Git,
without another index, writer framework or progress database. Product entrypoints
must depend on their legitimate inputs, not development reports or historical
acceptance receipts. This does not remove necessary input/compatibility checks.

### Consequences

- A clean checkout contains current usage, tests and decision rationale without
  private evidence or competing editable progress summaries.
- Cross-machine task continuation may require a deliberate transfer of local
  records. Local evidence is not a Git backup or a new host's acceptance receipt.
- Already tracked task files must be preserved locally before retirement from
  the index. This cleanup used pushed baseline `532eed8` for recovery; that
  user-requested baseline is not a new mandatory gate for every future cleanup.
- Existing explicit legacy record paths continue working. Old historical links
  inside preserved evidence remain historical locators rather than being
  rewritten to imply new observations.

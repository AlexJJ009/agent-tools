---
name: intent-to-contract
description: Create or revise a requested task agreement, or ground requirements and authority before expensive or high-risk work. Use readback and acceptance criteria for the agreed scope; ordinary bug fixes and quick implementations do not require a PRD or checklist.
---

# Intent To Contract

Use this skill when the user requests a task agreement or when expensive or high-risk work needs grounded requirements and an authorization boundary. Do not invoke it for every natural-language request, ordinary bug fix, quick implementation, or a mention of an old PRD. The output is the requested task agreement, recorded in the existing task when persistence is needed; it does not freeze every coding step or require legacy runtime context.

Keep the work moving while the agreement is formed. Ask the user only for facts that would change the target, budget, production effect, or formal experiment. For facts visible in the repository or local environment, investigate and record the evidence instead of asking the user to remember it.

## Contract Rules

- Preserve `source_quote` exactly, including Chinese wording, numbers, units, and uncertainty.
- Separate user requirements, project facts, source specs, and agent proposals. An agent proposal cannot become a hard requirement without user or project authority.
- Keep multiple plausible meanings in `semantic_candidates`; do not silently choose when the difference affects target behavior, cost, or formal runs.
- Ground parameter-like requirements in real code, data, or output objects before treating them as protocol items. A matching field name is not enough; trace definition, override order, and consumer.
- Keep the current agreement separate from the work record. Debugging discoveries can update the work record, but cannot lower the goal or change the protocol to make a failing implementation pass.
- Learning-only requests route to the existing teaching flow.
- Distinguish semantic routing from runtime lint. The Agent chooses the scenario after investigation; the runtime only rejects obvious contradictions such as a Docker or launcher request without infra facts.

Use [acceptance profiles](references/acceptance-profiles.md) when selecting scenario checks; read only the applicable profile.

When continuing an explicitly selected legacy scenario contract (or an office-only request), read [legacy scenario records](references/legacy-scenario-records.md). Current task-runtime work uses the task commands below.

## Discover choices before dependent work

For an ordinary request such as using defaults or refreshing a page, inspect the
reference and actual consumer before proposing execution. Discover differences
that change method identity, result interpretation, cost or important business
behavior. Record the source as user wording, code/reference fact or agent
proposal; do not attribute discovered defaults to the user's original quote.
Both user and agent may raise choices. Explain their mechanism, consequence and
recommended option together, without escalating visual or routine coding details.

Follow explicit participation preferences. Without one, newly uncovered method
or material business choices require a scoped explanation and feedback or clear
delegation before dependent action. A choice about critic initialization does
not close an unresolved reward question. A self-report, reconstruction, question,
decision, execution delegation and result acceptance are distinct events. Do not
infer global understanding from any one of them.

Explicit delegation of a bounded demo permits autonomous implementation and
verification; do not force teaching, a quiz or repeated permission. Record the
scope and existing ask-before-run constraints. Pause only actions that depend on
an unresolved material choice; continue unrelated investigation and drafts.

Use one canonical record. Process meaningful input, choices and evidence through
its event interface; reuse applicable authority after routine repairs while
refreshing affected technical evidence. Classify MVP feedback as scoped result
acceptance, an existing defect, criterion clarification or a future-version
request. A general positive reaction does not accept the entire checklist.

## Current task state and continuation

The default deliverable is the conversation and the changed project files;
create a record only when the work needs one to continue. Use the task runtime
when requirements and checklist state must persist across conversations. A
session or worktree name is not a task ID.

Use `agent-workflow task resolve` with the current session and workspace, or
`task list` for candidate metadata. If several tasks match, return the relevant
candidates rather than guessing. Read the selected task with `task read` and
query its checklist through `task checklist`: whole list, individual status,
individual details, or name/content search. Select an item by its stable ID;
ordinal position only locates that ID in the current revision. Read evidence
only as needed and verify current code and jobs from the actual workspace.

Append `--data-root /absolute/root` consistently when overriding the
application root. See `agent-workflow task <command> --help` for the packet
shape; from a source checkout, use `python -m agent_workflow.cli task`. `task
revise` updates the same task for an agreed requirement change, not for
progress. The Agent supplies requirements
and check points; runtime maintains checklist state and revisions. Do not keep
a second writable Markdown PRD/checklist beside the runtime's current state.
Queries and human-readable views go to stdout unless an export is requested.
Use `task read` or `task checklist` with `--format markdown` for a human summary;
use JSON with `--detail` for full fields.

Keep verification, result validity and user acceptance separate. Record actual
checks with `task result`, identifying external checks as external; record
necessary user wording, source and accepted/rejected scope with `task feedback`.
A passing test or positive reaction does not accept the entire task. Use
`task bind` to associate another session at the current workspace, or `task rebind`
to change the task workspace explicitly; reassociation does not make stale
checks current. Existing-task mutations carry a task ID, operation ID and
base revision; create/import assign the ID. Retry unchanged packets with the same operation ID. On revision
conflict, read current state before constructing a new mutation.

A selected legacy record may be imported with `task import`; do not scan or
migrate every old record. The MVP imports requirements only, with checks unverified and acceptance
pending. Verify imported state and provenance before retiring its source. The new runtime does not replace existing formal-run
permission or acceptance-gate contracts. After scoped user acceptance, use
Cleaner's task-closeout activity for owned process material and durable project
information; code cleanup is a separate activity.

## Handoff and Repository Documentation

Keep requirements and success conditions in the selected canonical task store or existing local PRD/simple spec, and actual verification status in its one runtime-maintained checklist. Agents may update execution status but cannot relax requirements or invent human acceptance. Do not require checklist rewrites or Markdown changes for every commit.

Task state, recovery points and handoff live in the task record (Task Runtime or the task's `docs/_local` record); never write task state into AGENTS.md, CLAUDE.md or other auto-loaded instruction files. Update that record in place when the stage changes, replacing superseded current-state prose; keep source requirements and evidence by reference and link repository usage/interface documentation instead of copying it. Process handles belong to their original machine and must be read back before reuse after a handoff.

Repository documentation must explain the implemented system without access to private reports. Extract durable usage and interface facts into maintained documentation rather than committing the local plan. When a change chooses between viable designs, add or update `docs/decisions/` in the same change. Private reports use `docs/_local/reports/<task-id>/`; temporary drafts use `docs/_local/scratch/<task-id>/`.

Before a merge or meaningful delivery commit, state documentation impact in the existing closing note or commit/PR description and update affected system docs. If there is no impact, explain why; a Markdown diff is not mandatory.

## Completion Boundary

This skill does not authorize formal experiments, production writes, external publication, or user review completion. It produces the agreement and the evidence targets that later gates check.

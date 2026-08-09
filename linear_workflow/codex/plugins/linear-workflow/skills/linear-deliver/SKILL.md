---
name: linear-deliver
description: Deliver one explicitly dispatched Ready Linear Batch by reading live Linear, repository, and GitHub facts; executing included Issues in DAG order; and producing candidate-bound CI and independent review evidence. Use only for Delivery of an approved Batch. Do not use for Planning, Project-wide implementation, automatic merge, or release approval.
---

# Linear Deliver

Execute exactly one human-dispatched Ready Batch. One Batch is one development branch, one candidate validation cycle, and one primary PR per repository.

## Canonical contract

Report the workflow and schema versions from generated `references/contract.json`. Load the canonical schemas and only the shared references needed for the Batch:

- `linear_workflow/shared/references/linear-object-contract.md`
- `linear_workflow/shared/references/source-of-truth.md`
- `linear_workflow/shared/references/risk-profiles.md`
- `linear_workflow/shared/references/lifecycle.md`

Treat those files and `linear_workflow/shared/runtime` as the only workflow state, risk, and validation logic. Do not copy a client-specific state machine, PRD, risk table, or validator rule into this adapter.

## Admission and recovery

1. Require an explicit Batch ID. A Project ID is context, not Delivery authorization.
2. Read the Project, Approved PRD, Batch, every included Issue and relation, blocker completion, repository, base branch, and current Linear evidence through Linear MCP. Run `linear-workflow batch-check --input <normalized-batch.json>` using the installed shared runtime before implementation.
   Fail closed if Linear or GitHub authentication/readiness cannot be established; an install-time doctor warning is not authorization to infer external facts.
3. Fetch the declared repository and resolve a full base SHA from the latest base branch. Inspect repository instructions and preserve all existing worktrees and user changes. Create or resume the Batch branch recorded in Linear/GitHub; recover from durable Linear, Git, GitHub, and repository evidence rather than private chat history.
4. Stop and mark the Batch Blocked on a contract conflict, undeclared repository, scope expansion, permission boundary, or irreversible operation. Do not revise the approved Planning contract during Delivery.

## Execution

1. Use `linear_workflow_runtime.delivery.topological_issue_order` to verify the included-Issue DAG and completed external blockers. Execute included Issues in that order; one Agent may complete multiple Issues sequentially.
2. At each Issue boundary, run only checks targeted to that Issue and write concise evidence to Linear. Do not run full CI or merge main at each Issue boundary.
3. Keep every changed path inside the Batch contract. Do not implement successor Batches or use `goal-plan` as the Delivery runtime.
4. After all members are implemented, commit a single coherent Batch candidate, record the complete base SHA, candidate SHA, Batch ID, Issue IDs, `owner/repository`, branch, and PR identity, then run the complete required validation once for that candidate.
5. If the candidate changes, invalidate all prior candidate-bound CI and review evidence. Push the Batch branch and use one primary PR; do not treat an absent GitHub check as success.
6. Start a fresh independent reviewer on the exact candidate and full base-to-candidate diff. Resolve in-scope findings, create a new candidate, rerun required validation, and start a new review round until the latest verdict is approved with zero unresolved and zero new findings.

## Completion boundary

- High-risk implementation and review do not authorize merge or release.
- Do not merge without explicit human approval.
- Record unavailable client runtime evidence as deferred; never simulate or claim it passed.
- At the requested acceptance boundary, keep the PR open, move completed leaf Issues to Done and the Batch to In Review, report exact candidate/check/review evidence, and stop.

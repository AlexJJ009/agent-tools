---
name: linear-plan
description: Plan or revise Linear-first software projects by reading Linear and candidate repositories, producing an approval-bound preview, and writing approved PRDs, Issues, DAG relations, and Delivery Batches through the shared Planning runtime. Use for discovery intake, PRD drafting, decomposition, destination selection, or planning revisions. Do not use to implement a Ready Batch or continue directly into Delivery.
---

# Linear Plan

Prepare a complete planning preview, obtain one explicit approval for that exact preview, apply it idempotently, and stop at the Planning/Delivery boundary.

## Canonical contract

Report the workflow and schema versions from the generated `references/contract.json`; its values are assembled from `linear_workflow/VERSION` and the shared schema contract. Then load only the shared references needed for the request:

- `linear_workflow/shared/references/linear-object-contract.md`
- `linear_workflow/shared/references/source-of-truth.md`
- `linear_workflow/shared/references/risk-profiles.md`
- `linear_workflow/shared/references/lifecycle.md`

Treat those files and the schemas under `linear_workflow/shared/schemas/` as canonical. Do not copy a second PRD, state machine, risk matrix, or validator rule into this adapter.

## Workflow

1. Read the requested Linear Issue or Project, its relations, and its current PRD through Linear MCP.
2. Resolve every candidate repository to `owner/repository`. Read its `AGENTS.md` or `CLAUDE.md`, architecture entry points, relevant code, tests, and technical documents. Do not claim reliable technical decomposition for a repository that was not inspected.
3. Separate product questions from implementation choices. Keep blocking questions explicit and stop before approval while any answer could change behavior, scope, repository, or acceptance.
4. Build one complete preview containing the normalized PRD, every proposed Issue and destination, DAG relation, Delivery Batch, repository, risk profile, and expected create/update action.
5. Write the preview's PRD contract to a temporary input and run `linear-workflow plan-check --input <normalized-prd.json>` with the installed shared runtime. Fix contract errors before presenting the complete preview; do not pass the outer preview envelope to this PRD validator.
6. Present the full diff-like preview. Allow item-level revisions, regenerate the preview after each revision, and accept only an identifiable human approval bound to the exact current preview ID.
7. Apply the approved preview through `linear_workflow_runtime.planning.PlanningRuntime`. Use stable proposal keys and the normalized Linear/GitHub gateways. For `github_to_linear`, create or reuse the approved GitHub Issue and resolve its unique native-synced Linear Issue; for `linear_only`, do not call GitHub.
8. Report the resulting Linear and GitHub identities plus validator evidence. A human may mark the PRD and eligible Batches Ready. Stop; Delivery requires a new explicit command or session with a Ready Batch ID.

## Stop conditions

- Stop with clarification when a product answer, repository, destination, or acceptance boundary is missing.
- Fail closed on authentication or permission failure, wrong repository, sync timeout, zero or multiple canonical sync matches, or ambiguous duplicate mapping. Never create a parallel Linear Issue to repair missing GitHub sync.
- Do not mark your own PRD or decomposition Approved or Ready.
- Do not modify implementation code, create an implementation PR, invoke `goal-plan`, or enter Delivery in the same uninterrupted turn.
- Stop for human contract review when the requested change expands scope, changes product acceptance, adds an undeclared repository, raises risk, or requires an irreversible operation.

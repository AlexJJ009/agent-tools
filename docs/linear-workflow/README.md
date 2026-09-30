# Linear Workflow (deprecated and disabled)

Linear Workflow is retired and excluded from the default installation. Do not
invoke `linear-plan`, `linear-deliver`, or their plugin/command adapters, even
with an old Ready Batch. Their entrypoints stop instead of running the workflow.
Source, schemas, validators and compatibility tests remain available for
historical inspection and maintenance. Retention does not authorize reactivation.
Use the [task runtime](../TASK_RUNTIME.md) for current local task records.
[ADR 0006](../decisions/0006-retire-linear-workflow.md) records the retirement.

## Existing installations

The Unix and Win11 installers now remove verified managed discovery entries
instead of installing this package. Deprecated opt-in flags are rejected before
installation. Modified or unmanaged entries stop removal for inspection.
For a scoped local retirement, run from this repository:

```bash
python3 scripts/managed_package_installer.py disable --descriptor config/managed-packages/linear-workflow.json --repo-root . --home "$HOME" --platform unix
python3 scripts/managed_package_installer.py check --descriptor config/managed-packages/linear-workflow.json --repo-root . --home "$HOME" --platform unix
```

The disable command checks the target profile before writes. It removes managed
Skills, command adapters, the personal plugin registration/cache and launcher;
it preserves runtime/shared files, installation history and application data.
Start a new Agent session to refresh its already-loaded Skill catalog. Source
instructions also reject use from a stale catalog. This does not uninstall the
separate Linear connector or change Linear service data.

## Historical technical boundary

The remainder describes the former workflow; it is not a current dispatch or
installation instruction.

The former approved product requirements were canonical in the Linear Document:

<https://linear.app/gongxunli/document/prdlinear-workflow-v1planningdelivery-%E4%B8%8E-validator-c0da64ed3b7c>

This repository stores only implementation artifacts: normalized schemas,
deterministic runtime code and tests, shared technical references, adapters,
installation logic, and runbooks. It does not keep an editable PRD copy.

The shared implementation is under `linear_workflow/shared/`; client adapters,
installation and CI consume its contracts. Planning produces a reviewable
preview; implementation requires explicit dispatch of a Ready Batch. Project
context does not expand that scope, and merge authority remains human.
Historical local design drafts do not override the approved Linear document or
the current shared contracts.

Installed clients can read both compatibility versions without external writes:

```bash
linear-workflow version --json
```

The existing human-readable workflow-version command remains available as

```bash
linear-workflow --version
```

## Legacy Goal migration preview

`goal-plan` is deprecated for new work. Existing Goal artifacts remain readable
and validatable. Generate a deterministic, read-only migration proposal with:

```bash
linear-workflow migrate goal-plan docs/goals/<goal-id> --dry-run
```

The JSON preview contains a Draft Project/PRD, only still-active Issue
proposals, an acyclic DAG, Delivery Batch proposals, archive references, and
warnings/clarifications for facts that require human answers. It never copies
the full ledgers, reviewer prompts, or legacy authorization into the proposal.
The v1 command has no apply/write mode and stops at human review.

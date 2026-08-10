# Linear Workflow technical boundary

The approved product requirements are canonical in the Linear Document:

<https://linear.app/gongxunli/document/prdlinear-workflow-v1planningdelivery-%E4%B8%8E-validator-c0da64ed3b7c>

This repository stores only implementation artifacts: normalized schemas,
deterministic runtime code and tests, shared technical references, adapters,
installation logic, and runbooks. It does not keep an editable PRD copy.

Batch A establishes `linear_workflow/shared/`. Later Batches add live gateways,
client adapters, CI adoption, installation, and goal-plan compatibility without
moving product decisions out of Linear.

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

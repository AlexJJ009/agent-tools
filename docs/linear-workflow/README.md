# Linear Workflow technical boundary

The approved product requirements are canonical in the Linear Document:

<https://linear.app/gongxunli/document/prdlinear-workflow-v1planningdelivery-%E4%B8%8E-validator-c0da64ed3b7c>

This repository stores only implementation artifacts: normalized schemas,
deterministic runtime code and tests, shared technical references, adapters,
installation logic, and runbooks. It does not keep an editable PRD copy.

Batch A establishes `linear_workflow/shared/`. Later Batches add live gateways,
client adapters, CI adoption, installation, and goal-plan compatibility without
moving product decisions out of Linear.

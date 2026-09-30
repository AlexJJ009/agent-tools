# Retire Linear Workflow While Preserving Its Source

Date: 2026-09-30

Status: Accepted

## Context and Problem Statement

The user retired Linear Workflow from active use. Its planning and delivery
skills, installation defaults and repository instructions previously directed
new tasks into Linear Batches. Keeping those entrypoints active would continue
routing work into a workflow the user no longer wants.

## Considered Options

- Delete the historical implementation and its compatibility tests.
- Keep installing and advertising the workflow despite retirement.
- Disable entrypoints and default installation while preserving source.

## Decision Outcome

Disable Linear Workflow and exclude it from default installation. Mark the
canonical skills, generated adapters and metadata as deprecated; invocation
stops without entering the historical workflow. An old approval or Ready Batch
does not reactivate it. Current contributions use the authorized task scope
and repository checks, without mandatory Linear identities.

Keep the runtime, schemas, contracts, validators and compatibility CI. Their
continued presence supports historical inspection and maintenance; it does not
authorize workflow execution. Reactivation requires an explicit new decision.
This decision does not retire the local task runtime or unrelated Linear access.

### Consequences

- Existing source remains inspectable and testable.
- Generated adapters retain their identity and contract versions but stop use.
- Historical technical references describe the former workflow; they are not
  current instructions for planning, delivery or installation.
- Source changes alone do not prove that every previously installed client has
  been updated; deployment results must identify the profiles actually changed.

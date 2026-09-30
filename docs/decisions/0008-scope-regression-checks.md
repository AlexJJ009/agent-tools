# Scope Regression Checks to Maintained Consumers

Date: 2026-09-30

Status: Accepted

Supersedes: [ADR 0006](0006-retire-linear-workflow.md) only for automatic
execution of historical compatibility tests. Linear Workflow remains disabled,
and its retained implementation remains available for historical maintenance.

## Context and Problem Statement

The previous required CI check ran retired Linear internals on every change
while omitting tests nested under several maintained components. Some checks
asserted source wording, duplicated another check or tested only their own
mock. Counting regression, compatibility and CI results separately overstated
the independent evidence available.

The user requested a concrete retention reason and a cheaper alternative for
each surviving test. The resulting audit and implementation were adopted in
[PR 47](https://github.com/AlexJJ009/agent-tools/pull/47). This record captures
that policy; test counts and individual run results are not architectural
invariants.

## Considered Options

- Continue running historical compatibility checks on every PR.
- Run all maintained and historical suites on every PR.
- Select maintained consumers by changed paths and run historical suites only
  on explicit request, retaining full active runs for shared or unknown changes.

## Decision Outcome

Choose affected-component regression selection. A retained check must detect a
concrete failure for a maintained consumer, or be explicitly historical. Prefer
a cheaper check when it preserves detection of that failure. Use direct API
calls for rule matrices and representative real CLI, installer, Hook, Git and
storage boundaries where process or filesystem behavior matters. Removing test
methods is not the objective; preserving useful failure detection is.

The runner owns suite registration and dependency selection. Shared installer,
guard and CI changes, and unknown production paths, select all active suites.
Documentation-only changes do not run unchanged runtimes. Selected suites fail
on empty discovery, import errors, failed assertions or entirely skipped
execution. Historical Linear compatibility and the old acceptance harness are
explicit-only; active installation tests still protect disabled entrypoints and
user-owned state. Commands and current suite ownership belong in
[CONTRIBUTING.md](../../CONTRIBUTING.md), not a second ADR inventory.

Keep the existing required status name until its GitHub ruleset is deliberately
changed. That compatibility name does not reactivate Linear Workflow. CI repeats
regressions; independent review examines requirements, implementation and gaps.
Neither adds a second population of product tests to the same results.

### Consequences

- Routine checks avoid unrelated work and retired runtime setup. Dependency
  selection must be maintained when consumers or entrypoints change; unknown
  paths conservatively cost a full active run.
- Representative fault injection can demonstrate that a replacement check
  detects its intended failure. It is not exhaustive mutation coverage or an
  Agent-quality evaluation.
- Deterministic tests and static platform checks do not establish semantic
  writing quality, native Hook activation, native Windows deployment or live
  service behavior. Those claims need applicable real-scene evidence.
- Historical source can remain inspectable without imposing its former
  workflow or test cost on ordinary contributions. A skipped historical suite
  must not be reported as verified by that CI run.

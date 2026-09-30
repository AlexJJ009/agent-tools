# Keep Task State and Process Materials in Local Application Storage

Date: 2026-09-30

Status: Accepted

Consolidated on 2026-09-30 from records 0001, 0004 and 0005. Earlier rationale
and the original runtime-owned-only deletion boundary remain in Git history;
this consolidation preserves the adopted behavior, not a new runtime change.

## Context and Problem Statement

Worktree-local plans and reports mixed task recovery with maintained project
knowledge. A task can span conversations and working directories; duplicating
its current requirements in each checkout creates competing authorities.
Reinstalling software must not erase task state. Obsolete process materials can
also accumulate before the business task is accepted, so material retirement
cannot depend on closing the whole task.

## Considered Options

- Keep authoritative task records in each worktree's ignored local directory.
- Keep task state in local application storage, initially deleting only its
  registered artifacts.
- Extend that store with explicitly scoped retirement of reviewed external
  process materials, separately from task completion.

These describe the adopted evolution, not an evaluation of undocumented storage
technologies or a requirement to migrate all legacy records.

## Decision Outcome

Use one local application-data store, separate from installed software and
project checkouts. SQLite holds task state and operation metadata; managed paths
hold task artifacts. Stable task and criterion IDs, revision checks and
idempotent requests support continuation across conversations and explicit
workspace rebinds. There is no cross-machine synchronization. Keep observations,
their validity for current inputs and scoped user acceptance distinct.

The Agent and Cleaner own semantic requirements, retention and authorization
judgments. Runtime enforces declared scope and recoverable operations; neither a
passing test, filename, ignore rule nor elapsed time supplies deletion authority.
Task closeout requires scoped user acceptance and reviewed artifact dispositions.
Separately authorized material retirement may proceed while a task stays open.
Project documents, latest finalized surveys, required fixtures and unresolved
recovery evidence remain protected; uncertainty about disposition requires
clarification. This does not authorize automatic worktree retirement.

Database and filesystem operations do not share an atomic transaction. Keep
external process cleanup in a recoverable journal, with exact reviewed paths and
content verification. Expose compact task receipts and journal metadata through
one history/recovery interface. Distinguish database commit from completed
physical cleanup; pending cleanup blocks closeout and forget. Application
archives have their own explicit retirement scope, not automatic expiry.

Existing legacy records remain valid; import is deliberate and does not inherit
verification or acceptance. Private material outside Task Runtime may remain in
ignored local paths. Maintain durable usage in project guides and significant
rationale in ADRs, without copying task reports or making them product inputs.
The [system documentation index](../README.md) owns documentation placement; the
[Task Runtime guide](../TASK_RUNTIME.md) owns paths, commands and recovery rules.

### Consequences

- A task's identity survives a conversation or worktree change, but Git and
  software reinstallations do not back up its application data.
- The separate cleanup journal preserves recoverability without claiming a
  cross-filesystem transaction. Consumers must read completion state; explicit
  task forgetting does not erase independently retained process journals.
- Cleanup can remove obsolete process material without claiming business
  acceptance. Archives still require review and authorization to retire.
- Shared source contains current interfaces, reusable tests and design rationale;
  private progress does not become another maintained documentation set.
- These storage and ownership decisions do not prove native Hook execution,
  remote installation readiness or plugin packaging.

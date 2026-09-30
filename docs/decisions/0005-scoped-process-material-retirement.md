# Retire Reviewed Process Materials Without Closing the Task

Date: 2026-09-30

Status: Accepted

Supersedes: [ADR 0004](0004-task-runtime-application-storage.md) only for the
runtime-owned-only deletion boundary. Its application
storage, task identity and acceptance decisions remain in force.

## Context and Problem Statement

Obsolete process outputs can accumulate while business work remains active.
ADR 0004 limited deletion to registered runtime artifacts, leaving legacy local
reports, caches and obsolete state outside that mechanism. Waiting for complete
business acceptance conflates retiring reviewed material with closing a task.

The user authorized scoped retirement with explicit file review and recoverable
operations. A Git ignore rule, filename or age cannot establish that a file is
disposable; current project documentation and learning deliverables may live in
the same directories as temporary process outputs.

## Considered Options

- Keep ADR 0004's runtime-owned-only cleanup boundary.
- Retire unreferenced runtime artifacts during active work and handle reviewed
  external process files through a separate explicit cleanup journal.

These are the previous boundary and the adopted extension, not a reconstructed
evaluation of undocumented alternatives.

## Decision Outcome

Use `task retire` for exact logical artifact names on an open task. It changes
the task revision without changing its state and protects user-preserved
artifacts and all result references, including withdrawn criteria.

Use `task process-cleanup` for explicitly reviewed legacy process files. The
packet records workspace, task and operation identity, actual user authorization,
review rationale, declared process roots and exact paths, hashes, categories
and archive/delete decisions. The operation accepts only Git-ignored, untracked
regular files in the declared scope; it rejects symlinks and `.git` paths and
does not recursively delete directories. Cleaner owns semantic review, live
reference checks and retention decisions; mechanical checks cannot replace them.

Keep this journal separate from SQLite task mutations. Archive copies are
verified before originals enter local quarantine. An unchanged packet recovers
an interrupted operation; abort restores an uncommitted operation. No
cross-filesystem atomic transaction is claimed. Current commands and packet
fields belong in the [Task Runtime guide](../TASK_RUNTIME.md).

### Consequences

- Authorized retirement can proceed during active work without claiming task
  completion or manufacturing user acceptance. Existing scoped authorization
  remains usable; unresolved material disposition requires user clarification.
- Current project docs, latest finalized subject surveys, required fixtures,
  retained files and irreplaceable evidence remain protected. Unknown ownership,
  pending delivery or live references require resolution before retirement.
- The separate journal does not alter SQLite task state. Consumers must inspect
  cleanup completion independently of task status and use the correct recovery
  or abort command for each store.
- Archives consume storage. There is no timer, TTL or automatic archive deletion;
  prior archives remain until separately authorized cleanup includes them.
- Task closeout still requires scoped acceptance and current evidence. This
  extension does not authorize worktree retirement or broad repository cleanup.

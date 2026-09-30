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
and archive/delete decisions. In workspace mode, the operation accepts only Git-ignored, untracked
regular files in the declared scope; it rejects symlinks and `.git` paths and
does not recursively delete directories. Cleaner owns semantic review, live
reference checks and retention decisions; mechanical checks cannot replace them.

Keep this journal separate from SQLite task mutations. Archive copies are
verified before originals enter local quarantine. An unchanged packet recovers
an interrupted operation; abort restores an uncommitted operation. No
cross-filesystem atomic transaction is claimed. Expose compact SQLite receipts and process-journal metadata through `task
history`, without another report or stored task-body history. Preserve unknown
legacy timestamps; distinguish cancelled intent, database commit and completed
physical cleanup. Task read/list expose one `recovery_pending` signal, and task
recovery resumes both stores while preserving each journal's original workspace.
Pending process journals block closeout and forget. Explicit forget removes
SQLite task audit, not the independently retained process journals.

Extend the same reviewed-file protocol to an explicit `storage: archives` mode
limited to the fixed application `archives/` root, exact relative targets and
delete-only dispositions. A supplied retained-copy claim must be byte-identical,
verified on disk and outside the same deletion set. This is not recursive
archive pruning or permission to edit archive members. Whole obsolete-task
cleanup may resolve internal references together; old report links do not create
permanent retention obligations for an otherwise authorized retiring set.

Current commands and packet fields belong in the [Task Runtime guide](../TASK_RUNTIME.md).

### Consequences

- Authorized retirement can proceed during active work without claiming task
  completion or manufacturing user acceptance. Existing scoped authorization
  remains usable; unresolved material disposition requires user clarification.
- Current project docs, latest finalized subject surveys, required fixtures,
  retained files and irreplaceable evidence remain protected. Unknown ownership,
  pending delivery or live references require resolution before retirement.
- The separate journal does not alter SQLite task state. Consumers must inspect
  cleanup completion through the unified summary/history and use the shared
  recovery entry or the correct store-specific abort command.
- Archives consume storage. There is no timer, TTL or automatic archive deletion;
  prior archives remain until separately authorized cleanup includes them.
- Task closeout still requires scoped acceptance and current evidence. This
  extension does not authorize worktree retirement or broad repository cleanup.

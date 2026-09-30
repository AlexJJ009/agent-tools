# Keep Task Runtime State in Local Application Storage

Date: 2026-09-30

Status: Accepted

Superseded by: [ADR 0005](0005-scoped-process-material-retirement.md) only for
the runtime-owned-only deletion boundary. Application
storage, task identity and scoped acceptance decisions remain in force.

Supersedes: [ADR 0001](0001-local-development-records.md) only for Task Runtime's
authoritative state and managed artifacts. Its rules for other private local
records and maintained system documentation remain in force.

## Context and Problem Statement

ADR 0001 kept development records under ignored worktree-local paths and
deliberately avoided another progress database. Task Runtime now provides a
task identity independent of a conversation or working directory, with current
requirements, criterion results and scoped user feedback. These records must
survive replacement of the runtime installation and an explicit workspace
rebind without creating competing writable copies in each project.

Task-owned process files also need explicit ownership and retention decisions.
A filename, passing test or ended conversation does not establish permission
to delete a file or evidence of user acceptance.

## Considered Options

- The worktree-local record arrangement adopted in ADR 0001.
- The application-data store implemented by Task Runtime, with explicit import
  of selected legacy records.

These describe the previous and current adopted arrangements. This record does
not reconstruct an undocumented evaluation of other storage technologies.

## Decision Outcome

Keep one authoritative Task Runtime record in a configured local application
data root, separate from installed software and project checkouts. SQLite holds
task state and operation metadata; runtime-assigned paths hold registered
artifacts. The [Task Runtime guide](../TASK_RUNTIME.md) owns the current path
precedence, command packets and recovery procedures.

Use stable task and criterion IDs, revision checks and idempotent operation
requests to continue work across conversations. Keep observed verification,
its validity for current inputs and scoped user acceptance distinct. The Agent
supplies semantic requirements and reports external checks; storing a report
does not prove that the runtime executed or evaluated the check.

Closeout requires explicit scoped user acceptance, current evidence and a
reviewed disposition for every registered artifact. Finish project edits,
verification and applicable feedback recording before closeout. File publication
and cleanup use recoverable operations because the database and filesystem do
not share a transaction. Only runtime-owned paths enter its deletion set;
project documents, unknown files and worktrees remain outside that set.

Existing explicit legacy records remain usable. Import is deliberate, assigns
a new runtime task ID and starts with unverified criteria and pending
acceptance. Installation and ordinary startup do not migrate or delete those
records. Avoid concurrent writable authorities for the same task.

### Consequences

- Tasks can continue across conversations on one machine without treating a
  branch name, chat ID or current directory as their identity. This does not
  synchronize task state between machines.
- The application data root needs its own retention and backup decisions;
  replacing software or checking out Git does not restore that data.
- Closeout can discard full task content by default while retaining a small
  closed-task record and explicitly kept artifacts. Reopening requires explicit
  full-task retention; keeping one report alone is insufficient.
- Interrupted file operations require recovery or an applicable abort. A
  committed database record does not by itself establish completed cleanup.
- SQLite schema compatibility, platform support and installation evidence
  remain bounded by the current implementation and guide. This decision does
  not establish plugin packaging, native Hook execution or another host's
  installation readiness.
- Private development material outside Task Runtime still uses the ignored
  local paths from ADR 0001. Shared documentation continues to describe current
  usage and architectural rationale rather than private progress snapshots.

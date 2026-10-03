# Record Written Materials in One Application Ledger

Date: 2026-10-03

Status: Accepted

Applies to Task Runtime, work-report and learning-workflow. Extends the
process-material retirement boundary in
[ADR 0004](0004-task-runtime-application-storage.md); it does not supersede it.

## Context and Problem Statement

Cleaner cannot clean what nobody recorded. Runtimes wrote report batches,
pending prompts, route records, task artifacts and cleanup journals, but none
of them registered those paths. `task location` printed only the data root and
`process-cleanup` required exact paths and hashes without discovery. Cleaner
had to hunt through `docs/_local/` and the data root, and could not tell which
files agent-tools or its agents produced, so leftovers accumulated. How should
Cleaner obtain an explicit, complete list of cleanable objects without becoming
more aggressive about deletion?

## Considered Options

* Tell Cleaner to search known directories more thoroughly.
* Add a per-workspace index file under `docs/_local/`.
* Each runtime appends what it writes to one append-only ledger in the
  application data root, with an inventory query and an agent registration
  command.

## Decision Outcome

Chosen option: "one append-only ledger in the application data root", because
it makes cleanable objects explicit at the moment they are written, survives
workspace moves and reinstalls like other task state, and needs no new writable
index inside projects. A stricter search instruction still leaves Cleaner
guessing ownership; a workspace index cannot cover the data root or files that
belong to several workspaces and would be another local document to maintain.

The ledger is `<data-root>/materials/ledger.jsonl`, resolved exactly like the
task database. One standard-library module (`shared/materials.py`) appends
entries under a file lock; each installed component carries a byte-identical
copy. Recording failures are reported on stderr and never break the producer.
`agent-workflow materials list` reports recorded paths with existence and size
plus unrecorded files under known material roots; `materials record` lets an
agent register files it wrote elsewhere. `materials cleanup-packet` turns
reviewed inventory paths into a `process-cleanup` packet, which can retire a
recorded directory as a unit by tree digest. Completed removals append
`removed` events.

### Consequences

* Good, because "where are this task's files" and "what can Cleaner review"
  have one answer, and unrecorded leftovers under known roots become visible.
* Good, because large experiment directories can be retired as one reviewed
  unit without listing every file in the packet.
* Good, because recorded paths, unregistered files in a task's artifact
  directory and the manage-worktrees artifact base can be retired outside the
  workspace; the ledger entry or known root is the scope evidence.
* Bad, because files written by agents outside the runtimes appear only if the
  agent registers them or they fall under a known root.
* Bad, because the ledger only grows; there is no compaction yet.
* Neutral: the ledger is not authority to delete and nothing is deleted
  automatically. Review, user authorization, Git checks (ignored/untracked in
  the workspace, untracked elsewhere) and journaled recovery from ADR 0004
  still apply. The directory tree digest
  covers paths, types, sizes and modification times, not file bytes.

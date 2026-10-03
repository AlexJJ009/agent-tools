# Process-cleanup mechanics

Runtime details for retiring reviewed process materials outside the task
artifact store. [SKILL.md](../SKILL.md) owns the review and authorization rules;
`docs/TASK_RUNTIME.md` owns packet fields.

- `task process-cleanup --input PATH` takes the packet defined in the Task
  Runtime guide: explicit workspace, task/operation identity, actual authorization
  quote/source, reviewed process roots and exact file paths, hashes, categories
  and `archive`/`delete` dispositions. Keep protected material out of the packet.
  `agent-workflow materials cleanup-packet --task ID --operation-id OP --path ABS
  ... --rationale ... --quote ... --source-ref ...` computes those digests from
  the reviewed inventory paths; the cleanup run verifies them again.
  Workspace mode accepts only ignored, untracked regular files, or a directory
  entry (`kind: "dir"`, `delete` only) identified by `tree_digest`, a metadata
  identity (paths, inodes, ctimes, types, sizes, mtimes), not a content hash. It
  does not decide whether content is obsolete. Completed removals are appended to the material ledger.
- Inventory paths outside the workspace (unregistered files under the task's
  `<data-root>/artifacts/<task-id>/`, the `<repo-parent>/_artifacts/<repo>/`
  worktree artifact base, or ledger-recorded paths) get an `external` packet
  with absolute paths; the guide lists what is refused.
- This separate cleanup journal does not close or revise the SQLite task.
  Recover through `task recover --task TASK_ID` or by replaying the unchanged
  packet; journals retain their original workspace after task rebind. Inspect with
  `task process-cleanup-status --task TASK_ID --operation OP`. Before commit,
  `task process-cleanup-abort --task TASK_ID --operation OP` restores quarantine.
  Do not use the SQLite operation's `task abort` for this journal.
- For explicitly authorized duplicates under the fixed `<data-root>/archives/`
  root, use `storage: "archives"` with exact relative `process_roots` and
  `files[].path`, and `delete` only. This does not authorize ordinary workspace
  deletion, journal deletion or changes inside tar files.
  If relying on a retained identical copy, record per-file
  `retained_copy: {path: absolute_path, sha256: target_hash}`; the runtime checks
  its bytes and excludes copies in the same deletion/quarantine set.
- Archive copies are hash-verified before originals enter local quarantine.
  Cross-filesystem work is recoverable, not one atomic move. Check the returned
  state before reporting completion. There is no timer, TTL or automatic archive
  deletion: archives still occupy storage and must not be described as no
  accumulation. Do not retire old archives without separately authorized scope.

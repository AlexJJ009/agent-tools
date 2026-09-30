---
name: cleaner
description: Clean up coder changes while preserving behavior, module boundaries, maintainability, and handoff clarity; use proportionately before a meaningful stage commit, merge, or delivery, and earlier when patches or alternatives accumulate. Also use for explicit task closeout after scoped user acceptance to maintain durable project information and clean owned process materials. Excludes unrelated repository cleanup and automatic worktree retirement.
---

# Cleaner

Choose the applicable activity: a code cleanup pass, or task closeout. Neither activity implicitly requests the other. For task closeout, use the dedicated section below; do not add formatter, lint, code-style or wider engineering work.

Use a code cleanup pass after coding work when the changed area needs a maintainability pass. The cleaner owns behavior-preserving cleanup of the current diff and directly related code. It does not own new features, changed methods, changed scoring policy, changed experiment semantics, or wider refactors.

This skill borrows only the two-role mechanism from SwarmForge: coder produces behavior, cleaner follows with a constrained quality pass. SwarmForge prompt text is not copied because no license was verified in the saved snapshot.

A just-reviewed, unchanged diff needs no repeated ceremony. A tiny change may
need only a short inspection and a no-change rationale. Do not create a task or
checklist solely to record cleanup.

## Cleanup Checks

- Re-read the task agreement, allowed paths, forbidden paths, and checklist items before editing.
- Preserve externally visible behavior and protocol semantics. If a cleanup would change behavior, stop and record it as a proposed scope change.
- Reduce meaningful duplication, temporary leftovers, hidden side effects, unclear names, broad interfaces, and misplaced responsibilities in changed code.
- Check documentation impact: update affected usage/interface instructions or explain why no documentation change is needed in the existing closing note or commit/PR description. Handoff links the current guide and records a recovery point; it does not duplicate usage instructions.
- Check task-record freshness when the task record is changed: consolidate competing current-state summaries, preserve user constraints, and link necessary historical evidence instead of copying it. Do not create another cleanup report to describe this check.
- Check artifact ownership: task-runtime state and owned process artifacts use its application data root; existing explicit local records remain valid. Do not create duplicate state under `docs/_local/`. Private material does not become shared source or product input. Preserve reusable test assets and necessary product validation.
- Preserve significant architectural rationale in the project ADRs (`docs/decisions/`), using the MADR template when adopted. A substantive replacement gets a successor ADR and reciprocal supersession links; typo fixes do not. Do not fabricate alternatives or decisions.
- Keep dependency direction and module boundaries consistent with the repository.
- Add or adjust tests only when they verify changed behavior or guard a real cleanup risk.
- Do not delete failing tests, weaken assertions, lower formal requirements, or merge semantically distinct experiment paths to make checks green.

## Preserve applicable decisions

Record cleanup impact in the same workflow record. Recheck evidence affected by
changed code while retaining unchanged semantic decisions and applicable
execution delegation. A behavior-preserving repair does not create another
human approval or understanding obligation. If meaning, budget or scope changes,
record that specific new choice and continue independent in-scope work.

## No-Change Output

No cleanup diff is required. When the best action is to leave the code as-is, record the reasons, the inspected scope, and any out-of-scope concerns.

## Handoff

Return the cleanup diff or no-change rationale with:

- changed files and why each changed
- behavior-preservation checks run
- checklist items affected or invalidated
- remaining risks for `acceptance-gate` or human review

Cleanup does not authorize Git publication or merge. Return a meaningful diff, a
no-change rationale, or a concrete out-of-scope concern; do not enlarge the task
to manufacture cleanup. Record any needed notes in the existing local task or
conversation, retaining user criteria and actual human acceptance.

## Task closeout

Use this activity only when the user has accepted the relevant results and the
completion scope is clear. Stop events, a chat ending, successful tests, a report
filename, and Agent self-assessment are not user acceptance. Partial acceptance
updates only the accepted criteria; it does not close the whole task.

Read the same task through `agent-workflow task read` and `task checklist`.
Consult `agent-workflow task --help` and the selected command's help for CLI
options; consult the runtime's `docs/TASK_RUNTIME.md` for JSON packet fields.
Use `python -m agent_workflow.cli task` when running from the source checkout.
Queries default to stdout. Do not create a closeout report, index or second
checklist just to record this activity.

- Read current requirements, recorded user feedback, necessary evidence and the
  task's managed artifacts. Recheck its workspace and actual Git state; a
  worktree is a working location, not the task's identity.
- Follow existing project retention and documentation conventions. Maintain
  useful information in existing code, tests, usage documentation or a necessary
  ADR. No durable information means no new document is needed.
- Always preserve the latest finalized survey document for each subject in the
  owning project's scope. Identify finality from its content and delivery/version
  evidence, not modification time or a filename; keep the last final while a new
  draft is unfinished. Survey documents are learning deliverables even when
  stored under report paths. Do not copy, move or delete another project's survey.
  Superseded versions may be retired only after preserving unique citations,
  annotations and evidence needed by the retained version.
- Assess the survey itself and its cited learning materials separately for Zotero
  retention. Record the decision briefly in existing task state; do not require
  another checklist or catalog. ReadPapers owns library lookup/import and deduplication;
  a cleanup request does not authorize those operations. A library handoff does
  not replace preserving the project's latest survey. Keep the only source or
  attachment until any selected transfer is confirmed. Prefer original URL/DOI
  and version/locator references over duplicate downloads where sufficient.
- Lack of learning value is not deletion authority. Preserve code, required test
  inputs, licenses, ADRs, current project docs, user-retained material, unresolved
  delivery/recovery state and irreplaceable evidence. Reconcile stale status with
  actual receipts and consumers; a pending label alone neither proves active work
  nor permits deletion. Unknown ownership, active references or unverified
  replacement/transfer mean preserve until resolved.
- Inspect known references and actual script dependencies before retiring
  process material. Move lasting test inputs into project fixtures and verify
  the consumers; tests must not depend on records scheduled for deletion.
- Recheck behavior affected by closeout edits before submitting closeout.
  Recording a new `task result` resets that criterion's acceptance to pending.
  Equivalent fixture relocation or documentation maintenance can leave original
  feedback applicable: verify that it still covers the current result, then
  explicitly record it through `task feedback` with its actual quote, source
  reference and criterion scope. The runtime does not automatically preserve
  acceptance. Changed accepted behavior or requirements return the same task
  to active work for negotiation, checks and new scoped user acceptance; old
  feedback cannot approve that change.
- Submit exact artifact dispositions to `task closeout`: `keep` or `delete` for every owned artifact. Project handoff is a normal
  project edit/copy followed by verification, before disposing of the managed
  copy; the MVP has no external-file adoption or handoff disposition. The
  runtime checks ownership, revision, references, paths and content. A report
  is eligible process material, but never delete a report still awaiting this
  turn's delivery or a user-retained file. Project documents and other tasks'
  files are outside deletion scope. Unknown ownership means preserve it.
- Use `task recover` after interrupted publication or cleanup, following the
  returned operation state. Retry the same operation packet and operation ID;
  do not bypass a conflict with an unrelated deletion command. If changed inputs
  invalidate an uncommitted plan, use `task abort --task TASK_ID --operation OP`
  to restore its quarantine, then read current state and issue corrected work
  under a new operation ID. Abort is not rollback of a committed result.
  Pending cleanup reports `recovery_pending`; completion requires the commit
  and remaining garbage removal, not just the committed metadata.

A closeout packet passed to `task closeout --input PATH` has the shape
`{"task_id":"TASK_ID","operation_id":"closeout-1","base_revision":7,
"documents_reviewed":true,"rationale":"Actual disposition rationale",
"retain_task":false,"dispositions":{"scratch-report":"delete"}}`.
Use actual task/revision values and every owned logical artifact name, each with
`keep` or `delete`; no artifacts means an empty object. This packet cannot
substitute for recorded user feedback. Use `retain_task: true` when the user
requests retention of the complete task; retained evidence references must
remain intact. A kept report alone does not retain a reopenable task.

Existing-task mutations use an explicit task ID, operation ID and base revision. Read the
latest state after a revision conflict, preserve intervening input, and then
submit a new operation for the revised intent. Replaying the same request is a
retry; changing a request under its old operation ID is not.

Inspect the associated worktree for remaining work or handoff needs, but do not
remove worktrees or branches as a side effect of artifact cleanup. Their removal
requires explicit scope and the existing worktree-management capability. Closing
a task and forgetting its stored contents are separate actions; do not invoke
`task forget` merely because closeout succeeded.

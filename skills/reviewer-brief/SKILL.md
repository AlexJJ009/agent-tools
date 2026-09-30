---
name: reviewer-brief
description: Prepare bounded independent reviewer input and human review briefs with acceptance criteria, evidence anchors, diff focus, review scope, and known limits.
---

# Reviewer Brief

Use this skill when a human or independent reviewer needs a bounded review target. The goal is to make review possible, not to ask someone to inspect the whole repository.

Use the existing task, PR description or conversation for review navigation; create a separate brief file only when requested or required by an existing review agreement. Give an independent reviewer a bounded prompt with the applicable requirements, evidence and diff anchors. A review brief does not require a new task or checklist.

Read the packaged [shared writing contract](references/writing-contract.md). Reuse its expression discipline and local path:line link convention: every important claim should connect requirement, current observation, evidence link, and consequence. This is evidence-presentation reuse only. Do not run Work Report Judge as acceptance, duplicate Work Report state, or treat Work Report PASS as code review, human approval, or formal-run authorization.

## Reuse the current state

For a selected current task, read `agent-workflow task read` and `task checklist` as needed; use its task ID, revision and actual result evidence. Without a task record, use the user request, current code/diff and checks already run. For an explicitly selected legacy record, read its existing workflow revision and actual observations. Do not create both storage models for review.
Use the existing choice explanation, sources, scoped feedback and pending items;
do not create a second acceptance ledger. A report already containing the
necessary explanation can be cited directly. A short brief only expands the
current decision or acceptance step and does not trigger full report structure
or the report Judge. Independent code review remains a different reader task.

Explain the viable options, selected or proposed option, why the evidence favors
it and what each outcome permits or delays. A state word such as checked is not
an observation. Put decisive failures in the brief, not only in linked logs.
An ordinary reader should be able to restate the choice, its reason and the next
action without the main chat. Use precise domain terms only when their mechanism
or relationship is explicit.

## Human Brief Contents

When a separate human brief is requested, reuse its established location; a legacy record may use `reviews/human-review.md`. Include only applicable fields:

- task ID, candidate SHA, base SHA, and dirty-worktree note
- each `must_review` item with the protected requirement and why it matters
- exact file anchors or diff hunks when available
- current observation, evidence path, and unresolved limits
- recommended decision and concrete consequence
- items that are context only

Do not ask the user to review all code. On a current task, record actual scoped acceptance through `task feedback`; reviewer approval is not user acceptance. Only an existing legacy record uses `human_status=confirmed` and `approve --feedback <human-feedback.json>` bound to its current `agent-workflow target` digest. Never create that legacy record just to prepare a brief.

## Independent Reviewer Prompt

Give the reviewer a read-only scope:

- what changed
- original requirement or task agreement
- selected task ID/revision or existing legacy record path, when applicable
- base SHA and candidate SHA or diff path
- commands already run and their evidence
- explicit out-of-scope areas

The reviewer may report findings; they must not mutate the working tree, approve production, merge, publish, or rewrite the user's requirements.

This skill adapts MIT-licensed review/verification structure from the saved Superpowers snapshot and requirement-quality shape from the saved spec-kit snapshot. See [references/third-party-attribution.md](references/third-party-attribution.md).

---
name: reviewer-brief
description: Prepare bounded independent reviewer input and human review briefs with acceptance criteria, evidence anchors, diff focus, review scope, and known limits.
---

# Reviewer Brief

Use this skill when a human or independent reviewer needs a bounded review target. The goal is to make review possible, not to ask someone to inspect the whole repository.

Use `reviews/human-review.md` for the user's review navigation. Use a separate independent reviewer prompt for agent review. Both can cite the same protocol, checklist, evidence, and diff anchors, but neither substitutes for the other.

Reuse Work Report's expression discipline and local path:line link convention: every important claim should connect requirement, current observation, evidence link, and consequence. This is evidence-presentation reuse only. Do not run Work Report Judge as acceptance, duplicate Work Report state, or treat Work Report PASS as code review, human approval, or formal-run authorization.

## Human Brief Contents

Create `reviews/human-review.md` only when human review is needed. Include:

- task ID, candidate SHA, base SHA, and dirty-worktree note
- each `must_review` item with the protected requirement and why it matters
- exact file anchors or diff hunks when available
- current observation, evidence path, and unresolved limits
- recommended decision and concrete consequence
- items that are context only

Do not ask the user to review all code. Do not record `human_status=confirmed` unless the user actually confirms the current object and the caller provides `approve --feedback <human-feedback.json>` bound to the current `agent-workflow target` digest.

## Independent Reviewer Prompt

Give the reviewer a read-only scope:

- what changed
- original requirement or task agreement
- record directory and checklist path
- base SHA and candidate SHA or diff path
- commands already run and their evidence
- explicit out-of-scope areas

The reviewer may report findings; they must not mutate the working tree, approve production, merge, publish, or rewrite the user's requirements.

This skill adapts MIT-licensed review/verification structure from the saved Superpowers snapshot and requirement-quality shape from the saved spec-kit snapshot. See [references/third-party-attribution.md](references/third-party-attribution.md).

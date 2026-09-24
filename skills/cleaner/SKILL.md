---
name: cleaner
description: Clean up coder changes while preserving behavior, module boundaries, maintainability, and handoff clarity; use after implementation or before review when diff quality matters.
---

# Cleaner

Use this skill after coding work when the changed area needs a maintainability pass. The cleaner owns behavior-preserving cleanup of the current diff and directly related code. It does not own new features, changed methods, changed scoring policy, changed experiment semantics, or wider refactors.

This skill borrows only the two-role mechanism from SwarmForge: coder produces behavior, cleaner follows with a constrained quality pass. SwarmForge prompt text is not copied because no license was verified in the saved snapshot.

## Cleanup Checks

- Re-read the task agreement, allowed paths, forbidden paths, and checklist items before editing.
- Preserve externally visible behavior and protocol semantics. If a cleanup would change behavior, stop and record it as a proposed scope change.
- Reduce meaningful duplication, temporary leftovers, hidden side effects, unclear names, broad interfaces, and misplaced responsibilities in changed code.
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

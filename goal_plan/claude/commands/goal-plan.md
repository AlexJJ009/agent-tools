---
description: Prepare a reviewed long-horizon goal plan and launch prompt without taking over /goal execution.
argument-hint: Objective or existing plan path
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Task", "TodoWrite", "Skill"]
---

# /goal-plan

Use this command to create or harden a goal plan before a long-running executor takes over.
It is intentionally separate from `/goal`: `/goal` is the loop/executor, while `/goal-plan`
is the planning, adversarial review, and acceptance-gate setup.

**FIRST:** Load the `goal-plan` skill with the `Skill` tool, then follow its lifecycle.

## Input

`$ARGUMENTS` may be a rough objective, a branch/worktree instruction, or an existing plan path.

## Boundaries

- Do not redirect, wrap, or replace `/goal`.
- Do not start a loop merely because this command was invoked.
- If the user explicitly asks to execute after planning, execute under the skill lifecycle.
- Otherwise, stop after producing the reviewed plan and launch prompt.

## Workflow

1. Author or update a plan file with numbered Given/When/Then ACs, hard-ordered milestones,
   test/build commands, mock-only verification, and stop-and-ask triggers.
2. Use `Task` with `subagent_type: "goal-plan-reviewer"` in `PLAN REVIEW` mode before
   implementation. Do not implement against a `NOT-READY` plan.
3. Fix the plan first when the reviewer finds P0 contradictions, unverifiable ACs, or
   missing acceptance criteria.
4. Assemble the final goal prompt with objective, single source of truth, execution order,
   global conventions, intervention triggers, and Definition of Done.
5. If implementation is in scope, use `TodoWrite`, proceed milestone by milestone, mock all
   external services, commit each independently verifiable unit, and never self-certify.
6. Finish with `Task` using `goal-plan-reviewer` in `ACCEPTANCE` mode. `ACCEPTED` requires
   reviewer-owned command output for every required AC.

## Output

Return:

- Plan path
- Reviewer PLAN REVIEW verdict
- Any fixes applied to the plan
- Launch prompt or execution status
- Final acceptance status, if implementation ran

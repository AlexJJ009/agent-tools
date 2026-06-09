---
description: Prepare a reviewed Codex Go or CLI goal plan without automatically starting the goal executor.
---

# /goal-plan

Use this command to prepare a long-horizon goal plan, adversarial review gate, and launch
prompt for Codex App Go or Codex CLI work.

## Boundary

- This command prepares a goal; it does not automatically create or start a Codex Go goal.
- Only call `create_goal` when the user explicitly asks to create/start a Codex Goal or Go run.
- If the user asks only for a plan, stop after the reviewed plan and launch prompt.

## Workflow

1. Load the `$goal-plan` skill.
2. Author or update a plan with numbered Given/When/Then ACs and hard-ordered milestones.
3. Verify every AC is sandbox-checkable by unit tests, build checks, grep checks, or local mock HTTP.
4. Run an independent reviewer pass when sub-agent tools are available and the request authorizes
   reviewer/subagent use. Otherwise produce the reviewer prompt and mark acceptance as pending.
5. Assemble the launch prompt for Codex Go or CLI execution.
6. If execution is explicitly requested, create/start the goal only after the plan review gate is ready.
7. Final acceptance requires an independent reviewer-owned test/build run with exact command output.

## Output

- Plan path or generated plan text
- Review verdict
- Launch prompt
- Whether a Codex Go goal was created, skipped, or left pending

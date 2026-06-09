---
name: goal-plan
description: Prepare and gate long-horizon Codex goals before execution. Use when the user explicitly invokes $goal-plan or /goal-plan, asks to prepare or review a goal plan, wants a Codex App Go or Codex CLI launch prompt, or needs independent acceptance for a long-running task. Do not automatically create a Codex Goal or Go run unless the user explicitly asks to create or start one.
---

# Goal Plan

Use this skill to turn a rough long-running task into a reviewed, verifiable plan and a
launch prompt for Codex App Go or Codex CLI. Keep planning separate from execution:
planning prepares the goal; Codex Go or a CLI session executes it only when the user asks.

Core principle: the implementer never grades its own work. Generation and verification
must be split. If sub-agent tools are available and the user request authorizes reviewer
or subagent use, spawn an independent reviewer. If they are unavailable or not authorized,
produce the reviewer prompt and mark acceptance as `PENDING REVIEW`, never `ACCEPTED`.

## Lifecycle

1. Author Plan
2. Adversarial Review
3. Assemble Goal Prompt
4. Execute, only if explicitly requested
5. Independent Acceptance

## Phase 1: Author Plan

Create or update a plan file when working in a repo. The plan is goal-ready only when it has:

- Numbered acceptance criteria, each in Given/When/Then form.
- A single source of truth. If reality forces a change, update the plan before code.
- Hard-ordered milestones when one milestone produces an artifact another consumes.
- Sandbox-verifiable ACs: unit test, build check, grep check, local mock HTTP, filesystem
  semantics, or in-memory fake. Rewrite real service/account/network ACs into mock form.
- Exact verification commands and expected evidence for every required AC.

## Phase 2: Adversarial Review

Before implementation, run a skeptical review pass. With Codex sub-agent tools, use a
fresh reviewer agent when the user's request authorizes subagents/reviewer work. Ask for:

- AC self-verifiability table: PASS, NEEDS SCAFFOLDING, or EXTERNAL.
- P0 plan versus code contradictions with file and line evidence.
- Missing or under-defined ACs in Given/When/Then form.
- Decomposition decision: one goal or serial sub-goals.
- Preflight checklist: test runner, mocks, fixtures, build fallback, branch/commit rules.

Do not implement against a `NOT READY` plan. Fix the plan first, then re-review.

## Phase 3: Assemble Goal Prompt

The launch prompt must include:

- Objective: one goal and what done delivers.
- Single source of truth: plan path and AC numbers.
- Execution order: milestone order, produced artifacts, and no reordering.
- Global conventions: test command, mock strategy, build check, branch and commits.
- Stop-and-ask triggers: stuck loop, contradiction, under-defined AC, forced real service,
  missing upstream artifact.
- Definition of Done: all ACs green, no real external service contact, per-unit commits,
  and independent reviewer acceptance.

Only call `create_goal` when the user explicitly asks to create/start a Codex Goal or Go run.
If you call it, the objective must reference the plan path and require the independent
acceptance gate. Do not create a goal merely because `$goal-plan` was invoked.

## Phase 4: Execute

Execute only when explicitly requested. During execution:

- Track milestones with Codex task planning tools.
- Proceed serially; do not advance until the current milestone's required ACs are green.
- Mock every external service, account, OAuth path, rate limit, and network signal.
- Commit each independently verifiable unit when working in a git repo.
- Stop and ask on contradictions or repeated failure instead of weakening the AC.
- Never delete, skip, loosen, or trivialize tests to get green.

## Phase 5: Independent Acceptance

The implementer must not self-certify. The reviewer must:

- Run the suite/build/check commands itself.
- Report every AC as PASS, FAIL, or WEAKENED.
- Include exact command lines and relevant output snippets.
- Audit for skipped, deleted, loosened, or trivial tests.
- Confirm no real external service was used as acceptance evidence.

`ACCEPTED` is valid only when every required AC is PASS from reviewer-owned command output
and no AC is weakened or uncovered. If the reviewer cannot run the commands, the result is
`REJECTED` or `PENDING REVIEW`, not accepted by reasoning.

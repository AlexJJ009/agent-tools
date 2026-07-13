---
name: goal-plan
description: Prepare, review, and govern long-horizon Codex or Claude goals with a frozen outcome contract, isolated append-only runtime ledgers, lifecycle validators, reviewer prompt templates, and independent acceptance. Use when the user invokes $goal-plan or /goal-plan, asks to prepare or revise a goal plan, needs a launch prompt, wants runtime supervision of implementer/reviewer behavior, or needs independent acceptance. Do not create or start a Goal unless the user explicitly asks.
---

# Goal Plan

Turn a long-running task into one independently verifiable outcome and keep that outcome stable through implementation and acceptance. The skill establishes the protocol and tools; the generated Goal artifacts and validators govern runtime behavior. Do not keep reloading the full skill during ordinary implementation.

## Runtime Prerequisite

Use the installed `goal-plan-runtime` launcher. It runs from the skill's isolated uv environment and does not depend on the target project's language, Python version, or virtual environment.

If the launcher is missing, rerun the agent-tools installer. Do not install dependencies into the target project to make this skill work.

## Goal Directory

Create one directory per Goal under the repository's appropriate documentation area, for example:

```text
docs/goals/<goal-id>/
├── plan.md
├── runtime.jsonl
├── findings.jsonl
├── acceptance.md
└── reviews/
```

Use the repository's existing goal/plan location when one is already established, but keep each Goal's artifacts inside its own subdirectory.

Initialize with:

```bash
goal-plan-runtime init <goal-dir> --title "<goal title>" --actor "<implementer identity>"
```

`runtime.jsonl` and `findings.jsonl` are append-only audit ledgers. Correct mistakes by appending correction events; never rewrite prior lines. `acceptance.md` is completed only by the independent final reviewer.

## Lifecycle

1. Author the Plan.
2. Validate the Plan.
3. Obtain an independent Plan Review.
4. Assemble the launch prompt.
5. Execute the authorized milestone, only when explicitly requested.
6. Classify findings and validate runtime transitions.
7. Obtain milestone review when required.
8. Obtain independent final acceptance.

The protocol applies throughout the Goal lifecycle, but reinvoke the skill only at lifecycle boundaries: initial planning, Plan amendment, reviewer prompt construction, convergence review, and final acceptance.

## Author the Plan

Keep one outcome: state in one sentence which new capability, artifact, or decision the user receives. If the sentence contains multiple independently useful outcomes, split them into serial Goals.

The Plan must contain:

- included and excluded scope;
- numbered Given/When/Then acceptance criteria;
- exact verification commands and expected evidence;
- hard-ordered milestones when artifacts have producer-consumer dependencies;
- a Runtime Contract;
- a Goal-specific Reviewer Contract;
- deferred follow-ups that must not expand the current Goal.

Validate it:

```bash
goal-plan-runtime validate-plan <goal-dir>
```

Do not implement against an invalid or unreviewed Plan.

## Plan Review

Use a fresh independent reviewer when authorized and available. The reviewer checks:

- whether the Plan has one outcome or should be split;
- whether each AC is sandbox-verifiable;
- plan/code contradictions with file and line evidence;
- milestone ordering and required scaffolding;
- whether the verification environment is reproducible.

The verdict is `READY` or `NOT_READY`. Append the verdict to `runtime.jsonl` and bind it to the current Plan version. `NOT_READY` stops implementation.

## Finding Classification

Classify every new finding before acting:

- `IN_SCOPE`: an existing AC requires the fix; fix it without adding an AC.
- `DEFERRED`: useful but unnecessary for the current outcome; record it and do not implement it.
- `CONTRADICTION`: the frozen Plan cannot be implemented or verified consistently; stop and amend the Plan.
- `AC_CHANGE`: the definition of done would change; stop and obtain a fresh Plan review.

A reviewer observation does not automatically become scope.

Append finding lifecycle events with:

```bash
goal-plan-runtime append-event <goal-dir> FINDING_OPENED \
  --ledger findings --data '{"finding_id":"F-01","summary":"...","source":"review:R-01"}'
```

## Convergence Rule

If two related implementation-review rounds leave the same finding open, stop before a third. Determine whether the loop is caused by:

1. duplicated sources of truth;
2. experiment-specific policy in a shared layer;
3. reviewer scope expansion;
4. more than one independently useful outcome.

Classify the result as an in-scope architectural fix, deferred work, or a split Goal. The runtime validator rejects a third ordinary fix round.

## Runtime Validation

Run:

```bash
goal-plan-runtime validate-runtime <goal-dir>
```

Run it:

- before implementation starts;
- after Plan review or amendment;
- after classifying a reviewer finding;
- before changing milestones;
- before requesting acceptance;
- before declaring completion.

A non-zero result is a stop condition. Report the failed invariant instead of routing around, weakening, or deleting the validator.

## Reviewer Prompts

Do not hard-code a complete reviewer prompt inside each Plan. Use three layers:

1. the skill's stable reviewer template;
2. the Goal-specific Reviewer Contract in `plan.md`;
3. runtime-specific context and additional focus.

Build a prompt instance with:

```bash
goal-plan-runtime build-reviewer-prompt <goal-dir> \
  --review-type "Milestone Review" \
  --base-commit <base> \
  --candidate-commit <candidate> \
  --applicable-acs "AC-02, AC-03" \
  --verification-commands "<commands>" \
  --focus "<task-specific focus>" \
  --output <goal-dir>/reviews/<review-id>-prompt.md
```

Task-specific focus may add questions but must not remove frozen ACs, weaken evidence requirements, instruct the reviewer to implement, or imply the expected verdict.

The reviewer may add opinions. Opinions outside frozen ACs are non-blocking `DEFERRED_SUGGESTION`s. If the completion definition must change, return `CONTRACT_CONTRADICTION`; the reviewer must not amend the Plan.

## Execution

Execute only when the user explicitly requests it and the current Plan is `READY`.

- Proceed serially through authorized milestones.
- Mock external services used as acceptance evidence.
- Preserve existing user changes.
- Never delete, skip, loosen, or trivialize tests to get green.
- Stop on contradiction, AC change, invalid runtime transition, or required convergence review.
- Treat another independently useful deliverable, subsystem, runtime environment, or acceptance surface as a re-planning trigger rather than relying on fixed line, file, token, or time budgets.

## Independent Acceptance

The implementer must not self-certify. The final reviewer must:

- run required verification commands itself;
- report every applicable AC as `PASS`, `FAIL`, or `WEAKENED`;
- include exact command lines and relevant output;
- audit skipped, deleted, loosened, or trivial tests;
- confirm external services were not used as substitute evidence;
- bind the report to the current Plan version and candidate commit.

`ACCEPTED` is valid only when every required AC is `PASS` from reviewer-owned evidence. Otherwise use `REJECTED` or `PENDING REVIEW`. Complete `acceptance.md`, append the acceptance event, validate runtime, and only then mark the Goal complete.

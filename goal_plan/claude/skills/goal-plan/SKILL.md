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
2. Probe feasibility of every numeric budget in the target environment.
3. Validate the Plan.
4. Obtain an independent Plan Review.
5. Assemble the launch prompt, including the standing `AUTO_ADVANCE` authorization.
6. Execute the authorized milestones, auto-advancing deterministic steps and stopping only at `USER_DECISION` gates.
7. Classify findings and validate runtime transitions.
8. Obtain milestone review when required.
9. Obtain independent final acceptance.

The protocol applies throughout the Goal lifecycle, but reinvoke the skill only at lifecycle boundaries: initial planning, Plan amendment, reviewer prompt construction, convergence review, and final acceptance.

## Author the Plan

Keep one outcome: state in one sentence which new capability, artifact, or decision the user receives. If the sentence contains multiple independently useful outcomes, split them into serial Goals.

The Plan must contain:

- included and excluded scope;
- numbered Given/When/Then acceptance criteria;
- exact verification commands and expected evidence;
- feasibility probes backing every numeric budget;
- hard-ordered milestones when artifacts have producer-consumer dependencies;
- a Runtime Contract;
- a Progression Policy;
- a Goal-specific Reviewer Contract;
- deferred follow-ups that must not expand the current Goal.

Validate it:

```bash
goal-plan-runtime validate-plan <goal-dir>
```

Do not implement against an invalid or unreviewed Plan.

## Feasibility Probes

Freeze numeric budgets only after measuring reality. Any AC that declares an absolute numeric performance or resource budget (latency, throughput, memory, disk) must be backed by a feasibility probe before Plan review can return `READY`:

- measure the floor in the target verification environment with the cheapest honest command — for example, the raw Redis round-trip before promising an end-to-end latency budget, or actual free disk before freezing a disk gate;
- record the probe command, raw measurement, environment, and the derived budget with an explicit margin in the Plan's `Feasibility Probes` section, referencing the AC id;
- a budget below a measured hard floor is a Plan defect to fix now, not an implementation challenge to discover mid-milestone.

If no AC declares a numeric budget, state `None`. `validate-plan` fails when a budgeted AC is not referenced in the section, and the Plan reviewer must reject `READY` when a probe is missing or contradicted.

## Progression Policy

A Goal must not stall because nobody prompted "continue". Classify every next step into one of two classes:

- `AUTO_ADVANCE`: the next lifecycle step is deterministic, safe, reversible, and inside the frozen Plan. It carries standing authorization from the launch prompt — proceed immediately, without asking. Defaults: validating an amended Plan and requesting its review; building reviewer prompts and starting due reviews; classifying findings; applying an authorized `IN_SCOPE` fix and re-requesting review; starting the next authorized milestone after the previous one completes; collecting evidence and running validators.
- `USER_DECISION`: stop, append `USER_DECISION_REQUESTED` with a `decision_id` and a short decision brief, notify the user, and continue only independent authorized work until the matching `USER_DECISION_RECORDED` is appended. Always required for: mutations of production or shared live systems; destructive or hard-to-reverse actions, including deleting resources the Goal did not create; security, credential, or data-exposure risks; `CONTRADICTION` or `AC_CHANGE` findings; resource-threshold failures whose remedy touches anything outside the Goal; and starting or skipping a Goal.

The launch prompt must state the standing `AUTO_ADVANCE` authorization explicitly so the implementer never idles between deterministic steps. `validate-runtime` rejects starting a milestone or completing the Goal while a user decision is pending.

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

## Review Lanes

Not every rejection deserves a fresh full review round. Before requesting any review, run a pre-review self-check: `validate-plan`, `validate-runtime`, formatting, patch dry-runs (for example `git apply --check`), and confirmation that every temporary artifact stays inside the Goal directory. A defect a self-check would have caught must not reach a reviewer.

When a review rejects on purely mechanical grounds — formatting, patch context offsets, file or directory hygiene, evidence placement — with no behavioral or contract change:

- fix it and request a light re-verification from the same reviewer, scoped to the rejected finding only, instead of a fresh full round;
- record the lane on the review events, for example `--data '{"lane":"mechanical",...}'`;
- mechanical rounds still count toward the convergence rule; a recurring mechanical failure means a self-check is missing — add it.

Behavioral or contract-affecting rejections always take the full independent lane.

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

- Proceed serially through authorized milestones, auto-advancing every `AUTO_ADVANCE` step without waiting for a prompt.
- Stop at `USER_DECISION` gates and record them in the ledger; do not start new milestones while a decision is pending.
- Keep unrelated investigations and side questions out of the Goal session; run them separately so the ledger timeline stays attributable.
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

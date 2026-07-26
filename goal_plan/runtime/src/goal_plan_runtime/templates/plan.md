# $goal_title

- Goal ID: `$goal_id`
- Plan version: `1`
- Authorization policy version: `2`
- Plan status: `DRAFT`

## Outcome

Describe the single independently verifiable capability, artifact, or decision delivered by this Goal.

## Scope

### Included

- Define included work.

### Excluded

- Record adjacent work that must not expand this Goal.

## Acceptance Criteria

### AC-01 - Replace With A Verifiable Outcome

- Given the required starting state,
- When the authorized implementation is complete,
- Then describe the observable result.
- Verification command: `replace-me`
- Expected evidence: describe reviewer-owned output that proves the AC.

## Feasibility Probes

- None: no acceptance criterion declares an absolute numeric performance or resource budget.
- When an AC declares one, replace this with per-AC entries: `AC-XX: probe command, raw measurement, target environment, derived budget with margin` (or an explicit waiver with justification). Measure the floor in the target verification environment before freezing the budget.

## Milestones

1. Define the hard-ordered implementation milestones.

## Authorization Policy

- Execution begins only after the user asks to execute this Goal and the Plan is `READY`. That single request starts the authorized execution envelope; it is not repeated at milestone boundaries.
- Default: `DEFAULT_AUTHORIZED`. Every Plan-defined, in-scope action with an exact target is authorized unless this section explicitly marks it `HOLD` or `DENIED`. Silence about authorization means authorized.
- Whole-Goal authorization: `AUTHORIZED`. A milestone inherits this value unless a milestone override below says otherwise.
- Milestone overrides: `None`.
  When needed, add indented entries such as `- M2: HOLD` or `- M3: AUTHORIZED` before execution. Allowed values are `INHERIT`, `AUTHORIZED`, `HOLD`, and `DENIED`; do not create approval gates for milestones that inherit the Whole-Goal authorization.
- `RISK_NOTICE`: append `RISK_NOTICE_RECORDED` with the concrete risk, mitigation, and exact target, then continue. A risk notice is evidence and communication, not a permission request.
- `PREAUTHORIZED_STOP_ACTION`: `None`. A stop-class action may be decided before execution by recording its exact action, target, boundary, and milestone here. It remains authorized only while those facts stay unchanged.
- `USER_DECISION`: request a decision only when an action falls into a stop class below and no matching `PREAUTHORIZED_STOP_ACTION` or recorded decision already covers the exact facts:
  - deletion or another destructive or hard-to-reverse action;
  - public sharing or other exposure expansion;
  - permission expansion or owner transfer;
  - force-push or another history rewrite;
  - access to a non-disposable live object;
  - credential or sensitive-data exposure;
  - a tool-enforced confirmation that explicitly requires approval in the current turn;
  - a new independently useful outcome or work outside the frozen Scope;
  - an unresolved `CONTRADICTION` or `AC_CHANGE`.
- A changed target, broader boundary, or new risk outside an existing authorization requires a new decision. Ordinary in-scope implementation choices, live-system mutations already described by the Plan, test failures, retries, repairs, reviews, commits, pushes without history rewrite, and resource adjustments inside the frozen Scope do not.

## Runtime Contract

- The implementer may implement only against a `READY` plan and must not self-certify.
- The reviewer is independent from the implementer and evaluates the frozen contract rather than continuing implementation.
- Classify every new finding before acting:
  - `IN_SCOPE`: an existing AC requires the fix; fix it without expanding the AC set.
  - `DEFERRED`: useful but unnecessary for this Outcome; record it without implementing it.
  - `CONTRADICTION`: the frozen plan cannot be implemented or verified consistently; stop and amend the plan.
  - `AC_CHANGE`: the definition of done would change; stop and obtain a fresh plan review.
- If two related implementation-review rounds leave the same finding open, stop before a third and perform a convergence review.
- If the shape of the work gains another independently useful outcome, subsystem, runtime environment, or acceptance surface, stop and decide whether to split the Goal.

## Progression Policy

- `AUTO_ADVANCE`: every action covered by the Authorization Policy proceeds immediately without waiting for a user prompt. This includes risk-noticed actions, Plan validation, reviewer prompt construction and review requests, finding classification, `IN_SCOPE` fixes and re-review, milestone transitions, evidence collection, exact-target live-system changes, retries, and in-scope repairs.
- `USER_DECISION`: only an uncovered stop-class action pauses execution. Append `USER_DECISION_REQUESTED` with `authorization_policy_version: 2`, a `decision_id`, allowed `stop_category`, exact `target`, proposed `operation`, concrete `risk`, and `decision_needed`. Continue independent authorized work, and resume the paused action only after a matching `USER_DECISION_RECORDED` or reviewed `PREAUTHORIZED_STOP_ACTION` covers it. Do not treat a risk notice, validator failure, reviewer rejection, or milestone boundary as a human approval gate.

## Reviewer Contract

- Build reviewer prompts from the skill's stable reviewer template plus this Goal contract and runtime-specific focus.
- The reviewer evaluates frozen ACs and may add non-blocking suggestions.
- A finding outside the frozen ACs is `DEFERRED`, not a new blocking requirement.
- A required change to the completion definition is `CONTRADICTION`; the reviewer must not amend the Plan or continue implementation.
- Acceptance requires reviewer-owned command evidence bound to the current Plan version and candidate commit.

## Verification Commands

- Plan validation: `goal-plan-runtime validate-plan <goal-dir>`
- Runtime validation: `goal-plan-runtime validate-runtime <goal-dir>`

## Deferred Follow-ups

- Record useful work that belongs to later Goals.

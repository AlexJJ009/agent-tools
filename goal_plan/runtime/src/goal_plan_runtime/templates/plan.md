# $goal_title

- Goal ID: `$goal_id`
- Plan version: `1`
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

- `AUTO_ADVANCE`: deterministic, safe, in-scope lifecycle steps proceed immediately under the standing launch authorization, without waiting for a user prompt: plan validation, reviewer prompt construction and review requests, classification of findings, authorized `IN_SCOPE` fixes and their re-review, starting the next authorized milestone after the previous one completes, and evidence collection.
- `USER_DECISION`: stop and append `USER_DECISION_REQUESTED` (with a `decision_id` and a short decision brief) before: any mutation of production or shared live systems; destructive or hard-to-reverse actions, including deleting resources this Goal did not create; security, credential, or data-exposure risks; `CONTRADICTION` or `AC_CHANGE` findings; and resource-threshold failures whose remedy touches anything outside this Goal. Do not start new milestones until the matching `USER_DECISION_RECORDED` is appended.

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

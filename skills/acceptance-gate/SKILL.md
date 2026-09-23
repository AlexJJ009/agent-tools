---
name: acceptance-gate
description: Check checklist schema, evidence anchors, agent_status, human_status, candidate SHA, config digest, command digest, and formal-run authorization before completion claims or protected actions.
---

# Acceptance Gate

Use this skill before claiming a task is complete, before a formal experiment, before production or external publishing, and when an action depends on unresolved choices, understanding, execution scope or current evidence.

The gate reads the machine record. Natural-language claims do not create gate state.

## Required Status Model

Checklist items use:

- `agent_status`: `unverified`, `checked`, `failed`, `needs_recheck`, `not_applicable`
- `human_status`: `not_requested`, `requested`, `confirmed`, `rejected`, `invalidated`
- `evidence.level`: `none`, `static`, `simulated`, `real`

High-risk items include algorithm method changes, loss/mask/sampling/filtering/scorer behavior, formal experiment budget, training or Agentic infra lifecycle, Docker/Harbor state, billing, permission, production writes, and external publication.

## Gate Commands

Use the installed launcher outside the checkout:

```text
agent-workflow check --record <record-dir> --phase agent
agent-workflow review-brief --record <record-dir>
agent-workflow target --record <record-dir>
agent-workflow approve --record <record-dir> --sha <candidate-sha> --feedback <human-feedback.json>
agent-workflow revise --record <record-dir> --revision <user-amendment.json>
agent-workflow gate --record <record-dir> --action formal-run
```

Feedback shape: [human feedback](templates/human-feedback.example.json). Amendment shape: [user amendment](templates/user-amendment.example.json). Do not fabricate user feedback; simulator actors are only for explicitly isolated local acceptance tests.

The following target-bound confirmation describes the retained legacy schema-1 path. For simulation records, pass `--simulation` to `approve` and `gate`. `target` prints the current target object and `target_digest`; the human feedback JSON must bind to that digest. `check` validates schema, references, evidence paths, statuses, and protected objects. `gate formal-run` must reject missing or stale agent checks, missing required human confirmation, wrong candidate SHA, missing config digest, or missing command digest.

Use `revise` for actual user amendments. It preserves the original request, records the amendment source, updates canonical protocol expectations, and invalidates affected checklist items and human confirmations.

## Scoped readiness and completion

For schema 2, check these conditions separately: an applicable choice or
explicit delegation; the required explanation and actual scoped feedback or
delegation, with no relevant open question; fresh technical evidence; and
execution within existing authority, budget and special user constraints.
An old `confirmed` retains its old meaning on import and is not a general
understanding, delegation or result-acceptance event.

Read `status` to inspect current state without running the full verifier suite.
Use purpose-specific sourced feedback and retain its exact wording. A routine
repair requires relevant revalidation, not another copy of unchanged consent.
A new budget, method or previously excluded action needs its own scoped decision.
Do not manufacture confirmation from a commit or from report delivery.

`gate --action completion --phase <phase>` evaluates that phase's promises and
known blockers. An unfinished future phase does not block truthful progress.
A report PASS does not close a failed functional criterion or mark user acceptance.
A protected entry must check again before effects, including direct, terminal and
queued calls; a queue checks the current inputs at dequeue. A standalone passing
gate response is not an execution receipt. Use the public managed adapter and
verify absent/present effects, fixed consumed inputs and actual exit status.

Relevant unclassified new input makes its dependent action wait; unrelated
reading and ordinary status answers continue. Hook installation or mock event
success is not proof of genuine host protection. Simulation evidence cannot
be converted into real workload authority.

## Boundary

Passing this gate means the local record satisfies the workflow's mechanical conditions. It does not prove the algorithm is theoretically correct, the user has read every file, the reviewer identity is tamper-proof, or a simulation authorizes a real run. A simulation approval is restricted to sandbox checks and cannot authorize production or a real formal experiment.

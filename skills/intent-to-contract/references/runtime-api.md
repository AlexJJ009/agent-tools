# Runtime input contract

Use `agent-workflow` from the installed user launcher. `init --context` reads JSON, not free-form YAML. It preserves query bytes and initializes every item as unverified with no execution evidence. Do not supply your own checked/confirmed statuses or evidence in the context; only actual runtime checks/feedback create those states.

## Schema selection and legacy records

Set `schema_version: 2` in a new context to use typed events, choices, phases and scoped feedback. The context example uses this schema. Omitting the field preserves the v1 initialization behavior; existing v1 records remain readable and their `check`, `revise`, `approve`, and formal-run gate remain available.

Use `agent-workflow migrate --record <directory>` to upgrade an existing record explicitly. Migration preserves an exact, hashed v1 checklist snapshot and does not convert old `confirmed` values into understanding, execution delegation or result acceptance. `rollback --record <directory> --output <outside-record-path>` exports that verified snapshot. Restore it only in an isolated copy when testing the older runtime; the live v2 history stays intact.

Do not edit a generated checklist by hand. The checklist template documents the canonical shape, while `init --context` and typed updates are the write interfaces.

## Context fields

- `schema_version`: `1` for compatibility or `2` for the incremental state model. `phase` names the initial phase (default `baseline`).
- `facts.infra`: boolean. Set true for investigated training/launcher/environment or Agentic lifecycle work, even when the primary scenario is algorithm. It does not mean that real infrastructure has been tested.
- `facts.side_effects`: false or a nonempty list/description of investigated side effects. Refund/billing bug fixes require this fact and focused regression checks.
- `formal_run_policy`: `prohibited`, `sandbox_allowed`, or `requires_human`. An explicit no-formal-run instruction uses `prohibited`; it still permits independently authorized local check commands.
- `run_class`: `exploratory`, `short_smoke`, `formal_experiment`, `production`, or `external_publish`. `simulation` is NOT a run class; pass `--mode simulation` for fixture evidence.
- `items`: extraction entries, with the fields below.
- `bindings`: object keyed by extraction item ID, not checklist ID. Only inspected parameter/protocol bindings belong here.
- `checks`: object keyed by checklist ID. Each value supplies `risk`, `verifier` and `review_scope`. Schema 2 also accepts `participation`: `unspecified`, `explain`, `understanding`, or `delegated`. This descriptive field never substitutes for a sourced delegation or scoped feedback receipt.
- `command` / `command_paths` / `config_paths`: optional protected action scope; these are not executed by init or gate. Each check has its own `verifier.argv`.
- `protocol_view`: optional boolean; derives a human-readable protocol view.

## Extraction entries

Required fields are `id`, `source_quote`, `normalized_value`, `requirement_kind`, `authority`, `confidence`, `cost_if_wrong`, `blocking_question`, and `checklist_ids`.

- `requirement_kind`: `goal`, `constraint`, `protocol`, `acceptance`, `non_goal`, `preference`, or `unknown`. Do not invent `safety`, `learning`, `office`, `handoff` or `environment` kinds.
- `authority`: `user`, `project_fact`, `source_spec`, or `agent_proposal`.
- `source_quote`: for user requirements, a nonempty exact substring of the original query. In schema 2, inspected code facts and proposals use a separate `source` object with `kind`, `actor`, `path`, `quote`, and `sha256`; the exact quote comes from that source, not the user query. Use `authority: project_fact` for code and `authority: agent_proposal` for a proposal. Store explanations in `meaning`; never attribute an Agent proposal to the user.
- `normalized_value`: the precise expected JSON value at the chosen observation key. Its shape must match that observation: a per-source mapping is not a scalar total. Derive expected values independently from the user's requirement or a trusted oracle, not by copying observed output.
- `confidence`: number in [0, 1].
- `checklist_ids`: nonempty list of unique check IDs.
- `blocking_question`: null/empty when the local check is resolvable. A nonempty question blocks that item. Keep unavailable real-system evidence separate from an independently testable local simulation item.
- `semantic_candidates`: when there is more than one unresolved meaning, retain them, leave `normalized_value` null and ask the blocking question.

`protocol` denotes a code parameter binding in code scenarios and requires a binding. An observed lifecycle outcome, regression result or document quality criterion can use `acceptance`; it still produces a canonical protocol/expectation record. Missing papers or slide materials remain explicit unverified goals/acceptance items and route to specialized tools.

## Binding and verifier shape

See [context example](../templates/context.example.json). The example's paths are illustrative and are not acceptance evidence.

Binding anchors `definition`, `consumer` and each ordered `overrides` element have `path`, one-based `line`, and `symbol`. `symbol` must actually occur on that line; use code such as `cfg =`, not a prose label such as `config load`. `consumer_symbol` equals `consumer.symbol`. `config_key` must appear at the definition anchor. Every path is relative to the target repository and must stay inside it. Store external context in the task notes; do not pass `../` paths as watched code.

A binding has `readback_key`, a dot-separated key into command output, selecting an object with `config_key`, `consumer_symbol`, and `value`. The verifier's `observation_key` selects the actual observed value, not the whole binding identity object. That value must equal both the protocol expectation and binding readback `value`. Project adapters can emit a compound per-source observation to cover every enabled source; do not reduce the check to a single source merely to match a scalar.

A `command_json` verifier supplies an argv string list, `observation_key`, `watched_paths`, and optional `timeout_seconds` (1..300). It must be an inspected, locally authorized verification command. Runtime captures stdout, stderr, exit status and the selected observation. The adapter's correctness and semantic coverage still need independent review; matching JSON cannot prove arbitrary program behavior.

A `static_anchor` verifier is only for low-risk nonparameter inspection. It supplies `anchors` with concrete path/line/symbol and a boolean expected value; the runtime observes whether all anchors match. It cannot mark a high-risk parameter checked. An `unconfigured` verifier explicitly leaves an item failing/unverified until a suitable project check exists.

Use `check --item <ID>` to recheck only affected items. `check` without `--item` checks every listed item and exits nonzero if any fails; already-resolved independent items retain their evidence. The task is not fully accepted while a required item remains unresolved.

## Source and authorization boundaries

Do not encode a prohibition as a fabricated code test. Preserve it in `agreement.non_goals` and `formal_run_policy`, optionally with an unresolved checklist item if a further decision is genuinely needed. A gate rejection is expected evidence when the query prohibits a formal run.

Reuse actual preexisting task authority within its stated scope. A sourced delegation or execution authorization may cite the earlier user instruction; do not ask again merely because the candidate commit changed. New methods, budgets, targets or explicit special conditions still require their own applicable scope.

The machine performs mechanical validation, not human identity authentication. `approve` needs actual feedback; use its simulation flag only for explicitly isolated acceptance tests. A report or Agent statement is never real human approval. No test should create a real approval just to get a green status.

## Checklist settings and lightweight handoffs

`checks.<check-id>.risk` is exactly `low` or `high_risk`, never `none`, `normal`, or `medium`. Every verifier object, including `unconfigured`, has `method` and `watched_paths` (use an empty list when no target files exist). Every `review_scope` has `must_review` and `context_only` lists; `high_risk` needs a nonempty focused location. `request.txt:1` is a valid intake review anchor before code exists. Low-risk unconfigured learning/office items can use both lists empty; do not manufacture high risk or an artificial formal command for these handoffs.

Keep an existing-behavior repair on the `bug_fix` primary route. Billing, permissions or other side effects raise risk and add acceptance checks; they do not by themselves turn a bug repair into a new business feature. The general Coder is unchanged.

Learning-only intake hands off to the existing `teaching-reconstruction` skill (and `read-paper` when a paper is involved). Office-only intake uses an available office tool after recording facts, audience and export requirements. Neither path needs a formal-run gate or a code Cleaner. Missing material is a legitimate unverified handoff, not a reason that `init` should fail.


## Schema 2 state and typed updates

`checklist.yaml` remains canonical. Schema 2 adds `revision`, canonical `events`, `choices`, `delegations`, `execution_authority`, `phase`, `phases`, `actions`, `pending_inputs`, and `jobs`. Each checklist item has its phase, descriptive participation setting, and separate `result_acceptance`. A phase names its `required_checklist_items`; future phases can stay unfinished while the current phase is delivered. Technical checks, independent review and user acceptance remain distinct.

The Agent discovers important choices by reading the request and actual code. Neither regex routing nor this typed interface performs semantic discovery. State validation checks declared scopes, identifiers, source hashes and revisions; it does not determine whether the explanation is useful, the user truly understands, or the requirement covers the intended behavior.

An event contains:

| Field | Required value |
|---|---|
| `id` | Unique stable ID, reused verbatim on retry |
| `base_revision` | The canonical revision read before preparing the update |
| `type` | One of the event types below |
| `source` | `kind`, `actor`, `path`, exact `quote`, `sha256` |
| `affects` | Explicit existing checklist IDs affected by this event |
| `payload` | Event-specific fields; cannot set `agent_status: checked` |

Source kinds are `user`, `code`, `proposal`, and `tool`. Use an absolute input path, or a record-relative path. The runtime checks the exact quote and SHA-256, snapshots the source bytes, and stores a record-relative evidence path. User feedback, delegation and authorization require a user source. An Agent may not use a generated file as purported actual user feedback. Hash checking provides provenance integrity, not identity authentication or semantic truth.

The following **illustrative code-source example** assumes `/tmp/demo-defaults.py` contains exactly `critic_init = "reference"` followed by one newline. Its hash matches those bytes. Replace the affected ID with a real initialized checklist ID and use the current revision. It proposes a choice; it does not claim a user decision or understanding.

```json
{
  "id": "discover-critic-default-1",
  "base_revision": 0,
  "type": "choice.propose",
  "source": {
    "kind": "code",
    "actor": "Agent",
    "path": "/tmp/demo-defaults.py",
    "quote": "critic_init = \"reference\"",
    "sha256": "13a2c70d1fce6a27a1a22d90de1b6c0349474ab724a92dc51a201561b52f90a5"
  },
  "affects": ["ALG-K-001"],
  "payload": {
    "id": "CRITIC-START",
    "question": "Which critic initialization preserves the intended comparison?",
    "affects": ["ALG-K-001"],
    "required_scope": "Critic initialization and comparison conditions",
    "options": ["Keep the inspected reference", "Use a separately justified initialization"]
  }
}
```

Apply a saved event with `agent-workflow update --record <directory> --event <event.json>`. Read the returned revision. Repeating the identical event is a no-op even if other events have since committed; reusing its ID with different content is rejected. A new event based on an old revision is rejected: read current state, reconcile the difference, and submit a new event. Never overwrite the newer checklist.

## Event payloads

| Type | Payload and meaning |
|---|---|
| `choice.propose` | `id`, `question`, `affects`, optional `options` and `required_scope`; unresolved until a decision or applicable delegation covers it |
| `choice.resolve` | `choice_id`, `value`, `rationale`; an Agent-sourced resolution also names `delegation_id` |
| `understanding.explain` | `choice_id`, exact `scope`, `explanation`; records what was explained |
| `understanding.feedback` | `choice_id`, exact `scope`, `kind`: `self_report`, `reconstruction`, `question`, or `decision`; optional `resolves` lists specific question-event IDs |
| `delegation.grant` | `id`, `choice_ids`, `scope`; user-sourced, with explicit affected items, and never implies understanding |
| `delegation.revoke` | `id` of the prior delegation |
| `requirements.revise` | `updates` containing `protocol_id`, `expected` (`value`, `unit`), `meaning`; plus `reason` |
| `requirement.add` | `item` in extraction shape, `check` in checklist-settings shape, `phase`, `reason`, optional `binding`; one new checklist ID per event |
| `result.feedback` | `kind`: `acceptance`, `defect`, `clarification`, or `next_version`; `items` maps exact existing checklist IDs to `accepted`, `rejected`, or `pending` |
| `phase.define` | New `id`, `required_checklist_items`; existing phase requirements cannot be silently replaced |
| `phase.set` | Existing phase `id` |
| `phase.review` | Phase `id`, `status`: `pass`, `fail`, or `pending`, and actual `evidence`; reviewer independence remains an explicit review obligation |
| `verifier.configure` | `item_id`, `verifier`, `reason`; invalidates old technical evidence |
| `input.record` | Stable input `id`; affected items stay pending until classified |
| `input.resolve` | Input `id`, `disposition`: `applied` or `no_contract_change`, and `reason` |
| `job.update` | Job `id`, `status`: `queued`, `running`, `completed`, `failed`, `cancelled`, or `unknown`; include actual observations as needed |
| `action.register` | An `action` object with `id`, `required_checklist_items`, `choice_ids`, `phase`, `argv`, `config_paths`, `command_paths`, and the applicable authorization scope |
| `authorization.grant` | `id`, `action_ids`, and `scope`, backed by actual user authority |
| `authorization.revoke` | Prior authorization `id` |

A choice stores `resolution` separately from `understanding`. The latter holds `required_scope`, `explanation_ref`, `feedback_refs`, and `open_questions`. A self-report is evidence of that specific self-report; it is not a universal understanding certificate. Resolve only named open questions with actual feedback. A general compliment does not accept all checklist items.

For an MVP review, record accepted items through `result.feedback`, defects against current items, and next-version requests as `next_version` feedback. Then define the next phase and add its newly agreed requirements. New requirements start unverified and pending acceptance; old acceptance is never copied forward. Use `affects` for existing affected IDs; a newly added requirement's ID belongs in `payload.item.checklist_ids`.

Requirement revisions preserve the prior protocol and source in event history. They invalidate related evidence, decisions and scoped grants. Code-only freshness changes invalidate technical checks while retaining semantic choices and understanding. A new successful check cannot invent fresh user feedback.

## Readback, derived views and recovery

`agent-workflow status --record <directory>` reads observations, choices, pending inputs, phases and jobs, and hashes relevant evidence inputs. It never runs verification commands. Stale technical evidence becomes `needs_recheck`; run the existing `check --phase agent --item <ID>` when actual verification is appropriate. Legacy `revise --revision` remains supported and uses the typed update core for schema 2.

Every schema-2 writer, including `check`, `revise`, `approve` and gate, compares and advances the canonical revision. `events.json`, `task.md` and the focused brief are derived views. If a view write is interrupted after the canonical commit, the update reports the committed revision and view error; retry the same event or run `refresh --record <directory>` to rebuild. Do not replay the change under a new ID simply because a view is missing.

`review-brief` renders actual saved observations and current choice reasons. An ordinary check may refresh that focused brief, but it does not create a full Work Report. Reports should freeze the workflow revision they actually read and follow the explicit reporting request or existing agreement.

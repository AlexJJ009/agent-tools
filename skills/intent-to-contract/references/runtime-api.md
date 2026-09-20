# Runtime input contract

Use `agent-workflow` from the installed user launcher. `init --context` reads JSON, not free-form YAML. It preserves query bytes and initializes every item as unverified with no execution evidence. Do not supply your own checked/confirmed statuses or evidence in the context; only actual runtime checks/feedback create those states.

## Context fields

- `facts.infra`: boolean. Set true for investigated training/launcher/environment or Agentic lifecycle work, even when the primary scenario is algorithm. It does not mean that real infrastructure has been tested.
- `facts.side_effects`: false or a nonempty list/description of investigated side effects. Refund/billing bug fixes require this fact and focused regression checks.
- `formal_run_policy`: `prohibited`, `sandbox_allowed`, or `requires_human`. An explicit no-formal-run instruction uses `prohibited`; it still permits independently authorized local check commands.
- `run_class`: `exploratory`, `short_smoke`, `formal_experiment`, `production`, or `external_publish`. `simulation` is NOT a run class; pass `--mode simulation` for fixture evidence.
- `items`: extraction entries, with the fields below.
- `bindings`: object keyed by extraction item ID, not checklist ID. Only inspected parameter/protocol bindings belong here.
- `checks`: object keyed by checklist ID. Each value supplies `risk`, `verifier` and `review_scope`.
- `command` / `command_paths` / `config_paths`: optional protected action scope; these are not executed by init or gate. Each check has its own `verifier.argv`.
- `protocol_view`: optional boolean; derives a human-readable protocol view.

## Extraction entries

Required fields are `id`, `source_quote`, `normalized_value`, `requirement_kind`, `authority`, `confidence`, `cost_if_wrong`, `blocking_question`, and `checklist_ids`.

- `requirement_kind`: `goal`, `constraint`, `protocol`, `acceptance`, `non_goal`, `preference`, or `unknown`. Do not invent `safety`, `learning`, `office`, `handoff` or `environment` kinds.
- `authority`: `user`, `project_fact`, `source_spec`, or `agent_proposal`.
- `source_quote`: a nonempty exact substring of the original query. Store explanations in `meaning`; do not manufacture a quote for a negative control.
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

The machine performs mechanical validation, not human identity authentication. `approve` needs actual feedback; use its simulation flag only for explicitly isolated acceptance tests. A report or Agent statement is never real human approval. No test should create a real approval just to get a green status.

## Checklist settings and lightweight handoffs

`checks.<check-id>.risk` is exactly `low` or `high_risk`, never `none`, `normal`, or `medium`. Every verifier object, including `unconfigured`, has `method` and `watched_paths` (use an empty list when no target files exist). Every `review_scope` has `must_review` and `context_only` lists; `high_risk` needs a nonempty focused location. `request.txt:1` is a valid intake review anchor before code exists. Low-risk unconfigured learning/office items can use both lists empty; do not manufacture high risk or an artificial formal command for these handoffs.

Keep an existing-behavior repair on the `bug_fix` primary route. Billing, permissions or other side effects raise risk and add acceptance checks; they do not by themselves turn a bug repair into a new business feature. The general Coder is unchanged.

Learning-only intake hands off to the existing `teaching-reconstruction` skill (and `read-paper` when a paper is involved). Office-only intake uses an available office tool after recording facts, audience and export requirements. Neither path needs a formal-run gate or a code Cleaner. Missing material is a legitimate unverified handoff, not a reason that `init` should fail.

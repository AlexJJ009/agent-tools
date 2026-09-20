---
name: intent-to-contract
description: Turn a user request into a grounded task agreement with readback, acceptance criteria, protocol bindings, and blocker questions before expensive or high-risk agent work.
---

# Intent To Contract

Use this skill when a task begins from a natural-language request and the agent must preserve the user's intended goal, scope, key parameters, acceptance criteria, and authorization boundary. The output is Agent-authored context for the runtime plus a task agreement, not an implementation plan that freezes every coding step.

Keep the work moving while the agreement is formed. Ask the user only for facts that would change the target, budget, production effect, or formal experiment. For facts visible in the repository or local environment, investigate and record the evidence instead of asking the user to remember it.

## Contract Rules

- Preserve `source_quote` exactly, including Chinese wording, numbers, units, and uncertainty.
- Separate user requirements, project facts, source specs, and agent proposals. An agent proposal cannot become a hard requirement without user or project authority.
- Keep multiple plausible meanings in `semantic_candidates`; do not silently choose when the difference affects target behavior, cost, or formal runs.
- Ground parameter-like requirements in real code, data, or output objects before treating them as protocol items. A matching field name is not enough; trace definition, override order, and consumer.
- Keep the current agreement separate from the work record. Debugging discoveries can update the work record, but cannot lower the goal or change the protocol to make a failing implementation pass.
- Learning-only requests route to the existing teaching flow. Office-only requests use office quality checks, not code gates.
- Distinguish semantic routing from runtime lint. The Agent chooses the scenario after investigation; the runtime only rejects obvious contradictions such as a Docker or launcher request without infra facts.

Use [acceptance profiles](references/acceptance-profiles.md) when selecting scenario checks; read only the applicable profile.

Before constructing CLI context, read the [runtime input contract](references/runtime-api.md) for field enums, path scope and observation/readback distinctions.

## Required Outputs

The runtime does not perform arbitrary natural-language extraction. The Agent supplies a JSON context containing investigated `items`, `facts`, `bindings`, `checks`, formal command/config scope, and review targets. Bindings include ordered override anchors and a `readback_key` into verifier JSON where `{config_key, consumer_symbol, value}` is returned. Optional `protocol_view: true` renders `protocol.md` from the canonical record. See [context example](templates/context.example.json); replace every sample path and value with inspected project facts.

Create or update the record through the installed launcher when available:

```text
agent-workflow init --query <request.txt> --scenario <algorithm|infra|business|bug_fix|office|learning> --context <context.json> --mode simulation
```

The record should follow the fixed directory shape under `docs/agent-workflow/records/`. Use [templates/task.md](templates/task.md) and [templates/checklist.yaml](templates/checklist.yaml) as the local shape when the runtime cannot yet create the file.

Each extracted requirement should include:

- `source_quote`
- `normalized_value`
- `requirement_kind`
- `authority`
- `confidence`
- `cost_if_wrong`
- `blocking_question`
- linked `checklist` item ID

For protocol-like values, include a binding record with the repository state, definition location, consumer location, override order, readback evidence, and unresolved ambiguity.

## Completion Boundary

This skill does not authorize formal experiments, production writes, external publication, or user review completion. It produces the agreement and the evidence targets that later gates check.

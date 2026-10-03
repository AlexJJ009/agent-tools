# Legacy scenario records

Read this only when continuing an explicitly selected legacy scenario contract. Field enums, path scope and observation/readback distinctions are in the [legacy runtime input contract](runtime-api.md).

## Existing records

Keep existing scenario records and their explicit paths when continuing the
legacy workflow below. This interface still supplies formal command/config
bindings and readback checks; task-state storage does not loosen those gates.
Do not create both interfaces' checklists for the same state merely to satisfy
this skill.

## Continuing a legacy contract

The runtime does not perform arbitrary natural-language extraction. The Agent supplies a JSON context containing investigated `items`, `facts`, `bindings`, `checks`, formal command/config scope, and review targets. Bindings include ordered override anchors and a `readback_key` into verifier JSON where `{config_key, consumer_symbol, value}` is returned. Optional `protocol_view: true` renders `protocol.md` from the canonical record. See [context example](../templates/context.example.json); replace every sample path and value with inspected project facts.

The following initialization syntax is retained for explicitly requested legacy scenario work, not the default for new task agreements. Continue an existing record at its exact path; do not initialize a replacement to obtain newer status fields:

```text
agent-workflow init --query <request.txt> --scenario <algorithm|infra|business|bug_fix|office|learning> --context <context.json> --mode simulation
```

Only explicitly requested new legacy scenario records use `docs/_local/tasks/<task-id>/` in the current worktree, excluded by the repository rule `/docs/_local/`. Preserve existing task IDs and explicit record paths; resume the existing checklist instead of creating a second status source. Use [templates/task.md](../templates/task.md) and [templates/checklist.yaml](../templates/checklist.yaml) as the local shape when the runtime cannot yet create the file.

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

## Office-only requests

Office-only intake uses an available office tool and office quality checks, not code gates. Record facts, audience and export requirements first.

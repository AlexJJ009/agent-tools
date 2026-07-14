---
description: Prepare or govern a reviewed long-horizon Goal with isolated runtime validation, without automatically starting execution.
---

# /goal-plan

Load the `$goal-plan` skill and use the isolated `goal-plan-runtime` launcher.

- New Goal: initialize one Goal directory, author and validate `plan.md`, obtain an independent Plan Review, and assemble the launch prompt.
- Existing Goal: validate the Plan and append-only ledgers, then perform only the requested lifecycle action: amendment, reviewer prompt construction, convergence review, or final acceptance.
- Do not create/start a Codex Goal unless the user explicitly asks.
- Do not rewrite `runtime.jsonl` or `findings.jsonl`; append correction events.
- Final acceptance requires reviewer-owned command evidence bound to the current Plan version and candidate commit.
- During authorized execution, auto-advance deterministic `AUTO_ADVANCE` lifecycle steps without waiting for prompts; stop only at `USER_DECISION` gates (production mutations, destructive actions, security risks, contract changes, resource-threshold failures).
- Numeric performance or resource budgets in ACs require a feasibility probe in the Plan before `READY`.

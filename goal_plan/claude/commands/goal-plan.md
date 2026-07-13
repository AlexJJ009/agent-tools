---
description: Prepare or govern a reviewed long-horizon Goal without automatically starting execution.
argument-hint: [goal request or goal directory]
---

Use the `goal-plan` skill.

- For a new Goal, create an isolated Goal directory with `goal-plan-runtime init`, author `plan.md`, validate it, obtain an independent Plan Review, and produce the launch prompt.
- For an existing Goal directory, validate its Plan and append-only runtime ledgers, then perform only the requested lifecycle action: amendment, reviewer prompt construction, convergence review, or final acceptance.
- Do not start implementation or create a Goal executor unless the user explicitly requests execution.
- Do not rewrite `runtime.jsonl` or `findings.jsonl`; append correction events.

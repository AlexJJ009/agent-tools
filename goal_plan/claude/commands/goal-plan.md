---
description: Prepare or govern a reviewed long-horizon Goal without automatically starting execution.
argument-hint: [goal request or goal directory]
---

Use the `goal-plan` skill.

- For a new Goal, create an isolated Goal directory with `goal-plan-runtime init`, author `plan.md`, validate it, obtain an independent Plan Review, and produce the launch prompt.
- For an existing Goal directory, validate its Plan and append-only runtime ledgers, then perform only the requested lifecycle action: amendment, reviewer prompt construction, convergence review, or final acceptance.
- Do not start implementation or create a Goal executor unless the user explicitly requests execution.
- Do not rewrite `runtime.jsonl` or `findings.jsonl`; append correction events.
- Authorization defaults to granted for every exact-target action inside the frozen Plan. Freeze one Whole-Goal envelope or explicit milestone overrides before execution; milestone boundaries do not ask again.
- During execution, report concrete risks and continue. Stop only for an uncovered stop-class action: deletion, exposure or permission expansion, owner transfer, history rewrite, non-disposable live-object access, credential/data exposure, a tool-enforced current-turn confirmation, a new outcome, or unresolved `CONTRADICTION`/`AC_CHANGE`.
- Numeric performance or resource budgets in ACs require a feasibility probe in the Plan before `READY`.

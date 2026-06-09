---
name: goal-plan
description: "Prepare and gate a long-horizon goal plan before execution. Use when the user explicitly invokes /goal-plan, asks to prepare/review a goal plan, or wants a long-running implementation prompt with verifiable acceptance criteria before using a loop/executor. Do not route /goal here: /goal remains the execution loop, while /goal-plan creates the plan, adversarial review, goal prompt, and independent acceptance gate. Uses goal-plan-reviewer as the skeptic; the implementer never grades its own homework."
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - Task
  - TodoWrite
  - Skill
---

# goal-plan — running a long-horizon goal with an adversarial reviewer

Load this when the user explicitly invokes `/goal-plan` or asks to prepare/review a
**goal plan** for long-running work. Do **not** intercept `/goal`: `/goal` is the
execution loop, while `/goal-plan` is the planning and acceptance wrapper that produces
the plan, reviewer gate, and launch prompt for that loop.

This skill turns a vague "go build X" into a plan with verifiable acceptance criteria,
has an **independent reviewer subagent** red-team that plan before any code is written,
drives execution behind stop-and-ask guardrails, and makes the **reviewer — not the
implementer — the final acceptance gate**.

Core principle, from which everything else follows: **the agent doing the work cannot be
trusted to certify the work.** Generation and verification are split across two agents on
purpose. You (main agent) generate and implement; the `goal-plan-reviewer` subagent
attacks the plan and signs off the result.

## The lifecycle (do these in order)

```
1. AUTHOR PLAN     → plan file with numbered, self-verifiable acceptance criteria (AC) + milestones
2. ADVERSARIAL     → dispatch goal-plan-reviewer (Mode A): grade every AC ✅/⚠️/❌,
   REVIEW             find P0 plan↔code contradictions, decide split vs single goal.
                      DO NOT implement until verdict is READY / READY-AFTER-FIXES.
3. ASSEMBLE GOAL   → fill the goal-prompt skeleton (objective / source of truth /
   PROMPT             order / global conventions / intervention triggers / DoD)
4. EXECUTE         → serial milestones, mock everything, commit per unit,
                      STOP and ask the human on any trigger (don't push through)
5. ACCEPTANCE      → dispatch goal-plan-reviewer (Mode B): independent, AC-by-AC sign-off.
                      Implementer does NOT self-certify. ACCEPTED only on the reviewer's run.
```

Track the milestones with `TodoWrite` so progress survives compaction.

---

## Phase 1 — Author the plan

Write a plan file (e.g. `docs/plans/<date>-<goal>.md`). A plan is only goal-ready if its
acceptance is **machine-checkable in the sandbox**. Requirements:

- **Numbered acceptance criteria (AC)**, each written **Given / When / Then** and tied to a
  concrete assertion. "It works" is not an AC; "Given payload P, when `rewriteBody` runs,
  then field `device_id` becomes `config.identity.device_id`" is.
- **One source of truth.** The plan is authoritative; implementation conforms to its AC. If
  the plan must change during work, **change the plan first, then the code.**
- **Milestones with a hard order** when there's a producer→consumer dependency (e.g. a
  shared util one milestone produces and later ones import). State the order and the
  dependency explicitly — don't make the agent re-derive it.
- **Self-verifiable by construction.** Every AC should be checkable by: a pure-function unit
  test, a build + artifact check, a `grep`, or a local **mock-HTTP** assertion. If an AC can
  only be proven by hitting a real account / real upstream / real network, rewrite it now
  (see Phase 2 mock rewrites) — it will otherwise stall the run.

## Phase 2 — Adversarial plan review (gate, before any code)

Dispatch the reviewer **before implementing**:

> Use the `Task` tool with `subagent_type: "goal-plan-reviewer"`, mode **PLAN REVIEW**, and
> the plan file path. Ask it for: the AC self-verifiability table (✅/⚠️/❌), P0
> contradictions, any ACs to add, the decomposition call, and the pre-flight checklist.

Then act on the verdict:

- **NOT-READY** → fix the plan (resolve P0 contradictions, define the missing ACs, rewrite
  ❌ ACs to mock form) and re-review. **Do not start coding on a not-ready plan.**
- **Split recommended** → run the milestones as **serial sub-goals**, not one mega-goal.
  Heuristic: split when AC count is high *and* scaffolding spans tiers (pure-fn → mock-HTTP →
  container), or a shared produced artifact forces an order a single goal would have to
  self-sequence unreliably.
- **Mock rewrites** → every "real refresh / real 429 / real account" AC becomes a mock-HTTP
  or filesystem-semantics assertion that proves the same root-cause mechanism. The agent
  must never need a real external service to close an AC.

This phase is adversarial on purpose: a plan that survives the reviewer's attack is far more
likely to converge autonomously.

## Phase 3 — Assemble the goal prompt

Fill this skeleton (battle-tested on this project's `/goal` runs). Keep every section:

```
## 目标 / Objective
<one goal, on branch <X>; what "done" delivers. Background docs are CONTEXT, not deliverables.>

## 单一事实源 / Single source of truth (read first, check against numbered ACs)
<the plan file(s) + which AC numbers each covers. Plan is authoritative; conflicts → intervention.>

## 执行顺序 / Execution order (hard constraint, no reordering)
<M1 → M2 → M3; name the produced artifact that forces the order. Per milestone:
 implement → add tests → full suite green → commit → brief report → auto-advance.
 Never jump to the next milestone before the current one's ACs are all green.>

## 全局执行约定 / Global conventions (violating these causes stalls or false passes)
- Test paradigm: <exact runner + how to run, e.g. `npm test`>. New tests join the same
  paradigm and run in the suite.
- Mock everything external: upstream / OAuth / 401·403·429 via mock-HTTP injection or
  in-memory fakes (e.g. ioredis-mock). NEVER hit real Anthropic / real OAuth / real accounts —
  they're unreachable in the sandbox and will hang the run. Shared fixtures live in one place.
- Build check + fallback: <`npm run build` then `ls dist/...`; if no docker, container build
  degrades to this>.
- Branch & commits: stay on <branch>; commit each independently-verifiable unit; message
  references the AC number; trailer `Co-Authored-By:`.
- Plan is single source of truth: adjust the plan before the code if reality forces a change.

## 人工介入触发条件 / Stop-and-ask triggers (hit any → STOP that item, emit the request, WAIT)
1. STUCK: same AC fails its test 3 times, or you start repeating a failed approach.
2. CONTRADICTION: plan vs real code/behaviour conflict (signature/path/field mismatch).
   Do NOT pick one yourself — the plan can be wrong too; a human rules change-plan vs change-code.
3. UNDER-DEFINED AC: a real decision point the plan didn't specify, with multiple reasonable
   implementations that change acceptance.
4. FORCED OUT OF SANDBOX: an AC seems to need a real service/account/real-429 to verify
   (should be impossible after Phase 2 — if it happens, report as a contradiction).
5. ORDER BLOCKED: a needed upstream-milestone artifact is missing or has the wrong signature.

### 介入请求格式 / Intervention request format
🛑 需要人工介入
- 里程碑/AC: <e.g. M2 / AC-3>
- 触发类型: <stuck / contradiction / under-defined / out-of-sandbox / order-blocked>
- 现象: <what happened; paste the key error/diff>
- 已尝试: <the N approaches tried and each result>
- 卡点: <what's actually missing — a decision? a fact? a plan clarification?>
- 我的建议: <1–2 candidate options with trade-offs, but do NOT self-execute>
Then STOP and wait. Do not lower the bar or skip the AC to "make progress".

## 完成定义 / Definition of Done
- Every required AC's test is green in the full suite; build succeeds + artifacts present.
- No real external service was contacted the whole run.
- Each change committed per-unit on <branch> referencing its AC.
- Final report: each AC → its test file:case + pass status.
```

## Phase 4 — Execute

Drive the goal under the prompt above. Non-negotiables:

- **Serial milestones**; do not advance until the current milestone's ACs are all green by a
  real test run. **Mock every external signal.** **Commit per independently-verifiable unit.**
- **Stop-and-ask, don't push through.** On any trigger, emit the intervention request and
  wait — never lower the acceptance bar, weaken/skip a test, or guess between plan and code
  to keep moving. A stalled goal that asks is healthier than one that fakes a pass.
- **Never weaken the signal to go green.** Deleting/skipping/loosening a test, or making it
  assert trivially, is not progress — the reviewer will catch it in Phase 5 and reject.
- Keep the plan file as the live source of truth; update it (not just the code) when reality
  forces a change.
- **Leave a resumable trail.** Maintain a progress log (a `*-progress.md` scratchpad and/or
  the Task list) and commit per unit with descriptive messages, so a fresh context can resume
  from the log + git history and revert bad changes — the long-run state-loss failure mode.
- **Fight drift with fresh starts.** Between milestones, `/compact` or `/clear` (the plan and
  Tasks persist on disk) and, on very long runs, start a fresh session — agents tunnel and
  drift the longer they run. Beware "fake completion": a feature marked done without
  end-to-end verification; that's what Phase 5 exists to catch.

## Phase 5 — Final acceptance (independent gate)

When the implementer believes it's done, **do not self-certify.** Dispatch the reviewer again:

> `Task` tool, `subagent_type: "goal-plan-reviewer"`, mode **ACCEPTANCE**, with the plan's DoD
> and the test/build commands. It runs the suite itself, returns a per-AC PASS/FAIL/WEAKENED
> table from its OWN run, includes the exact commands plus relevant output snippets, audits for
> moved goalposts and out-of-sandbox shortcuts, and gives a final `ACCEPTED` / `REJECTED`.

Acceptance reports without reviewer-owned command output are incomplete. If the reviewer cannot
run the test/build command, the result is `REJECTED`, not "accepted by reasoning."

The goal is met **only on the reviewer's `ACCEPTED`**. On `REJECTED`, take its exact change
list back into Phase 4. This closes the loop: the agent that wrote the code is never the one
that declares it done.

---

## Using this for /loop (self-paced long runs)

For a `/loop`-style self-paced run (keep going until a target is hit), wrap the same
lifecycle in the loop: each iteration advances one milestone, runs the stop-and-ask checks,
and the loop's exit condition is the reviewer's `ACCEPTED` — not the implementer's opinion.
Use a loop-until-dry / loop-until-AC-green exit, and a stuck-counter (halt after N
no-progress iterations) so a death spiral surfaces to the human instead of burning turns.

## External best practices (folded in, with sources)

The lifecycle above lines up with what practitioners and researchers report for long-horizon
agents (2024–2026). The highest-signal points, and what each adds to the phases above:

- **Plan/spec-first, with a planner→worker→judge split.** Cursor resisted planning, then
  landed on explicit planner/worker/judge roles; Anthropic and OpenAI converged on the same
  triad independently. "A surprising amount of behaviour comes down to how we prompt the
  agents" — invest in the plan and prompt, not the harness.
  [Cursor](https://cursor.com/blog/scaling-agents) ·
  [Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) ·
  [OpenAI](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex) ·
  [Simon Willison](https://simonwillison.net/2026/jan/19/scaling-long-running-autonomous-coding/)
- **The implementer must not grade its own work — the generator/verifier gap is real.** LLMs
  are consistently better reviewers than generators; same-mind self-verification reinforces
  its own mistakes ("hallucinated verification"). Separate generation and review prompts give
  ~20% over self-refinement. Prefer *externally checkable* signals (tests, schemas, env
  rewards) over narrative self-reflection. This is exactly why Phase 2 and Phase 5 are a
  **separate** subagent. [generator-verifier gap](https://buildml.substack.com/p/the-verification-problem-why-your) ·
  [verification loops](https://timjwilliams.medium.com/llm-verification-loops-best-practices-and-patterns-07541c854fd8)
- **Review in a fresh context that sees only the diff + criteria, and demand evidence not
  assertions.** A reviewer that never saw the reasoning judges the result on its own terms;
  make it show the command + output, not claim success. Backs the Writer/Reviewer pattern.
  [Claude Code best practices](https://code.claude.com/docs/en/best-practices) ·
  [power-user tips](https://support.claude.com/en/articles/14554000-claude-code-power-user-tips)
- **Run ≥2 review passes and go wide, not deep.** Rounds 1–2 capture ~75% of the gains; cap
  at ~5–6 to avoid oscillation. Any single verifier is itself unreliable — use multiple
  verification strategies rather than one deep loop.
  [verification loops](https://timjwilliams.medium.com/llm-verification-loops-best-practices-and-patterns-07541c854fd8)
- **Reward hacking is the signature long-horizon failure: the agent weakens the test to go
  green.** Benchmarks (SpecBench, ImpossibleBench, EvilGenie) show the validation↔held-out
  gap grows with task length and shrinking models; "the sneakiest version is weakening the
  rule itself" then technically obeying it. Mitigations: treat test files as **read-only**
  during implementation, prefer **held-out tests** the implementer didn't write, flag any
  edit/skip/loosen of tests or hooks, never `--no-verify`. This is Phase 5's goalpost audit.
  [SpecBench](https://arxiv.org/html/2605.21384) ·
  [ImpossibleBench](https://www.lesswrong.com/posts/qJYMbrabcQqCZ7iqm/impossiblebench-measuring-reward-hacking-in-llm-coding-1) ·
  [EvilGenie](https://arxiv.org/pdf/2511.21654) ·
  [cheating the guardrails](https://stevekinney.com/courses/self-testing-ai-agents/making-it-hard-to-cheat-the-guardrails)
- **Survive context resets with a progress artifact + commit-often.** Anthropic's harness uses
  an init agent + a `claude-progress.txt` log + a git commit per session so a fresh context
  can resume from the log and revert bad changes. Watch for "fake completion" — models mark a
  feature done without end-to-end verification, which is why the judge gate matters.
  [Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- **Fight drift with periodic fresh starts + aggressive context management.** Long runs drift
  and tunnel; `/clear`·`/compact` between milestones (plan/Tasks persist on disk) and the
  occasional fresh session keep the agent on-spec. [Addy Osmani](https://addyosmani.com/blog/long-running-agents/)
- **Match the model to the role.** Planner, implementer, and reviewer have different strengths
  — use the best-suited model per seat rather than one universal model.
  [Cursor](https://cursor.com/blog/scaling-agents)

Where the community disagrees: some argue the subagent abstraction is "more theatre than
utility" (it's a system prompt over file-read tools), and that monitoring chain-of-thought as
a reward can backfire (teaching evasion, not honesty). Net: keep the verifier's signal
**externally checkable** (does the test pass on the reviewer's own run?) rather than trusting
introspection.

## Reference (this project's distilled source material)

This skill is distilled from real `/goal` runs in cc-gateway. For worked examples:
- `docs/plans/2026-06-02-goal-prompt.md` — the goal-prompt skeleton in full.
- `docs/plans/2026-06-02-goal-readiness.md` — AC self-verifiability grading (✅/⚠️/❌) + pre-flight.
- `docs/plans/2026-06-02-plan-review.md` — an adversarial plan review with P0 blockers + Given/When/Then ACs.
- `docs/plans/2026-06-03-goal-status.md` — archived/active/deferred status discipline.

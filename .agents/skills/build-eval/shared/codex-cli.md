# Codex CLI host adapter

This project-local port preserves Anthropic's build-eval and hillclimb guides.
Only the host-specific instructions below replace their Claude/API equivalents.
Resolve `shared/...` paths against the loaded skill directory, not the task cwd.
Both skills share this directory; install/update them together.

## Invocation and tools

- `/claude-api build-eval` means `$build-eval`; `/claude-api hillclimb` means
  `$hillclimb`. References to the other eval guide resolve to the other skill.
- Claude as the executing assistant means Codex. Keep the interviews, input and
  grader review, scoped changes, frozen comparisons, audit and stopping rules.
  Existing explicit user authorization remains valid for its stated scope.
- `AskUserQuestion` means the host's user-input tool, or a concise question in
  chat when no suitable tool exists. A pending required answer is not approval.
- `Bash` means the shell tool. Background runs use its session/yield mechanism;
  retain the process handle and await completion. `Agent` means an available
  independent subagent. A headless `-p`/SDK run means `codex exec` here.
- Do not install another skill-creator; use the OpenAI built-in creator.

## Subscription execution

Use the installed `codex` CLI and its saved ChatGPT login, not an Anthropic SDK,
API key, custom provider, or direct subscription-token HTTP request. Check
`codex login status` first; if it is not ChatGPT login, report that prerequisite
without changing account/provider configuration. The helper invokes
`codex exec --ignore-user-config -c 'model_provider="openai"' --ephemeral --json`
with a prompt on stdin. This is an invocation-only override: it keeps saved auth,
does not rewrite config, and avoids inheriting an unrelated custom provider.
Pass the agreed model/effort explicitly since user config is not loaded.

For a new runner, copy `shared/evals/report/runner-scaffold.mjs` **and**
`shared/evals/report/codex-exec.mjs` beside it. Fill `loadCases` and `gradeCase`
as upstream describes; the `runCase` example uses `runCodex`. For existing apps,
keep their real entry point rather than rebuilding the app around this helper.
Every agent case needs its own prepared workspace; do not reuse writable state
across cases or expose answer keys to the tested agent. `read-only` is the helper
default; select `workspace-write` only for an authorized disposable fixture.
Include the helper and any copied report script in `_state.json.harness_paths`.

For a model judge, use an independent `runCodex` call with a blind, fixed rubric
and `outputSchema` when needed. Do not assume it has a different model merely
because it has a fresh context. Use programmatic checks where possible.

## Telemetry differences

The helper preserves the raw CLI events alongside a normalized transcript.
Those are the events the CLI exposes, **not** a claim to capture hidden prompts,
reasoning, every subagent turn, or internal retries. Token usage comes from
`turn.completed`; cached input is separated from noncached input for the upstream
schema. Never infer usage from prompt length or replace missing usage with zero.

Codex JSONL may omit the served model. In that case `model` is absent and
`meta.served_model_verified` is false; `meta.requested_model` is only a request.
Do not claim the upstream served-model audit passed. A comparison requiring
verified server identity needs additional evidence before it can proceed.
CLI errors/timeouts are execution failures, not bad quality scores. The helper
terminates its process group on timeout; keep its timeout within the runner's
case budget (including the grader). Internal CLI retries are not individually
observable here; record that limit instead of inventing a retry count.

Ignore Claude model tables, Claude-specific SDK/structured-output syntax, cache
price multipliers, and API-dollar estimates in the upstream text. Record runs,
latency and actual tokens. Subscription dollars and remaining quota are **not
measured**, not zero. Prefer token/latency objectives; a dollar-cost hillclimb is
unsupported until an applicable, user-agreed cost source exists. Set report
`perf_fields` explicitly, e.g. `in_tokens`, `out_tokens`, `latency_s`.

## Paths and approval boundaries

Use `docs/_local/evals/<flow>/` in this repository instead of the upstream
`.claude/hillclimb/<flow>/`. Keep the upstream files/row schema beneath it.
The skill directory is **inside this project**; it is not protected from edits
by a separate permission boundary. Execute only the pinned, reviewed report
builder under this skill directory (or a reviewed copy included in harness
paths). The harness hash is a change detector, not a security boundary.

The upstream full viewer is optional and not included. Use the bundled lite
builder; do not fetch an unrelated full viewer. This port does not add a human
A/B preference collection UI. Preserve actual human labels as user feedback;
never generate them on the user's behalf. Selection of real tasks and preference
labeling remains a separate step after installation smoke checks.

## Scope of installation verification

A smoke check may validate discovery, loading, subscription execution, usage,
failure handling and report generation using a synthetic fixture. It does not
approve a real dataset/grader, start hillclimbing on existing skills, or establish
that any skill improves task performance.

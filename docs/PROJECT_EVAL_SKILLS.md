# Project evaluation skills

This checkout provides two project-local Codex skills: `$build-eval` and
`$hillclimb`. They adapt Anthropic's `claude-api` subcommands while preserving
the upstream guide bodies. They are development tools for this project, not
part of the user-level skill installers. OpenAI's built-in `skill-creator`
remains the sole creator; Web App Testing is not included.

## Use and scope

Codex discovers `.agents/skills/build-eval/SKILL.md` and
`.agents/skills/hillclimb/SKILL.md` from this repository. No user configuration
change or global installation is needed. Start a new session if the current
session's skill catalog predates the files. The hillclimb entry shares resources
and license through relative symlinks to build-eval; keep both directories
together. This installation is verified on the current Linux/WSL host, not
native Windows.

- `$build-eval`: design representative inputs, calibrate grading, reuse or build
  a runner, and produce a baseline report. Input and grader decisions remain
  user decisions under the original workflow.
- `$hillclimb`: improve an agreed target against an existing, trustworthy eval,
  within the authorized scope and stopping conditions. Do not run it simply
  because a skill file was edited.

Example future requests: “Use $build-eval to design an evaluation for this
skill” or “Use $hillclimb on this approved eval; only change the target skill.”
Installation and smoke checks do not choose those tasks or approve a dataset.
Human A/B preferences are a future evaluation-design input; this installation
does not manufacture labels or add a preference-collection application.

## Minimal adaptation

Upstream: [anthropics/skills](https://github.com/anthropics/skills/tree/8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4/skills/claude-api),
revision `8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4`.
`build-eval/UPSTREAM.json` records original source hashes; `LICENSE.txt` preserves
the Apache-2.0 license. The two main guides become SKILL.md bodies with only
frontmatter and a host-adapter preface added. Audit, cost-hillclimb, report schema
and lite report builder are copied unchanged. The optional full viewer is absent.

`shared/codex-cli.md` maps host tools, paths and telemetry. Conditional Claude
model-migration and API-cost references have small Codex replacements instead
of importing unrelated API manuals. The runner scaffold changes only its model
call, local output path and CLI metadata/raw-event persistence. New helper
`codex-exec.mjs` uses saved ChatGPT authentication, checks login, and invokes the
built-in OpenAI provider with `--ignore-user-config`; this per-process setting
does not rewrite a custom provider or the user's files. No API key is required.
Pass the selected model/effort explicitly. Never treat a requested model name
as observed server identity when the CLI omits that field.

The adapter retains visible CLI JSONL, normalized messages and token usage.
It does not claim hidden context, internal retry details, subscription dollars,
remaining quota, or a complete account of hidden subagent work. Grading uses
the same run that produced the trace. Timeout terminates the subprocess group
on this host. The default sandbox is read-only; writable agent evaluations
need disposable, individually prepared workspaces.

For a new runner, copy both `runner-scaffold.mjs` and `codex-exec.mjs`, implement
the task-specific case loader/grader, and include the helper in
`_state.json.harness_paths`. Use `docs/_local/evals/<flow>/` for private results.
The upstream harness hash detects changes; project-local skill files are not
a permission boundary. An approved installation smoke does not approve later
unattended optimization runs.

## Verification and updates

Run the adapter tests without model calls:

```bash
node --test tests/test_codex_eval_adapter.mjs
python3 -m unittest tests.test_project_eval_skills
```

Native smoke checks require saved ChatGPT login and consume subscription usage.
Use a synthetic fixture to check discovery/loading, a baseline and a second
variant, raw events, token accounting, resume and report generation. Scores on
that fixture establish plumbing only, not skill quality or optimization gains.

Initial local verification (2026-09-30): a fresh Codex CLI session read both
skills and the adapter; two real subscription calls completed the synthetic
baseline/v1 fixture and produced raw events, usage, traces and the lite report.
Rerunning v1 scheduled zero calls. Deliberately changing the copied helper made
the harness gate reject before execution. The three packaging checks and eight
adapter behavior checks passed, including failed-login and process-group timeout
cases. Config, auth and CC Switch DB hashes were unchanged across those checks.
This is evidence for this host and pinned port, not a general skill benchmark.

Upstream trailing whitespace is intentionally retained in the copied guides,
schema and scaffold to avoid unrelated source changes.

Before deploying changes, run the repository target guard as required by
AGENTS.md. Project-only installation uses its path-only mode; a host without
the CC Switch CLI may skip its CLI read check while still checking profile
paths and contamination. Do not alter provider settings to satisfy a deployment
check unrelated to these local files.

Update by choosing a new upstream revision, comparing the source hashes and
port diff, and rerunning the tests. Do not track upstream main automatically.
Removing both project skill directories removes their discovery entries; no
user-level installation or account state needs rollback.

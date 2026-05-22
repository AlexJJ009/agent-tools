---
name: experiment-registry
description: Use this when querying, importing, validating, or maintaining the local SQLite experiment registry for DPO and verl experiment results. The registry is agent-readable structured memory for completed experiments, checkpoints, training metadata, eval parameters, metrics, trust status, and source artifact paths.
---

# Experiment Registry

Use the registry before scanning long experiment markdown files when the user
asks for historical DPO, RL, or selected verl experiment facts, comparisons,
model weight paths, training params, eval params, final metrics, or stale/buggy
result status.

## Context Loading Rules

Load this skill when the task is about the experiment registry itself or about
records that should be in it:

- querying previous DPO, RL, verl, WDL-SFT, ablation, or branch experiment
  results;
- comparing experiments, branches, methods, model paths, checkpoints, datasets,
  or metrics;
- importing new training/eval results into SQLite;
- validating source artifacts against database values;
- marking rows as `trusted`, `usable_with_caution`, `needs_review`, `buggy`, or
  `superseded`;
- repairing registry docs, schema usage, canned queries, branch forms, or
  agent-facing registry rules;
- answering "where is this result recorded?" or "which source file supports
  this metric?".

Do not load this skill for unrelated local coding work, live training health
checks, GPU/Docker readiness checks, fresh training launches, checkpoint
cleanup, general documentation edits outside experiment bookkeeping, or model
evaluation execution before the user asks to record/query the result. For those
tasks, use the relevant project workflow first; load this skill only when the
result needs registry lookup, import, validation, or archival.

If the user asks for current/live status, verify live logs/processes first. Use
the registry only as historical context, and clearly separate database state
from live state.

## Locate

Registry data-directory index:

```bash
/data-1/experiment_registry/README.md
```

Preferred database:

```bash
/data-1/experiment_registry/experiment_registry.sqlite
```

Branch/project management policy:

```bash
/data-1/agent-tools/experiment_registry/BRANCH_MANAGEMENT.md
```

Use one shared database by default. Separate new algorithm branches with
`projects.name = verl:<git-branch>` plus `git_branch` / `git_commit` columns,
not with ad hoc new SQLite files or duplicate physical metric tables.

Tooling:

```bash
/data-1/agent-tools/experiment_registry
```

Fallback tooling in the DPO repo:

```bash
/data-1/dpo-experiment/experiment_registry
```

If `/data-1/agent-tools/experiment_registry` is absent, use the fallback path.
Do not edit fallback copies when the agent-tools path exists; project-local
registry directories should be symlinks or thin pointers to agent-tools.

## Read

Use read-only canned queries first:

```bash
cd /data-1/agent-tools/experiment_registry
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite query --name dpo-code-n1
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite query --name dpo-math-best
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite query --name best-bcb-model
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite query --name verl-v123
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite query --name needs-review
```

For ad hoc SQL, keep it read-only:

```bash
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite query --sql "select * from experiments limit 20"
```

Return concise Markdown tables to humans and include source paths when the user
needs traceability.

## Import

Initialize and import:

```bash
cd /data-1/agent-tools/experiment_registry
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite init
python3 import_dpo.py --db /data-1/experiment_registry/experiment_registry.sqlite --repo /data-1/dpo-experiment
python3 import_verl.py --db /data-1/experiment_registry/experiment_registry.sqlite --repo /data-1/verl07/verl --branch feature/on-policy-wdl-sft
python3 validate_imports.py --db /data-1/experiment_registry/experiment_registry.sqlite
```

Imports are idempotent. They copy metadata into SQLite and preserve source
paths. They must not delete, rewrite, move, or clean original experiment files.

For new branch-specific imports, preserve:

- branch-scoped `project_id`, for example `verl:feature/on-policy-wdl-sft`
- stable branch-scoped `experiment_key`
- `git_branch` and `git_commit`
- source files in `artifacts` and `source_records`
- source-vs-database checks in `validation_checks`

Do not import values from memory or conversation summaries. Parse the original
training logs, training metrics JSONL, eval metrics JSON, validation JSONL,
checkpoint metadata JSON, and launch scripts.

## Update

Add simple metadata:

```bash
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite upsert-experiment --project dpo --experiment-key dpo.dpo.code.qwen3_4b.new.step1 --display-name new --method dpo --domain code --trust-level needs_review
```

Mark stale or bad evals instead of deleting:

```bash
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite mark-eval --eval-id 123 --trust-level superseded --notes "Replaced by parser-fix rerun"
```

Use `trusted`, `usable_with_caution`, `needs_review`, `buggy`, or `superseded`.

## Validation

After imports or meaningful updates, run:

```bash
cd /data-1/agent-tools/experiment_registry
python3 validate_imports.py --db /data-1/experiment_registry/experiment_registry.sqlite
```

Check the report path printed by the command. If validation fails, inspect the
source path and database row before trusting the imported result.

## Safety

Never overwrite or delete source experiment artifacts. Do not hide old results;
mark them with trust status and notes. Treat high extraction failure, parser
bugs, preamble fixes, and pre-fix verl `wdl_sft_is` runs as queryable caveats,
not as reasons to erase rows.

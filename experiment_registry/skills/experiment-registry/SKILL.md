---
name: experiment-registry
description: Use this when querying, importing, validating, or maintaining the local SQLite experiment registry for DPO and verl experiment results. The registry is agent-readable structured memory for completed experiments, checkpoints, training metadata, eval parameters, metrics, trust status, and source artifact paths.
---

# Experiment Registry

Use the registry before scanning long experiment markdown files when the user
asks for historical DPO or selected verl experiment facts, comparisons, model
weight paths, training params, eval params, final metrics, or stale/buggy result
status.

## Locate

Preferred database:

```bash
/data-1/experiment_registry/experiment_registry.sqlite
```

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

# Local Experiment Registry

This directory implements the SQLite registry described in
`docs/experiment_registry_plan.md`.

The registry is not a TensorBoard or WandB replacement. It stores searchable
metadata, final/latest/best checkpoint references, evaluation parameters,
row-wise metrics, trust status, known issues, and source paths so coding agents
can answer experiment-history questions without rereading long markdown files.

## Paths

Preferred database:

```bash
/data-1/experiment_registry/experiment_registry.sqlite
```

Canonical tooling source:

```bash
/data-1/agent-tools/experiment_registry
```

Project-local registry directories and skills should be symlinks to the
canonical tooling. The DPO repo copy is only a fallback for older checkouts, not
the primary edit location.

Expected links on this machine:

```bash
/data-1/dpo-experiment/experiment_registry -> /data-1/agent-tools/experiment_registry
/data-1/dpo-experiment/.codex/skills/experiment-registry -> /data-1/agent-tools/experiment_registry/skills/experiment-registry
/data-1/verl07/verl/.codex/skills/experiment-registry -> /data-1/agent-tools/experiment_registry/skills/experiment-registry
```

## Commands

No third-party packages are required.

```bash
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite init
python3 import_dpo.py --db /data-1/experiment_registry/experiment_registry.sqlite --repo /data-1/dpo-experiment
python3 import_verl.py --db /data-1/experiment_registry/experiment_registry.sqlite --repo /data-1/verl07/verl --branch feature/on-policy-wdl-sft
python3 validate_imports.py --db /data-1/experiment_registry/experiment_registry.sqlite
python3 registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite query --name dpo-code-n1
```

`uv run` also works if the environment uses UV:

```bash
uv run registry_cli.py --db /data-1/experiment_registry/experiment_registry.sqlite query --name needs-review
```

## Canned Queries

List query names:

```bash
python3 registry_cli.py query --list
```

Available v0 queries:

- `dpo-code-n1`: DPO code evaluations with `n=1`, `temperature=0`.
- `dpo-math-best`: DPO math comparison with sampling params and extraction
  failure.
- `best-bcb-model`: best BigCodeBench n=1 DPO result with model/training/eval
  paths.
- `verl-v123`: selected verl on-policy-wdl-sft V1/V2/V3 comparison.
- `needs-review`: rows marked `buggy`, `superseded`, `needs_review`, or
  `usable_with_caution`.

Ad hoc read-only SQL:

```bash
python3 registry_cli.py query --sql "select count(*) from eval_metrics"
```

The CLI rejects non-`SELECT` / non-`WITH` SQL in `query`.

## Updates

Add or update a simple experiment row:

```bash
python3 registry_cli.py upsert-experiment \
  --project dpo \
  --experiment-key dpo.dpo.code.qwen3_4b.example.step1 \
  --display-name example \
  --method dpo \
  --domain code \
  --trust-level needs_review
```

Mark an evaluation:

```bash
python3 registry_cli.py mark-eval --eval-id 123 --trust-level superseded --notes "Replaced by parser-fix rerun"
```

Do not delete or rewrite source experiment artifacts. Old rows should normally
be marked `superseded`, `buggy`, or `needs_review`.

## Install Links

On a new Linux or WSL machine, install project-local links from agent-tools:

```bash
/path/to/agent-tools/experiment_registry/install_registry_links.sh --init-db
```

The script creates the machine-local database directory and only initializes the
SQLite file when `--init-db` is passed and the file is missing. It does not
commit or move the database. Use `--force` only when replacing an existing
project-local copy with a symlink is intentional.

Validate the setup:

```bash
/path/to/agent-tools/experiment_registry/validate_registry_install.sh
```

## Validation

`validate_imports.py` writes a Markdown spot-check report and records checks in
the `validation_checks` table. The required checks cover:

- DPO code HumanEval/MBPP.
- DPO code BigCodeBench.
- DPO code LiveCodeBench.
- DPO math `eval_metrics.json`.
- High extraction-failure math result.
- verl V1 and V2 offline eval metrics.

## Schema Notes

Metrics are row-wise in `eval_metrics`, not fixed benchmark columns. Lineage is
represented by `experiment_links` and `eval_run_links`. Known issues are
queryable through `trust_level`, `trust_reason`, and `quality_flags`. Extra
project-specific data is preserved as JSON where needed.

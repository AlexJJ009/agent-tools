# Branch-Scoped Experiment Registry Management

This registry is the shared experiment database for DPO, RL, WDL-SFT, and future
algorithm branches. Use one SQLite database and one schema. Do not create a new
database for every algorithm unless the data is operationally unrelated or must
have different access control.

## Storage Boundary

Use `projects` as the human-facing "form" boundary.

- Historical DPO imports stay under `projects.name = dpo`.
- Historical verl aggregate imports may stay under `projects.name = verl`.
- New branch-scoped work should use `projects.name = verl:<git-branch>`.

Examples:

```text
verl:feature/on-policy-wdl-sft
verl:feature/new-algorithm-name
verl:ablation/some-branch
```

Every branch-scoped `experiments`, `training_runs`, `eval_runs`, and `models`
row must also carry `git_branch` and, when available, `git_commit`. This keeps
the branch boundary visible even when querying without joining `projects`.

## What Goes In This Database

Store experiments here when they need to be compared, traced, or reused by
agents:

- DPO training and evaluation results.
- RL or verl training runs.
- Standalone input-model evaluations that explain a later training result.
- Ablation and negative-result experiments.
- Future algorithm branches, as long as their results should be compared with
  the existing DPO/RL/verl records.

Use a new database only when the experiment family is not comparable to these
records, requires a materially different schema, or has different privacy or
retention rules.

## Required Fields

For every imported experiment-like record, preserve these fields where they are
available from source artifacts:

- `project_id`: branch or project form, such as `verl:feature/on-policy-wdl-sft`.
- `experiment_key`: stable, unique, branch-scoped key.
- `display_name`: readable name including branch, method, run, and role.
- `method`, `method_family`, `method_variant`, `method_version`.
- `domain`, `variant`, `status`, `trust_level`, `trust_reason`.
- `git_branch`, `git_commit`.
- source paths in `artifacts` and `source_records`.

For training runs, also record:

- input and output model ids.
- train and validation dataset ids.
- key hyperparameters in first-class columns when possible.
- remaining launcher/config details in `hyperparams_json`.
- step-wise scalar metrics in `training_metrics`.

For eval runs, also record:

- model id and model role.
- `n`, `temperature`, `top_p`, `top_k`, `do_sample`, `max_tokens`, `seed`.
- prompt mode, system prompt mode, harness, command, cwd, hostname.
- per-dataset metrics in row-wise `eval_metrics`.

## Source-of-Truth Rule

Do not import values from memory or conversation summaries. Import values from
the original local artifacts:

- training logs.
- training metrics JSONL.
- eval metrics JSON.
- eval details parquet paths.
- validation JSONL.
- checkpoint metadata JSON.
- launch scripts and resolved config in logs.

Every import should add `artifacts` and `source_records` for the files used.
Important imports should add `validation_checks` comparing source values against
database values.

## Archival Policy

Do not delete old rows just because they are stale, buggy, or superseded. Mark
them:

- `trusted`: source artifacts and parser are reliable.
- `usable_with_caution`: usable but has known caveats.
- `needs_review`: imported or documented, but not yet fully validated.
- `buggy`: known bad parser, implementation, or measurement issue.
- `superseded`: replaced by a later run or parser-fix rerun.

Use `quality_flags` for specific caveats such as parser bugs, high extraction
failure, branch-specific implementation mismatch, or incomplete source
coverage.

## Queryability Contract

No imported result should be "only visible if you know the path." At minimum, it
must be discoverable by:

- project or branch.
- method or method family.
- model path or model role.
- dataset name.
- metric name.
- trust level.
- source artifact path.

Prefer adding canned SQL queries or views for common workflows instead of
creating duplicate physical tables.

## Branch Views

For spreadsheet-like branch forms, create SQLite views over the unified schema.
The views should filter by `projects.name`, not duplicate data.

Suggested view naming:

```text
view_verl_feature_on_policy_wdl_sft_experiments
view_verl_feature_on_policy_wdl_sft_training_metrics
view_verl_feature_on_policy_wdl_sft_eval_metrics
```

This gives branch-local readability while preserving cross-branch comparison.

## Import Naming

Use branch-scoped keys:

```text
verl.branch.<branch_slug>.<method_variant>.<run_or_eval_name>
```

Examples:

```text
verl.branch.feature_on_policy_wdl_sft.wdl_sft_is.labelfix_1a.1779075938
verl.branch.feature_on_policy_wdl_sft.model2_standalone.qwen3_4b_base_sft_stage_1.greedy_n1_7sets.20260519
```

Standalone input-model evaluations should be separate experiments and linked to
training experiments with `experiment_links`, for example
`uses_input_model2_eval`.


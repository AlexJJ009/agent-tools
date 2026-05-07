# Experiment Registry Completion Audit

Checked at: 2026-05-03.

## Objective

Implement `docs/experiment_registry_plan.md`: schema, SQLite initialization,
DPO import, selected verl `feature/on-policy-wdl-sft` import, agent skill,
query CLI, validation reports, and acceptance queries.

## Evidence

| Requirement | Evidence | Status |
|---|---|---|
| v0 schema documented | `experiment_registry/schema.sql`, `experiment_registry/README.md` | PASS |
| SQLite initialization works | `python3 experiment_registry/registry_cli.py --db experiment_registry/test_registry_v4.sqlite init` | PASS |
| DPO importer exists and runs | `experiment_registry/import_dpo.py`; imported 31 DPO eval runs on fresh DB | PASS |
| verl importer exists and runs | `experiment_registry/import_verl.py`; imported V1/V2 plus V3 placeholder evidence | PASS |
| Row-wise arbitrary metrics | `eval_metrics` has 1314 rows in local validation DB | PASS |
| Source paths preserved | `source_records` has 61 stable records after rerun; no duplicate growth | PASS |
| DPO import idempotent | Fresh DB summary stayed at 46 eval runs, 1314 metrics, 61 source records after rerun | PASS |
| verl import idempotent | Same rerun summary; V1/V2/V3 relation records stable | PASS |
| Spot-check validation | `experiment_registry/reports/validation_report.md`; 8/8 checks PASS | PASS |
| Required DPO code n=1 query | `registry_cli.py query --name dpo-code-n1` returns Qwen3-4B Code-SFT, Code-M1, WDL-v3 with HE/MBPP/BCB/LCB where present | PASS |
| Required DPO math query | `registry_cli.py query --name dpo-math-best` returns Qwen/Gemma math runs and extraction failures | PASS |
| Required BigCodeBench model query | `registry_cli.py query --name best-bcb-model` returns model path, training data/params, eval output/source | PASS |
| Required verl V1/V2/V3 query | `registry_cli.py query --name verl-v123` returns V1/V2 metrics and V3 needs-review placeholder | PASS |
| Required needs-review query | `registry_cli.py query --name needs-review` returns buggy, needs-review, usable-with-caution rows and reasons | PASS |
| Skill instructions | `experiment_registry/skills/experiment-registry/SKILL.md` | PASS |
| Claude-compatible instructions | `experiment_registry/CLAUDE_EXPERIMENT_REGISTRY.md` | PASS |
| Skill read/update/mark flows exercised | `query --list`, `upsert-experiment`, and `mark-eval` succeeded on local test DB | PASS |
| Preferred DB path `/data-1/experiment_registry/experiment_registry.sqlite` | Exists, 520192 bytes, initialized/imported by deployment script | PASS |
| Preferred tooling path `/data-1/agent-tools/experiment_registry` | Exists with schema, CLI, importers, validator, queries, README, skill | PASS |
| Codex-compatible skill | `/data-1/agent-tools/experiment_registry/skills/experiment-registry/SKILL.md` | PASS |
| Project-local Codex skill mirror | `.codex/skills/experiment-registry/SKILL.md` | PASS |
| Project-local Claude skill mirror | `.claude/skills/experiment-registry/SKILL.md` | PASS |
| One-shot deployment script | `experiment_registry/deploy_to_global_paths.sh` | PASS |

## Current Local Validation Database

`experiment_registry/test_registry_v5.sqlite`

Counts after rerun:

| Table | Rows |
|---|---:|
| projects | 2 |
| experiments | 16 |
| models | 32 |
| datasets | 21 |
| training_runs | 8 |
| eval_runs | 46 |
| eval_metrics | 1314 |
| artifacts | 62 |
| source_records | 61 |

Additional post-audit fixes:

- `registry_cli.py init --db ...` and `registry_cli.py --db ... init` both work.
- DPO experiment keys now recover checkpoint step from source paths when possible
  (`code_sft.step45`, `code_m1.step50`).

## Final Official Deployment Evidence

The deployment script ran successfully after escalation approval recovered:

- Tooling path: `/data-1/agent-tools/experiment_registry`
- Database path: `/data-1/experiment_registry/experiment_registry.sqlite`
- Validation report: `/data-1/agent-tools/experiment_registry/reports/validation_report.md`
- Required query templates: `/data-1/agent-tools/experiment_registry/queries/`
- Codex skill: `/data-1/agent-tools/experiment_registry/skills/experiment-registry/SKILL.md`
- Project-local Codex skill mirror: `/data-1/dpo-experiment/.codex/skills/experiment-registry/SKILL.md`
- Project-local Claude skill mirror: `/data-1/dpo-experiment/.claude/skills/experiment-registry/SKILL.md`
- Claude-compatible instructions: `/data-1/agent-tools/experiment_registry/CLAUDE_EXPERIMENT_REGISTRY.md`

Official DB summary after idempotency rerun:

| Table | Rows |
|---|---:|
| projects | 2 |
| experiments | 15 |
| models | 32 |
| datasets | 21 |
| training_runs | 8 |
| eval_runs | 46 |
| eval_metrics | 1314 |
| artifacts | 62 |
| source_records | 61 |

Validation checks in the official DB: 8 PASS, 0 FAIL.

Experiment lineage links in the official DB:

| link_type | Rows |
|---|---:|
| derived_from | 1 |
| bugfix_of | 1 |

No remaining blocker is known.

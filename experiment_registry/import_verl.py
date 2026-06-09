#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from registry_core import (
    add_artifact,
    add_db_arg,
    add_quality_flag,
    add_source_record,
    add_tag,
    connect,
    init_db,
    load_json,
    slug,
    upsert_dataset,
    upsert_eval_run,
    upsert_experiment,
    upsert_metric,
    upsert_model,
    upsert_project,
)


IMPORTER = "import_verl_v1"
ONLINE_IMPORTER = "import_verl_online_v1"

METHODS = {
    "MATH-M5-5": ("EXP-13", "v1", "wdl_sft", "v1_wdl_sft", "trusted", "V1 forward-only baseline"),
    "WDL-SFT-M5-5": ("EXP-13", "v1", "wdl_sft", "v1_wdl_sft", "trusted", "V1 forward-only baseline"),
    "MATH-M5-6": ("EXP-14", "v1", "wdl_sft", "v1_wdl_sft", "usable_with_caution", "V1 beta=0.1; model1 format collapse caution"),
    "WDL-SFT-M5-6": ("EXP-14", "v1", "wdl_sft", "v1_wdl_sft", "usable_with_caution", "V1 beta=0.1; model1 format collapse caution"),
    "MATH-LR3": ("EXP-15", "v1", "wdl_sft", "v1_wdl_sft", "usable_with_caution", "V1 lr=1e-6 stopped early; best step 125"),
    "WDL-SFT-LR3": ("EXP-15", "v1", "wdl_sft", "v1_wdl_sft", "usable_with_caution", "V1 lr=1e-6 stopped early; best step 125"),
    "MATH-1A": ("EXP-16", "v2", "wdl_sft_is", "v2_wdl_sft_is_prefix", "buggy", "Pre-fix wdl_sft_is used GRPO-centered advantages as labels"),
    "MATH-1B": ("EXP-17", "v2", "wdl_sft_is", "v2_wdl_sft_is_prefix", "buggy", "Pre-fix wdl_sft_is label bug; beta=0.1 anchor collapse"),
    "MATH-1C": ("EXP-18", "v2", "wdl_sft_is", "v2_wdl_sft_is_prefix", "buggy", "Pre-fix wdl_sft_is label bug"),
    "2Z-SFT": ("ABL-MINIRL-01", "ablation", "minirl", "single_model_minirl_sft", "trusted", "Single-model MiniRL SFT-init baseline"),
    "2A-SFT": ("ABL-MINIRL-02", "ablation", "wdl_sft_is", "single_model_wdl_sft_is_sft", "usable_with_caution", "Pre-fix wdl_sft_is single-model SFT-init ablation"),
    "2A-BASE-LABELFIX": ("LABELFIX-2A-BASE", "v3", "wdl_sft_is", "v3_wdl_sft_is_labelfix", "needs_review", "V3 label-fix checkpoint present but logs/extraction/offline eval missing"),
}

EVAL_PATTERNS = [
    "/data-1/model_weights/WDL-SFT-4B-MATH-M5-5/*/inference_n3/eval_metrics.json",
    "/data-1/model_weights/WDL-SFT-4B-MATH-M5-6/*/inference_n3/eval_metrics.json",
    "/data-1/model_weights/WDL-SFT-4B-MATH-LR3/*/inference_n3/eval_metrics.json",
    "/data-1/model_weights/WDL-SFT-4B-MATH-1A/*/inference_n3/eval_metrics.json",
    "/data-1/model_weights/WDL-SFT-4B-MATH-1B/*/inference_n3/eval_metrics.json",
    "/data-1/model_weights/WDL-SFT-4B-MATH-1C/*/inference_n3/eval_metrics.json",
    "/data-1/model_weights/MINIRL-Qwen3-4B-MATH-2Z-SFT/*/inference_n3/eval_metrics.json",
    "/data-1/model_weights/WDL-SFT-Qwen3-4B-MATH-2A-SFT/*/inference_n3/eval_metrics.json",
]

ONLINE_JSONL_RUNS = {
    "WDL-SFT-Qwen3-4B-MATH-M5-5_1775980322": ("EXP-13", "v1_wdl_sft", "wdl_sft", "v1", "trusted", "Online validation curve for V1 M5.5 forward-only baseline"),
    "WDL-SFT-Qwen3-4B-MATH-M5-6_1776095760": ("EXP-14", "v1_wdl_sft", "wdl_sft", "v1", "usable_with_caution", "Online validation curve for V1 M5.6 beta=0.1; offline model1 collapse caveat"),
    "WDL-SFT-Qwen3-4B-MATH-LR3_1776359574": ("EXP-15", "v1_wdl_sft", "wdl_sft", "v1", "usable_with_caution", "Online validation curve for V1 LR3; later drift after promoted step"),
    "Baseline-MiniRL-Qwen3-1.7B-MATH-GC500_1773643860": ("EXP-06", "joint_minirl_gc500", "minirl", "joint_training", "trusted", "Online validation curve for grad-clip fixed MiniRL baseline"),
    "Baseline-MiniRL-Qwen3-1.7B-MATH_1773625595": ("EXP-05", "joint_minirl_gc1", "minirl", "joint_training", "usable_with_caution", "Online validation curve for MiniRL baseline with grad_clip=1.0 issue"),
    "Joint-MiniRL-Qwen3-1.7B-MATH-GC500-Dual-Step680_1773714465": ("EXP-07", "joint_minirl_gc500_dual", "minirl", "joint_training", "usable_with_caution", "Online validation curve for dual MiniRL run; late extraction-failure regression caveat"),
    "Joint-GRPO-Qwen3-1.7B-GSM8K_1773500863": ("EXP-01", "joint_grpo_gsm8k", "grpo", "joint_training", "trusted", "Online validation curve for sane Joint-GRPO GSM8K run"),
}

ONLINE_WANDB_TABLE_RUNS = {
    "WDL-SFT-Qwen3-4B-MATH-2A-BASE-LABELFIX": (
        "/data-1/wandb_runs/WDL-SFT-Qwen3-4B-MATH-2A-BASE-LABELFIX/wandb/offline-run-20260428_033322-kto2ukn2/files/media/table/val/*.table.json",
        "LABELFIX-2A-BASE",
        "v3_wdl_sft_is_labelfix",
        "wdl_sft_is",
        "v3",
        "needs_review",
        "W&B online validation samples for 2A label-fix; offline extraction/loadability not verified",
    )
}

CODE_TASK_RETENTION_RUNS = [
    {
        "stage": "stage1",
        "beta_label": "beta0",
        "beta": 0.0,
        "run_name": "ONPOLICY-SFT-Qwen3-4B-CODE-KODCODE-S1-BETA0-V2-RETENTION-R2_1780811946",
        "experiment_key": "verl.on_policy_wdl_sft.code.kodcode_s1_beta0_v2_retention_r2.step150",
        "display_name": "On-Policy SFT Code KodCode S1 beta=0.0 V2 retention R2 step150",
        "method": "on_policy_sft",
        "method_variant": "stage1_retention_r2",
        "total_steps": 150,
        "checkpoint_root": "/data-1/checkpoints/ONPOLICY-SFT-Qwen3-4B-CODE-KODCODE-S1-BETA0-V2-RETENTION-R2_1780811946",
        "metrics_rel": "recipe/on_policy_wdl_sft/code_task/metrics/OnPolicyWDLSFT-CodeTask/ONPOLICY-SFT-Qwen3-4B-CODE-KODCODE-S1-BETA0-V2-RETENTION-R2_1780811946.jsonl",
        "log_rel": "recipe/on_policy_wdl_sft/code_task/ONPOLICY-SFT-Qwen3-4B-CODE-KODCODE-S1-BETA0-V2-RETENTION-R2_1780811946.log",
        "queue_status_rel": "recipe/on_policy_wdl_sft/code_task/run_code_task_retention_queue_status.tsv",
        "train_dataset_key": "code.kodcode_light_rl_10k.train",
        "train_dataset_path": "/data-1/dataset/code/verl_rl/kodcode_light_rl_10k_train_rl_format.parquet",
        "train_dataset_rows": 10000,
        "protected_steps": [70, 80, 90, 100, 110, 120],
        "older_experiment_key": "verl.on_policy_wdl_sft.code.kodcode_s1_beta0_v2.step150",
    },
    {
        "stage": "stage1",
        "beta_label": "beta01",
        "beta": 0.1,
        "run_name": "ONPOLICY-SFT-Qwen3-4B-CODE-KODCODE-S1-BETA01-V2-RETENTION-R2_1780833499",
        "experiment_key": "verl.on_policy_wdl_sft.code.kodcode_s1_beta01_v2_retention_r2.step150",
        "display_name": "On-Policy SFT Code KodCode S1 beta=0.1 V2 retention R2 step150",
        "method": "on_policy_sft",
        "method_variant": "stage1_retention_r2",
        "total_steps": 150,
        "checkpoint_root": "/data-1/checkpoints/ONPOLICY-SFT-Qwen3-4B-CODE-KODCODE-S1-BETA01-V2-RETENTION-R2_1780833499",
        "metrics_rel": "recipe/on_policy_wdl_sft/code_task/metrics/OnPolicyWDLSFT-CodeTask/ONPOLICY-SFT-Qwen3-4B-CODE-KODCODE-S1-BETA01-V2-RETENTION-R2_1780833499.jsonl",
        "log_rel": "recipe/on_policy_wdl_sft/code_task/ONPOLICY-SFT-Qwen3-4B-CODE-KODCODE-S1-BETA01-V2-RETENTION-R2_1780833499.log",
        "queue_status_rel": "recipe/on_policy_wdl_sft/code_task/run_code_task_retention_queue_status.tsv",
        "train_dataset_key": "code.kodcode_light_rl_10k.train",
        "train_dataset_path": "/data-1/dataset/code/verl_rl/kodcode_light_rl_10k_train_rl_format.parquet",
        "train_dataset_rows": 10000,
        "protected_steps": [70, 80, 90, 100, 110, 120],
        "older_experiment_key": "verl.on_policy_wdl_sft.code.kodcode_s1_beta01_v2.step150",
    },
    {
        "stage": "stage2",
        "beta_label": "beta0",
        "beta": 0.0,
        "run_name": "CODE-S2-RETENTION-BETA0-BETA0_1780898035",
        "experiment_key": "verl.on_policy_wdl_sft.code.kodcode_s2_p70_retention_beta0.step30",
        "display_name": "On-Policy WDL-SFT Code Stage2 P70 beta=0.0 step30",
        "method": "on_policy_wdl_sft",
        "method_variant": "stage2_p70_model2_rollout_retention",
        "total_steps": 30,
        "handoff_step": 70,
        "stage1_experiment_key": "verl.on_policy_wdl_sft.code.kodcode_s1_beta0_v2_retention_r2.step150",
        "stage1_metrics_rel": "recipe/on_policy_wdl_sft/code_task/metrics/OnPolicyWDLSFT-CodeTask/ONPOLICY-SFT-Qwen3-4B-CODE-KODCODE-S1-BETA0-V2-RETENTION-R2_1780811946.jsonl",
        "checkpoint_root": "/data-1/checkpoints/CODE-S2-RETENTION-BETA0-BETA0_1780898035",
        "metrics_rel": "recipe/on_policy_wdl_sft/staged_v1/metrics/OnPolicyWDLSFT-CodeTask/CODE-S2-RETENTION-BETA0-BETA0_1780898035.jsonl",
        "validation_rel": "recipe/on_policy_wdl_sft/staged_v1/validation/CODE-S2-RETENTION-BETA0-BETA0_1780898035",
        "log_rel": "recipe/on_policy_wdl_sft/staged_v1/CODE-S2-RETENTION-BETA0-BETA0_1780898035.log",
        "queue_status_rel": "recipe/on_policy_wdl_sft/code_task/run_code_task_stage2_retention_queue_status.tsv",
        "train_dataset_key": "code.kodcode_stage2_after_s1_seed20260604_beta0_p70_handoff.train",
        "train_dataset_path": "/data-1/dataset/code/verl_rl/kodcode_stage2_after_s1_seed20260604_beta0_p70_handoff.parquet",
        "manifest_path": "/data-1/dataset/code/verl_rl/kodcode_stage2_after_s1_seed20260604_beta0_p70_handoff.manifest.json",
        "model2_path": "/data-1/model_weights/code_task/stage2_retention/beta0/step_70",
        "provenance_path": "/data-1/model_weights/code_task/stage2_retention/beta0/step_70/stage1_source.json",
    },
    {
        "stage": "stage2",
        "beta_label": "beta01",
        "beta": 0.1,
        "run_name": "CODE-S2-RETENTION-BETA01-BETA01_1780902470",
        "experiment_key": "verl.on_policy_wdl_sft.code.kodcode_s2_p70_retention_beta01.step30",
        "display_name": "On-Policy WDL-SFT Code Stage2 P70 beta=0.1 step30",
        "method": "on_policy_wdl_sft",
        "method_variant": "stage2_p70_model2_rollout_retention",
        "total_steps": 30,
        "handoff_step": 70,
        "stage1_experiment_key": "verl.on_policy_wdl_sft.code.kodcode_s1_beta01_v2_retention_r2.step150",
        "stage1_metrics_rel": "recipe/on_policy_wdl_sft/code_task/metrics/OnPolicyWDLSFT-CodeTask/ONPOLICY-SFT-Qwen3-4B-CODE-KODCODE-S1-BETA01-V2-RETENTION-R2_1780833499.jsonl",
        "checkpoint_root": "/data-1/checkpoints/CODE-S2-RETENTION-BETA01-BETA01_1780902470",
        "metrics_rel": "recipe/on_policy_wdl_sft/staged_v1/metrics/OnPolicyWDLSFT-CodeTask/CODE-S2-RETENTION-BETA01-BETA01_1780902470.jsonl",
        "validation_rel": "recipe/on_policy_wdl_sft/staged_v1/validation/CODE-S2-RETENTION-BETA01-BETA01_1780902470",
        "log_rel": "recipe/on_policy_wdl_sft/staged_v1/CODE-S2-RETENTION-BETA01-BETA01_1780902470.log",
        "queue_status_rel": "recipe/on_policy_wdl_sft/code_task/run_code_task_stage2_retention_queue_status.tsv",
        "train_dataset_key": "code.kodcode_stage2_after_s1_seed20260604_beta01_p70_handoff.train",
        "train_dataset_path": "/data-1/dataset/code/verl_rl/kodcode_stage2_after_s1_seed20260604_beta01_p70_handoff.parquet",
        "manifest_path": "/data-1/dataset/code/verl_rl/kodcode_stage2_after_s1_seed20260604_beta01_p70_handoff.manifest.json",
        "model2_path": "/data-1/model_weights/code_task/stage2_retention/beta01/step_70",
        "provenance_path": "/data-1/model_weights/code_task/stage2_retention/beta01/step_70/stage1_source.json",
    },
]

MARKDOWN_SOURCES = [
    "recipe/on_policy_wdl_sft/EXPERIMENT_INDEX.md",
    "recipe/on_policy_wdl_sft/INFERENCE_RESULTS.md",
    "docs/joint_training/plans/active/wdl_sft_is.md",
    "docs/joint_training/plans/active/ablation_single_model.md",
]


def existing_paths(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    for pattern in patterns:
        out.extend(sorted(Path("/").glob(pattern.lstrip("/"))))
    return out


def classify(model_path: str) -> tuple[str, str, str, str, str, str]:
    normalized = model_path.upper().replace("_", "-")
    for marker, values in METHODS.items():
        if marker in normalized:
            return values
    return ("UNKNOWN", "unknown", "wdl_sft", "unknown", "needs_review", "Unclassified verl WDL-SFT artifact")


def step_from_path(path: str) -> int | None:
    m = re.search(r"step_(\d+)|global_step_(\d+)", path)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def step_from_eval_file(path: Path, rows: list[dict[str, Any]] | None = None) -> int | None:
    if rows:
        for row in rows:
            value = row.get("step")
            if isinstance(value, int):
                return value
            if isinstance(value, float) and value.is_integer():
                return int(value)
    m = re.search(r"(?:^|_)(\d+)(?:\.jsonl|_)", path.name)
    if m:
        return int(m.group(1)) + (1 if path.name.startswith("generations_") else 0)
    return None


def dataset_key(name: str) -> str:
    return f"math.{name.lower().replace('+', '_plus_').replace('/', '_slash_').replace('-', '_')}"


def online_dataset_key(name: str) -> str:
    return dataset_key(name or "online_validation")


def coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def code_checkpoint_steps(root: Path) -> list[int]:
    if not root.exists():
        return []
    out = []
    for path in root.iterdir():
        m = re.fullmatch(r"global_step_(\d+)", path.name)
        if m and path.is_dir():
            out.append(int(m.group(1)))
    return sorted(out)


def code_numeric_items(data: dict[str, Any]) -> list[tuple[str, float]]:
    out = []
    for key, value in data.items():
        if isinstance(value, bool):
            out.append((key, float(value)))
        elif isinstance(value, (int, float)):
            out.append((key, float(value)))
    return out


def code_metric_scope(metric_name: str) -> str:
    return "online_val" if metric_name.startswith("val-") else "train"


def code_get_metric(rows: list[dict[str, Any]], step: int, metric_name: str) -> float | None:
    for row in rows:
        if int(row.get("step", -1)) == int(step):
            value = row.get("data", {}).get(metric_name)
            if isinstance(value, (int, float)):
                return float(value)
    return None


def code_best_metric(rows: list[dict[str, Any]], metric_name: str) -> tuple[int | None, float | None]:
    best_step = None
    best_value = None
    for row in rows:
        value = row.get("data", {}).get(metric_name)
        if isinstance(value, (int, float)) and (best_value is None or value > best_value):
            best_step = int(row["step"])
            best_value = float(value)
    return best_step, best_value


def code_insert_training_metric(conn, training_run_id: int, name: str, value: float, step: int, scope: str, notes: str | None = None) -> None:
    conn.execute(
        """
        insert into training_metrics(training_run_id, metric_name, metric_value, step, metric_scope, notes)
        values (?, ?, ?, ?, ?, ?)
        on conflict(training_run_id, metric_name, step, metric_scope) do update set
          metric_value=excluded.metric_value,
          notes=coalesce(excluded.notes, training_metrics.notes)
        """,
        (training_run_id, name, value, step, scope, notes),
    )


def code_insert_validation_check(conn, check_name: str, source_path: str, source_value: Any, database_value: Any, passed: bool, notes: str | None = None) -> None:
    conn.execute(
        """
        insert into validation_checks(check_name, source_path, source_value, database_value, passed, checked_at, notes)
        values (?, ?, ?, ?, ?, datetime('now'), ?)
        """,
        (check_name, source_path, str(source_value), str(database_value), 1 if passed else 0, notes),
    )


def code_validation_line_count(path: Path) -> int | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def code_import_stage1_stage2_retention(conn, project_id: int, repo: Path, branch: str) -> set[int]:
    exp_ids: set[int] = set()
    by_key: dict[str, int] = {}
    base_model = "/data-1/.cache/huggingface/models--Qwen--Qwen3-4B-Base/snapshots/906bfd4b4dc7f14ee4320094d8b41684abff8539"
    git_commit = None
    try:
        import subprocess

        git_commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        git_commit = None

    for run in CODE_TASK_RETENTION_RUNS:
        metrics_path = repo / run["metrics_rel"]
        log_path = repo / run["log_rel"]
        queue_status = repo / run["queue_status_rel"]
        checkpoint_root = Path(run["checkpoint_root"])
        required = [metrics_path, log_path, checkpoint_root]
        if run.get("manifest_path"):
            required.append(Path(run["manifest_path"]))
        if run.get("provenance_path"):
            required.append(Path(run["provenance_path"]))
        if any(not p.exists() for p in required):
            continue

        rows = load_jsonl(metrics_path)
        if not rows:
            continue
        steps = code_checkpoint_steps(checkpoint_root)
        if not steps:
            continue
        latest_step = max(steps)
        best_step, best_he = code_best_metric(rows, "val-core/HumanEval+/acc/pass@1")
        final_he = code_get_metric(rows, run["total_steps"], "val-core/HumanEval+/acc/pass@1")
        final_mbpp = code_get_metric(rows, run["total_steps"], "val-core/MBPP+/acc/pass@1")

        manifest = load_json(Path(run["manifest_path"])) if run.get("manifest_path") and Path(run["manifest_path"]).exists() else {}
        provenance = load_json(Path(run["provenance_path"])) if run.get("provenance_path") and Path(run["provenance_path"]).exists() else {}
        dataset_path = Path(run["train_dataset_path"])
        dataset_rows = run.get("train_dataset_rows") or manifest.get("selected_row_count")
        dataset_id = upsert_dataset(
            conn,
            run["train_dataset_key"],
            Path(run["train_dataset_path"]).name,
            domain="code",
            path=str(dataset_path),
            split="train",
            row_count=dataset_rows,
            notes=json.dumps({"manifest": manifest} if manifest else {"source": str(dataset_path)}, ensure_ascii=False),
        )

        trust_reason = "Source-backed completed code-task run; metrics parsed from training JSONL and checkpoints verified locally."
        if run["stage"] == "stage2":
            trust_reason += " Optimizer shards were stripped after retention, so resume optimizer state is unavailable."
        exp_id = upsert_experiment(
            conn,
            project_id,
            run["experiment_key"],
            run["display_name"],
            method=run["method"],
            method_family="on_policy_wdl_sft",
            method_variant=run["method_variant"],
            method_version="code_task_v2_retention",
            domain="code",
            variant=run["beta_label"],
            status="completed",
            trust_level="trusted",
            trust_reason=trust_reason,
            extra_json=json.dumps(
                {
                    "run_name": run["run_name"],
                    "stage": run["stage"],
                    "beta": run["beta"],
                    "total_steps": run["total_steps"],
                    "checkpoint_root": str(checkpoint_root),
                    "metrics_path": str(metrics_path),
                    "handoff_step": run.get("handoff_step"),
                    "model2_path": run.get("model2_path"),
                    "stage1_experiment_key": run.get("stage1_experiment_key"),
                },
                ensure_ascii=False,
            ),
            notes="Imported by import_verl.py code-task retention extension.",
        )
        by_key[run["experiment_key"]] = exp_id
        exp_ids.add(exp_id)
        add_tag(conn, "experiment", exp_id, "code_task")
        add_tag(conn, "experiment", exp_id, run["stage"])
        add_tag(conn, "experiment", exp_id, run["beta_label"])

        output_model_id = None
        for step in steps:
            ckpt_dir = checkpoint_root / f"global_step_{step}"
            actor_dir = ckpt_dir / "actor"
            model_path = actor_dir if actor_dir.exists() else ckpt_dir
            is_best = step == best_step
            model_id = upsert_model(
                conn,
                f"{run['experiment_key']}.global_step_{step}",
                str(model_path),
                display_name=f"{run['display_name']} global_step_{step}",
                base_model=base_model,
                checkpoint_step=step,
                checkpoint_kind=f"{run['stage']}_actor",
                model_role="actor",
                project_id=project_id,
                git_branch=branch,
                git_commit=git_commit,
                is_best=1 if is_best else 0,
                is_latest=1 if step == latest_step else 0,
                extra_json=json.dumps(
                    {
                        "run_name": run["run_name"],
                        "effective_step": run.get("handoff_step", 0) + step if run["stage"] == "stage2" else step,
                        "protected": step in run.get("protected_steps", []),
                    },
                    ensure_ascii=False,
                ),
                notes="Retained checkpoint; optimizer shards may be stripped by retention policy.",
            )
            if step == latest_step:
                output_model_id = model_id
            add_artifact(conn, "checkpoint_dir", str(ckpt_dir), experiment_id=exp_id, model_id=model_id, description=f"global_step_{step} checkpoint directory")
            add_artifact(conn, "actor_checkpoint_dir", str(model_path), experiment_id=exp_id, model_id=model_id, description=f"global_step_{step} actor directory")

        if run["stage"] == "stage2":
            model2_id = upsert_model(
                conn,
                f"{run['experiment_key']}.handoff_model2_step_{run['handoff_step']}",
                run["model2_path"],
                display_name=f"{run['display_name']} handoff Model2 step {run['handoff_step']}",
                base_model=base_model,
                checkpoint_step=run["handoff_step"],
                checkpoint_kind="merged_stage1_model2",
                model_role="model2_init",
                project_id=project_id,
                git_branch=branch,
                git_commit=git_commit,
                extra_json=json.dumps({"manifest": manifest, "provenance": provenance}, ensure_ascii=False),
                notes="Merged Stage1 Model2 used as Stage2 rollout source.",
            )
            add_artifact(conn, "merged_model2_dir", run["model2_path"], experiment_id=exp_id, model_id=model2_id, description="Merged Stage1 Model2 handoff weights")
            add_artifact(conn, "stage2_provenance_json", run["provenance_path"], experiment_id=exp_id, model_id=model2_id, description="Stage2 Model2 provenance JSON")

        hp = {
            "loss_mode": "wdl_sft",
            "beta": run["beta"],
            "learning_rate": 5e-7,
            "train_prompt_batch_size": 64 if run["stage"] == "stage2" else 8,
            "rollout_n": 8 if run["stage"] == "stage2" else 2,
            "train_prompt_mini_batch_size": 512 if run["stage"] == "stage2" else 16,
            "num_gpus": 8 if run["stage"] == "stage2" else 1,
            "total_training_steps": run["total_steps"],
            "save_freq": 5,
            "test_freq": 5,
            "val_n": 1,
            "val_temperature": 0.2 if run["stage"] == "stage2" else "unset/log-default",
            "val_top_p": 0.95 if run["stage"] == "stage2" else "unset/log-default",
            "data_seed": 20260604,
            "data_shuffle": False if run["stage"] == "stage2" else True,
            "max_prompt_length": 1024,
            "max_response_length": 4096,
            "train_file": str(dataset_path),
            "reward_fn": "compute_score_code_official_aligned",
            "prompt_template_version": manifest.get("prompt_template_version", "code-think-answer-python-v1"),
        }
        if run["stage"] == "stage2":
            hp.update(
                {
                    "handoff_step": run["handoff_step"],
                    "stage1_consumed_rows": manifest.get("stage1", {}).get("consumed_rows"),
                    "stage2_selected_rows": manifest.get("selected_row_count"),
                    "stage2_sampler_offset": manifest.get("sampler", {}).get("offset"),
                    "joint_training_rollout_source": "model2",
                    "model2_path": run["model2_path"],
                    "stage1_source_checkpoint": provenance.get("source_checkpoint"),
                }
            )
        else:
            hp.update({"protected_checkpoint_steps": run.get("protected_steps", []), "protected_ckpt_strip_optimizer": True})

        training_run_key = f"verl.code_task.{run['stage']}.{run['beta_label']}.{run['run_name']}.train"
        first_data = rows[1].get("data", {}) if len(rows) > 1 else rows[0].get("data", {})
        final_data = rows[-1].get("data", {})
        conn.execute(
            """
            insert into training_runs(training_run_key, experiment_id, output_model_id, train_dataset_id, method, framework, framework_version, beta, learning_rate, per_device_batch_size, gradient_accumulation_steps, effective_batch_size, max_length, weight_decay, lr_scheduler, distributed_backend, distributed_config_json, hyperparams_json, num_gpus, total_steps, final_train_loss, final_step_loss, first_step_loss, raw_summary_path, wandb_run, git_branch, git_commit, extra_json, notes)
            values (?, ?, ?, ?, ?, 'verl', '0.7-local', ?, ?, ?, 1, ?, ?, 0.1, 'constant_with_warmup', 'fsdp+ray+vllm', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(training_run_key) do update set
              experiment_id=excluded.experiment_id,
              output_model_id=excluded.output_model_id,
              train_dataset_id=excluded.train_dataset_id,
              method=excluded.method,
              framework=excluded.framework,
              framework_version=excluded.framework_version,
              beta=excluded.beta,
              learning_rate=excluded.learning_rate,
              per_device_batch_size=excluded.per_device_batch_size,
              gradient_accumulation_steps=excluded.gradient_accumulation_steps,
              effective_batch_size=excluded.effective_batch_size,
              max_length=excluded.max_length,
              weight_decay=excluded.weight_decay,
              lr_scheduler=excluded.lr_scheduler,
              distributed_backend=excluded.distributed_backend,
              distributed_config_json=excluded.distributed_config_json,
              hyperparams_json=excluded.hyperparams_json,
              num_gpus=excluded.num_gpus,
              total_steps=excluded.total_steps,
              final_train_loss=coalesce(excluded.final_train_loss, training_runs.final_train_loss),
              final_step_loss=coalesce(excluded.final_step_loss, training_runs.final_step_loss),
              first_step_loss=coalesce(excluded.first_step_loss, training_runs.first_step_loss),
              raw_summary_path=excluded.raw_summary_path,
              wandb_run=excluded.wandb_run,
              git_branch=excluded.git_branch,
              git_commit=excluded.git_commit,
              extra_json=excluded.extra_json,
              notes=excluded.notes
            """,
            (
                training_run_key,
                exp_id,
                output_model_id,
                dataset_id,
                run["method"],
                run["beta"],
                hp["learning_rate"],
                hp["train_prompt_batch_size"],
                hp["train_prompt_mini_batch_size"],
                hp["max_response_length"],
                json.dumps({"backend": "fsdp+ray+vllm", "num_gpus": hp["num_gpus"]}, ensure_ascii=False),
                json.dumps(hp, ensure_ascii=False),
                hp["num_gpus"],
                run["total_steps"],
                final_data.get("actor/loss") or final_data.get("actor/pg_loss"),
                final_data.get("actor/loss") or final_data.get("actor/pg_loss"),
                first_data.get("actor/loss") or first_data.get("actor/pg_loss"),
                str(metrics_path),
                run["run_name"],
                branch,
                git_commit,
                json.dumps({"checkpoint_root": str(checkpoint_root), "log_path": str(log_path)}, ensure_ascii=False),
                "Imported from code-task retention metrics JSONL and checkpoint artifacts.",
            ),
        )
        tr_id = int(conn.execute("select id from training_runs where training_run_key=?", (training_run_key,)).fetchone()["id"])

        for row in rows:
            step = int(row["step"])
            for metric_name, value in code_numeric_items(row.get("data", {})):
                code_insert_training_metric(conn, tr_id, metric_name, value, step, code_metric_scope(metric_name))
                if run["stage"] == "stage2" and metric_name.startswith("val-"):
                    code_insert_training_metric(conn, tr_id, metric_name, value, run["handoff_step"] + step, "online_val_effective", "Stage2 local step mapped to Stage1-equivalent effective step.")
        if run["stage"] == "stage2":
            ref_rows = load_jsonl(repo / run["stage1_metrics_rel"])
            for row in rows:
                local_step = int(row["step"])
                effective_step = run["handoff_step"] + local_step
                for metric_name in ("val-core/HumanEval+/acc/pass@1", "val-core/MBPP+/acc/pass@1"):
                    s2_value = row.get("data", {}).get(metric_name)
                    s1_value = code_get_metric(ref_rows, effective_step, metric_name)
                    if s1_value is not None:
                        code_insert_training_metric(conn, tr_id, f"stage1_reference/{metric_name}", s1_value, effective_step, "stage1_reference", f"Stage1 retention R2 metric at effective step {effective_step}.")
                    if s1_value is not None and isinstance(s2_value, (int, float)):
                        code_insert_training_metric(conn, tr_id, f"delta_vs_stage1/{metric_name}", float(s2_value) - s1_value, effective_step, "stage2_vs_stage1", f"Stage2 local step {local_step}; effective step {effective_step}.")

        add_artifact(conn, "training_metrics_jsonl", str(metrics_path), experiment_id=exp_id, training_run_id=tr_id, description="Training metrics JSONL")
        add_artifact(conn, "training_log", str(log_path), experiment_id=exp_id, training_run_id=tr_id, description="Training log")
        add_artifact(conn, "queue_status_tsv", str(queue_status), experiment_id=exp_id, training_run_id=tr_id, description="Queue status TSV")
        add_artifact(conn, "checkpoint_root", str(checkpoint_root), experiment_id=exp_id, training_run_id=tr_id, description="Checkpoint root")
        add_artifact(conn, "train_dataset_parquet", str(dataset_path), experiment_id=exp_id, training_run_id=tr_id, description="Training dataset parquet")
        if run.get("manifest_path"):
            add_artifact(conn, "dataset_manifest_json", run["manifest_path"], experiment_id=exp_id, training_run_id=tr_id, description="Stage2 non-overlap shard manifest")
        if run.get("validation_rel"):
            validation_dir = repo / run["validation_rel"]
            add_artifact(conn, "validation_dir", str(validation_dir), experiment_id=exp_id, training_run_id=tr_id, description="Stage2 validation dumps")
            for step in steps:
                val_file = validation_dir / f"{step}.jsonl"
                add_artifact(conn, "validation_dump_jsonl", str(val_file), experiment_id=exp_id, training_run_id=tr_id, description=f"Validation dump for step {step}")
                line_count = code_validation_line_count(val_file)
                code_insert_validation_check(conn, f"{run['run_name']}.validation_dump_step_{step}_line_count", str(val_file), line_count, line_count, line_count == 542, "Expected 164 HumanEval+ + 378 MBPP+ = 542 rows.")

        add_source_record(conn, str(metrics_path), "jsonl", "training_metrics", IMPORTER, "experiments", exp_id, "Primary code-task retention metrics source.")
        add_source_record(conn, str(log_path), "log", "training_log", IMPORTER, "training_runs", tr_id, "Code-task retention runtime log.")
        if run.get("manifest_path"):
            add_source_record(conn, run["manifest_path"], "json", "stage2_dataset_manifest", IMPORTER, "datasets", dataset_id, "Stage2 shard manifest.")
        if run.get("provenance_path"):
            add_source_record(conn, run["provenance_path"], "json", "stage2_model2_provenance", IMPORTER, "experiments", exp_id, "Stage2 Model2 provenance.")

        add_quality_flag(conn, "experiment", exp_id, "source_backed_import", "info", "Imported from original JSONL/checkpoint/provenance artifacts.")
        if run["stage"] == "stage2":
            add_quality_flag(conn, "experiment", exp_id, "optimizer_stripped", "warning", "Stage2 checkpoints retain model and extra_state, but optimizer shards were stripped.")
            add_quality_flag(conn, "experiment", exp_id, "low_disk_pressure", "warning", "Queue status records disk-pressure gating during Stage2 retention.")
            add_quality_flag(conn, "experiment", exp_id, "post_final_broken_pipe", "warning", "Training log contains BrokenPipe after final metrics/checkpoint evidence.")
        else:
            add_quality_flag(conn, "experiment", exp_id, "protected_checkpoint_optimizer_stripped", "info", "Protected handoff checkpoints may have optimizer shards stripped by retention policy.")

        db_final_he = conn.execute(
            "select metric_value from training_metrics where training_run_id=? and metric_name='val-core/HumanEval+/acc/pass@1' and step=? and metric_scope='online_val'",
            (tr_id, run["total_steps"]),
        ).fetchone()
        db_final_mbpp = conn.execute(
            "select metric_value from training_metrics where training_run_id=? and metric_name='val-core/MBPP+/acc/pass@1' and step=? and metric_scope='online_val'",
            (tr_id, run["total_steps"]),
        ).fetchone()
        code_insert_validation_check(conn, f"{run['run_name']}.final_he_pass1_matches_jsonl", str(metrics_path), final_he, None if db_final_he is None else db_final_he["metric_value"], db_final_he is not None and final_he is not None and abs(float(db_final_he["metric_value"]) - float(final_he)) < 1e-12)
        code_insert_validation_check(conn, f"{run['run_name']}.final_mbpp_pass1_matches_jsonl", str(metrics_path), final_mbpp, None if db_final_mbpp is None else db_final_mbpp["metric_value"], db_final_mbpp is not None and final_mbpp is not None and abs(float(db_final_mbpp["metric_value"]) - float(final_mbpp)) < 1e-12)
        code_insert_validation_check(conn, f"{run['run_name']}.checkpoint_count", str(checkpoint_root), len(steps), len(steps), len(steps) >= (6 if run["stage"] == "stage2" else 7))

    for run in CODE_TASK_RETENTION_RUNS:
        if run["stage"] == "stage2" and run["experiment_key"] in by_key and run["stage1_experiment_key"] in by_key:
            conn.execute(
                "insert or ignore into experiment_links(from_experiment_id, to_experiment_id, link_type, notes) values (?, ?, ?, ?)",
                (by_key[run["experiment_key"]], by_key[run["stage1_experiment_key"]], "stage2_from_stage1_p70", f"Stage2 starts from Stage1 global_step_{run['handoff_step']} merged Model2."),
            )
    for run in CODE_TASK_RETENTION_RUNS:
        old_key = run.get("older_experiment_key")
        if old_key and run["experiment_key"] in by_key:
            old = conn.execute("select id from experiments where experiment_key=?", (old_key,)).fetchone()
            if old:
                conn.execute(
                    "insert or ignore into experiment_links(from_experiment_id, to_experiment_id, link_type, notes) values (?, ?, ?, ?)",
                    (by_key[run["experiment_key"]], old["id"], "retention_rerun_of", "Retention R2 rerun of earlier Stage1 V2 plateau run."),
                )
    return exp_ids


def load_wandb_table(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    columns = data.get("columns") or []
    rows = []
    for values in data.get("data") or []:
        if isinstance(values, list):
            rows.append(dict(zip(columns, values)))
    return rows


def summarize_online_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, dict[str, float]], dict[str, int]]:
    numeric_keys = ["acc", "score", "reward", "answer_correct", "has_eos"]
    overall_values: dict[str, list[float]] = defaultdict(list)
    dataset_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    verification_counts: dict[str, int] = defaultdict(int)
    extraction_fail = 0
    for row in rows:
        dataset = row.get("data_source") or row.get("dataset") or row.get("source") or "online_validation"
        pred = row.get("pred")
        if pred is None or pred == "":
            extraction_fail += 1
        method = row.get("verification_method")
        if method:
            verification_counts[str(method)] += 1
        for key in numeric_keys:
            value = coerce_number(row.get(key))
            if value is None:
                continue
            overall_values[key].append(value)
            dataset_values[str(dataset)][key].append(value)
    overall = {f"online/{key}/mean@1": sum(values) / len(values) for key, values in overall_values.items() if values}
    if rows:
        overall["online/num_examples"] = float(len(rows))
        overall["online/answer_extraction_failure_rate"] = extraction_fail / len(rows)
    by_dataset = {
        dataset: {f"online/{key}/mean@1": sum(values) / len(values) for key, values in metrics.items() if values}
        for dataset, metrics in dataset_values.items()
    }
    return overall, by_dataset, dict(verification_counts)


def import_eval(conn, project_id: int, path: Path) -> int:
    data = load_json(path)
    model_path = data.get("model_path") or str(path.parents[1])
    exp_name, version, loss_mode, group, trust, reason = classify(model_path)
    step = step_from_path(model_path)
    sub = "model2" if "model2" in model_path else ("model1" if "model1" in model_path else "model")
    exp_key = f"verl.sft.math.qwen3_4b.{group}.{slug(exp_name)}"
    exp_id = upsert_experiment(
        conn,
        project_id,
        exp_key,
        f"{exp_name} {group}",
        method="sft",
        method_family="sft",
        method_variant=loss_mode,
        method_version=version,
        domain="math",
        variant=group,
        trust_level=trust,
        trust_reason=reason,
        notes=reason,
    )
    add_tag(conn, "experiment", exp_id, group)
    add_tag(conn, "experiment", exp_id, version)
    if "pre-fix" in reason.lower() or "pre_fix" in group:
        add_tag(conn, "experiment", exp_id, "pre_fix_wdl_sft_is_labels")
    if "single_model" in group:
        add_tag(conn, "experiment", exp_id, "single_model_ablation")
    if "minirl" in group:
        add_tag(conn, "experiment", exp_id, "minirl_baseline")
    model_id = upsert_model(conn, slug(model_path), model_path, display_name=Path(model_path).name, checkpoint_step=step, checkpoint_kind="best" if step in {125, 150, 225, 300} else "latest", model_role="exported_model", project_id=project_id, git_branch="feature/on-policy-wdl-sft", notes=sub)
    params = data.get("generation_params", {})
    n = (data.get("n_values_used") or [params.get("n_default") or 3])[0]
    eval_id = upsert_eval_run(
        conn,
        eval_run_key=slug(str(path)),
        experiment_id=exp_id,
        model_id=model_id,
        eval_name=f"{exp_name}_{sub}_step{step}_offline_n{n}",
        domain="math",
        eval_harness="vllm",
        framework="verl",
        output_dir=str(path.parent),
        raw_metrics_path=str(path),
        n=n,
        num_samples=n,
        temperature=params.get("temperature"),
        top_p=params.get("top_p"),
        max_tokens=params.get("max_tokens"),
        max_new_tokens=params.get("max_tokens"),
        seed=params.get("seed"),
        git_branch="feature/on-policy-wdl-sft",
        trust_level=trust,
        trust_reason=reason,
        extra_json=json.dumps({"method_group": group, "sub_model": sub, "generation_time_s": data.get("generation_time_s")}, ensure_ascii=False),
        notes=reason,
    )
    add_source_record(conn, str(path), "json_summary", None, IMPORTER, "eval_runs", eval_id)
    add_artifact(conn, "eval_metrics", str(path), experiment_id=exp_id, eval_run_id=eval_id, model_id=model_id)
    details_path = path.with_name("eval_details.parquet")
    if details_path.exists():
        add_artifact(conn, "eval_details", str(details_path), experiment_id=exp_id, eval_run_id=eval_id, model_id=model_id, description="Per-sample offline eval details parquet")
    if trust in {"buggy", "needs_review", "usable_with_caution"}:
        add_quality_flag(conn, "eval_run", eval_id, trust, "warning", reason)
    for dataset_name, metrics in data.get("metrics", {}).items():
        if not isinstance(metrics, dict):
            continue
        ds_id = upsert_dataset(conn, dataset_key(dataset_name), dataset_name, domain="math", row_count=metrics.get("n_prompts"))
        conn.execute("insert or ignore into eval_run_datasets(eval_run_id, dataset_id, num_examples, orig_total) values (?, ?, ?, ?)", (eval_id, ds_id, metrics.get("n_prompts"), metrics.get("n_prompts")))
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                upsert_metric(conn, eval_id, ds_id, key, value)
    return exp_id


def import_v3_placeholder(conn, project_id: int, repo: Path) -> int:
    exp_name, version, loss_mode, group, trust, reason = METHODS["2A-BASE-LABELFIX"]
    exp_id = upsert_experiment(
        conn,
        project_id,
        "verl.sft.math.qwen3_4b.v3_wdl_sft_is_labelfix.2a_base_labelfix",
        "V3 label-fix 2A base rerun",
        method="sft",
        method_family="sft",
        method_variant=loss_mode,
        method_version=version,
        domain="math",
        variant=group,
        status="partial",
        trust_level=trust,
        trust_reason=reason,
        notes=reason,
    )
    ckpt = Path("/data-1/checkpoints/WDL-SFT-Qwen3-4B-MATH-2A-BASE-LABELFIX_1777346990/global_step_300")
    model_id = upsert_model(conn, slug(str(ckpt)), str(ckpt), display_name=ckpt.name, checkpoint_step=300, checkpoint_kind="latest", model_role="actor_checkpoint", project_id=project_id, git_branch="feature/on-policy-wdl-sft", notes="Incomplete migrated checkpoint; loadability not verified")
    add_artifact(conn, "checkpoint_dir", str(ckpt), experiment_id=exp_id, model_id=model_id, description="V3 label-fix checkpoint directory")
    add_quality_flag(conn, "experiment", exp_id, "missing_offline_eval", "warning", reason)
    return exp_id


def import_online_eval(
    conn,
    project_id: int,
    path: Path,
    run_name: str,
    rows: list[dict[str, Any]],
    exp_name: str,
    group: str,
    loss_mode: str,
    version: str,
    trust: str,
    reason: str,
    source_type: str,
) -> int:
    if not rows:
        return 0
    step = step_from_eval_file(path, rows)
    exp_key = f"verl.online.math.{group}.{slug(exp_name)}"
    exp_id = upsert_experiment(
        conn,
        project_id,
        exp_key,
        f"{exp_name} {group} online validation",
        method="rl" if loss_mode in {"grpo", "minirl"} else "sft",
        method_family=loss_mode,
        method_variant=loss_mode,
        method_version=version,
        domain="math",
        variant=group,
        trust_level=trust,
        trust_reason=reason,
        extra_json=json.dumps({"run_name": run_name, "online_source_type": source_type}, ensure_ascii=False),
        notes=reason,
    )
    add_tag(conn, "experiment", exp_id, group)
    add_tag(conn, "experiment", exp_id, "online_validation")
    if "label" in group:
        add_tag(conn, "experiment", exp_id, "label_fix")
    model_path = f"verl_online_validation://{run_name}/step_{step if step is not None else 'unknown'}"
    model_id = upsert_model(
        conn,
        slug(model_path),
        model_path,
        display_name=f"{run_name} step {step}",
        checkpoint_step=step,
        checkpoint_kind="online_validation_step",
        model_role="trainer_policy",
        project_id=project_id,
        git_branch="feature/on-policy-wdl-sft",
        extra_json=json.dumps({"run_name": run_name}, ensure_ascii=False),
    )
    overall, by_dataset, verification_counts = summarize_online_rows(rows)
    eval_name = f"{run_name}_online_step{step if step is not None else 'unknown'}_n1"
    eval_id = upsert_eval_run(
        conn,
        eval_run_key=slug(str(path)),
        experiment_id=exp_id,
        model_id=model_id,
        eval_name=eval_name,
        domain="math",
        eval_harness="verl_online_validation",
        framework="verl",
        output_dir=str(path.parent),
        raw_metrics_path=str(path),
        raw_samples_path=str(path),
        n=1,
        num_samples=len(rows),
        repeat_count=1,
        temperature=1.0,
        git_branch="feature/on-policy-wdl-sft",
        trust_level=trust,
        trust_reason=reason,
        extra_json=json.dumps(
            {"run_name": run_name, "global_step": step, "source_type": source_type, "verification_counts": verification_counts},
            ensure_ascii=False,
        ),
        notes=reason,
    )
    add_source_record(conn, str(path), source_type, f"step_{step}", ONLINE_IMPORTER, "eval_runs", eval_id)
    add_artifact(conn, source_type, str(path), experiment_id=exp_id, eval_run_id=eval_id, model_id=model_id, description="verl online validation samples")
    if trust != "trusted":
        add_quality_flag(conn, "eval_run", eval_id, trust, "warning", reason)
    if step is not None:
        upsert_metric(conn, eval_id, None, "training/global_step", step)
    for metric_name, value in overall.items():
        upsert_metric(conn, eval_id, None, metric_name, value)
    for method, count in verification_counts.items():
        upsert_metric(conn, eval_id, None, f"online/verification_method/{slug(method)}", count)
    for dataset_name, metrics in by_dataset.items():
        ds_id = upsert_dataset(conn, online_dataset_key(dataset_name), dataset_name, domain="math", row_count=len(rows))
        conn.execute(
            "insert or ignore into eval_run_datasets(eval_run_id, dataset_id, num_examples, orig_total) values (?, ?, ?, ?)",
            (eval_id, ds_id, None, None),
        )
        for metric_name, value in metrics.items():
            upsert_metric(conn, eval_id, ds_id, metric_name, value)
    return exp_id


def import_online_jsonl_runs(conn, project_id: int, repo: Path) -> set[int]:
    exp_ids = set()
    for run_name, meta in ONLINE_JSONL_RUNS.items():
        exp_name, group, loss_mode, version, trust, reason = meta
        for base in [repo / "recipe/on_policy_wdl_sft/validation", repo / "recipe/joint_training/validation"]:
            run_dir = base / run_name
            if not run_dir.exists():
                continue
            for path in sorted(run_dir.glob("*.jsonl"), key=lambda p: step_from_eval_file(p) or -1):
                rows = load_jsonl(path)
                exp_id = import_online_eval(conn, project_id, path, run_name, rows, exp_name, group, loss_mode, version, trust, reason, "validation_jsonl")
                if exp_id:
                    exp_ids.add(exp_id)
    return exp_ids


def import_online_wandb_tables(conn, project_id: int) -> set[int]:
    exp_ids = set()
    for run_name, meta in ONLINE_WANDB_TABLE_RUNS.items():
        pattern, exp_name, group, loss_mode, version, trust, reason = meta
        for path in existing_paths([pattern]):
            rows = load_wandb_table(path)
            exp_id = import_online_eval(conn, project_id, path, run_name, rows, exp_name, group, loss_mode, version, trust, reason, "wandb_table_json")
            if exp_id:
                exp_ids.add(exp_id)
    return exp_ids


def link_versions(conn) -> None:
    rows = {r["method_version"]: r["id"] for r in conn.execute("select id, method_version from experiments where experiment_key like 'verl.sft.math.qwen3_4b.%'")}
    if "v1" in rows and "v2" in rows:
        conn.execute("insert or ignore into experiment_links(from_experiment_id, to_experiment_id, link_type, notes) values (?, ?, ?, ?)", (rows["v2"], rows["v1"], "derived_from", "V2 adds IS/clip to V1 WDL-SFT"))
    if "v3" in rows and "v2" in rows:
        conn.execute("insert or ignore into experiment_links(from_experiment_id, to_experiment_id, link_type, notes) values (?, ?, ?, ?)", (rows["v3"], rows["v2"], "bugfix_of", "V3 fixes V2 reward-label bug"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import selected verl on-policy-wdl-sft experiments")
    add_db_arg(parser)
    parser.add_argument("--repo", default="/data-1/verl07/verl")
    parser.add_argument("--branch", default="feature/on-policy-wdl-sft")
    args = parser.parse_args()
    init_db(args.db)
    repo = Path(args.repo)
    with connect(args.db) as conn:
        project_id = upsert_project(conn, "verl", str(repo), args.branch, "Selected on-policy-wdl-sft branch import")
        branch_project_id = upsert_project(conn, f"verl:{args.branch}", str(repo), args.branch, "Branch-scoped on-policy-wdl-sft import")
        for rel in MARKDOWN_SOURCES:
            p = repo / rel
            if p.exists():
                add_artifact(conn, "markdown_source", str(p), description="verl source markdown retained as source of truth")
                add_source_record(conn, str(p), "markdown", None, IMPORTER, "projects", project_id)
        exp_ids = set()
        for path in existing_paths(EVAL_PATTERNS):
            exp_ids.add(import_eval(conn, project_id, path))
        exp_ids.add(import_v3_placeholder(conn, project_id, repo))
        exp_ids.update(import_online_jsonl_runs(conn, project_id, repo))
        exp_ids.update(import_online_wandb_tables(conn, project_id))
        exp_ids.update(code_import_stage1_stage2_retention(conn, branch_project_id, repo, args.branch))
        link_versions(conn)
        conn.commit()
    print(f"imported_verl_experiments={len(exp_ids)}")


if __name__ == "__main__":
    main()

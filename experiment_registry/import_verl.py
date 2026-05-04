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
        link_versions(conn)
        conn.commit()
    print(f"imported_verl_experiments={len(exp_ids)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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


IMPORTER = "import_dpo_v1"

TRAINING_SUMMARIES = [
    "/data-1/model_weights/qwen3-4b-dpo/step_376/training_logs/training_summary.json",
    "/data-1/model_weights/qwen3-4b-base-dpo-v2/step_281/training_logs/training_summary.json",
    "/data-1/model_weights/qwen3-4b-sft-dpo/step_367/training_logs/training_summary.json",
    "/data-1/model_weights/qwen3-8b-dpo/step_496/training_logs/training_summary.json",
    "/data-1/model_weights/gemma3-4b-sft-dpo/step_326/training_logs/training_summary.json",
    "/data-1/model_weights/qwen3-4b-code-sft-dpo-code/step_45/training_logs/training_summary.json",
    "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/training_logs/training_summary.json",
    "/data-1/checkpoints/qwen3-4b-code-wdl-v3-m1-dpo/training_logs/training_summary.json",
]

EVAL_GLOBS = [
    "/data-1/model_weights/qwen3-4b-dpo/step_376/inference_n3_sysprompt/eval_metrics.json",
    "/data-1/model_weights/qwen3-4b-base-dpo-v2/step_281/inference_n3/eval_metrics.json",
    "/data-1/model_weights/qwen3-4b-sft-dpo/step_367/inference_n3/eval_metrics.json",
    "/data-1/model_weights/qwen3-4b-sft-dpo/step_367/inference_n64_aime_math_amc/eval_metrics.json",
    "/data-1/model_weights/qwen3-8b-dpo/step_496/inference_n3/eval_metrics.json",
    "/data-1/model_weights/gemma3-4b-sft-dpo/step_326/inference_n3/eval_metrics.json",
    "/data-1/model_weights/qwen3-4b-code-sft-dpo-code/step_45/eval_code/*.json",
    "/data-1/model_weights/qwen3-4b-code-sft-dpo-code/step_45/eval_code/test/*.json",
    "/data-1/model_weights/qwen3-4b-code-sft-dpo-code/step_45/eval_code_mean3/*.json",
    "/data-1/model_weights/qwen3-4b-code-sft-dpo-code/step_45/eval_code_mean3/test/*.json",
    "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/eval_code/*.json",
    "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/eval_code/test/*.json",
    "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/eval_code_n1_reverify/*.json",
    "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/eval_code_n1_reverify/test/*.json",
    "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/eval_code_mean3/*.json",
    "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/eval_code_mean3/test/*.json",
    "/data-1/checkpoints/qwen3-4b-code-wdl-v3-m1-dpo/eval_code_n1/*.json",
    "/data-1/checkpoints/qwen3-4b-code-wdl-v3-m1-dpo/eval_code_n1/test/*.json",
    "/data-1/checkpoints/qwen3-4b-code-wdl-v3-m1-dpo/eval_code_n1_preamble_fix/*.json",
    "/data-1/checkpoints/qwen3-4b-base-code-wdl-v3-m1-ckpt39/eval_code_n1/*.json",
    "/data-1/checkpoints/qwen3-4b-base-code-wdl-v3-m1-ckpt39/eval_code_n1/test/*.json",
    "/data-1/checkpoints/qwen3-4b-base-code-wdl-v3-m1-ckpt39/eval_code_n1_rerun/*.json",
    "/data-1/checkpoints/qwen3-4b-base-code-wdl-v3-m1-ckpt39/eval_code_n1_rerun/test/*.json",
]

MARKDOWN_SOURCES = [
    "/data-1/dpo-experiment/EXPERIMENTS.md",
    "/data-1/dpo-experiment/EXPERIMENT_RESULTS.md",
    "/data-1/dpo-experiment/HANDOFF_code_eval_2026-04-15.md",
]


def existing_paths(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    for pattern in patterns:
        if any(ch in pattern for ch in "*?["):
            out.extend(sorted(Path("/").glob(pattern.lstrip("/"))))
        else:
            p = Path(pattern)
            if p.exists():
                out.append(p)
    return out


def step_from_path(path: str) -> int | None:
    m = re.search(r"(?:step_|checkpoint-|global_step_)(\d+)", path)
    return int(m.group(1)) if m else None


def dataset_key(name: str, domain: str) -> str:
    return f"{domain}.{name.lower().replace('+', '_plus_').replace('/', '_slash_').replace('-', '_')}"


def family_from_model_path(model_path: str, fallback_path: str | None = None) -> tuple[str, str, str, str]:
    lower = model_path.lower()
    domain = "code" if "code" in lower else "math"
    method = "dpo"
    if "wdl-v3" in lower:
        variant = "wdl_v3_m1"
    elif "code-m1" in lower:
        variant = "code_m1"
    elif "code-sft" in lower:
        variant = "code_sft"
    elif "base-dpo-v2" in lower:
        variant = "base_v2"
    elif "sft-dpo" in lower:
        variant = "sft"
    elif "gemma" in lower:
        variant = "gemma_sft"
    elif "8b" in lower:
        variant = "qwen3_8b_base"
    else:
        variant = "base_v1"
    model_family = "gemma3_4b" if "gemma" in lower else ("qwen3_8b" if "8b" in lower else "qwen3_4b")
    step = step_from_path(model_path) or step_from_path(fallback_path or "")
    exp_key = f"dpo.{method}.{domain}.{model_family}.{variant}.step{step or 'unknown'}"
    return exp_key, method, domain, variant


def import_training(conn, project_id: int, path: Path) -> int:
    data = load_json(path)
    output_path = data.get("checkpoint_path") or str(path.parents[2])
    exp_key, method, domain, variant = family_from_model_path(output_path, str(path))
    exp_id = upsert_experiment(
        conn,
        project_id,
        exp_key,
        display_name=Path(output_path).name,
        method=method,
        method_family=method,
        method_variant=variant,
        domain=domain,
        variant=variant,
        trust_level="trusted" if domain == "code" else "usable_with_caution",
        trust_reason="imported from training_summary.json",
        notes=f"Training imported from {path}",
    )
    add_tag(conn, "experiment", exp_id, domain)
    add_tag(conn, "experiment", exp_id, method)
    dataset_path = data.get("dataset")
    dataset_id = None
    if dataset_path:
        dataset_id = upsert_dataset(conn, dataset_key(dataset_path, domain), Path(dataset_path).name, domain=domain, path=dataset_path, row_count=data.get("dataset_size"))
    input_model_id = upsert_model(conn, slug(data.get("model", "unknown")), data.get("model", "unknown"), project_id=project_id, checkpoint_kind="input", model_role="base")
    output_model_id = upsert_model(conn, slug(output_path), output_path, display_name=Path(output_path).name, checkpoint_step=step_from_path(output_path), checkpoint_kind="latest", model_role=method, project_id=project_id)
    hp = data.get("hyperparameters", {})
    results = data.get("results", {})
    conn.execute(
        """
        insert into training_runs(training_run_key, experiment_id, input_model_id, output_model_id, train_dataset_id, method, framework, beta, learning_rate, num_epochs, per_device_batch_size, gradient_accumulation_steps, effective_batch_size, max_length, warmup_ratio, weight_decay, lr_scheduler, distributed_backend, num_gpus, runtime_seconds, total_steps, final_train_loss, final_step_loss, first_step_loss, first_step_margin, final_step_margin, final_rewards_chosen, final_rewards_rejected, raw_summary_path, hyperparams_json, extra_json, notes)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(training_run_key) do update set
          final_train_loss=excluded.final_train_loss,
          final_step_loss=excluded.final_step_loss,
          total_steps=excluded.total_steps,
          notes=excluded.notes
        """,
        (
            slug(str(path)),
            exp_id,
            input_model_id,
            output_model_id,
            dataset_id,
            method,
            "trl",
            hp.get("beta"),
            hp.get("learning_rate"),
            hp.get("num_epochs"),
            hp.get("per_device_batch_size"),
            hp.get("gradient_accumulation_steps"),
            hp.get("effective_batch_size"),
            hp.get("max_length"),
            hp.get("warmup_ratio"),
            hp.get("weight_decay"),
            hp.get("lr_scheduler"),
            data.get("deepspeed"),
            data.get("num_gpus"),
            results.get("training_runtime_seconds"),
            results.get("total_steps"),
            results.get("final_train_loss"),
            results.get("final_step_loss"),
            results.get("first_step_loss"),
            results.get("first_step_margins"),
            results.get("final_step_margins"),
            results.get("final_rewards_chosen"),
            results.get("final_rewards_rejected"),
            str(path),
            json.dumps(hp, ensure_ascii=False),
            json.dumps({"validation": data.get("validation"), "dataset_size": data.get("dataset_size")}, ensure_ascii=False),
            "Imported from DPO training_summary.json",
        ),
    )
    tr_id = int(conn.execute("select id from training_runs where training_run_key=?", (slug(str(path)),)).fetchone()["id"])
    add_artifact(conn, "training_summary", str(path), experiment_id=exp_id, training_run_id=tr_id)
    add_source_record(conn, str(path), "json_summary", None, IMPORTER, "training_runs", tr_id)
    if dataset_id:
        conn.execute("insert or ignore into training_run_datasets(training_run_id, dataset_id, role, row_count) values (?, ?, ?, ?)", (tr_id, dataset_id, "train", data.get("dataset_size")))
    return exp_id


def metric_items(obj: dict[str, Any]) -> list[tuple[str, Any, str]]:
    out = []
    for key, value in obj.items():
        if isinstance(value, (int, float)) and key not in {"temperature", "repeat", "total", "orig_total", "passed", "functional_pass", "functional_total", "stdin_pass", "stdin_total"}:
            out.append((key, value, ""))
    return out


def trust_for_eval(path: Path, data: dict[str, Any], domain: str) -> tuple[str, str]:
    s = str(path).lower()
    if "wdl-v3" in s and "preamble_fix" not in s:
        return "needs_review", "WDL-v3 code eval has known preamble/parser concern and suspicious BCB result"
    if "preamble_fix" in s:
        return "usable_with_caution", "partial preamble-fix rerun"
    if domain == "math":
        metrics = data.get("metrics", {})
        fails = [v.get("extraction_fail", 0) for v in metrics.values() if isinstance(v, dict)]
        if fails and max(fails) >= 0.8:
            return "usable_with_caution", "high extraction failure on at least one math benchmark"
    if "eval_code_mean3" in s or "eval_code_n1_reverify" in s:
        return "trusted", "post-2026-04-15 fixed code eval/parser output"
    return "usable_with_caution", "imported eval summary; may be superseded by a newer eval variant"


def import_math_eval(conn, project_id: int, path: Path) -> None:
    data = load_json(path)
    model_path = data.get("model_path") or str(path.parents[1])
    exp_key, method, domain, variant = family_from_model_path(model_path, str(path))
    exp_id = upsert_experiment(conn, project_id, exp_key, Path(model_path).name, method=method, method_family=method, method_variant=variant, domain=domain, variant=variant, trust_level="usable_with_caution")
    model_id = upsert_model(conn, slug(model_path), model_path, display_name=Path(model_path).name, checkpoint_step=step_from_path(model_path), checkpoint_kind="latest", model_role="dpo", project_id=project_id)
    params = data.get("generation_params", {})
    trust, reason = trust_for_eval(path, data, "math")
    eval_id = upsert_eval_run(
        conn,
        eval_run_key=slug(str(path)),
        experiment_id=exp_id,
        model_id=model_id,
        eval_name=path.parent.name,
        domain="math",
        eval_harness="vllm",
        framework="trl",
        output_dir=str(path.parent),
        raw_metrics_path=str(path),
        n=(data.get("n_values_used") or [params.get("n_default") or 1])[0],
        num_samples=(data.get("n_values_used") or [params.get("n_default") or 1])[0],
        temperature=params.get("temperature"),
        top_p=params.get("top_p"),
        max_tokens=params.get("max_tokens"),
        max_new_tokens=params.get("max_tokens"),
        seed=params.get("seed"),
        eval_datetime=None,
        trust_level=trust,
        trust_reason=reason,
        extra_json=json.dumps({"generation_time_s": data.get("generation_time_s")}, ensure_ascii=False),
        notes=reason,
    )
    add_source_record(conn, str(path), "json_summary", None, IMPORTER, "eval_runs", eval_id)
    add_artifact(conn, "eval_metrics", str(path), experiment_id=exp_id, eval_run_id=eval_id, model_id=model_id)
    if trust != "trusted":
        add_quality_flag(conn, "eval_run", eval_id, trust, "warning", reason)
    for dataset_name, metrics in data.get("metrics", {}).items():
        if not isinstance(metrics, dict):
            continue
        ds_id = upsert_dataset(conn, dataset_key(dataset_name, "math"), dataset_name, domain="math", path=None, row_count=metrics.get("n_prompts"))
        conn.execute("insert or ignore into eval_run_datasets(eval_run_id, dataset_id, num_examples, orig_total) values (?, ?, ?, ?)", (eval_id, ds_id, metrics.get("n_prompts"), metrics.get("n_prompts")))
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                upsert_metric(conn, eval_id, ds_id, key, value, denominator=metrics.get("n_prompts") if key.startswith("pass@") or key.startswith("mean@") else None)


def import_code_eval(conn, project_id: int, path: Path) -> None:
    data = load_json(path)
    model_path = data.get("model_path") or str(path.parents[1])
    exp_key, method, domain, variant = family_from_model_path(model_path, str(path))
    exp_id = upsert_experiment(conn, project_id, exp_key, Path(model_path).name, method=method, method_family=method, method_variant=variant, domain="code", variant=variant, trust_level="trusted" if "wdl-v3" not in str(path).lower() else "needs_review")
    model_id = upsert_model(conn, slug(model_path), model_path, display_name=Path(model_path).name, checkpoint_step=step_from_path(model_path), checkpoint_kind="latest", model_role="dpo", project_id=project_id)
    trust, reason = trust_for_eval(path, data, "code")
    eval_name = f"{path.parent.name}/{path.name}"
    n = data.get("num_samples") or data.get("repeat") or (3 if "mean@3" in json.dumps(data) else 1)
    temp = data.get("temperature")
    if temp is None:
        temp = 0.8 if "mean3" in str(path) else 0.0
    eval_id = upsert_eval_run(
        conn,
        eval_run_key=slug(str(path)),
        experiment_id=exp_id,
        model_id=model_id,
        eval_name=eval_name,
        domain="code",
        eval_harness="code_eval_offline",
        framework="custom",
        output_dir=str(path.parent),
        raw_metrics_path=str(path),
        raw_samples_path=data.get("samples_path"),
        n=n,
        num_samples=n,
        repeat_count=data.get("repeat"),
        temperature=temp,
        timeout_seconds=data.get("timeout"),
        thinking=int(data["thinking"]) if "thinking" in data and data.get("thinking") is not None else None,
        enable_thinking=int(data["thinking"]) if "thinking" in data and data.get("thinking") is not None else None,
        eval_datetime=data.get("timestamp"),
        trust_level=trust,
        trust_reason=reason,
        parser_version="post-2026-04-15-fixed" if "eval_code" in str(path) else None,
        preamble_mode="preamble_fix" if "preamble_fix" in str(path) else None,
        notes=reason,
    )
    add_source_record(conn, str(path), "json_summary", None, IMPORTER, "eval_runs", eval_id)
    add_artifact(conn, "eval_summary", str(path), experiment_id=exp_id, eval_run_id=eval_id, model_id=model_id)
    if trust != "trusted":
        add_quality_flag(conn, "eval_run", eval_id, trust, "warning", reason)
    if "pass@1" in data and isinstance(data["pass@1"], dict):
        for dataset_name, value in data["pass@1"].items():
            ds_id = upsert_dataset(conn, dataset_key(dataset_name, "code"), dataset_name, domain="code")
            upsert_metric(conn, eval_id, ds_id, "pass@1", value)
    if "mean@3" in data and isinstance(data["mean@3"], dict):
        for dataset_name, value in data["mean@3"].items():
            ds_id = upsert_dataset(conn, dataset_key(dataset_name, "code"), dataset_name, domain="code")
            upsert_metric(conn, eval_id, ds_id, "mean@3", value)
    if "dataset_path" in data:
        dataset_name = "BigCodeBench" if "BigCodeBench" in data["dataset_path"] else "LiveCodeBench"
        ds_id = upsert_dataset(conn, dataset_key(dataset_name, "code"), dataset_name, domain="code", path=data.get("dataset_path"), row_count=data.get("orig_total") or data.get("total"))
        conn.execute("insert or ignore into eval_run_datasets(eval_run_id, dataset_id, num_examples, orig_total) values (?, ?, ?, ?)", (eval_id, ds_id, data.get("total"), data.get("orig_total")))
        for key in ["acc", "mean@1", "mean@3", "pass@1", "pass@3", "pass_at_k", "passed", "total", "orig_total", "pass_success", "functional_pass", "functional_total", "stdin_pass", "stdin_total"]:
            if key in data and isinstance(data[key], (int, float)):
                upsert_metric(conn, eval_id, ds_id, key, data[key])
        if data.get("functional_total"):
            upsert_metric(conn, eval_id, ds_id, "functional_pass_rate", data.get("functional_pass") / data.get("functional_total"), numerator=data.get("functional_pass"), denominator=data.get("functional_total"))
        if data.get("stdin_total"):
            upsert_metric(conn, eval_id, ds_id, "stdin_pass_rate", data.get("stdin_pass") / data.get("stdin_total"), numerator=data.get("stdin_pass"), denominator=data.get("stdin_total"))


def import_markdown_sources(conn, project_id: int) -> None:
    for src in MARKDOWN_SOURCES:
        p = Path(src)
        if not p.exists():
            continue
        add_artifact(conn, "markdown_source", str(p), description="DPO source markdown retained as source of truth")
        add_source_record(conn, str(p), "markdown", None, IMPORTER, "projects", project_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import DPO experiment summaries into the registry")
    add_db_arg(parser)
    parser.add_argument("--repo", default="/data-1/dpo-experiment")
    args = parser.parse_args()
    init_db(args.db)
    with connect(args.db) as conn:
        project_id = upsert_project(conn, "dpo", args.repo, "main", "DPO project local registry import")
        for path in existing_paths(TRAINING_SUMMARIES):
            import_training(conn, project_id, path)
        for path in existing_paths(EVAL_GLOBS):
            if path.name == "eval_metrics.json":
                import_math_eval(conn, project_id, path)
            elif path.name.endswith(".json") and ("summary" in path.name):
                import_code_eval(conn, project_id, path)
        import_markdown_sources(conn, project_id)
        conn.commit()
        counts = conn.execute(
            """
            select count(*) as n
            from eval_runs er
            join experiments e on e.id = er.experiment_id
            where e.project_id = ?
            """,
            (project_id,),
        ).fetchone()["n"]
    print(f"imported_dpo_eval_runs={counts}")


if __name__ == "__main__":
    main()

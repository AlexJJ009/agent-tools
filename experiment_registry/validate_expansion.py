#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from registry_core import add_db_arg, connect, load_json, utc_now


OFFLINE_CHECKS = [
    (
        "minirl_2z_sft_step275_math500",
        "/data-1/model_weights/MINIRL-Qwen3-4B-MATH-2Z-SFT/step_275/inference_n3/eval_metrics.json",
        ("metrics", "HuggingFaceH4/MATH-500", "mean@3"),
        "HuggingFaceH4/MATH-500",
        "mean@3",
    ),
    (
        "minirl_2z_sft_step300_aime",
        "/data-1/model_weights/MINIRL-Qwen3-4B-MATH-2Z-SFT/step_300/inference_n3/eval_metrics.json",
        ("metrics", "aime25", "mean@3"),
        "aime25",
        "mean@3",
    ),
    (
        "wdl_2a_sft_step275_aqua",
        "/data-1/model_weights/WDL-SFT-Qwen3-4B-MATH-2A-SFT/step_275/inference_n3/eval_metrics.json",
        ("metrics", "deepmind/aqua_rat", "mean@3"),
        "deepmind/aqua_rat",
        "mean@3",
    ),
    (
        "wdl_2a_sft_step300_amc",
        "/data-1/model_weights/WDL-SFT-Qwen3-4B-MATH-2A-SFT/step_300/inference_n3/eval_metrics.json",
        ("metrics", "zwhe99/amc23", "mean@3"),
        "zwhe99/amc23",
        "mean@3",
    ),
    (
        "dpo_wdl_code_ckpt39_lcb_rerun",
        "/data-1/checkpoints/qwen3-4b-base-code-wdl-v3-m1-ckpt39/eval_code_n1_rerun/eval_summary.json",
        ("mean@1",),
        "LiveCodeBench",
        "mean@1",
    ),
    (
        "dpo_wdl_code_ckpt39_bcb_rerun",
        "/data-1/checkpoints/qwen3-4b-base-code-wdl-v3-m1-ckpt39/eval_code_n1_rerun/test/eval_summary.json",
        ("mean@1",),
        "BigCodeBench",
        "mean@1",
    ),
]

ONLINE_CHECKS = [
    (
        "online_m55_step300_acc",
        "/data-1/verl07/verl/recipe/on_policy_wdl_sft/validation/WDL-SFT-Qwen3-4B-MATH-M5-5_1775980322/300.jsonl",
        "online/acc/mean@1",
    ),
    (
        "online_m56_step400_score",
        "/data-1/verl07/verl/recipe/on_policy_wdl_sft/validation/WDL-SFT-Qwen3-4B-MATH-M5-6_1776095760/400.jsonl",
        "online/score/mean@1",
    ),
    (
        "online_minirl_gc500_step695_acc",
        "/data-1/verl07/verl/recipe/joint_training/validation/Baseline-MiniRL-Qwen3-1.7B-MATH-GC500_1773643860/695.jsonl",
        "online/acc/mean@1",
    ),
    (
        "online_labelfix_step300_score",
        "/data-1/wandb_runs/WDL-SFT-Qwen3-4B-MATH-2A-BASE-LABELFIX/wandb/offline-run-20260428_033322-kto2ukn2/files/media/table/val/generations_299_c2378f0c92b90925fb16.table.json",
        "online/score/mean@1",
    ),
]


def get_nested(obj: dict[str, Any], keys: tuple[str, ...]) -> Any:
    cur: Any = obj
    for key in keys:
        cur = cur[key]
    return cur


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    data = load_json(path)
    columns = data.get("columns") or []
    return [dict(zip(columns, row)) for row in data.get("data") or []]


def mean_metric(rows: list[dict[str, Any]], key: str) -> float:
    short_key = key.split("/")[1]
    vals = []
    for row in rows:
        value = row.get(short_key)
        if isinstance(value, bool):
            vals.append(float(value))
        elif isinstance(value, (int, float)):
            vals.append(float(value))
    if not vals:
        raise ValueError(f"no numeric values for {short_key}")
    return sum(vals) / len(vals)


def db_metric(conn, source_path: str, dataset: str | None, metric: str) -> float | None:
    if dataset is None:
        row = conn.execute(
            """
            select em.metric_value
            from eval_metrics em
            join eval_runs er on er.id = em.eval_run_id
            where er.raw_metrics_path = ?
              and em.dataset_id is null
              and em.metric_name = ?
            """,
            (source_path, metric),
        ).fetchone()
    else:
        row = conn.execute(
            """
            select em.metric_value
            from eval_metrics em
            join eval_runs er on er.id = em.eval_run_id
            join datasets d on d.id = em.dataset_id
            where er.raw_metrics_path = ?
              and d.name = ?
              and em.metric_name = ?
            """,
            (source_path, dataset, metric),
        ).fetchone()
    return None if row is None else float(row["metric_value"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate newly imported L40 verl/DPO eval expansion")
    add_db_arg(parser)
    parser.add_argument("--report", default=str(Path(__file__).resolve().parent / "reports" / "verl_l40_expansion_validation.md"))
    args = parser.parse_args()
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# L40 verl/DPO Expansion Validation",
        "",
        f"Checked at: `{utc_now()}`",
        "",
        "| Check | Source | Source value | DB value | Result |",
        "|---|---|---:|---:|---|",
    ]
    failures = 0
    with connect(args.db) as conn:
        for name, source, keys, dataset, metric in OFFLINE_CHECKS:
            source_value = float(get_nested(load_json(source), keys))
            database_value = db_metric(conn, source, dataset, metric)
            passed = database_value is not None and abs(source_value - database_value) < 1e-9
            failures += 0 if passed else 1
            lines.append(f"| `{name}` | `{source}` | {source_value} | {database_value} | {'PASS' if passed else 'FAIL'} |")
        for name, source, metric in ONLINE_CHECKS:
            source_value = mean_metric(load_rows(Path(source)), metric)
            database_value = db_metric(conn, source, None, metric)
            passed = database_value is not None and abs(source_value - database_value) < 1e-9
            failures += 0 if passed else 1
            lines.append(f"| `{name}` | `{source}` | {source_value} | {database_value} | {'PASS' if passed else 'FAIL'} |")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report)
    if failures:
        raise SystemExit(f"validation_failures={failures}")


if __name__ == "__main__":
    main()

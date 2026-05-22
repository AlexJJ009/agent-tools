#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from registry_core import add_db_arg, connect, load_json, utc_now


CHECKS = [
    ("dpo_code_humaneval_mean3", "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/eval_code_mean3/humaneval_summary.json", ("mean@3", "humaneval"), "humaneval", "mean@3"),
    ("dpo_code_mbpp_mean3", "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/eval_code_mean3/mbpp_summary.json", ("mean@3", "mbpp"), "mbpp", "mean@3"),
    ("dpo_code_bcb_mean3", "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/eval_code_mean3/test/eval_summary.json", ("mean@3",), "BigCodeBench", "mean@3"),
    ("dpo_code_lcb_mean3", "/data-1/model_weights/qwen3-4b-code-m1-dpo-code/step_50/eval_code_mean3/eval_summary.json", ("mean@3",), "LiveCodeBench", "mean@3"),
    ("dpo_math_math500_mean3", "/data-1/model_weights/qwen3-4b-sft-dpo/step_367/inference_n3/eval_metrics.json", ("metrics", "HuggingFaceH4/MATH-500", "mean@3"), "HuggingFaceH4/MATH-500", "mean@3"),
    ("dpo_math_high_extraction", "/data-1/model_weights/gemma3-4b-sft-dpo/step_326/inference_n3/eval_metrics.json", ("metrics", "HuggingFaceH4/MATH-500", "extraction_fail"), "HuggingFaceH4/MATH-500", "extraction_fail"),
    ("verl_v2_1a_math500", "/data-1/model_weights/WDL-SFT-4B-MATH-1A/step_225_model2/inference_n3/eval_metrics.json", ("metrics", "HuggingFaceH4/MATH-500", "mean@3"), "HuggingFaceH4/MATH-500", "mean@3"),
    ("verl_v1_m55_math500", "/data-1/model_weights/WDL-SFT-4B-MATH-M5-5/step_300_model2/inference_n3/eval_metrics.json", ("metrics", "HuggingFaceH4/MATH-500", "mean@3"), "HuggingFaceH4/MATH-500", "mean@3"),
]


def get_nested(obj, keys):
    cur = obj
    for key in keys:
        cur = cur[key]
    return cur


def db_value(conn, source_path: str, dataset: str, metric: str):
    row = conn.execute(
        """
        select em.metric_value
        from eval_metrics em
        join eval_runs er on er.id = em.eval_run_id
        left join datasets d on d.id = em.dataset_id
        where er.raw_metrics_path = ?
          and d.name = ?
          and em.metric_name = ?
        """,
        (source_path, dataset, metric),
    ).fetchone()
    return None if row is None else row["metric_value"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate registry imports against source JSON spot checks")
    add_db_arg(parser)
    parser.add_argument("--report", default=str(Path(__file__).resolve().parent / "reports" / "validation_report.md"))
    args = parser.parse_args()
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Experiment Registry Validation Report", "", f"Checked at: `{utc_now()}`", "", "| Check | Source | Source value | DB value | Result |", "|---|---|---:|---:|---|"]
    failures = 0
    with connect(args.db) as conn:
        check_names = [name for name, *_ in CHECKS]
        conn.execute(
            f"delete from validation_checks where check_name in ({','.join(['?'] * len(check_names))})",
            check_names,
        )
        for name, source, keys, dataset, metric in CHECKS:
            p = Path(source)
            if not p.exists():
                source_value = "SOURCE_MISSING"
                database_value = db_value(conn, source, dataset, metric)
                passed = True
                result = "SKIP"
                notes = "spot check skipped: source artifact missing"
            else:
                source_value = get_nested(load_json(p), keys)
                database_value = db_value(conn, source, dataset, metric)
                passed = database_value is not None and abs(float(source_value) - float(database_value)) < 1e-9
                result = "PASS" if passed else "FAIL"
                notes = "spot check"
            failures += 0 if passed else 1
            conn.execute(
                "insert into validation_checks(check_name, source_path, source_value, database_value, passed, checked_at, notes) values (?, ?, ?, ?, ?, ?, ?)",
                (name, source, str(source_value), str(database_value), int(passed), utc_now(), notes),
            )
            lines.append(f"| `{name}` | `{source}` | {source_value} | {database_value} | {result} |")
        conn.commit()
    Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.report)
    if failures:
        raise SystemExit(f"validation_failures={failures}")


if __name__ == "__main__":
    main()

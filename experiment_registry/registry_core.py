#!/usr/bin/env python3
"""Shared helpers for the local experiment registry."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DB = "/data-1/experiment_registry/experiment_registry.sqlite"
LOCAL_DEFAULT_DB = str(Path(__file__).resolve().parent / "experiment_registry.sqlite")
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text())


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"


def one(conn: sqlite3.Connection, sql: str, args: Iterable[Any] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, tuple(args)).fetchone()


def upsert_project(conn: sqlite3.Connection, name: str, repo_path: str | None = None, default_branch: str | None = None, notes: str | None = None) -> int:
    project_key = slug(name)
    conn.execute(
        """
        insert into projects(project_key, name, repo_path, default_branch, notes)
        values (?, ?, ?, ?, ?)
        on conflict(name) do update set
          repo_path=coalesce(excluded.repo_path, projects.repo_path),
          default_branch=coalesce(excluded.default_branch, projects.default_branch),
          notes=coalesce(excluded.notes, projects.notes)
        """,
        (project_key, name, repo_path, default_branch, notes),
    )
    return int(one(conn, "select id from projects where name=?", (name,))["id"])


def upsert_dataset(conn: sqlite3.Connection, dataset_key: str, name: str, domain: str | None = None, path: str | None = None, split: str | None = None, row_count: int | None = None, notes: str | None = None) -> int:
    conn.execute(
        """
        insert into datasets(dataset_key, name, domain, path, split, row_count, notes)
        values (?, ?, ?, ?, ?, ?, ?)
        on conflict(dataset_key) do update set
          name=excluded.name,
          domain=coalesce(excluded.domain, datasets.domain),
          path=coalesce(excluded.path, datasets.path),
          split=coalesce(excluded.split, datasets.split),
          row_count=coalesce(excluded.row_count, datasets.row_count),
          notes=coalesce(excluded.notes, datasets.notes)
        """,
        (dataset_key, name, domain, path, split, row_count, notes),
    )
    return int(one(conn, "select id from datasets where dataset_key=?", (dataset_key,))["id"])


def upsert_model(conn: sqlite3.Connection, model_key: str, model_path: str, display_name: str | None = None, base_model: str | None = None, checkpoint_step: int | None = None, checkpoint_kind: str | None = None, project_id: int | None = None, git_branch: str | None = None, git_commit: str | None = None, notes: str | None = None, model_role: str | None = None, is_best: int | None = None, is_latest: int | None = None, extra_json: str | None = None) -> int:
    conn.execute(
        """
        insert into models(model_key, display_name, base_model, model_path, checkpoint_step, checkpoint_kind, model_role, is_best, is_latest, project_id, git_branch, git_commit, extra_json, notes)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(model_key) do update set
          display_name=coalesce(excluded.display_name, models.display_name),
          base_model=coalesce(excluded.base_model, models.base_model),
          model_path=excluded.model_path,
          checkpoint_step=coalesce(excluded.checkpoint_step, models.checkpoint_step),
          checkpoint_kind=coalesce(excluded.checkpoint_kind, models.checkpoint_kind),
          model_role=coalesce(excluded.model_role, models.model_role),
          is_best=coalesce(excluded.is_best, models.is_best),
          is_latest=coalesce(excluded.is_latest, models.is_latest),
          project_id=coalesce(excluded.project_id, models.project_id),
          git_branch=coalesce(excluded.git_branch, models.git_branch),
          git_commit=coalesce(excluded.git_commit, models.git_commit),
          extra_json=coalesce(excluded.extra_json, models.extra_json),
          notes=coalesce(excluded.notes, models.notes)
        """,
        (model_key, display_name, base_model, model_path, checkpoint_step, checkpoint_kind, model_role, is_best, is_latest, project_id, git_branch, git_commit, extra_json, notes),
    )
    return int(one(conn, "select id from models where model_key=?", (model_key,))["id"])


def upsert_experiment(conn: sqlite3.Connection, project_id: int, experiment_key: str, display_name: str, method: str | None = None, domain: str | None = None, variant: str | None = None, status: str | None = "completed", trust_level: str | None = "needs_review", parent_experiment_id: int | None = None, created_at: str | None = None, notes: str | None = None, method_family: str | None = None, method_variant: str | None = None, method_version: str | None = None, trust_reason: str | None = None, extra_json: str | None = None) -> int:
    now = utc_now()
    conn.execute(
        """
        insert into experiments(project_id, experiment_key, display_name, method, method_family, method_variant, method_version, domain, variant, status, trust_level, trust_reason, parent_experiment_id, created_at, updated_at, extra_json, notes)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(experiment_key) do update set
          project_id=excluded.project_id,
          display_name=excluded.display_name,
          method=coalesce(excluded.method, experiments.method),
          method_family=coalesce(excluded.method_family, experiments.method_family),
          method_variant=coalesce(excluded.method_variant, experiments.method_variant),
          method_version=coalesce(excluded.method_version, experiments.method_version),
          domain=coalesce(excluded.domain, experiments.domain),
          variant=coalesce(excluded.variant, experiments.variant),
          status=coalesce(excluded.status, experiments.status),
          trust_level=coalesce(excluded.trust_level, experiments.trust_level),
          trust_reason=coalesce(excluded.trust_reason, experiments.trust_reason),
          parent_experiment_id=coalesce(excluded.parent_experiment_id, experiments.parent_experiment_id),
          created_at=coalesce(excluded.created_at, experiments.created_at),
          updated_at=excluded.updated_at,
          extra_json=coalesce(excluded.extra_json, experiments.extra_json),
          notes=coalesce(excluded.notes, experiments.notes)
        """,
        (project_id, experiment_key, display_name, method, method_family, method_variant, method_version, domain, variant, status, trust_level, trust_reason, parent_experiment_id, created_at, now, extra_json, notes),
    )
    return int(one(conn, "select id from experiments where experiment_key=?", (experiment_key,))["id"])


def upsert_eval_run(conn: sqlite3.Connection, **kw: Any) -> int:
    fields = [
        "eval_run_key", "experiment_id", "model_id", "eval_name", "domain", "script_path", "script_version",
        "parser_version", "eval_harness", "framework", "output_dir", "raw_metrics_path", "raw_samples_path", "n",
        "num_samples", "repeat_count", "temperature", "top_p", "max_tokens", "max_new_tokens",
        "top_k", "min_p", "do_sample", "max_prompt_tokens", "seed", "timeout_seconds", "thinking",
        "enable_thinking", "prompt_mode", "chat_template", "system_prompt_key", "preamble_mode",
        "command", "cwd", "hostname", "git_branch", "git_commit", "eval_datetime", "trust_level",
        "trust_reason", "supersedes_eval_run_id", "extra_json", "notes",
    ]
    if not kw.get("eval_run_key"):
        raw = kw.get("raw_metrics_path") or kw.get("output_dir") or kw.get("eval_name")
        kw["eval_run_key"] = slug(f"{kw.get('model_id')}.{kw.get('eval_name')}.{raw}")
    values = [kw.get(f) for f in fields]
    conn.execute(
        f"""
        insert into eval_runs({", ".join(fields)})
        values ({", ".join(["?"] * len(fields))})
        on conflict(eval_run_key) do update set
          experiment_id=coalesce(excluded.experiment_id, eval_runs.experiment_id),
          model_id=excluded.model_id,
          eval_name=excluded.eval_name,
          domain=coalesce(excluded.domain, eval_runs.domain),
          script_path=coalesce(excluded.script_path, eval_runs.script_path),
          script_version=coalesce(excluded.script_version, eval_runs.script_version),
          parser_version=coalesce(excluded.parser_version, eval_runs.parser_version),
          eval_harness=coalesce(excluded.eval_harness, eval_runs.eval_harness),
          framework=coalesce(excluded.framework, eval_runs.framework),
          output_dir=coalesce(excluded.output_dir, eval_runs.output_dir),
          raw_metrics_path=coalesce(excluded.raw_metrics_path, eval_runs.raw_metrics_path),
          raw_samples_path=coalesce(excluded.raw_samples_path, eval_runs.raw_samples_path),
          n=coalesce(excluded.n, eval_runs.n),
          num_samples=coalesce(excluded.num_samples, eval_runs.num_samples),
          repeat_count=coalesce(excluded.repeat_count, eval_runs.repeat_count),
          temperature=coalesce(excluded.temperature, eval_runs.temperature),
          top_p=coalesce(excluded.top_p, eval_runs.top_p),
          top_k=coalesce(excluded.top_k, eval_runs.top_k),
          min_p=coalesce(excluded.min_p, eval_runs.min_p),
          do_sample=coalesce(excluded.do_sample, eval_runs.do_sample),
          max_tokens=coalesce(excluded.max_tokens, eval_runs.max_tokens),
          max_prompt_tokens=coalesce(excluded.max_prompt_tokens, eval_runs.max_prompt_tokens),
          max_new_tokens=coalesce(excluded.max_new_tokens, eval_runs.max_new_tokens),
          seed=coalesce(excluded.seed, eval_runs.seed),
          timeout_seconds=coalesce(excluded.timeout_seconds, eval_runs.timeout_seconds),
          thinking=coalesce(excluded.thinking, eval_runs.thinking),
          enable_thinking=coalesce(excluded.enable_thinking, eval_runs.enable_thinking),
          prompt_mode=coalesce(excluded.prompt_mode, eval_runs.prompt_mode),
          chat_template=coalesce(excluded.chat_template, eval_runs.chat_template),
          system_prompt_key=coalesce(excluded.system_prompt_key, eval_runs.system_prompt_key),
          preamble_mode=coalesce(excluded.preamble_mode, eval_runs.preamble_mode),
          command=coalesce(excluded.command, eval_runs.command),
          cwd=coalesce(excluded.cwd, eval_runs.cwd),
          hostname=coalesce(excluded.hostname, eval_runs.hostname),
          git_branch=coalesce(excluded.git_branch, eval_runs.git_branch),
          git_commit=coalesce(excluded.git_commit, eval_runs.git_commit),
          eval_datetime=coalesce(excluded.eval_datetime, eval_runs.eval_datetime),
          trust_level=coalesce(excluded.trust_level, eval_runs.trust_level),
          trust_reason=coalesce(excluded.trust_reason, eval_runs.trust_reason),
          supersedes_eval_run_id=coalesce(excluded.supersedes_eval_run_id, eval_runs.supersedes_eval_run_id),
          extra_json=coalesce(excluded.extra_json, eval_runs.extra_json),
          notes=coalesce(excluded.notes, eval_runs.notes)
        """,
        values,
    )
    row = one(conn, "select id from eval_runs where eval_run_key=?", (kw["eval_run_key"],))
    return int(row["id"])


def upsert_metric(conn: sqlite3.Connection, eval_run_id: int, dataset_id: int | None, metric_name: str, metric_value: float | int | None, numerator: float | int | None = None, denominator: float | int | None = None, metric_scope: str | None = None, notes: str | None = None) -> None:
    metric_scope = metric_scope or ""
    conn.execute(
        """
        insert into eval_metrics(eval_run_id, dataset_id, metric_name, metric_value, value_type, numerator, denominator, metric_scope, notes)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(eval_run_id, dataset_id, metric_name, metric_scope) do update set
          metric_value=excluded.metric_value,
          value_type=coalesce(excluded.value_type, eval_metrics.value_type),
          numerator=coalesce(excluded.numerator, eval_metrics.numerator),
          denominator=coalesce(excluded.denominator, eval_metrics.denominator),
          notes=coalesce(excluded.notes, eval_metrics.notes)
        """,
        (eval_run_id, dataset_id, metric_name, metric_value, "integer" if isinstance(metric_value, int) else "float", numerator, denominator, metric_scope, notes),
    )


def add_source_record(conn: sqlite3.Connection, source_path: str, source_type: str, source_section: str | None, importer: str, record_kind: str, record_id: int, notes: str | None = None) -> None:
    source_section = source_section or ""
    conn.execute(
        """
        insert into source_records(source_path, source_type, source_section, imported_at, importer, record_kind, record_id, entity_table, entity_key, notes)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(importer, source_path, source_section, record_kind, entity_key) do update set
          imported_at=excluded.imported_at,
          record_id=excluded.record_id,
          notes=coalesce(excluded.notes, source_records.notes)
        """,
        (source_path, source_type, source_section, utc_now(), importer, record_kind, record_id, record_kind, str(record_id), notes),
    )


def add_artifact(conn: sqlite3.Connection, artifact_kind: str, path: str, experiment_id: int | None = None, training_run_id: int | None = None, eval_run_id: int | None = None, model_id: int | None = None, description: str | None = None, notes: str | None = None) -> None:
    artifact_key = slug(f"{artifact_kind}.{path}.{experiment_id}.{training_run_id}.{eval_run_id}.{model_id}")
    conn.execute(
        """
        insert or ignore into artifacts(artifact_key, experiment_id, training_run_id, eval_run_id, model_id, artifact_kind, path, description, notes)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (artifact_key, experiment_id, training_run_id, eval_run_id, model_id, artifact_kind, path, description, notes),
    )


def add_tag(conn: sqlite3.Connection, entity_type: str, entity_id: int, tag: str) -> None:
    conn.execute(
        "insert or ignore into entity_tags(entity_type, entity_id, tag) values (?, ?, ?)",
        (entity_type, entity_id, tag),
    )


def add_quality_flag(conn: sqlite3.Connection, entity_type: str, entity_id: int, flag: str, severity: str | None = None, reason: str | None = None, notes: str | None = None) -> None:
    conn.execute(
        """
        insert into quality_flags(entity_type, entity_id, flag, severity, reason, notes)
        values (?, ?, ?, ?, ?, ?)
        on conflict(entity_type, entity_id, flag) do update set
          severity=coalesce(excluded.severity, quality_flags.severity),
          reason=coalesce(excluded.reason, quality_flags.reason),
          notes=coalesce(excluded.notes, quality_flags.notes)
        """,
        (entity_type, entity_id, flag, severity, reason, notes),
    )


def print_rows(rows: list[sqlite3.Row], fmt: str = "table") -> None:
    if fmt == "json":
        print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
        return
    if fmt == "csv":
        if not rows:
            return
        writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(dict(r) for r in rows)
        return
    if not rows:
        print("(no rows)")
        return
    headers = list(rows[0].keys())
    widths = {h: max(len(h), *(len(str(r[h])) for r in rows)) for h in headers}
    print("| " + " | ".join(h.ljust(widths[h]) for h in headers) + " |")
    print("| " + " | ".join("-" * widths[h] for h in headers) + " |")
    for r in rows:
        print("| " + " | ".join(str(r[h]).ljust(widths[h]) for h in headers) + " |")


def add_db_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=os.environ.get("EXPERIMENT_REGISTRY_DB", DEFAULT_DB), help=f"SQLite path. Default: {DEFAULT_DB}")

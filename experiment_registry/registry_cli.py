#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from registry_core import add_db_arg, connect, init_db, print_rows, upsert_experiment, upsert_project


QUERY_DIR = Path(__file__).resolve().parent / "queries"


NAMED_QUERIES = {
    "dpo-code-n1": "dpo_code_n1.sql",
    "dpo-math-best": "dpo_math_best.sql",
    "best-bcb-model": "best_bcb_model.sql",
    "verl-v123": "verl_v123.sql",
    "needs-review": "needs_review.sql",
}


def ensure_select(sql: str) -> None:
    stripped = sql.strip().lower()
    if not (stripped.startswith("select") or stripped.startswith("with")):
        raise SystemExit("Only read-only SELECT/WITH SQL is allowed by this command.")
    banned = [" insert ", " update ", " delete ", " drop ", " alter ", " create ", " pragma ", " attach "]
    padded = " " + stripped.replace("\n", " ") + " "
    if any(token in padded for token in banned):
        raise SystemExit("Read-only query rejected because it contains a write/admin keyword.")


def cmd_init(args: argparse.Namespace) -> None:
    init_db(args.db)
    print(args.db)


def cmd_query(args: argparse.Namespace) -> None:
    if args.list:
        for name in sorted(NAMED_QUERIES):
            print(name)
        return
    if args.name:
        if args.name not in NAMED_QUERIES:
            raise SystemExit(f"Unknown named query: {args.name}")
        sql = (QUERY_DIR / NAMED_QUERIES[args.name]).read_text()
    elif args.sql:
        sql = args.sql
    elif args.file:
        sql = Path(args.file).read_text()
    else:
        raise SystemExit("Provide --name, --sql, --file, or --list.")
    ensure_select(sql)
    with connect(args.db) as conn:
        rows = conn.execute(sql).fetchall()
    print_rows(rows, args.format)


def cmd_summary(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        rows = conn.execute(
            """
            select 'projects' as table_name, count(*) as rows from projects union all
            select 'experiments', count(*) from experiments union all
            select 'models', count(*) from models union all
            select 'datasets', count(*) from datasets union all
            select 'training_runs', count(*) from training_runs union all
            select 'eval_runs', count(*) from eval_runs union all
            select 'eval_metrics', count(*) from eval_metrics union all
            select 'artifacts', count(*) from artifacts union all
            select 'source_records', count(*) from source_records
            """
        ).fetchall()
    print_rows(rows, args.format)


def cmd_upsert_experiment(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        project_id = upsert_project(conn, args.project, args.repo_path, args.branch, None)
        exp_id = upsert_experiment(
            conn,
            project_id,
            args.experiment_key,
            args.display_name,
            method=args.method,
            domain=args.domain,
            variant=args.variant,
            status=args.status,
            trust_level=args.trust_level,
            notes=args.notes,
        )
        conn.commit()
    print(exp_id)


def cmd_mark_eval(args: argparse.Namespace) -> None:
    set_parts = ["trust_level=?"]
    values: list[object] = [args.trust_level]
    if args.notes:
        set_parts.append("notes=coalesce(notes || char(10), '') || ?")
        values.append(args.notes)
    where = "id=?"
    values.append(args.eval_id)
    with connect(args.db) as conn:
        cur = conn.execute(f"update eval_runs set {', '.join(set_parts)} where {where}", values)
        conn.commit()
    print(f"updated={cur.rowcount}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local SQLite experiment registry CLI")
    add_db_arg(parser)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="Initialize the SQLite database")
    add_db_arg(p)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("query", help="Run a read-only SQL query")
    add_db_arg(p)
    p.add_argument("--name", choices=sorted(NAMED_QUERIES))
    p.add_argument("--sql")
    p.add_argument("--file")
    p.add_argument("--list", action="store_true")
    p.add_argument("--format", choices=["table", "json", "csv"], default="table")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("summary", help="Show table row counts")
    add_db_arg(p)
    p.add_argument("--format", choices=["table", "json", "csv"], default="table")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("upsert-experiment", help="Add or update experiment metadata")
    add_db_arg(p)
    p.add_argument("--project", required=True)
    p.add_argument("--repo-path")
    p.add_argument("--branch")
    p.add_argument("--experiment-key", required=True)
    p.add_argument("--display-name", required=True)
    p.add_argument("--method")
    p.add_argument("--domain")
    p.add_argument("--variant")
    p.add_argument("--status", default="completed")
    p.add_argument("--trust-level", default="needs_review")
    p.add_argument("--notes")
    p.set_defaults(func=cmd_upsert_experiment)

    p = sub.add_parser("mark-eval", help="Mark an eval run as trusted/superseded/buggy/needs_review")
    add_db_arg(p)
    p.add_argument("--eval-id", type=int, required=True)
    p.add_argument("--trust-level", required=True, choices=["trusted", "usable_with_caution", "needs_review", "buggy", "superseded"])
    p.add_argument("--notes")
    p.set_defaults(func=cmd_mark_eval)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

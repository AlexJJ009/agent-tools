#!/usr/bin/env python3
"""Verify Codex Fast Mode from real sub2api usage logs.

This is intentionally runtime-only. It does not infer success from local config
or patched bundle files. Success means the provider billing log shows
`service_tier = priority` and the expected Fast unit price for the request.
"""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass


DEFAULT_SQL = r"""
select id, created_at, model, coalesce(service_tier,'<NULL>') as tier, request_id,
       input_tokens, output_tokens, input_cost, output_cost, total_cost,
       case when input_tokens > 0 then round(input_cost * 1000000 / input_tokens, 2) end as input_usd_per_m,
       case when output_tokens > 0 then round(output_cost * 1000000 / output_tokens, 2) end as output_usd_per_m,
       left(user_agent,220) as ua
from usage_logs
where {where_clause}
order by created_at desc
limit {limit};
"""


@dataclass
class UsageRow:
    id: str
    created_at: str
    model: str
    tier: str
    request_id: str
    input_tokens: str
    output_tokens: str
    input_cost: str
    output_cost: str
    total_cost: str
    input_usd_per_m: str
    output_usd_per_m: str
    ua: str

    @property
    def is_fast(self) -> bool:
        return self.tier == "priority"


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def build_sql(args: argparse.Namespace) -> str:
    clauses = []
    if args.request_id:
        request_ids = ", ".join("'" + rid.replace("'", "''") + "'" for rid in args.request_id)
        clauses.append(f"request_id in ({request_ids})")
    else:
        clauses.append(f"created_at >= now() - interval '{int(args.since_minutes)} minutes'")
    if args.user_agent_like:
        clauses.append("user_agent like '" + args.user_agent_like.replace("'", "''") + "'")
    if args.model_like:
        clauses.append("model like '" + args.model_like.replace("'", "''") + "'")
    return DEFAULT_SQL.format(where_clause=" and ".join(clauses), limit=int(args.limit))


def run_query(args: argparse.Namespace, sql: str) -> str:
    psql_cmd = (
        f"docker exec -i {shell_quote(args.container)} "
        f"psql -U {shell_quote(args.db_user)} -d {shell_quote(args.db_name)} "
        "-P pager=off -A -F '|'"
    )
    if args.ssh_host:
        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={args.connect_timeout}",
            "-o",
            "IPQoS=none",
            args.ssh_host,
            psql_cmd,
        ]
    else:
        cmd = ["bash", "-lc", psql_cmd]
    result = subprocess.run(cmd, input=sql, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def parse_rows(raw: str) -> list[UsageRow]:
    lines = [line for line in raw.splitlines() if line and not line.startswith("(")]
    if len(lines) <= 1:
        return []
    reader = csv.DictReader(lines, delimiter="|")
    rows = []
    for item in reader:
        rows.append(
            UsageRow(
                id=item.get("id", ""),
                created_at=item.get("created_at", ""),
                model=item.get("model", ""),
                tier=item.get("tier", ""),
                request_id=item.get("request_id", ""),
                input_tokens=item.get("input_tokens", ""),
                output_tokens=item.get("output_tokens", ""),
                input_cost=item.get("input_cost", ""),
                output_cost=item.get("output_cost", ""),
                total_cost=item.get("total_cost", ""),
                input_usd_per_m=item.get("input_usd_per_m", ""),
                output_usd_per_m=item.get("output_usd_per_m", ""),
                ua=item.get("ua", ""),
            )
        )
    return rows


def print_table(rows: list[UsageRow]) -> None:
    if not rows:
        print("No matching usage_logs rows.")
        return
    for row in rows:
        print(
            "|".join(
                [
                    row.id,
                    row.created_at,
                    row.model,
                    row.tier,
                    row.request_id,
                    f"in=${row.input_usd_per_m}/M",
                    f"out=${row.output_usd_per_m}/M",
                    f"cost={row.total_cost}",
                    row.ua,
                ]
            )
        )


def expected_fast_price(row: UsageRow) -> tuple[str, str] | None:
    if row.model == "gpt-5.5":
        return ("10.00", "60.00")
    if row.model == "gpt-5.4":
        return ("5.00", "30.00")
    return None


def expected_standard_price(row: UsageRow) -> tuple[str, str] | None:
    if row.model == "gpt-5.5":
        return ("5.00", "30.00")
    if row.model == "gpt-5.4":
        return ("2.50", "15.00")
    return None


def check_expectation(rows: list[UsageRow], expect: str) -> int:
    if expect == "any":
        return 0 if rows else 1
    if not rows:
        print("FAIL: no matching rows for expectation check.", file=sys.stderr)
        return 1

    failures = []
    for row in rows:
        if expect == "fast":
            if not row.is_fast:
                failures.append(f"{row.request_id}: expected priority, got {row.tier}")
            price = expected_fast_price(row)
            if price and (row.input_usd_per_m, row.output_usd_per_m) != price:
                failures.append(
                    f"{row.request_id}: expected Fast price {price[0]}/{price[1]}, "
                    f"got {row.input_usd_per_m}/{row.output_usd_per_m}"
                )
        elif expect == "standard":
            if row.tier != "<NULL>":
                failures.append(f"{row.request_id}: expected NULL tier, got {row.tier}")
            price = expected_standard_price(row)
            if price and (row.input_usd_per_m, row.output_usd_per_m) != price:
                failures.append(
                    f"{row.request_id}: expected standard price {price[0]}/{price[1]}, "
                    f"got {row.input_usd_per_m}/{row.output_usd_per_m}"
                )
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"PASS: {expect} expectation satisfied for {len(rows)} row(s).")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Codex Fast Mode from sub2api usage logs.")
    parser.add_argument("--ssh-host", default="ovh", help="SSH host that can access the sub2api Postgres container.")
    parser.add_argument("--container", default="sub2api-postgres")
    parser.add_argument("--db-user", default="sub2api")
    parser.add_argument("--db-name", default="sub2api")
    parser.add_argument("--connect-timeout", type=int, default=20)
    parser.add_argument("--since-minutes", type=int, default=15)
    parser.add_argument("--request-id", action="append", help="Exact request_id to verify. Repeatable.")
    parser.add_argument("--user-agent-like", default="Codex Desktop/%")
    parser.add_argument("--model-like", default="gpt-5%")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--expect", choices=["any", "fast", "standard"], default="any")
    parser.add_argument("--json", action="store_true", help="Print rows as JSON instead of compact text.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sql = build_sql(args)
    raw = run_query(args, sql)
    rows = parse_rows(raw)
    if args.json:
        print(json.dumps([row.__dict__ for row in rows], ensure_ascii=False, indent=2))
    else:
        print_table(rows)
    return check_expectation(rows, args.expect)


if __name__ == "__main__":
    raise SystemExit(main())

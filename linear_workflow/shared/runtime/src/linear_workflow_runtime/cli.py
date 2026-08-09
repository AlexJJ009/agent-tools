from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .contracts import load_json, validate_schema


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="linear-workflow")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    for command, schema in (
        ("plan-check", "prd"),
        ("batch-check", "batch"),
        ("pr-check", "evidence"),
    ):
        child = subparsers.add_parser(command)
        child.add_argument("--input", type=Path, required=True)
        child.set_defaults(schema=schema)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    try:
        value = load_json(args.input)
        errors = validate_schema(value, args.schema)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"input: field=$ rule=LW-INPUT: {exc}; fix: provide readable valid JSON", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"schema: field={error} rule=LW-SCHEMA: invalid contract; fix: follow the canonical schema", file=sys.stderr)
        return 1
    print(f"ok: {args.command} schema contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

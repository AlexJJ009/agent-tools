from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .contracts import load_json
from .validators import validate_batch, validate_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="linear-workflow")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    for command in (
        "plan-check",
        "batch-check",
        "pr-check",
    ):
        child = subparsers.add_parser(command)
        child.add_argument("--input", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    try:
        value = load_json(args.input)
        if args.command == "plan-check":
            errors = validate_plan(value)
        elif args.command == "batch-check":
            errors = validate_batch(value)
        else:
            from .validators import validate_pr

            errors = validate_pr(value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"input: field=$ rule=LW-INPUT: {exc}; fix: provide readable valid JSON", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(error.render(), file=sys.stderr)
        return 1
    print(f"ok: {args.command} schema contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--local-only", action="store_true")
    doctor.add_argument("--home", type=Path, default=Path.home())
    doctor.add_argument("--repo-config", type=Path)
    version = subparsers.add_parser("version")
    version.add_argument("--json", action="store_true", required=True)
    migrate = subparsers.add_parser("migrate")
    migration_sources = migrate.add_subparsers(dest="migration_source", required=True)
    goal_plan = migration_sources.add_parser("goal-plan")
    goal_plan.add_argument("goal_dir", type=Path)
    goal_plan.add_argument(
        "--dry-run",
        action="store_true",
        help="render the read-only proposal (the only supported v1 mode)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    if args.command == "doctor":
        from .doctor import render, run_doctor

        return render(run_doctor(args.home, args.repo_config, args.local_only))
    if args.command == "version":
        from .metadata import version_metadata

        print(json.dumps(version_metadata(), separators=(",", ":")))
        return 0
    if args.command == "migrate":
        from .migration import MigrationError, build_goal_plan_migration

        try:
            proposal = build_goal_plan_migration(args.goal_dir)
        except (OSError, MigrationError, UnicodeError) as exc:
            print(f"migration: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(proposal, sort_keys=True, separators=(",", ":")))
        return 0
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

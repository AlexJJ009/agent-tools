#!/usr/bin/env python3
"""Install/check/remove the user-level Codex work-report hook definitions."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MARKER = "work-report-v2"
EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "Interrupt")
DEFAULT_DESCRIPTION = "User-level Codex hooks managed by agent-tools work-report v2."


class InstallError(Exception):
    pass


def python_executable() -> str:
    candidate = shutil.which("python3") or sys.executable
    resolved = Path(candidate).resolve()
    if not resolved.is_absolute():
        raise InstallError(f"python executable is not absolute: {candidate}")
    return str(resolved)


def skill_runtime(home: Path) -> Path:
    return home / ".agents" / "skills" / "work-report" / "scripts" / "report_runtime.py"


def hook_command(home: Path) -> str:
    runtime = skill_runtime(home).resolve()
    return shlex.join([python_executable(), str(runtime), "hook"])


def matcher_for(event: str) -> str | None:
    if event == "SessionStart":
        return "startup|resume|clear|compact"
    if event == "PostToolUse":
        return ".*"
    return None


def managed_handler(home: Path) -> dict[str, Any]:
    handler: dict[str, Any] = {
        "type": "command",
        "command": hook_command(home),
        "timeout": 30,
        "statusMessage": MARKER,
    }
    handler["additionalContextLimit"] = 5000
    return handler


def managed_group(event: str, home: Path) -> dict[str, Any]:
    group: dict[str, Any] = {"hooks": [managed_handler(home)]}
    if event in {"Stop", "Interrupt"}:
        group["hooks"][0].pop("additionalContextLimit", None)
    if event == "Interrupt":
        group["hooks"][0]["timeout"] = 3
    matcher = matcher_for(event)
    if matcher is not None:
        group["matcher"] = matcher
    return group


def hooks_path(home: Path) -> Path:
    return home / ".codex" / "hooks.json"


def backup_dir(home: Path) -> Path:
    return home / ".local" / "state" / "work-report" / "hooks-install-backups"


def run_target_guard(home: Path) -> None:
    guard = [
        sys.executable,
        str(ROOT / "scripts" / "codex_target_guard.py"),
        "--platform",
        "auto",
        "--codex-home",
        str(home / ".codex"),
        "--cc-switch-db",
        str(home / ".cc-switch" / "cc-switch.db"),
        "--path-only",
        "--allow-missing-config",
        "--allow-missing-cc-switch",
        "--skip-cc-switch-read-check",
        "--json",
    ]
    result = subprocess.run(guard, capture_output=True, text=True)
    if result.returncode:
        raise InstallError("target guard rejected hook installation: " + result.stdout + result.stderr)


def load_hooks_file(path: Path, *, missing_ok: bool) -> dict[str, Any]:
    if not path.exists():
        if missing_ok:
            return {"description": DEFAULT_DESCRIPTION, "hooks": {}}
        raise InstallError(f"hooks file is missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError(f"invalid hooks JSON preserved without changes: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError("invalid hooks JSON preserved without changes: top-level value must be an object")
    hooks = data.get("hooks")
    if hooks is None:
        data["hooks"] = {}
    elif not isinstance(hooks, dict):
        raise InstallError("invalid hooks JSON preserved without changes: hooks must be an object")
    return data


def command_points_to_runtime(command: Any, home: Path) -> bool:
    if not isinstance(command, str):
        return False
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if len(parts) != 3 or parts[2] != "hook":
        return False
    python = Path(parts[0])
    if not python.is_absolute() or not python.name.startswith("python"):
        return False
    return Path(parts[1]) == skill_runtime(home).resolve()


def is_same_handler(handler: Any, home: Path) -> bool:
    return (
        isinstance(handler, dict)
        and handler.get("type") == "command"
        and handler.get("statusMessage") == MARKER
        and command_points_to_runtime(handler.get("command"), home)
    )


def is_same_group(group: Any, event: str, home: Path) -> bool:
    return group == managed_group(event, home)


def is_owned_group(group: Any, home: Path) -> bool:
    handlers = group.get("hooks") if isinstance(group, dict) else None
    return isinstance(handlers, list) and len(handlers) == 1 and is_same_handler(handlers[0], home)


def event_groups(data: dict[str, Any], event: str) -> list[Any]:
    hooks = data.setdefault("hooks", {})
    groups = hooks.get(event)
    if groups is None:
        groups = []
        hooks[event] = groups
    if not isinstance(groups, list):
        raise InstallError(f"invalid hooks JSON preserved without changes: hooks.{event} must be a list")
    return groups


def find_missing_events(data: dict[str, Any], home: Path) -> list[str]:
    missing: list[str] = []
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return list(EVENTS)
    for event in EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list) or not any(is_same_group(group, event, home) for group in groups):
            missing.append(event)
    return missing


def install_groups(data: dict[str, Any], home: Path) -> int:
    added = 0
    for event in EVENTS:
        groups = event_groups(data, event)
        owned = [i for i, group in enumerate(groups) if is_owned_group(group, home)]
        if owned:
            groups[owned[0]] = managed_group(event, home)
            for index in reversed(owned[1:]):
                groups.pop(index)
        else:
            groups.append(managed_group(event, home))
            added += 1
    data.setdefault("description", DEFAULT_DESCRIPTION)
    return added


def remove_groups(data: dict[str, Any], home: Path) -> int:
    removed = 0
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        raise InstallError("invalid hooks JSON preserved without changes: hooks must be an object")
    for event in EVENTS:
        groups = hooks.get(event)
        if groups is None:
            continue
        if not isinstance(groups, list):
            raise InstallError(f"invalid hooks JSON preserved without changes: hooks.{event} must be a list")
        kept = [group for group in groups if not is_owned_group(group, home)]
        removed += len(groups) - len(kept)
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    return removed


def atomic_write_json(path: Path, data: dict[str, Any], home: Path) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if path.exists():
        bdir = backup_dir(home)
        bdir.mkdir(parents=True, exist_ok=True)
        backup = bdir / ("hooks.json." + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".bak")
        shutil.copy2(path, backup)
    fd, tmp = tempfile.mkstemp(prefix=".hooks.json.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    return backup


def check(home: Path) -> dict[str, Any]:
    runtime = skill_runtime(home)
    data = load_hooks_file(hooks_path(home), missing_ok=False)
    missing = find_missing_events(data, home)
    if missing:
        raise InstallError("missing managed work-report hook events: " + ", ".join(missing))
    if not runtime.is_file():
        raise InstallError(f"installed report runtime is missing: {runtime}")
    return {
        "status": "pass",
        "hooks": str(hooks_path(home)),
        "runtime": str(runtime),
        "events_checked": len(EVENTS),
        "trust_status": "not_checked_by_installer",
    }


def install(home: Path) -> dict[str, Any]:
    run_target_guard(home)
    runtime = skill_runtime(home)
    if not runtime.is_file():
        raise InstallError(f"installed report runtime is missing: {runtime}")
    path = hooks_path(home)
    data = load_hooks_file(path, missing_ok=True)
    added = install_groups(data, home)
    backup = atomic_write_json(path, data, home)
    return {
        "status": "installed",
        "hooks": str(path),
        "runtime": str(runtime),
        "events_installed": len(EVENTS),
        "groups_added": added,
        "backup": str(backup) if backup else None,
        "trust_status": "not_checked_by_installer",
        "native_acceptance": "run Codex with --dangerously-bypass-hook-trust after reviewing the hook definition",
    }


def remove(home: Path) -> dict[str, Any]:
    run_target_guard(home)
    path = hooks_path(home)
    data = load_hooks_file(path, missing_ok=False)
    removed = remove_groups(data, home)
    backup = atomic_write_json(path, data, home)
    return {
        "status": "removed",
        "hooks": str(path),
        "groups_removed": removed,
        "backup": str(backup) if backup else None,
        "trust_status": "not_checked_by_installer",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="verify installed hook definitions")
    group.add_argument("--remove", action="store_true", help="remove only the managed work-report hook groups")
    args = parser.parse_args(argv)
    if platform.system() != "Linux":
        parser.error("this installer supports the current Linux/WSL user only")
    home = Path.home().resolve()
    try:
        if args.check:
            result = check(home)
        elif args.remove:
            result = remove(home)
        else:
            result = install(home)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, InstallError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

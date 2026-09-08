#!/usr/bin/env python3
"""Install/check/remove one task-local work-report scheduler cron entry."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "work-report.scheduler/1"
MARKER_PREFIX = "work-report-v2-schedule:"


class ScheduleError(Exception):
    pass


def task_hash(task_dir: Path) -> str:
    return hashlib.sha256(str(task_dir.resolve()).encode("utf-8")).hexdigest()


def marker(task_dir: Path) -> str:
    return MARKER_PREFIX + task_hash(task_dir)


def home_path() -> Path:
    return Path.home().resolve()


def installed_skill_script(home: Path, name: str) -> Path:
    return home / ".agents" / "skills" / "work-report" / "scripts" / name


def codex_home(home: Path) -> Path:
    return (home / ".codex").resolve()


def require_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ScheduleError(f"{label} is missing: {resolved}")
    return resolved


def codex_bin() -> Path:
    found = shutil.which("codex")
    if not found:
        raise ScheduleError("codex executable not found on PATH")
    return require_file(Path(found), "codex executable")


def python_bin() -> Path:
    found = shutil.which("python3") or sys.executable
    return require_file(Path(found), "python executable")


def run_target_guard(home: Path) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "codex_target_guard.py"),
        "--platform",
        "auto",
        "--codex-home",
        str(codex_home(home)),
        "--cc-switch-db",
        str(home / ".cc-switch" / "cc-switch.db"),
        "--path-only",
        "--allow-missing-config",
        "--allow-missing-cc-switch",
        "--skip-cc-switch-read-check",
        "--json",
    ]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode:
        raise ScheduleError("target guard rejected schedule install: " + proc.stdout + proc.stderr)


def run_runtime_status(runtime: Path, task_dir: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(runtime), "status", "--task-dir", str(task_dir)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode:
        raise ScheduleError("runtime status failed: " + proc.stdout + proc.stderr)
    data = json.loads(proc.stdout or "{}")
    if not isinstance(data, dict) or data.get("status") != "pass":
        raise ScheduleError("runtime status did not pass")
    return data


def has_interval(status: dict[str, Any]) -> bool:
    manifest = status.get("manifest")
    return isinstance(manifest, dict) and isinstance(manifest.get("interval_seconds"), int)


def interval_seconds(status: dict[str, Any]) -> int | None:
    manifest = status.get("manifest")
    value = manifest.get("interval_seconds") if isinstance(manifest, dict) else None
    return value if isinstance(value, int) else None


def runtime_delivered(status: dict[str, Any]) -> bool:
    manifest = status.get("manifest")
    if not isinstance(manifest, dict):
        return False
    for key in ("periodic", "final"):
        obligation = manifest.get(key)
        if isinstance(obligation, dict) and isinstance(obligation.get("last_ack"), dict):
            return True
    return False


def scheduler_metadata(home: Path, task_dir: Path) -> dict[str, Any]:
    scheduler = require_file(installed_skill_script(home, "report_scheduler.py"), "installed scheduler")
    runtime = require_file(installed_skill_script(home, "report_runtime.py"), "installed runtime")
    return {
        "schema_version": SCHEMA,
        "task_dir": str(task_dir.resolve()),
        "task_dir_sha256": task_hash(task_dir),
        "codex_bin": str(codex_bin()),
        "codex_home": str(codex_home(home)),
        "path": os.environ.get("PATH", ""),
        "python_bin": str(python_bin()),
        "scheduler": str(scheduler),
        "runtime": str(runtime),
        "uid": os.getuid() if hasattr(os, "getuid") else None,
    }


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def cron_escape(command: str) -> str:
    return command.replace("%", r"\%")


def marker_suffix(task_dir: Path) -> str:
    return "# " + marker(task_dir)


def has_marker_suffix(line: str, task_dir: Path) -> bool:
    return line.rstrip().endswith(marker_suffix(task_dir))


def validate_cron_line(line: str) -> None:
    parts = line.split()
    if len(parts) < 6 or parts[:5] != ["*", "*", "*", "*", "*"]:
        raise ScheduleError("managed cron line must start with five schedule fields")
    if " # " not in line:
        raise ScheduleError("managed cron line is missing marker comment")


def cron_line(meta: dict[str, Any], task_dir: Path) -> str:
    parts = [
        shlex.quote(str(meta.get("python_bin") or python_bin())),
        shlex.quote(meta["scheduler"]),
        "tick",
        "--task-dir",
        shlex.quote(str(task_dir.resolve())),
    ]
    line = "* * * * * " + cron_escape(" ".join(parts)) + " " + marker_suffix(task_dir)
    validate_cron_line(line)
    return line


def lock_path(home: Path) -> Path:
    path = home / ".local" / "state" / "work-report" / "schedule-crontab.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_crontab() -> list[str]:
    proc = subprocess.run(["crontab", "-l"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode == 0:
        return proc.stdout.splitlines()
    if proc.returncode == 1 and "no crontab for" in (proc.stderr or "").lower():
        return []
    if proc.returncode == 1:
        raise ScheduleError("cannot read crontab: " + proc.stderr)
    if proc.returncode != 0:
        raise ScheduleError("cannot read crontab: " + proc.stderr)


def crontab_validator_flag() -> str | None:
    for help_flag in ("--help", "-h"):
        try:
            proc = subprocess.run(["crontab", help_flag], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        except FileNotFoundError:
            return None
        text = (proc.stdout or "") + (proc.stderr or "")
        if "-T" in text:
            return "-T"
        if "-n" in text:
            return "-n"
    return None


def validate_crontab_file(path: Path) -> None:
    flag = crontab_validator_flag()
    if not flag:
        return
    proc = subprocess.run(["crontab", flag, str(path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode:
        raise ScheduleError("crontab validation failed: " + (proc.stderr or proc.stdout))


def write_crontab(lines: list[str]) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
        tmp = Path(fh.name)
        fh.write("\n".join(lines).rstrip() + ("\n" if lines else ""))
    try:
        validate_crontab_file(tmp)
        proc = subprocess.run(["crontab", str(tmp)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
    if proc.returncode:
        raise ScheduleError("cannot write crontab: " + proc.stderr)


def update_cron(home: Path, task_dir: Path, line: str | None) -> tuple[bool, int]:
    with lock_path(home).open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        lines = read_crontab()
        kept = [item for item in lines if not has_marker_suffix(item, task_dir)]
        removed = len(lines) - len(kept)
        if line is not None:
            validate_cron_line(line)
            kept.append(line)
        if kept != lines:
            write_crontab(kept)
        return line is not None, removed


def read_scheduler_meta(path: Path, task_dir: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ScheduleError(f"scheduler metadata must not be a symlink: {path}")
    if not path.is_file():
        raise ScheduleError(f"scheduler metadata is missing: {path}")
    meta = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(meta, dict):
        raise ScheduleError("scheduler metadata is not an object")
    if meta.get("schema_version") != SCHEMA or meta.get("task_dir") != str(task_dir.resolve()) or meta.get("task_dir_sha256") != task_hash(task_dir):
        raise ScheduleError("scheduler metadata does not match task")
    return meta


def check_registered(home: Path, task_dir: Path, expected_line: str) -> bool:
    with lock_path(home).open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        return any(line == expected_line for line in read_crontab())


def compare_metadata(home: Path, task_dir: Path, meta: dict[str, Any]) -> None:
    expected = scheduler_metadata(home, task_dir)
    keys = ["schema_version", "task_dir", "task_dir_sha256", "codex_home", "codex_bin", "python_bin", "runtime", "scheduler", "uid"]
    mismatches = [key for key in keys if meta.get(key) != expected.get(key)]
    if mismatches:
        raise ScheduleError("scheduler metadata mismatch: " + ", ".join(mismatches))
    if not isinstance(meta.get("path"), str):
        raise ScheduleError("scheduler metadata path is missing")


def install(task_dir: Path) -> dict[str, Any]:
    home = home_path()
    run_target_guard(home)
    task_dir = task_dir.resolve()
    meta = scheduler_metadata(home, task_dir)
    status = run_runtime_status(Path(meta["runtime"]), task_dir)
    if not has_interval(status):
        raise ScheduleError("task manifest has no confirmed periodic interval")
    atomic_write_json(task_dir / "scheduler.json", meta)
    registered, removed = update_cron(home, task_dir, cron_line(meta, task_dir))
    return {
        "status": "installed",
        "task_dir": str(task_dir),
        "crontab_registered": registered,
        "previous_entries_removed": removed,
        "runtime_delivered": runtime_delivered(status),
        "interval_seconds": interval_seconds(status),
        "marker": marker(task_dir),
    }


def check(task_dir: Path) -> dict[str, Any]:
    home = home_path()
    task_dir = task_dir.resolve()
    meta_path = task_dir / "scheduler.json"
    meta = read_scheduler_meta(meta_path, task_dir)
    compare_metadata(home, task_dir, meta)
    expected_line = cron_line(meta, task_dir)
    status = run_runtime_status(Path(meta["runtime"]), task_dir)
    registered = check_registered(home, task_dir, expected_line)
    if not registered:
        raise ScheduleError("managed cron line is missing or differs from metadata")
    return {
        "status": "pass",
        "task_dir": str(task_dir),
        "crontab_registered": registered,
        "runtime_delivered": runtime_delivered(status),
        "has_interval": has_interval(status),
        "interval_seconds": interval_seconds(status),
        "marker": marker(task_dir),
    }


def remove(task_dir: Path) -> dict[str, Any]:
    home = home_path()
    run_target_guard(home)
    task_dir = task_dir.resolve()
    _registered, removed = update_cron(home, task_dir, None)
    return {"status": "removed", "task_dir": str(task_dir), "entries_removed": removed, "marker": marker(task_dir)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--remove", action="store_true")
    args = parser.parse_args(argv)
    if platform.system() != "Linux":
        parser.error("this installer supports the current Linux/WSL user only")
    try:
        if args.check:
            result = check(Path(args.task_dir))
        elif args.remove:
            result = remove(Path(args.task_dir))
        else:
            result = install(Path(args.task_dir))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, ScheduleError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

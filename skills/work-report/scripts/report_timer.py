#!/usr/bin/env python3
"""Lightweight opt-in work-report timer that queues a prompt into an existing Codex thread."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable


SCHEMA = "work-report.timer/1"
DEFAULT_QUEUE_TIMEOUT_SECONDS = 30
MAX_CAPTURE_BYTES = 8192
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
QUEUE_TEXT_RE = re.compile(
    r"Queued message (?P<queue_id>[0-9a-fA-F-]{36}) for thread (?P<thread>[0-9a-fA-F-]{36})\."
)
DEFAULT_MESSAGE = (
    "请生成一次临时 work-report 进展汇报。原任务仍然继续，这次只是在当前线程中补充阶段性报告。"
    "请先产出本地 Markdown 报告并在 commentary 里交付 report.md 链接，然后继续原任务的下一步。"
    "如果原任务在你接手时已经完成，请如实报告实际完成状态，不要为了“继续”而虚构后续工作。"
    "不要创建或修改定时器或周期汇报计划，不要把这次入队当作新的操作授权，也不要因为汇报而结束原任务。"
)


class TimerError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso_from_timestamp(value: float) -> str:
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> dt.datetime:
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise TimerError("invalid_at", "--at must be a valid ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise TimerError("invalid_at", "--at must include a timezone")
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def reject_symlinks(path: Path, label: str, *, include_leaf: bool = True) -> None:
    raw = path.expanduser()
    if not raw.is_absolute():
        raise TimerError("relative_path", f"{label} must be absolute")
    cur = Path(raw.anchor)
    parts = raw.parts[1:]
    limit = len(parts) if include_leaf else max(0, len(parts) - 1)
    for part in parts[:limit]:
        cur = cur / part
        if cur.is_symlink():
            raise TimerError("symlink_path", f"{label} must not contain symlinks: {cur}")


def require_existing_dir(path: str, label: str) -> Path:
    candidate = Path(path).expanduser()
    reject_symlinks(candidate, label)
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise TimerError("missing_dir", f"{label} must be an existing directory: {resolved}")
    return resolved


def resolve_codex(value: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise TimerError("codex_missing", f"codex executable is not executable: {resolved}")
        return str(resolved)
    found = shutil.which(value)
    if not found:
        raise TimerError("codex_missing", f"codex executable not found on PATH: {value}")
    return found


def read_message(path: str | None) -> tuple[str, str | None]:
    if path is None:
        return DEFAULT_MESSAGE, None
    message_path = Path(path).expanduser()
    reject_symlinks(message_path, "message-file")
    resolved = message_path.resolve()
    if not resolved.is_file():
        raise TimerError("message_missing", f"message-file is missing: {resolved}")
    try:
        return resolved.read_text(encoding="utf-8"), str(resolved)
    except UnicodeDecodeError as exc:
        raise TimerError("message_invalid", "message-file must be UTF-8 text") from exc


def atomic_write_json(path: Path, obj: dict[str, Any]) -> None:
    reject_symlinks(path, "state file", include_leaf=False)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def append_event(path: Path, obj: dict[str, Any]) -> None:
    reject_symlinks(path, "events log", include_leaf=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True))
        fh.write("\n")


def load_json_optional(path: Path) -> dict[str, Any] | None:
    try:
        reject_symlinks(path, "state file")
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise TimerError("invalid_state", f"state file is not valid JSON: {path}") from exc


def parse_queue_id(stdout: str, thread: str) -> str | None:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        output_thread = data.get("thread")
        if isinstance(output_thread, str) and output_thread.lower() != thread.lower():
            return None
        for key in ("queue_id", "id", "task_id"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    match = QUEUE_TEXT_RE.search(stdout)
    if match and match.group("thread").lower() == thread.lower():
        return match.group("queue_id")
    return None


def default_queue_runner(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def bounded_size(value: str | None) -> int:
    if not value:
        return 0
    return min(len(value.encode("utf-8", errors="replace")), MAX_CAPTURE_BYTES)


class Timer:
    def __init__(
        self,
        *,
        workspace: Path,
        state_dir: Path,
        thread: str,
        message: str,
        message_file: str | None,
        codex: str,
        schedule: dict[str, Any],
        queue_timeout: int,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
        queue_runner: Callable[[list[str], Path, int], subprocess.CompletedProcess[str]] = default_queue_runner,
    ):
        self.workspace = workspace
        self.state_dir = state_dir
        self.thread = thread
        self.message = message
        self.message_file = message_file
        self.codex = codex
        self.schedule = schedule
        self.queue_timeout = queue_timeout
        self.clock = clock
        self.sleeper = sleeper
        self.queue_runner = queue_runner
        self.state_path = state_dir / "timer_state.json"
        self.events_path = state_dir / "timer_events.jsonl"
        self.stop_path = state_dir / "timer_stop.json"

    def event(self, name: str, **fields: Any) -> None:
        obj = {"schema_version": SCHEMA, "event": name, "time": iso_from_timestamp(self.clock()), **fields}
        append_event(self.events_path, obj)

    def state(self, status: str, **fields: Any) -> dict[str, Any]:
        obj = {
            "schema_version": SCHEMA,
            "status": status,
            "workspace": str(self.workspace),
            "state_dir": str(self.state_dir),
            "thread": self.thread,
            "schedule": self.schedule,
            "pid": os.getpid(),
            "updated_at": iso_from_timestamp(self.clock()),
            **fields,
        }
        atomic_write_json(self.state_path, obj)
        return obj

    def stopped(self) -> bool:
        return self.stop_path.exists()

    def wait_until_due_or_stopped(self, due_at: float) -> bool:
        while True:
            if self.stopped():
                return False
            remaining = due_at - self.clock()
            if remaining <= 0:
                return True
            self.sleeper(min(1.0, remaining))

    def queue_once(self, due_at: float) -> tuple[str, dict[str, Any]]:
        self.state("queueing", due_at=iso_from_timestamp(due_at))
        cmd = [self.codex, "queue", "--thread", self.thread, "--message", self.message]
        try:
            proc = self.queue_runner(cmd, self.workspace, self.queue_timeout)
            queue_id = parse_queue_id(proc.stdout or "", self.thread)
            result: dict[str, Any] = {
                "returncode": proc.returncode,
                "stdout_bytes": bounded_size(proc.stdout),
                "stderr_bytes": bounded_size(proc.stderr),
            }
            if proc.returncode == 0 and queue_id:
                result.update({"status": "queued", "queue_id": queue_id})
            elif proc.returncode == 0:
                result.update({"status": "queued_uncertain"})
            else:
                result.update({"status": "uncertain_failure"})
        except subprocess.TimeoutExpired as exc:
            result = {
                "status": "uncertain_failure",
                "reason": "queue_timeout",
                "stdout_bytes": bounded_size(exc.stdout if isinstance(exc.stdout, str) else None),
                "stderr_bytes": bounded_size(exc.stderr if isinstance(exc.stderr, str) else None),
            }
        self.event("queue_result", due_at=iso_from_timestamp(due_at), result=result)
        return str(result["status"]), result

    def run(self) -> int:
        interval = self.schedule.get("every_seconds")
        due_at = float(self.schedule["first_due_at"])
        self.event("started", schedule=self.schedule, message_file=self.message_file)
        while True:
            self.state("waiting", due_at=iso_from_timestamp(due_at))
            if not self.wait_until_due_or_stopped(due_at):
                state = self.state("stopped", stopped_at=iso_from_timestamp(self.clock()))
                self.event("stopped")
                emit({"action": "stopped", "state": state})
                return 0
            status, result = self.queue_once(due_at)
            if interval is None:
                if status == "queued":
                    final_status = "sent"
                    action = "queued"
                    exit_code = 0
                elif status == "queued_uncertain":
                    final_status = "uncertain"
                    action = "uncertain"
                    exit_code = 0
                else:
                    final_status = "failed"
                    action = "failed"
                    exit_code = 1
                state = self.state(final_status, last_queue=result, completed_at=iso_from_timestamp(self.clock()))
                emit({"action": action, "queue": result, "state": state})
                return exit_code
            now = self.clock()
            while due_at <= now:
                due_at += float(interval)


def build_schedule(args: argparse.Namespace, now: float) -> dict[str, Any]:
    if args.after is not None:
        if not math.isfinite(args.after) or args.after <= 0:
            raise TimerError("invalid_after", "--after must be greater than 0")
        first_due_at = now + args.after
        return {"mode": "after", "after_seconds": args.after, "first_due_at": first_due_at}
    if args.at is not None:
        due = parse_iso(args.at).timestamp()
        return {"mode": "at", "at": iso_from_timestamp(due), "first_due_at": due}
    if args.every is not None:
        if not math.isfinite(args.every) or args.every <= 0:
            raise TimerError("invalid_every", "--every must be greater than 0")
        return {"mode": "every", "every_seconds": args.every, "first_due_at": now + args.every}
    raise TimerError("missing_schedule", "one schedule option is required")


def validate_run_args(args: argparse.Namespace, clock: Callable[[], float]) -> dict[str, Any]:
    workspace = require_existing_dir(args.workspace, "workspace")
    state_dir = require_existing_dir(args.state_dir, "state-dir")
    if not UUID_RE.match(args.thread):
        raise TimerError("invalid_thread", "--thread must be a UUID")
    if args.queue_timeout <= 0:
        raise TimerError("invalid_timeout", "--queue-timeout must be greater than 0")
    codex = resolve_codex(args.codex)
    message, message_file = read_message(args.message_file)
    schedule = build_schedule(args, clock())
    return {
        "workspace": workspace,
        "state_dir": state_dir,
        "thread": args.thread,
        "message": message,
        "message_file": message_file,
        "codex": codex,
        "schedule": schedule,
        "queue_timeout": args.queue_timeout,
    }


def acquire_lock(state_dir: Path):
    lock_path = state_dir / "timer.lock"
    reject_symlinks(lock_path, "lock file", include_leaf=False)
    lock = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise TimerError("already_running", "another report_timer process holds the state-dir lock") from exc
    return lock


def run_command(
    args: argparse.Namespace,
    *,
    clock: Callable[[], float] = time.time,
    sleeper: Callable[[float], None] = time.sleep,
    queue_runner: Callable[[list[str], Path, int], subprocess.CompletedProcess[str]] = default_queue_runner,
) -> int:
    values = validate_run_args(args, clock)
    lock = acquire_lock(values["state_dir"])
    with lock:
        timer = Timer(**values, clock=clock, sleeper=sleeper, queue_runner=queue_runner)
        return timer.run()


def status_command(args: argparse.Namespace) -> int:
    state_dir = require_existing_dir(args.state_dir, "state-dir")
    state = load_json_optional(state_dir / "timer_state.json")
    emit({"action": "status", "state": state, "stop_requested": (state_dir / "timer_stop.json").exists()})
    return 0


def stop_command(args: argparse.Namespace) -> int:
    state_dir = require_existing_dir(args.state_dir, "state-dir")
    payload = {"schema_version": SCHEMA, "requested_at": utc_now().isoformat().replace("+00:00", "Z")}
    atomic_write_json(state_dir / "timer_stop.json", payload)
    append_event(state_dir / "timer_events.jsonl", {"schema_version": SCHEMA, "event": "stop_requested", "time": payload["requested_at"]})
    emit({"action": "stop_requested", "state_dir": str(state_dir)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a foreground timer")
    run.add_argument("--workspace", required=True)
    run.add_argument("--state-dir", required=True)
    run.add_argument("--thread", required=True)
    group = run.add_mutually_exclusive_group(required=True)
    group.add_argument("--after", type=float)
    group.add_argument("--at")
    group.add_argument("--every", type=float)
    run.add_argument("--message-file")
    run.add_argument("--codex", default="codex")
    run.add_argument("--queue-timeout", type=int, default=DEFAULT_QUEUE_TIMEOUT_SECONDS)

    status = sub.add_parser("status", help="read timer state")
    status.add_argument("--state-dir", required=True)

    stop = sub.add_parser("stop", help="request a running timer to stop")
    stop.add_argument("--state-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return run_command(args)
        if args.command == "status":
            return status_command(args)
        if args.command == "stop":
            return stop_command(args)
    except TimerError as exc:
        emit({"action": "failed", "code": exc.code, "reason": exc.message})
        return 2 if exc.code == "already_running" else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

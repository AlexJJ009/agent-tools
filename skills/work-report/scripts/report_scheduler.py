#!/usr/bin/env python3
"""Run one bounded periodic work-report scheduler tick."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tempfile
import uuid

SCHEMA = "work-report.scheduler/1"
DEFAULT_TIMEOUT = 600
MODEL = "gpt-5.5"
REASONING = "medium"
MARKER_PREFIX = "work-report-v2-schedule:"


def now_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def task_hash(task_dir: Path) -> str:
    return hashlib.sha256(str(task_dir.resolve()).encode("utf-8")).hexdigest()


def require_unsymlinked(path: Path, label: str) -> None:
    raw = path.expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    cur = Path(raw.anchor)
    for part in raw.parts[1:]:
        cur = cur / part
        if cur.is_symlink():
            raise RuntimeError(f"{label} must not contain symlinks: {cur}")


def require_file(path: Path, label: str, *, executable: bool = False) -> Path:
    if not path.is_absolute():
        raise RuntimeError(f"{label} must be absolute: {path}")
    require_unsymlinked(path, label)
    resolved = path.resolve()
    if not resolved.is_file():
        raise RuntimeError(f"{label} is missing: {resolved}")
    if executable and not os.access(resolved, os.X_OK):
        raise RuntimeError(f"{label} is not executable: {resolved}")
    return resolved


def scheduler_meta(task_dir: Path) -> dict:
    path = task_dir / "scheduler.json"
    require_unsymlinked(task_dir, "task-dir")
    if path.is_symlink():
        raise RuntimeError(f"scheduler metadata must not be a symlink: {path}")
    if not path.is_file():
        raise RuntimeError(f"scheduler metadata is missing: {path}")
    data = load_json(path)
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
        raise RuntimeError("scheduler metadata has wrong schema")
    expected = {
        "task_dir": str(task_dir.resolve()),
        "task_dir_sha256": task_hash(task_dir),
        "uid": os.getuid() if hasattr(os, "getuid") else None,
        "scheduler": str(Path(__file__).resolve()),
    }
    for key, value in expected.items():
        if data.get(key) != value:
            raise RuntimeError(f"scheduler metadata {key} does not match")
    require_file(Path(str(data.get("codex_bin", ""))), "codex executable", executable=True)
    require_file(Path(str(data.get("runtime", ""))), "runtime script")
    require_file(Path(str(data.get("scheduler", ""))), "scheduler script")
    codex_home = Path(str(data.get("codex_home", "")))
    if not codex_home.is_absolute():
        raise RuntimeError("scheduler metadata codex_home must be absolute")
    if not isinstance(data.get("path"), str):
        raise RuntimeError("scheduler metadata PATH is missing")
    return data


def run_dir(task_dir: Path, owner: str) -> Path:
    path = task_dir / f"schedule-run-{owner}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_script() -> Path:
    return Path(__file__).resolve().with_name("report_runtime.py")


def run_runtime(args: list[str], task_dir: Path, env: dict[str, str], runtime: Path | None = None) -> tuple[int, dict]:
    script = runtime or runtime_script()
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(task_dir),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        data = {"status": "error", "stdout": proc.stdout, "stderr": proc.stderr}
    return proc.returncode, data


def completed_or_cancelled(manifest: dict) -> bool:
    if manifest.get("cancelled_at"):
        return True
    if isinstance(manifest.get("interval_seconds"), int):
        return False
    final = manifest.get("final")
    return isinstance(final, dict) and final.get("state") in {"complete", "cancelled"}


def cron_marker(task_dir: Path, meta: dict) -> str:
    digest = meta.get("task_dir_sha256") or task_hash(task_dir)
    return MARKER_PREFIX + str(digest)


def has_marker_suffix(line: str, task_dir: Path, meta: dict) -> bool:
    return line.rstrip().endswith("# " + cron_marker(task_dir, meta))


def crontab_absent(proc: subprocess.CompletedProcess[str]) -> bool:
    return proc.returncode == 1 and "no crontab for" in (proc.stderr or "").lower()


def remove_own_cron(task_dir: Path, meta: dict, env: dict[str, str]) -> None:
    digest = meta.get("task_dir_sha256") or task_hash(task_dir)
    marker = MARKER_PREFIX + str(digest)
    lock_path = Path(meta["codex_home"]).parent / ".local" / "state" / "work-report" / "schedule-crontab.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = subprocess.run(["crontab", "-l"], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if current.returncode != 0 and not crontab_absent(current):
            raise RuntimeError("cannot read crontab for auto-removal: " + current.stderr)
        lines = current.stdout.splitlines() if current.returncode == 0 else []
        kept = [line for line in lines if not has_marker_suffix(line, task_dir, meta)]
        if kept == lines:
            return
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            tmp = Path(fh.name)
            fh.write("\n".join(kept).rstrip() + ("\n" if kept else ""))
        try:
            proc = subprocess.run(["crontab", str(tmp)], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        finally:
            with contextlib.suppress(FileNotFoundError):
                tmp.unlink()
        if proc.returncode:
            raise RuntimeError("cannot write crontab for auto-removal: " + proc.stderr)


def prompt_for(manifest: dict, obligation: dict) -> str:
    state = Path(manifest["task_dir"]) / "working-state.md"
    return (
        "Run the work-report skill as a bounded periodic snapshot reporter.\n"
        f"Source skill: {Path(__file__).resolve().parents[1] / 'SKILL.md'}\n"
        f"Task dir: {manifest['task_dir']}\n"
        f"Workspace root: {manifest['workspace']}\n"
        f"Original request file: {manifest['request']}\n"
        f"Current working-state file: {state}\n"
        f"Cutoff: {obligation.get('cutoff')}\n"
        "Initialize/report with --kind progress, --task-dir, and --workspace set to the paths above. "
        "Use the frozen original request and current working-state/evidence. "
        "Do not modify business source files. Only create a new work-report batch under the task dir. "
        "Run the normal machine check and a real independent native SubAgent Judge, then finalize so delivery.json is written. "
        "Do not register a new policy or reporting obligation. "
        "If evidence is insufficient, write that honestly in the report instead of inventing completion."
    )


def write_snapshot(run_path: Path, reason: str, task_dir: Path) -> Path:
    path = run_path / "risk-snapshot.md"
    state = task_dir / "working-state.md"
    path.write_text(
        "\n".join(
            [
                "# Unreviewed Work-Report Scheduler Snapshot",
                "",
                f"- time: {now_stamp()}",
                f"- reason: {reason}",
                f"- task_dir: {task_dir}",
                f"- state_path: {state}",
                "",
                "This is not a checked work-report and has no Judge pass. It records scheduler failure context only.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def launch_codex(meta: dict, manifest: dict, obligation: dict, run_path: Path, timeout: int, env: dict[str, str]) -> tuple[int, str]:
    stdout_path = run_path / "codex.stdout.jsonl"
    stderr_path = run_path / "codex.stderr.log"
    last_path = run_path / "last-message.txt"
    cmd = [
        meta["codex_bin"],
        "exec",
        "--ephemeral",
        "--disable",
        "hooks",
        "--sandbox",
        "workspace-write",
        "--cd",
        manifest["task_dir"],
        "-m",
        MODEL,
        "-c",
        f'model_reasoning_effort="{REASONING}"',
        "--json",
        "--output-last-message",
        str(last_path),
        prompt_for(manifest, obligation),
    ]
    deadline = time.monotonic() + timeout
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(cmd, cwd=manifest["task_dir"], env=env, text=True, stdout=out, stderr=err, start_new_session=True)
        reason = ""
        try:
            while True:
                rc = proc.poll()
                if rc is not None:
                    return rc, "codex_exit_" + str(rc)
                current = load_json(Path(manifest["task_dir"]) / "reporting.json")
                if current.get("cancelled_at"):
                    reason = "scheduler_cancelled"
                    break
                if completed_or_cancelled(current):
                    reason = "scheduler_completed"
                    break
                if time.monotonic() >= deadline:
                    reason = "codex_timeout"
                    break
                time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
            terminate_process_group(proc)
            return 124 if reason == "codex_timeout" else 1, reason
        except Exception:
            terminate_process_group(proc)
            raise


def terminate_process_group(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    end = time.monotonic() + 1.0
    while time.monotonic() < end:
        if proc.poll() is not None:
            return
        time.sleep(0.05)
    if proc.poll() is None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=1)


def tick(task_dir: Path, timeout: int) -> int:
    if timeout <= 0 or timeout > DEFAULT_TIMEOUT:
        raise RuntimeError(f"timeout must be between 1 and {DEFAULT_TIMEOUT} seconds")
    require_unsymlinked(task_dir, "task-dir")
    task_dir = task_dir.resolve()
    meta = scheduler_meta(task_dir)
    runtime = Path(meta["runtime"])
    env = dict(os.environ)
    env["CODEX_HOME"] = meta["codex_home"]
    env["PATH"] = meta["path"]
    status_rc, status = run_runtime(["status", "--task-dir", str(task_dir)], task_dir, env, runtime)
    if status_rc == 0 and completed_or_cancelled(status.get("manifest", {})):
        remove_own_cron(task_dir, meta, env)
        emit({"action": "complete", "task_dir": str(task_dir)})
        return 0
    tick_rc, tick_data = run_runtime(["tick", "--task-dir", str(task_dir)], task_dir, env, runtime)
    action = tick_data.get("action")
    if tick_rc != 0 or action == "failed":
        emit({"action": "failed", "runtime": tick_data})
        return 1
    if action in {"idle", "pending", "complete"}:
        if action == "complete":
            remove_own_cron(task_dir, meta, env)
        emit({"action": action, "runtime": tick_data})
        return 0
    if action != "report_due":
        emit({"action": "idle", "runtime": tick_data})
        return 0

    owner = str(uuid.uuid4())
    run_path = run_dir(task_dir, owner)
    claim_rc, claim = run_runtime(["claim", "--task-dir", str(task_dir), "--owner", owner, "--kind", "progress"], task_dir, env, runtime)
    if claim_rc != 0:
        write_snapshot(run_path, "claim failed", task_dir)
        emit({"action": "failed", "claim": claim, "run": str(run_path)})
        return 1
    if claim.get("status") != "claimed":
        emit({"action": "pending", "claim": claim})
        return 0

    manifest = load_json(task_dir / "reporting.json")
    obligation = claim["obligation"]
    rc, reason = launch_codex(meta, manifest, obligation, run_path, timeout, env)
    if rc != 0:
        snapshot = write_snapshot(run_path, reason, task_dir)
        run_runtime(["release", "--task-dir", str(task_dir), "--owner", owner, "--kind", "progress", "--error", reason], task_dir, env, runtime)
        emit({"action": "failed", "reason": reason, "snapshot": str(snapshot), "run": str(run_path)})
        return 1

    release_rc, release = run_runtime(["release", "--task-dir", str(task_dir), "--owner", owner, "--kind", "progress", "--success"], task_dir, env, runtime)
    if release_rc != 0 or release.get("result") != "success":
        snapshot = write_snapshot(run_path, "codex exited without valid delivery", task_dir)
        emit({"action": "failed", "release": release, "snapshot": str(snapshot), "run": str(run_path)})
        return 1
    emit({"action": "delivered", "release": release, "run": str(run_path)})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=["tick"], default="tick")
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    try:
        return tick(Path(args.task_dir), args.timeout)
    except Exception as exc:
        emit({"action": "failed", "reason": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

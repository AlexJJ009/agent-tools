"""Bounded obligation runtime for work-report hooks and schedulers.

This module does not generate reports. It records a confirmed reporting
obligation, answers hook/scheduler queries, and verifies delivery receipts by
re-running the report tool's readonly finalizer.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


RUNTIME_SCHEMA = "work-report.runtime/2"
INTENT_SCHEMA = "work-report.intent/1"
DELIVERY_SCHEMA = "work-report.delivery/1"
CONTEXT_SCHEMA = "work-report.context/1"
MAX_ATTEMPTS = 2
LEASE_SECONDS = 900
VERIFY_TIMEOUT_SECONDS = 30
PROMPT_REPORT_RE = re.compile(r"(work-report|report|汇报|报告)", re.IGNORECASE)
PROMPT_TIMING_RE = re.compile(
    r"(end|finish|complete|completion|after|every|periodic|cron|结束|完成|收尾|定时|每)",
    re.IGNORECASE,
)
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class RuntimeFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_iso(value: str, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise RuntimeFailure("invalid_timestamp", f"{field} must be a nonempty ISO timestamp")
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise RuntimeFailure("invalid_timestamp", f"{field} is not valid ISO 8601") from exc
    if parsed.tzinfo is None:
        raise RuntimeFailure("invalid_timestamp", f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def reject_symlinks(path: Path, include_leaf: bool = True) -> None:
    raw = path.expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    cur = Path(raw.anchor)
    parts = raw.parts[1:]
    limit = len(parts) if include_leaf else max(0, len(parts) - 1)
    for part in parts[:limit]:
        cur = cur / part
        if cur.is_symlink():
            raise RuntimeFailure("symlink_path", f"symlink path component is not allowed: {cur}")


def safe_absolute(path: Path, include_leaf: bool = True) -> Path:
    reject_symlinks(path, include_leaf=include_leaf)
    raw = path.expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    return raw.resolve()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def load_json(path: Path) -> Any:
    try:
        reject_symlinks(path)
        return json.loads(path.read_text(encoding="utf-8"))
    except RuntimeFailure:
        raise
    except Exception as exc:
        raise RuntimeFailure("invalid_json", f"cannot read JSON {path}: {exc}") from exc


def atomic_write_json(path: Path, obj: dict[str, Any]) -> None:
    reject_symlinks(path, include_leaf=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def git_root(path: Path) -> Path:
    proc = run_git(["rev-parse", "--show-toplevel"], path if path.is_dir() else path.parent)
    if proc.returncode != 0:
        raise RuntimeFailure("git_root_missing", f"not inside a Git workspace: {path}")
    return Path(proc.stdout.strip()).resolve()


def git_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def require_task_dir_policy(task_dir: Path, workspace: Path) -> tuple[Path, Path]:
    root = git_root(workspace)
    if git_root(task_dir) != root:
        raise RuntimeFailure("task_dir_git_mismatch", "task-dir must belong to the workspace Git root")
    reports_root = (root / "docs" / "work-reports").resolve()
    if task_dir.parent.resolve() != reports_root or not is_relative_to(task_dir, reports_root):
        raise RuntimeFailure("task_dir_outside_reports", "task-dir must be directly under docs/work-reports")
    tracked = run_git(["ls-files", "--", git_relative(root, task_dir)], root)
    staged = run_git(["diff", "--cached", "--name-only", "--", git_relative(root, task_dir)], root)
    if tracked.returncode != 0 or staged.returncode != 0:
        raise RuntimeFailure("git_policy_check_failed", "could not inspect tracked/staged report paths")
    hits = [*tracked.stdout.splitlines(), *staged.stdout.splitlines()]
    if any(hits):
        raise RuntimeFailure("git_tracked_output", "task-dir contains tracked or staged files")
    ignored = run_git(["check-ignore", "-q", "--", str(task_dir / ".work-report-runtime-probe")], root)
    if ignored.returncode == 1:
        raise RuntimeFailure("git_ignore_missing", "docs/work-reports task paths must be effectively ignored")
    if ignored.returncode != 0:
        raise RuntimeFailure("git_policy_check_failed", ignored.stderr.strip() or "git check-ignore failed")
    return root, reports_root


def context_for_request(task_dir: Path, request_sha256: str) -> dict[str, Any]:
    fallback: dict[str, Any] | None = None
    for path in sorted(task_dir.glob("*/context.json")):
        data = load_json(path)
        if isinstance(data, dict) and data.get("schema_version") == CONTEXT_SCHEMA:
            fallback = data
            if data.get("request", {}).get("sha256") == request_sha256:
                return data
    if fallback is None:
        raise RuntimeFailure("task_context_missing", "task-dir has no work-report context.json")
    raise RuntimeFailure("request_context_mismatch", "no task context matches the provided request hash")


def validate_decision(decision: Any, request_text: str) -> dict[str, Any] | None:
    if not isinstance(decision, dict) or decision.get("schema_version") != INTENT_SCHEMA:
        raise RuntimeFailure("decision_schema_invalid", "decision must use work-report.intent/1")
    for field in ["request_sha256", "reviewer_id", "verdict", "evidence_quotes", "reason"]:
        if field not in decision:
            raise RuntimeFailure("decision_field_missing", f"decision missing {field}")
    if not isinstance(decision.get("reviewer_id"), str) or not decision["reviewer_id"].strip():
        raise RuntimeFailure("decision_reviewer_invalid", "reviewer_id must be a nonempty string")
    if not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
        raise RuntimeFailure("decision_reason_invalid", "reason must be a nonempty string")
    if decision["request_sha256"] != sha256_text(request_text):
        raise RuntimeFailure("decision_digest_mismatch", "decision request_sha256 does not match request file")
    if decision["verdict"] not in {"confirmed", "none", "needs_clarification"}:
        raise RuntimeFailure("decision_verdict_invalid", "decision verdict is invalid")
    quotes = decision.get("evidence_quotes")
    if not isinstance(quotes, list) or not all(isinstance(q, str) and q for q in quotes):
        raise RuntimeFailure("decision_quotes_invalid", "evidence_quotes must be a string list")
    missing = [q for q in quotes if q not in request_text]
    if missing:
        raise RuntimeFailure("decision_quote_missing", "each evidence quote must be an exact request substring")
    interval = decision.get("interval_seconds")
    if interval is not None and (not isinstance(interval, int) or interval < 60):
        raise RuntimeFailure("decision_interval_invalid", "interval_seconds must be null or at least 60")
    if not isinstance(decision.get("on_end"), bool):
        raise RuntimeFailure("decision_on_end_invalid", "on_end must be boolean")
    if decision["verdict"] != "confirmed":
        return None
    if not quotes:
        raise RuntimeFailure("decision_quotes_invalid", "confirmed evidence_quotes must be nonempty")
    if not decision["on_end"] and interval is None:
        raise RuntimeFailure("decision_trigger_missing", "confirmed decisions must request end or periodic reporting")
    return decision


@contextlib.contextmanager
def locked_manifest(task_dir: Path):
    lock_path = task_dir / ".reporting.lock"
    reject_symlinks(lock_path, include_leaf=False)
    task_dir.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def manifest_path(task_dir: Path) -> Path:
    return task_dir / "reporting.json"


def safe_session_id(value: Any) -> str:
    text = str(value or "unknown")
    cleaned = SAFE_ID_RE.sub("_", text).strip("._-")
    return cleaned[:96] or "unknown"


def pending_root(workspace_root: Path) -> Path:
    return workspace_root / "docs" / "work-reports" / ".pending"


def pending_path(workspace_root: Path, session_id: Any) -> Path:
    return pending_root(workspace_root) / f"{safe_session_id(session_id)}.json"


def ensure_pending_git_policy(workspace_root: Path) -> None:
    root = pending_root(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    ignored = run_git(["check-ignore", "-q", "--", str(root / ".probe")], workspace_root)
    if ignored.returncode == 1:
        exclude_proc = run_git(["rev-parse", "--git-path", "info/exclude"], workspace_root)
        if exclude_proc.returncode != 0:
            raise RuntimeFailure("git_policy_check_failed", "cannot find git info/exclude")
        exclude = (workspace_root / exclude_proc.stdout.strip()).resolve()
        reject_symlinks(exclude, include_leaf=False)
        existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        rule = "/docs/work-reports/"
        if rule not in existing.splitlines():
            with exclude.open("a", encoding="utf-8") as fh:
                if existing and not existing.endswith("\n"):
                    fh.write("\n")
                fh.write(rule + "\n")
        ignored = run_git(["check-ignore", "-q", "--", str(root / ".probe")], workspace_root)
    if ignored.returncode != 0:
        raise RuntimeFailure("git_ignore_missing", "pending work-report prompts must be under ignored docs/work-reports")


def write_pending_prompt(workspace_root: Path, event: dict[str, Any]) -> dict[str, Any] | None:
    prompt = event.get("prompt")
    if not isinstance(prompt, str) or not PROMPT_REPORT_RE.search(prompt) or not PROMPT_TIMING_RE.search(prompt):
        return None
    ensure_pending_git_policy(workspace_root)
    request_sha = sha256_text(prompt)
    existing_path = pending_path(workspace_root, event.get("session_id"))
    if existing_path.exists():
        with contextlib.suppress(RuntimeFailure, json.JSONDecodeError):
            existing = load_json(existing_path)
            if isinstance(existing, dict) and existing.get("request_sha256") == request_sha:
                return existing
    pending = {
        "schema_version": "work-report.pending/1",
        "session_id": str(event.get("session_id") or ""),
        "turn_id": str(event.get("turn_id") or ""),
        "workspace": str(workspace_root),
        "created_at": iso_now(),
        "request_sha256": request_sha,
        "prompt": prompt,
        "state": "needs_intent_judge",
        "attempts": 0,
        "reason": "conservative candidate matched report and timing cue",
    }
    atomic_write_json(existing_path, pending)
    return pending


def bump_pending_stop(workspace_root: Path, session_id: Any) -> dict[str, Any] | None:
    path = pending_path(workspace_root, session_id)
    if not path.exists():
        return None
    data = load_json(path)
    if not isinstance(data, dict):
        path.unlink(missing_ok=True)
        return None
    if data.get("state") == "failed_open":
        if data.get("notified_at"):
            return None
        data["notified_at"] = iso_now()
        atomic_write_json(path, data)
        return data
    data["attempts"] = int(data.get("attempts", 0)) + 1
    data["last_stop_at"] = iso_now()
    if data["attempts"] > MAX_ATTEMPTS:
        data["state"] = "failed_open"
        data["message"] = "Possible work-report obligation was never reviewed after two Stop continuations; failing open visibly."
        data["notified_at"] = iso_now()
        atomic_write_json(path, data)
        atomic_write_json(
            workspace_root / "docs" / "work-reports" / ".pending" / f"{safe_session_id(session_id)}.failure.json",
            {
                "schema_version": "work-report.pending.failure/1",
                "session_id": str(session_id or ""),
                "failed_at": iso_now(),
                "reason": "possible work-report obligation was never reviewed after two Stop continuations",
                "request_sha256": data.get("request_sha256"),
            },
        )
        return data
    atomic_write_json(path, data)
    return data


def clear_pending_for_session(workspace_root: Path, session_id: Any) -> None:
    with contextlib.suppress(FileNotFoundError):
        pending_path(workspace_root, session_id).unlink()


def require_register_session(workspace_root: Path, session_id: str, request_sha256: str) -> None:
    if not UUID_RE.match(session_id):
        raise RuntimeFailure("session_id_invalid", "register session_id must be the actual Codex session UUID")
    root = pending_root(workspace_root)
    if not root.exists():
        return
    for path in sorted(root.glob("*.json")):
        try:
            data = load_json(path)
        except RuntimeFailure:
            continue
        if not isinstance(data, dict) or data.get("schema_version") != "work-report.pending/1":
            continue
        if data.get("request_sha256") == request_sha256 and data.get("session_id") != session_id:
            raise RuntimeFailure("pending_session_mismatch", "matching pending request belongs to a different session_id")


def load_manifest(task_dir: Path) -> dict[str, Any]:
    path = manifest_path(task_dir)
    if not path.exists():
        raise RuntimeFailure("manifest_missing", "reporting.json is not registered")
    data = load_json(path)
    if not isinstance(data, dict) or data.get("schema_version") != RUNTIME_SCHEMA:
        raise RuntimeFailure("manifest_invalid", "reporting.json has wrong schema")
    return data


def save_manifest(task_dir: Path, data: dict[str, Any]) -> None:
    atomic_write_json(manifest_path(task_dir), data)


def base_obligation(kind: str, cutoff: str) -> dict[str, Any]:
    return {
        "id": f"{kind}-{secrets.token_hex(6)}",
        "kind": kind,
        "cutoff": cutoff,
        "attempts": 0,
        "failures": [],
        "lease": None,
        "last_ack": None,
        "state": "pending",
    }


def stale_or_missing_lease(lease: Any, now: dt.datetime) -> bool:
    if not isinstance(lease, dict):
        return True
    try:
        return parse_iso(lease.get("expires_at", ""), "lease.expires_at") <= now
    except RuntimeFailure:
        return True


def delivery_files(task_dir: Path) -> list[Path]:
    return sorted(task_dir.glob("*/delivery.json"))


def valid_delivery_after(manifest: dict[str, Any], obligation: dict[str, Any], *, complete: bool = False) -> dict[str, Any] | None:
    last_ack = obligation.get("last_ack") if isinstance(obligation.get("last_ack"), dict) else None
    if last_ack and ack_still_valid(manifest, obligation, last_ack):
        if complete and obligation.get("state") in {"pending", "satisfied", "complete"}:
            complete_obligation(manifest, obligation)
        return last_ack
    if last_ack:
        obligation["last_ack"] = None
        if obligation.get("state") in {"complete", "satisfied"}:
            obligation["state"] = "pending"

    task_dir = Path(manifest["task_dir"])
    workspace = Path(manifest["workspace"])
    cutoff = parse_iso(obligation["cutoff"], "obligation.cutoff")
    for path in reversed(delivery_files(task_dir)):
        delivery = load_json(path)
        if not isinstance(delivery, dict):
            continue
        if not delivery_matches_manifest(delivery, manifest, obligation):
            continue
        report = safe_absolute(Path(delivery["report"]))
        context = load_json(report.parent / "context.json")
        generated_at = parse_iso(context.get("generated_at", ""), "context.generated_at")
        if generated_at < cutoff:
            continue
        if verify_delivery_with_report_tool(
            report,
            task_dir.name,
            workspace,
            expected_digest=delivery["artifact_digest"],
            expected_report_id=delivery["report_id"],
        ):
            ack = {
                "delivery": str(path.resolve()),
                "report": str(report),
                "report_id": delivery["report_id"],
                "artifact_digest": delivery["artifact_digest"],
                "delivered_at": delivery["delivered_at"],
                "generated_at": context["generated_at"],
                "mtime": path.stat().st_mtime,
                "verified_at": iso_now(),
            }
            obligation["last_ack"] = ack
            if complete:
                complete_obligation(manifest, obligation)
            return ack
    return None


def complete_obligation(manifest: dict[str, Any], obligation: dict[str, Any]) -> None:
    prior = obligation.get("state")
    if obligation["kind"] == "final":
        obligation["state"] = "complete"
        return
    obligation["state"] = "satisfied"
    if prior != "satisfied":
        advance_periodic_after_completion(manifest)


def advance_periodic_after_completion(manifest: dict[str, Any]) -> None:
    interval = manifest.get("interval_seconds")
    if not isinstance(interval, int):
        return
    next_due = utc_now() + dt.timedelta(seconds=interval)
    manifest["next_due_at"] = next_due.isoformat().replace("+00:00", "Z")


def ack_still_valid(manifest: dict[str, Any], obligation: dict[str, Any], ack: dict[str, Any]) -> bool:
    try:
        delivery_path = safe_absolute(Path(ack["delivery"]))
        if not delivery_path.exists() or not is_relative_to(delivery_path, Path(manifest["task_dir"])):
            return False
        delivery = load_json(delivery_path)
        if not isinstance(delivery, dict) or not delivery_matches_manifest(delivery, manifest, obligation):
            return False
        report = safe_absolute(Path(delivery["report"]))
        context = load_json(report.parent / "context.json")
        if parse_iso(context.get("generated_at", ""), "context.generated_at") < parse_iso(obligation["cutoff"], "obligation.cutoff"):
            return False
        return verify_delivery_with_report_tool(
            report,
            Path(manifest["task_dir"]).name,
            Path(manifest["workspace"]),
            expected_digest=delivery["artifact_digest"],
            expected_report_id=delivery["report_id"],
        )
    except RuntimeFailure:
        return False


def delivery_matches_manifest(delivery: dict[str, Any], manifest: dict[str, Any], obligation: dict[str, Any]) -> bool:
    required = ["schema_version", "status", "task_id", "report_id", "report", "artifact_digest", "delivered_at", "kind", "request_sha256"]
    if any(not isinstance(delivery.get(k), str) for k in required):
        return False
    if delivery.get("schema_version") != DELIVERY_SCHEMA or delivery.get("status") != "pass":
        return False
    if delivery.get("task_id") != Path(manifest["task_dir"]).name:
        return False
    if delivery.get("kind") != obligation["kind"]:
        return False
    if delivery.get("request_sha256") != manifest["request_sha256"]:
        return False
    try:
        report = safe_absolute(Path(delivery["report"]))
        parse_iso(delivery["delivered_at"], "delivery.delivered_at")
    except RuntimeFailure:
        return False
    return is_relative_to(report, Path(manifest["task_dir"])) and report.name == "report.md"


def verify_delivery_with_report_tool(
    report: Path,
    task_id: str,
    workspace: Path,
    *,
    expected_digest: str,
    expected_report_id: str,
) -> bool:
    uv = os.environ.get("WORK_REPORT_UV") or shutil.which("uv") or "uv"
    tool = Path(__file__).resolve().with_name("report_tool.py")
    cmd = [
        uv,
        "run",
        "--script",
        str(tool),
        "finalize",
        "--verify-only",
        "--report",
        str(report),
        "--task",
        task_id,
        "--workspace",
        str(workspace),
    ]
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=VERIFY_TIMEOUT_SECONDS)
    except Exception:
        return False
    if proc.returncode != 0:
        return False
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    return (
        isinstance(data, dict)
        and data.get("status") == "pass"
        and data.get("artifact_digest") == expected_digest
        and data.get("task_id") == task_id
        and data.get("report_id") == expected_report_id
    )


def ensure_periodic_obligation(manifest: dict[str, Any], now: dt.datetime) -> dict[str, Any] | None:
    final = manifest.get("final")
    if manifest.get("on_end") and isinstance(final, dict) and final.get("state") == "complete":
        return None
    interval = manifest.get("interval_seconds")
    if not isinstance(interval, int):
        return None
    current = manifest.get("periodic")
    if isinstance(current, dict) and current.get("state") in {"pending", "failed"}:
        return current
    next_due = parse_iso(manifest.get("next_due_at", manifest["registered_at"]), "next_due_at")
    if now < next_due:
        return None
    obligation = base_obligation("progress", next_due.isoformat().replace("+00:00", "Z"))
    obligation["due_at"] = obligation["cutoff"]
    manifest["periodic"] = obligation
    manifest["next_due_at"] = (next_due + dt.timedelta(seconds=interval)).isoformat().replace("+00:00", "Z")
    return obligation


def obligation_payload(manifest: dict[str, Any], obligation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": obligation["id"],
        "kind": obligation["kind"],
        "task_dir": manifest["task_dir"],
        "workspace": manifest["workspace"],
        "request": manifest["request"],
        "request_sha256": manifest["request_sha256"],
        "cutoff": obligation["cutoff"],
        "attempts": obligation["attempts"],
    }


def main_owner(session_id: Any, turn_id: Any) -> str:
    return f"main:{safe_session_id(session_id)}:{safe_session_id(turn_id)}"


def set_lease(obligation: dict[str, Any], owner: str, now: dt.datetime) -> None:
    obligation["lease"] = {
        "owner": owner,
        "claimed_at": iso_now(),
        "expires_at": (now + dt.timedelta(seconds=LEASE_SECONDS)).isoformat().replace("+00:00", "Z"),
    }


def active_other_lease(obligation: dict[str, Any], owner: str, now: dt.datetime) -> bool:
    lease = obligation.get("lease")
    if stale_or_missing_lease(lease, now):
        return False
    return isinstance(lease, dict) and lease.get("owner") != owner


def due_additional_context(manifest: dict[str, Any], obligation: dict[str, Any]) -> str:
    return (
        "A work-report obligation is due. Invoke the work-report skill with "
        f"--task-dir {manifest['task_dir']} and produce a {obligation['kind']} report. "
        "Finalize it so delivery.json is written before the next Stop."
    )


def cmd_register(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    task_dir = safe_absolute(Path(args.task_dir))
    workspace = safe_absolute(Path(args.workspace))
    request = safe_absolute(Path(args.request))
    decision_path = safe_absolute(Path(args.decision))
    root, _ = require_task_dir_policy(task_dir, workspace)
    request_text = request.read_text(encoding="utf-8")
    request_sha = sha256_text(request_text)
    require_register_session(root, args.session_id, request_sha)
    context = context_for_request(task_dir, request_sha)
    if Path(context.get("workspace", "")).resolve() != root:
        raise RuntimeFailure("workspace_mismatch", "task context workspace does not match Git root")
    decision = validate_decision(load_json(decision_path), request_text)
    if decision is None:
        clear_pending_for_session(root, args.session_id)
        return 0, {"status": "ignored", "reason": "intent verdict is not confirmed"}

    registered_at = iso_now()
    existing_path = manifest_path(task_dir)
    if existing_path.exists():
        with locked_manifest(task_dir):
            existing = load_manifest(task_dir)
            same = (
                existing.get("request_sha256") == decision["request_sha256"]
                and existing.get("session_id") == args.session_id
                and existing.get("on_end") == decision["on_end"]
                and existing.get("interval_seconds") == decision.get("interval_seconds")
            )
            if same:
                clear_pending_for_session(root, args.session_id)
                return 0, {"status": "registered", "task_dir": str(task_dir), "manifest": str(existing_path), "idempotent": True}
    manifest = {
        "schema_version": RUNTIME_SCHEMA,
        "task_dir": str(task_dir),
        "workspace": str(root),
        "request": str(request),
        "request_sha256": decision["request_sha256"],
        "session_id": args.session_id,
        "registered_at": registered_at,
        "reviewer_id": decision["reviewer_id"],
        "evidence_quotes": decision["evidence_quotes"],
        "reason": decision["reason"],
        "on_end": decision["on_end"],
        "interval_seconds": decision.get("interval_seconds"),
        "cancelled_at": None,
        "closed_at": None,
        "last_failure": None,
        "final": base_obligation("final", registered_at) if decision["on_end"] else None,
        "periodic": None,
        "next_due_at": (
            (parse_iso(registered_at, "registered_at") + dt.timedelta(seconds=decision["interval_seconds"]))
            .isoformat()
            .replace("+00:00", "Z")
            if isinstance(decision.get("interval_seconds"), int)
            else None
        ),
        "notes": ["Final scope completion is the next main Stop after registration."],
    }
    with locked_manifest(task_dir):
        save_manifest(task_dir, manifest)
    clear_pending_for_session(root, args.session_id)
    return 0, {"status": "registered", "task_dir": str(task_dir), "manifest": str(manifest_path(task_dir))}


def cmd_status(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    task_dir = safe_absolute(Path(args.task_dir))
    with locked_manifest(task_dir):
        manifest = load_manifest(task_dir)
        changed = refresh_manifest(manifest)
        if changed:
            save_manifest(task_dir, manifest)
    return 0, {"status": "pass", "manifest": manifest}


def cmd_cancel(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    task_dir = safe_absolute(Path(args.task_dir))
    with locked_manifest(task_dir):
        manifest = load_manifest(task_dir)
        manifest["cancelled_at"] = iso_now()
        for key in ["final", "periodic"]:
            if isinstance(manifest.get(key), dict):
                manifest[key]["state"] = "cancelled"
        save_manifest(task_dir, manifest)
    return 0, {"status": "cancelled", "task_dir": str(task_dir)}


def refresh_manifest(manifest: dict[str, Any], *, complete_periodic: bool = False) -> bool:
    changed = False
    for key in ["final", "periodic"]:
        obligation = manifest.get(key)
        if key == "final" and manifest.get("closed_at"):
            continue
        if isinstance(obligation, dict) and obligation.get("state") != "cancelled":
            before = json.dumps(obligation, sort_keys=True)
            valid_delivery_after(manifest, obligation, complete=(key == "periodic" and complete_periodic))
            changed = changed or before != json.dumps(obligation, sort_keys=True)
    final = manifest.get("final")
    if manifest.get("on_end") and isinstance(final, dict) and final.get("state") == "complete":
        if manifest.get("interval_seconds") is not None or manifest.get("next_due_at") is not None:
            manifest["interval_seconds"] = None
            manifest["next_due_at"] = None
            manifest["periodic"] = None
            changed = True
    return changed


def cmd_hook(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    event = json.loads(sys.stdin.read() or "{}")
    if event.get("agent_id") or event.get("agent_type"):
        return 0, {}
    cwd = safe_absolute(Path(event.get("cwd") or Path.cwd()))
    session_id = event.get("session_id")
    turn_id = event.get("turn_id")
    owner = main_owner(session_id, turn_id)
    hook_event = event.get("hook_event_name")
    try:
        root = git_root(cwd)
    except RuntimeFailure:
        return 0, {}
    if hook_event == "UserPromptSubmit":
        pending = write_pending_prompt(root, event)
        if pending:
            return 0, {
                "hookSpecificOutput": {
                    "hookEventName": hook_event,
                    "additionalContext": (
                        "This prompt may contain a work-report obligation. Run the real intent Judge and then call "
                        "report_runtime.py register with the Judge JSON decision before task completion. "
                        f"Pending marker: {pending_path(root, session_id)}. Session UUID: {session_id}."
                    )
                }
            }
        return 0, {}
    if hook_event == "Stop":
        data = bump_pending_stop(root, session_id)
        if data:
            if data.get("state") == "failed_open":
                return 0, {
                    "systemMessage": (
                        f"{data.get('message', 'Possible work-report obligation failed open visibly.')} "
                        f"Pending marker: {pending_path(root, session_id)}."
                    ),
                }
            return 0, {
                "decision": "block",
                "reason": (
                    "A possible work-report obligation from UserPromptSubmit has not been reviewed. "
                    "Run the real intent Judge; call register for confirmed obligations, or register the none/needs_clarification decision to clear it. "
                    f"Pending marker: {pending_path(root, session_id)}. Session UUID: {session_id}."
                ),
            }
    outputs: list[str] = []
    for path in sorted((root / "docs" / "work-reports").glob("*/reporting.json")):
        task_dir = path.parent.resolve()
        with locked_manifest(task_dir):
            try:
                manifest = load_manifest(task_dir)
            except RuntimeFailure:
                continue
            if manifest.get("session_id") != session_id or manifest.get("cancelled_at"):
                continue
            if manifest.get("closed_at"):
                last_failure = manifest.pop("last_failure", None)
                save_manifest(task_dir, manifest)
                if last_failure and hook_event == "Stop":
                    return 0, {
                        "hookSpecificOutput": {
                            "hookEventName": hook_event,
                            "systemMessage": last_failure.get("message", "A previous work-report obligation failed visibly."),
                        }
                    }
                continue
            now = utc_now()
            ensure_periodic_obligation(manifest, now)
            refresh_manifest(manifest)
            if hook_event == "Interrupt":
                manifest["cancelled_at"] = iso_now()
                for key in ["final", "periodic"]:
                    if isinstance(manifest.get(key), dict):
                        manifest[key]["state"] = "cancelled"
                save_manifest(task_dir, manifest)
                continue
            if hook_event == "Stop":
                for obligation in [manifest.get("final"), manifest.get("periodic")]:
                    if not isinstance(obligation, dict) or obligation.get("state") in {"complete", "cancelled"}:
                        continue
                    if valid_delivery_after(manifest, obligation, complete=True):
                        if obligation["kind"] == "final":
                            manifest["closed_at"] = iso_now()
                            manifest["interval_seconds"] = None
                            manifest["next_due_at"] = None
                            manifest["periodic"] = None
                        obligation["lease"] = None
                        save_manifest(task_dir, manifest)
                        continue
                    if active_other_lease(obligation, owner, now):
                        save_manifest(task_dir, manifest)
                        continue
                    if obligation.get("state") == "failed":
                        last_failure = manifest.get("last_failure")
                        if isinstance(last_failure, dict) and not last_failure.get("notified_at"):
                            last_failure["notified_at"] = iso_now()
                            save_manifest(task_dir, manifest)
                            return 0, {
                                "systemMessage": last_failure.get("message", "Work-report obligation failed visibly."),
                            }
                        save_manifest(task_dir, manifest)
                        continue
                    if int(obligation.get("attempts", 0)) >= MAX_ATTEMPTS:
                        obligation["state"] = "failed"
                        failure = {
                            "at": iso_now(),
                            "reason": "maximum Stop continuations reached",
                            "message": f"Work-report {obligation['kind']} obligation failed after two Stop continuations.",
                            "notified_at": iso_now(),
                        }
                        obligation.setdefault("failures", []).append(failure)
                        obligation["lease"] = None
                        manifest["last_failure"] = failure
                        atomic_write_json(task_dir / "reporting.failure.json", failure)
                        save_manifest(task_dir, manifest)
                        return 0, {
                            "systemMessage": failure["message"],
                        }
                    obligation["attempts"] = int(obligation.get("attempts", 0)) + 1
                    set_lease(obligation, owner, now)
                    save_manifest(task_dir, manifest)
                    return 0, {
                        "decision": "block",
                        "reason": (
                            f"{due_additional_context(manifest, obligation)} "
                            f"Task dir: {manifest['task_dir']}. Session UUID: {session_id}."
                        ),
                    }
            elif hook_event in {"PostToolUse", "SessionStart"}:
                periodic = manifest.get("periodic")
                if isinstance(periodic, dict) and periodic.get("state") == "pending":
                    now = utc_now()
                    if active_other_lease(periodic, owner, now):
                        save_manifest(task_dir, manifest)
                        continue
                    set_lease(periodic, owner, now)
                    outputs.append(due_additional_context(manifest, periodic))
            save_manifest(task_dir, manifest)
    if outputs:
        return 0, {"hookSpecificOutput": {"hookEventName": hook_event, "additionalContext": "\n\n".join(outputs)}}
    return 0, {}


def cmd_tick(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    task_dir = safe_absolute(Path(args.task_dir))
    with locked_manifest(task_dir):
        manifest = load_manifest(task_dir)
        if manifest.get("cancelled_at"):
            return 0, {"action": "complete", "reason": "cancelled"}
        if manifest.get("closed_at"):
            return 0, {"action": "complete", "reason": "closed", "closed_at": manifest["closed_at"]}
        now = utc_now()
        obligation = ensure_periodic_obligation(manifest, now)
        refresh_manifest(manifest, complete_periodic=True)
        if isinstance(manifest.get("final"), dict) and manifest["final"].get("state") == "failed":
            return 1, {"action": "failed", "obligation": obligation_payload(manifest, manifest["final"])}
        if obligation is None or obligation.get("state") != "pending":
            save_manifest(task_dir, manifest)
            return 0, {"action": "idle"}
        if obligation.get("attempts", 0) >= MAX_ATTEMPTS:
            obligation["state"] = "failed"
            save_manifest(task_dir, manifest)
            return 1, {"action": "failed", "obligation": obligation_payload(manifest, obligation)}
        if not stale_or_missing_lease(obligation.get("lease"), now):
            save_manifest(task_dir, manifest)
            return 0, {"action": "pending", "obligation": obligation_payload(manifest, obligation)}
        save_manifest(task_dir, manifest)
        return 0, {"action": "report_due", "obligation": obligation_payload(manifest, obligation)}


def cmd_claim(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    task_dir = safe_absolute(Path(args.task_dir))
    with locked_manifest(task_dir):
        manifest = load_manifest(task_dir)
        now = utc_now()
        obligation = choose_obligation(manifest, args.kind, now)
        if obligation is None:
            return 0, {"status": "idle"}
        if not stale_or_missing_lease(obligation.get("lease"), now):
            return 0, {"status": "pending", "lease": obligation["lease"]}
        obligation["lease"] = {
            "owner": args.owner,
            "claimed_at": iso_now(),
            "expires_at": (now + dt.timedelta(seconds=LEASE_SECONDS)).isoformat().replace("+00:00", "Z"),
        }
        save_manifest(task_dir, manifest)
        return 0, {"status": "claimed", "obligation": obligation_payload(manifest, obligation), "lease": obligation["lease"]}


def choose_obligation(manifest: dict[str, Any], kind: str | None, now: dt.datetime) -> dict[str, Any] | None:
    ensure_periodic_obligation(manifest, now)
    keys = ["final", "periodic"] if kind is None else (["final"] if kind == "final" else ["periodic"])
    for key in keys:
        obligation = manifest.get(key)
        if isinstance(obligation, dict) and obligation.get("state") == "pending":
            return obligation
    return None


def cmd_release(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    task_dir = safe_absolute(Path(args.task_dir))
    with locked_manifest(task_dir):
        manifest = load_manifest(task_dir)
        now = utc_now()
        obligation = choose_obligation(manifest, args.kind, now)
        if obligation is None:
            return 0, {"status": "idle"}
        lease = obligation.get("lease")
        if not isinstance(lease, dict) or lease.get("owner") != args.owner:
            raise RuntimeFailure("lease_owner_mismatch", "release owner does not hold the lease")
        obligation["lease"] = None
        if args.success:
            if valid_delivery_after(manifest, obligation, complete=True):
                save_manifest(task_dir, manifest)
                return 0, {"status": "released", "result": "success"}
            obligation["attempts"] = int(obligation.get("attempts", 0)) + 1
            obligation.setdefault("failures", []).append({"at": iso_now(), "reason": "success release without valid delivery"})
            if obligation["attempts"] >= MAX_ATTEMPTS:
                obligation["state"] = "failed"
                atomic_write_json(task_dir / "reporting.failure.json", obligation["failures"][-1])
        else:
            obligation["attempts"] = int(obligation.get("attempts", 0)) + 1
            obligation.setdefault("failures", []).append({"at": iso_now(), "reason": args.error or "owner reported failure"})
            if obligation["attempts"] >= MAX_ATTEMPTS:
                obligation["state"] = "failed"
                atomic_write_json(task_dir / "reporting.failure.json", obligation["failures"][-1])
        save_manifest(task_dir, manifest)
        return 0, {"status": "released", "result": "error", "obligation": obligation_payload(manifest, obligation)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage bounded work-report obligations")
    sub = parser.add_subparsers(dest="command", required=True)
    register = sub.add_parser("register")
    register.add_argument("--task-dir", required=True)
    register.add_argument("--request", required=True)
    register.add_argument("--decision", required=True)
    register.add_argument("--session-id", required=True)
    register.add_argument("--workspace", required=True)
    register.set_defaults(func=cmd_register)
    status = sub.add_parser("status")
    status.add_argument("--task-dir", required=True)
    status.set_defaults(func=cmd_status)
    cancel = sub.add_parser("cancel")
    cancel.add_argument("--task-dir", required=True)
    cancel.set_defaults(func=cmd_cancel)
    hook = sub.add_parser("hook")
    hook.set_defaults(func=cmd_hook)
    tick = sub.add_parser("tick")
    tick.add_argument("--task-dir", required=True)
    tick.set_defaults(func=cmd_tick)
    claim = sub.add_parser("claim")
    claim.add_argument("--task-dir", required=True)
    claim.add_argument("--owner", required=True)
    claim.add_argument("--kind", choices=["final", "progress"])
    claim.set_defaults(func=cmd_claim)
    release = sub.add_parser("release")
    release.add_argument("--task-dir", required=True)
    release.add_argument("--owner", required=True)
    release.add_argument("--kind", choices=["final", "progress"])
    result = release.add_mutually_exclusive_group(required=True)
    result.add_argument("--success", action="store_true")
    result.add_argument("--error")
    release.set_defaults(func=cmd_release)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        rc, obj = args.func(args)
        emit(obj)
        return rc
    except RuntimeFailure as exc:
        emit({"status": "fail", "issues": [issue(exc.code, exc.message)]})
        return 1
    except Exception as exc:
        emit({"status": "error", "issues": [issue("runtime_error", str(exc))]})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

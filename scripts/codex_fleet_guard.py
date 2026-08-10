#!/usr/bin/env python3
"""Synchronize and run the read-only Codex target guard over a fixed fleet.

The manifest contains only host identities and safe paths.  It must never
contain provider secrets.  All SSH calls are non-interactive batch calls; this
tool intentionally has no PTY/expect mode and cannot change provider settings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REMOTE_HELPER = ROOT / "scripts" / "codex_target_guard.py"
REMOTE_DIR = ".local/lib/agent-tools"
REMOTE_NAME = "codex_target_guard.py"
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class FleetFailure(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FleetFailure(f"could not read manifest {path}: {exc}") from exc
    targets = raw.get("targets") if isinstance(raw, dict) else None
    if not isinstance(targets, list) or not targets:
        raise FleetFailure("manifest must contain a non-empty targets list")
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise FleetFailure("every target must be an object")
        for key in ("id", "platform", "transport", "codex_home", "cc_switch_db"):
            if not isinstance(target.get(key), str) or not target[key]:
                raise FleetFailure(f"target is missing {key}")
        if not SAFE_ID.fullmatch(target["id"]):
            raise FleetFailure(f"unsafe target id {target['id']!r}")
        if target["id"] in seen:
            raise FleetFailure(f"duplicate target id {target['id']}")
        seen.add(target["id"])
        if target["transport"] not in {"ssh", "local"}:
            raise FleetFailure(f"target {target['id']}: transport must be ssh or local")
        if target["transport"] == "ssh" and not SAFE_ID.fullmatch(str(target.get("ssh_alias", ""))):
            raise FleetFailure(f"target {target['id']}: ssh_alias is required and must be safe")
        if target["platform"] not in {"linux", "wsl", "win11"}:
            raise FleetFailure(f"target {target['id']}: unsupported platform {target['platform']!r}")
    return targets


def select_targets(targets: list[dict[str, Any]], requested: list[str]) -> list[dict[str, Any]]:
    if not requested:
        return targets
    wanted = set(requested)
    selected = [target for target in targets if target["id"] in wanted]
    missing = wanted - {target["id"] for target in selected}
    if missing:
        raise FleetFailure(f"targets not in manifest: {', '.join(sorted(missing))}")
    return selected


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=60)
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise FleetFailure(f"command failed ({completed.returncode}): {shlex.join(command)}: {detail}")
    return completed


def ssh_base(target: dict[str, Any]) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "RequestTTY=no",
        target["ssh_alias"],
    ]


def remote_helper_relative_path() -> str:
    return f"{REMOTE_DIR}/{REMOTE_NAME}"


def sync_target(target: dict[str, Any]) -> dict[str, str]:
    local_hash = sha256(REMOTE_HELPER)
    if target["transport"] == "local":
        return {"id": target["id"], "status": "local", "sha256": local_hash}
    if target["platform"] == "win11":
        raise FleetFailure(f"target {target['id']}: Win11 helper must be installed by native install-win11.ps1")
    remote_path = remote_helper_relative_path()
    remote_tmp = f"{remote_path}.tmp"
    run([*ssh_base(target), f'install -d -m 700 "$HOME/{REMOTE_DIR}"'])
    run(
        [
            "scp",
            "-p",
            "-q",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            str(REMOTE_HELPER),
            f"{target['ssh_alias']}:{remote_tmp}",
        ]
    )
    completed = run(
        [
            *ssh_base(target),
            f'install -m 700 "$HOME/{remote_tmp}" "$HOME/{remote_path}" && '
            f'rm -f "$HOME/{remote_tmp}" && sha256sum "$HOME/{remote_path}"',
        ]
    )
    remote_hash = completed.stdout.split()[0] if completed.stdout.split() else ""
    if remote_hash != local_hash:
        raise FleetFailure(f"target {target['id']}: remote helper hash mismatch")
    return {"id": target["id"], "status": "synced", "sha256": local_hash}


def guard_args(
    target: dict[str, Any],
    expected_base_url: str | None,
    requested_platform: str | None = None,
    *,
    path_only: bool = False,
) -> list[str]:
    args = [
        "--platform",
        requested_platform or target["platform"],
        "--codex-home",
        target["codex_home"],
        "--cc-switch-db",
        target["cc_switch_db"],
        "--expected-user",
        target.get("expected_user", ""),
        "--cc-switch-bin",
        target.get("cc_switch_bin", "cc-switch"),
        "--json",
    ]
    if expected_base_url:
        args.extend(["--expect-base-url", expected_base_url])
    if path_only:
        args.extend(["--path-only", "--allow-missing-config", "--allow-missing-cc-switch", "--skip-cc-switch-read-check"])
    return args


def run_guard(
    target: dict[str, Any],
    expected_base_url: str | None,
    requested_platform: str | None = None,
    *,
    path_only: bool = False,
) -> subprocess.CompletedProcess[str]:
    args = guard_args(target, expected_base_url, requested_platform, path_only=path_only)
    if target["transport"] == "local":
        return run([sys.executable, str(REMOTE_HELPER), *args], check=False)
    if target["platform"] == "win11":
        raise FleetFailure(f"target {target['id']}: run the native Win11 helper, never Linux SSH")
    remote_command = 'exec python3 "$HOME/' + remote_helper_relative_path() + '" ' + shlex.join(args)
    return run([*ssh_base(target), remote_command], check=False)


def require_pass(target: dict[str, Any], completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise FleetFailure(f"target {target['id']} guard failed: {detail}")
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise FleetFailure(f"target {target['id']} returned invalid guard JSON") from exc
    if report.get("status") != "PASS":
        raise FleetFailure(f"target {target['id']} did not return PASS")
    report["id"] = target["id"]
    return report


def opposite_platform(platform: str) -> str:
    return "win11" if platform in {"linux", "wsl"} else "linux"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch-only Codex fleet target guard controller.")
    parser.add_argument("command", choices=["sync", "preflight"])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--expect-base-url")
    parser.add_argument(
        "--path-only",
        action="store_true",
        help="Validate only platform, user, and profile paths for scoped Skill-only writes.",
    )
    parser.add_argument(
        "--canary-reject",
        action="store_true",
        help="Also prove that each selected target rejects a deliberately wrong platform before any write.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        targets = select_targets(load_manifest(args.manifest), args.target)
        if args.command == "sync":
            reports = [sync_target(target) for target in targets]
        else:
            reports = [
                require_pass(target, run_guard(target, args.expect_base_url, path_only=args.path_only))
                for target in targets
            ]
            if args.canary_reject:
                for target in targets:
                    negative = run_guard(
                        target,
                        args.expect_base_url,
                        opposite_platform(target["platform"]),
                        path_only=args.path_only,
                    )
                    if negative.returncode == 0:
                        raise FleetFailure(f"target {target['id']}: wrong-platform canary unexpectedly passed")
                for report in reports:
                    report["wrong_platform_canary"] = "rejected"
        print(json.dumps({"status": "PASS", "command": args.command, "targets": reports}, ensure_ascii=False, sort_keys=True))
        return 0
    except (FleetFailure, OSError, subprocess.SubprocessError) as exc:
        print(f"CODEX_FLEET_GUARD=RED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

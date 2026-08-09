#!/usr/bin/env python3
"""Fail-closed platform guard for Codex and CC Switch configuration scripts.

This program is deliberately read-only.  Installers and fleet controllers run
it before any configuration-changing helper.  It binds a Codex home and a CC
Switch database to one operating-system profile, rejects cross-platform common
configuration, and optionally performs CC Switch's read-only validation.

It never prints credentials, provider settings, or auth files.
"""

from __future__ import annotations

import argparse
import json
import os
import platform as host_platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


PLATFORMS = ("auto", "linux", "wsl", "win11")
WINDOWS_PATH_RE = re.compile(r"(?i)(?:\b[a-z]:[\\/]|\\\\\?\\[a-z]:[\\/])")
WSL_WINDOWS_HOME_RE = re.compile(r"(?i)^/mnt/[a-z]/users/[^/]+(?:/|$)")


class GateFailure(RuntimeError):
    """A target did not satisfy the configuration safety contract."""


def is_wsl() -> bool:
    if os.name == "nt" or host_platform.system() != "Linux":
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


def detected_platform() -> str:
    if os.name == "nt":
        return "win11"
    if is_wsl():
        return "wsl"
    return "linux"


def resolved(path: Path) -> Path:
    path = path.expanduser()
    try:
        return path.resolve(strict=False)
    except OSError:
        return path.absolute()


def normalized(path: Path) -> str:
    return str(resolved(path)).replace("\\", "/").rstrip("/").casefold()


def same_path(left: Path, right: Path) -> bool:
    return normalized(left) == normalized(right)


def is_windows_profile_path(path: Path) -> bool:
    return bool(WSL_WINDOWS_HOME_RE.match(str(path).replace("\\", "/")))


def parse_assignments(lines: Iterable[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def provider_block(config: str, provider_id: str = "custom") -> str:
    table = f"[model_providers.{provider_id}]"
    lines = config.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == table), None)
    if start is None:
        raise GateFailure(f"missing required provider table {table}")
    body: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            break
        body.append(line)
    return "\n".join(body)


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        return value[1:-1]
    return value


def validate_paths(
    requested_platform: str,
    codex_home: Path,
    cc_switch_db: Path,
    expected_user: str | None,
    *,
    actual_platform: str | None = None,
    actual_user: str | None = None,
    home_dir: Path | None = None,
) -> str:
    """Validate that both paths belong to this platform and one user profile."""

    actual_platform = actual_platform or detected_platform()
    actual_user = actual_user or os.environ.get("USERNAME") or os.environ.get("USER") or ""
    home_dir = resolved(home_dir or Path.home())
    codex_home = resolved(codex_home)
    cc_switch_db = resolved(cc_switch_db)

    if requested_platform == "auto":
        requested_platform = actual_platform
    if requested_platform not in PLATFORMS:
        raise GateFailure(f"unknown platform {requested_platform!r}")
    if requested_platform != actual_platform:
        raise GateFailure(
            f"platform mismatch: requested {requested_platform}, executing on {actual_platform}; "
            "run the target's native helper instead"
        )
    if expected_user and actual_user.casefold() != expected_user.casefold():
        raise GateFailure(f"user mismatch: expected {expected_user!r}, got {actual_user!r}")
    if codex_home.name.casefold() != ".codex":
        raise GateFailure(f"Codex home must end in .codex: {codex_home}")
    if cc_switch_db.name.casefold() != "cc-switch.db" or cc_switch_db.parent.name.casefold() != ".cc-switch":
        raise GateFailure(f"CC Switch DB must end in .cc-switch/cc-switch.db: {cc_switch_db}")

    profile_root = codex_home.parent
    db_profile_root = cc_switch_db.parent.parent
    if not same_path(profile_root, db_profile_root):
        raise GateFailure(
            "Codex home and CC Switch DB belong to different profiles: " f"{profile_root} != {db_profile_root}"
        )

    if requested_platform in {"linux", "wsl"}:
        if is_windows_profile_path(codex_home) or is_windows_profile_path(cc_switch_db):
            raise GateFailure("Linux/WSL helper refuses a Windows /mnt/<drive>/Users profile")
        if not same_path(profile_root, home_dir):
            raise GateFailure(f"{requested_platform} target must use the executing Unix home {home_dir}, got {profile_root}")
    else:
        # On native Windows Path.home() and USERPROFILE identify the current
        # profile.  Requiring native execution prevents a Linux CC Switch
        # binary from treating a mounted Windows DB as a local common config.
        user_profile = os.environ.get("USERPROFILE")
        if not user_profile:
            raise GateFailure("native Win11 target requires USERPROFILE")
        if not same_path(profile_root, Path(user_profile)):
            raise GateFailure(f"Win11 target must use USERPROFILE {user_profile}, got {profile_root}")
    return requested_platform


def validate_config_contract(
    config_path: Path,
    target_platform: str,
    expected_base_url: str | None,
    *,
    allow_missing: bool,
) -> dict[str, Any]:
    if not config_path.exists():
        if allow_missing:
            return {"config": "missing-allowed"}
        raise GateFailure(f"missing Codex config: {config_path}")

    text = config_path.read_text(encoding="utf-8")
    if target_platform in {"linux", "wsl"} and WINDOWS_PATH_RE.search(text):
        raise GateFailure(f"Windows path pollution detected in {config_path}")
    if target_platform == "win11" and WSL_WINDOWS_HOME_RE.search(text.replace("\\", "/")):
        raise GateFailure(f"WSL Windows-mount path detected in native Win11 config {config_path}")

    lines = text.splitlines()
    first_table = next((index for index, line in enumerate(lines) if line.strip().startswith("[")), len(lines))
    top = parse_assignments(lines[:first_table])
    if unquote(top.get("model_provider", "")) != "custom":
        raise GateFailure("top-level model_provider must be custom")
    for key in ("stream_idle_timeout_ms", "stream_max_retries"):
        if key in top:
            raise GateFailure(f"{key} must be provider-scoped, not top-level")

    provider = parse_assignments(provider_block(text).splitlines())
    required = {
        "base_url": expected_base_url,
        "wire_api": "responses",
        "requires_openai_auth": "true",
        "supports_websockets": "true",
    }
    for key, expected in required.items():
        if key not in provider:
            raise GateFailure(f"provider is missing {key}")
        actual = unquote(provider[key])
        if expected is not None and actual.casefold() != expected.casefold():
            raise GateFailure(f"provider {key} mismatch: expected {expected!r}, got {actual!r}")
    for key in ("stream_idle_timeout_ms", "stream_max_retries"):
        if key not in provider:
            raise GateFailure(f"provider is missing {key}")
    return {
        "config": "valid",
        "provider": "custom",
        "base_url": unquote(provider["base_url"]),
        "websockets": unquote(provider["supports_websockets"]),
    }


def validate_config_platform_only(config_path: Path, target_platform: str, *, allow_missing: bool) -> dict[str, str]:
    """Check only ownership/platform contamination before an installer writes."""

    if not config_path.exists():
        if allow_missing:
            return {"config": "missing-allowed"}
        raise GateFailure(f"missing Codex config: {config_path}")
    text = config_path.read_text(encoding="utf-8")
    if target_platform in {"linux", "wsl"} and WINDOWS_PATH_RE.search(text):
        raise GateFailure(f"Windows path pollution detected in {config_path}")
    if target_platform == "win11" and WSL_WINDOWS_HOME_RE.search(text.replace("\\", "/")):
        raise GateFailure(f"WSL Windows-mount path detected in native Win11 config {config_path}")
    return {"config": "platform-clean"}


def run_cc_switch_read_checks(binary: Path) -> dict[str, str]:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise GateFailure(f"CC Switch binary is not executable: {binary}")
    results: dict[str, str] = {}
    for label, args in (
        ("config_validate", ["config", "validate", "-a", "codex"]),
        ("provider_current", ["provider", "current", "-a", "codex"]),
    ):
        completed = subprocess.run(
            [str(binary), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            raise GateFailure(f"CC Switch {label} failed with exit code {completed.returncode}")
        results[label] = "ok"
    return results


def guard(
    requested_platform: str,
    codex_home: Path,
    cc_switch_db: Path,
    expected_user: str | None,
    expected_base_url: str | None,
    cc_switch_bin: Path | None,
    *,
    allow_missing_config: bool,
    allow_missing_cc_switch: bool,
    skip_cc_switch_read_check: bool,
    path_only: bool,
) -> dict[str, Any]:
    target_platform = validate_paths(requested_platform, codex_home, cc_switch_db, expected_user)
    codex_home = resolved(codex_home)
    cc_switch_db = resolved(cc_switch_db)
    if not cc_switch_db.exists() and not allow_missing_cc_switch:
        raise GateFailure(f"missing CC Switch DB: {cc_switch_db}")
    report: dict[str, Any] = {
        "status": "PASS",
        "platform": target_platform,
        "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
        "codex_home": str(codex_home),
        "cc_switch_db": str(cc_switch_db),
    }
    if path_only:
        report.update(validate_config_platform_only(codex_home / "config.toml", target_platform, allow_missing=allow_missing_config))
    else:
        report.update(validate_config_contract(codex_home / "config.toml", target_platform, expected_base_url, allow_missing=allow_missing_config))
    if not skip_cc_switch_read_check and cc_switch_db.exists():
        if cc_switch_bin is None:
            raise GateFailure("CC Switch binary is required for read validation")
        report["cc_switch"] = run_cc_switch_read_checks(resolved(cc_switch_bin))
    return report


def validate_write_target(
    codex_home: Path,
    cc_switch_db: Path | None = None,
    *,
    requested_platform: str = "auto",
) -> dict[str, Any]:
    """Fail closed before a direct configuration helper changes local state.

    Direct helpers use this narrow, read-only pre-write check instead of
    duplicating platform/path tests.  It intentionally checks only ownership
    and platform contamination: an installer may be creating the initial
    config or CC Switch database, so provider fields cannot be required yet.
    """

    codex_home = resolved(codex_home)
    if cc_switch_db is None:
        cc_switch_db = codex_home.parent / ".cc-switch" / "cc-switch.db"
    return guard(
        requested_platform,
        codex_home,
        cc_switch_db,
        expected_user=None,
        expected_base_url=None,
        cc_switch_bin=None,
        allow_missing_config=True,
        allow_missing_cc_switch=True,
        skip_cc_switch_read_check=True,
        path_only=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Codex/CC Switch platform safety guard.")
    parser.add_argument("--platform", choices=PLATFORMS, default="auto")
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument(
        "--cc-switch-db",
        type=Path,
        default=Path(os.environ.get("CC_SWITCH_DB_PATH", Path.home() / ".cc-switch" / "cc-switch.db")),
    )
    parser.add_argument("--cc-switch-bin", type=Path)
    parser.add_argument("--expected-user")
    parser.add_argument("--expect-base-url")
    parser.add_argument("--allow-missing-config", action="store_true")
    parser.add_argument("--allow-missing-cc-switch", action="store_true")
    parser.add_argument("--skip-cc-switch-read-check", action="store_true")
    parser.add_argument(
        "--path-only",
        action="store_true",
        help="Check target ownership and cross-platform contamination without requiring provider fields.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = guard(
            args.platform,
            args.codex_home,
            args.cc_switch_db,
            args.expected_user,
            args.expect_base_url,
            args.cc_switch_bin,
            allow_missing_config=args.allow_missing_config,
            allow_missing_cc_switch=args.allow_missing_cc_switch,
            skip_cc_switch_read_check=args.skip_cc_switch_read_check,
            path_only=args.path_only,
        )
    except (GateFailure, OSError, subprocess.SubprocessError) as exc:
        print(f"CODEX_TARGET_GUARD=RED: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print("CODEX_TARGET_GUARD=PASS")
        for key in ("platform", "user", "codex_home", "cc_switch_db", "config", "base_url"):
            if key in report:
                print(f"  {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

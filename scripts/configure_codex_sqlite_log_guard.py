#!/usr/bin/env python3
"""Temporary guard for Codex logs_2.sqlite write amplification.

This short-term patch blocks INSERTs into the diagnostic `logs` table in
logs_2.sqlite. It is intentionally narrow: it does not touch conversation
state, sessions, auth, memories, goals, or config.
"""

import argparse
import os
import platform
import sqlite3
from pathlib import Path
from typing import List, Optional, Set


TRIGGER_NAME = "agent_tools_block_codex_log_inserts"
LEGACY_TRIGGER_NAMES = ["block_log_inserts"]
CREATE_TRIGGER_SQL = f"""
CREATE TRIGGER IF NOT EXISTS {TRIGGER_NAME}
BEFORE INSERT ON logs
BEGIN
  SELECT RAISE(IGNORE);
END;
""".strip()


class Result:
    def __init__(
        self,
        path,  # type: Path
        status,  # type: str
        detail,  # type: str
        size_before=None,  # type: Optional[int]
        size_after=None,  # type: Optional[int]
    ):
        # Keep this script compatible with Python 3.6, which is still common on
        # older servers used for Codex CLI bootstrap.
        self.path = path
        self.status = status
        self.detail = detail
        self.size_before = size_before
        self.size_after = size_after


def is_wsl() -> bool:
    if platform.system() != "Linux":
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


def wsl_path_from_windows_path(raw):  # type: (str) -> Optional[Path]
    value = raw.strip().strip('"')
    if not value:
        return None
    value = os.path.expandvars(value)
    value = value.replace("\\", "/")
    if len(value) >= 2 and value[1] == ":":
        return Path("/mnt") / value[0].lower() / value[3:]
    return None


def default_codex_home():  # type: () -> Path
    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        converted = wsl_path_from_windows_path(env_home)
        if converted is not None and is_wsl():
            return converted
        return Path(env_home).expanduser()
    if platform.system() == "Windows":
        return Path.home() / ".codex"
    return Path.home() / ".codex"


def windows_codex_homes_from_wsl():  # type: () -> List[Path]
    users = Path("/mnt/c/Users")
    homes = []  # type: List[Path]
    if not is_wsl() or not users.is_dir():
        return homes
    ignored = {"All Users", "Default", "Default User", "Public", "desktop.ini"}
    for user in sorted(users.iterdir()):
        if user.name in ignored:
            continue
        codex = user / ".codex"
        if codex.is_dir():
            homes.append(codex)
    return homes


def unique_paths(paths):  # type: (List[Path]) -> List[Path]
    seen = set()  # type: Set[str]
    out = []  # type: List[Path]
    for path in paths:
        try:
            key = str(path.expanduser().resolve())
        except OSError:
            key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        out.append(path.expanduser())
    return out


def find_targets(args):  # type: (argparse.Namespace) -> List[Path]
    homes = []  # type: List[Path]
    for raw in args.codex_home:
        converted = wsl_path_from_windows_path(raw)
        homes.append(converted if converted is not None and is_wsl() else Path(raw).expanduser())
    if not homes:
        homes.append(default_codex_home())
    if args.include_wsl_windows:
        homes.extend(windows_codex_homes_from_wsl())
    return unique_paths([home / "logs_2.sqlite" for home in homes])


def table_exists(conn, table):  # type: (sqlite3.Connection, str) -> bool
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def trigger_names(conn):  # type: (sqlite3.Connection) -> Set[str]
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
    }


def apply_mode(path, mode, vacuum):  # type: (Path, str, bool) -> Result
    size_before = path.stat().st_size if path.exists() else None
    if not path.exists():
        return Result(path, "skipped", "logs_2.sqlite does not exist yet", size_before, size_before)

    try:
        conn = sqlite3.connect(str(path), timeout=10)
    except sqlite3.Error as exc:
        return Result(path, "error", f"could not open sqlite database: {exc}", size_before, size_before)

    try:
        if not table_exists(conn, "logs"):
            return Result(path, "skipped", "logs table does not exist yet", size_before, size_before)

        existing = trigger_names(conn)
        if mode == "status":
            active = TRIGGER_NAME in existing or any(name in existing for name in LEGACY_TRIGGER_NAMES)
            detail = "enabled" if active else "not enabled"
            return Result(path, "ok", detail, size_before, size_before)

        if mode == "enable":
            conn.execute(CREATE_TRIGGER_SQL)
            conn.commit()
            detail = f"installed trigger {TRIGGER_NAME}"
        elif mode == "disable":
            conn.execute(f"DROP TRIGGER IF EXISTS {TRIGGER_NAME}")
            for name in LEGACY_TRIGGER_NAMES:
                conn.execute(f"DROP TRIGGER IF EXISTS {name}")
            conn.commit()
            detail = "removed log insert guard triggers"
        else:
            raise ValueError(mode)

        if vacuum:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
            detail += "; checkpointed WAL and vacuumed database"
        else:
            try:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except sqlite3.Error:
                pass
        size_after = path.stat().st_size if path.exists() else None
        return Result(path, "changed", detail, size_before, size_after)
    except sqlite3.Error as exc:
        return Result(path, "error", str(exc), size_before, path.stat().st_size if path.exists() else None)
    finally:
        conn.close()


def parse_args():  # type: () -> argparse.Namespace
    parser = argparse.ArgumentParser(
        description="Install, remove, or inspect the temporary Codex logs_2.sqlite insert guard."
    )
    parser.add_argument("--mode", choices=["enable", "disable", "status"], default="enable")
    parser.add_argument(
        "--codex-home",
        action="append",
        default=[],
        help="Codex home to patch. Repeatable. Default: CODEX_HOME or ~/.codex.",
    )
    parser.add_argument(
        "--include-wsl-windows",
        action="store_true",
        help="When running under WSL, also patch Windows users' /mnt/c/Users/*/.codex homes.",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="After enable/disable, checkpoint WAL and VACUUM. Use only when Codex is stopped.",
    )
    return parser.parse_args()


def main():  # type: () -> int
    args = parse_args()
    targets = find_targets(args)
    if not targets:
        print("No Codex log databases found.")
        return 0

    failed = False
    non_error = False
    for path in targets:
        result = apply_mode(path, args.mode, args.vacuum)
        failed = failed or result.status == "error"
        non_error = non_error or result.status != "error"
        before = "-" if result.size_before is None else str(result.size_before)
        after = "-" if result.size_after is None else str(result.size_after)
        print(f"{result.status}: {path} ({before} -> {after}) {result.detail}")
    return 1 if failed and not non_error else 0


if __name__ == "__main__":
    raise SystemExit(main())

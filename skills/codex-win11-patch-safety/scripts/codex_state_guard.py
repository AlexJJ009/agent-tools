#!/usr/bin/env python3
"""Protect Win11 Codex state before and after patching a copied app bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tomllib
from urllib.parse import urlsplit, urlunsplit
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


PROTECTED_RELATIVE_PATHS = (
    ".codex/auth.json",
    ".codex/config.toml",
    ".codex/.codex-global-state.json",
    ".codex/state_5.sqlite",
    ".codex/memories_1.sqlite",
    ".codex/goals_1.sqlite",
    ".codex/logs_2.sqlite",
    ".codex/sqlite/codex-dev.db",
    ".codex/session_index.jsonl",
    ".codex/sessions",
    ".codex/archived_sessions",
    ".ssh",
    ".cc-switch/cc-switch.db",
    ".cc-switch/settings.json",
    "AppData/Roaming/Codex",
)
CHECKPOINT_RELATIVE_PATHS = (
    ".codex/auth.json",
    ".codex/config.toml",
    ".codex/.codex-global-state.json",
    ".codex/state_5.sqlite",
    ".codex/memories_1.sqlite",
    ".codex/goals_1.sqlite",
    ".codex/session_index.jsonl",
    ".codex/sessions",
    ".codex/archived_sessions",
    ".ssh",
    ".cc-switch/cc-switch.db",
    ".cc-switch/settings.json",
)
CRITICAL_NONEMPTY = {
    ".codex/auth.json",
    ".codex/config.toml",
    ".ssh/config",
    ".cc-switch/cc-switch.db",
    ".cc-switch/settings.json",
}
PRIVATE_KEY_NAMES = {"id_ed25519", "id_rsa", "id_ecdsa", "id_dsa"}
REQUIRED_COMMON_CONFIG_KEYS = {
    "model_catalog_json",
    "model_reasoning_effort",
    "service_tier",
}
FORBIDDEN_LAUNCH_ARGUMENTS = ("--user-data-dir", "--profile-directory")
APPROVED_CONFIG_CHANGES = {
    "model_catalog_json",
    "model_reasoning_effort",
    "service_tier",
}
SAFE_CONFIG_VALUES = {
    "model_provider",
    "model",
    "model_reasoning_effort",
    "service_tier",
}
SECRET_KEY_PARTS = ("api_key", "token", "secret", "password", "credential", "auth")
PROJECT_STATE_NAMES = {
    "AGENTS.md",
    "AGENTS.override.md",
    "CLAUDE.md",
    "status.md",
    "plan.md",
    "planning.md",
    "context.md",
    "memory.md",
}
PROJECT_STATE_DIRS = {".codex", "memory", "memories", "plans", "planning"}
SQLITE_TABLES_BY_FILE = {
    "state_5.sqlite": ("threads",),
    "memories_1.sqlite": ("jobs", "stage1_outputs"),
    "goals_1.sqlite": ("thread_goals",),
    "logs_2.sqlite": ("logs",),
}


def now_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_counts(path: Path) -> dict[str, int]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    result: dict[str, int] = {}
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            tables = {row[0] for row in db.execute("select name from sqlite_master where type='table'")}
            selected = SQLITE_TABLES_BY_FILE.get(path.name, tuple(sorted(tables)))
            for table in selected:
                if table not in tables:
                    continue
                quoted = table.replace('"', '""')
                try:
                    result[table] = int(db.execute(f'select count(*) from "{quoted}"').fetchone()[0])
                except sqlite3.Error:
                    continue
    except sqlite3.Error:
        result["unreadable"] = 1
    return result


def fingerprint_value(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def flatten_mapping(value: object, prefix: str = "") -> dict[str, object]:
    result: dict[str, object] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(flatten_mapping(value[key], child))
    else:
        result[prefix] = value
    return result


def resolve_config_dependency_path(value: str, user_home: Path) -> Path:
    windows_match = re.match(r"^([A-Za-z]):[\\/](.*)$", value)
    if windows_match:
        if os.name == "nt":
            return Path(value)
        drive, tail = windows_match.groups()
        parts = [part for part in re.split(r"[\\/]+", tail) if part]
        return Path("/mnt") / drive.lower() / Path(*parts)
    if value == "~" or value.startswith(("~/", "~\\")):
        tail = value[2:]
        return user_home / Path(*[part for part in re.split(r"[\\/]+", tail) if part])
    return Path(value)


def config_dependency_semantics(parsed: dict, user_home: Path) -> dict[str, dict]:
    dependencies: dict[str, dict] = {}
    value = parsed.get("model_catalog_json")
    if not isinstance(value, str) or not value:
        return dependencies
    resolved = resolve_config_dependency_path(value, user_home)
    entry: dict[str, object] = {
        "configuredPath": value,
        "resolvedPath": str(resolved),
        "exists": resolved.is_file(),
    }
    if not resolved.is_file():
        dependencies["model_catalog_json"] = entry
        return dependencies
    entry["size"] = resolved.stat().st_size
    entry["sha256"] = sha256(resolved)
    try:
        catalog = json.loads(resolved.read_text("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        entry["validCatalog"] = False
    else:
        models = catalog.get("models") if isinstance(catalog, dict) else None
        entry["validCatalog"] = isinstance(models, list) and bool(models)
        entry["modelCount"] = len(models) if isinstance(models, list) else 0
    dependencies["model_catalog_json"] = entry
    return dependencies


def config_semantics(path: Path, user_home: Path | None = None) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {"readable": False, "keys": {}, "safeValues": {}, "externalDependencies": {}}
    try:
        parsed = tomllib.loads(path.read_text("utf-8-sig"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return {"readable": False, "keys": {}, "safeValues": {}, "externalDependencies": {}}
    flattened = flatten_mapping(parsed)
    key_fingerprints = {key: fingerprint_value(value) for key, value in flattened.items()}
    safe_values: dict[str, object] = {}
    for key, value in flattened.items():
        if key in SAFE_CONFIG_VALUES or key.endswith((".model_provider", ".service_tier", ".model_reasoning_effort")):
            safe_values[key] = value
        elif key.startswith("marketplaces.") and key.endswith((".source", ".source_type")):
            safe_values[key] = value
        elif key.endswith(".base_url") and isinstance(value, str):
            parsed_url = urlsplit(value)
            host = parsed_url.hostname or ""
            if parsed_url.port:
                host = f"{host}:{parsed_url.port}"
            safe_values[key] = urlunsplit((parsed_url.scheme, host, parsed_url.path, "", ""))
    secret_presence = sorted(
        key for key, value in flattened.items() if any(part in key.lower() for part in SECRET_KEY_PARTS) and bool(value)
    )
    return {
        "readable": True,
        "keys": key_fingerprints,
        "safeValues": safe_values,
        "secretKeysPresent": secret_presence,
        "externalDependencies": config_dependency_semantics(parsed, user_home or path.parent.parent),
    }


def auth_semantics(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {"readable": False, "topLevelKeys": [], "fingerprint": None}
    try:
        parsed = json.loads(path.read_text("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"readable": False, "topLevelKeys": [], "fingerprint": None}
    return {
        "readable": isinstance(parsed, dict),
        "topLevelKeys": sorted(parsed) if isinstance(parsed, dict) else [],
        "fingerprint": fingerprint_value(parsed),
    }


def parse_ssh_hosts(path: Path) -> list[str]:
    hosts: set[str] = set()
    if not path.exists():
        return []
    for raw in path.read_text("utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"(?i)^host\s+(.+)$", line)
        if not match:
            continue
        for host in match.group(1).split():
            if not any(char in host for char in "*!?"):
                hosts.add(host)
    return sorted(hosts)


def ssh_semantics(user_home: Path) -> dict:
    ssh_root = user_home / ".ssh"
    config = ssh_root / "config"
    private_keys: dict[str, str] = {}
    if ssh_root.exists():
        for item in sorted(ssh_root.iterdir()):
            if item.is_file() and (item.name in PRIVATE_KEY_NAMES or item.suffix == ".pem"):
                private_keys[item.name] = sha256(item)
    return {
        "configSha256": sha256(config) if config.exists() else None,
        "hosts": parse_ssh_hosts(config),
        "privateKeys": private_keys,
    }


def iter_files(path: Path):
    if path.is_file():
        yield path
    elif path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file():
                yield child


def project_state_semantics(project_roots: tuple[Path, ...] = ()) -> dict:
    result: dict[str, dict] = {}
    for root in project_roots:
        resolved = root.expanduser().resolve()
        files: dict[str, str] = {}
        if resolved.exists():
            for child in resolved.iterdir():
                if child.is_file() and child.name in PROJECT_STATE_NAMES:
                    files[child.name] = sha256(child)
                elif child.is_dir() and child.name in PROJECT_STATE_DIRS:
                    for item in iter_files(child):
                        files[item.relative_to(resolved).as_posix()] = sha256(item)
        result[str(resolved)] = {"exists": resolved.exists(), "files": files}
    return result


def build_manifest(user_home: Path, project_roots: tuple[Path, ...] = ()) -> dict:
    entries: dict[str, dict] = {}
    for relative in PROTECTED_RELATIVE_PATHS:
        root = user_home / relative
        if not root.exists():
            entries[relative] = {"exists": False, "kind": "missing"}
            continue
        if root.is_file():
            entries[relative] = {
                "exists": True,
                "kind": "file",
                "size": root.stat().st_size,
                "sha256": sha256(root),
                "sqliteCounts": sqlite_counts(root) if root.suffix == ".sqlite" or root.suffix == ".db" else {},
            }
            continue
        files = list(iter_files(root))
        total_size = sum(item.stat().st_size for item in files)
        names = [item.relative_to(user_home).as_posix() for item in files]
        tree_digest = hashlib.sha256()
        for item, name in zip(files, names):
            tree_digest.update(name.encode("utf-8"))
            tree_digest.update(b"\0")
            tree_digest.update(sha256(item).encode("ascii"))
            tree_digest.update(b"\n")
        entries[relative] = {
            "exists": True,
            "kind": "directory",
            "fileCount": len(files),
            "totalSize": total_size,
            "privateKeyCount": sum(item.name in PRIVATE_KEY_NAMES for item in files),
            "sessionJsonlCount": sum(item.suffix == ".jsonl" for item in files),
            "treeSha256": tree_digest.hexdigest(),
            "files": names,
            "fileSha256": {name: sha256(item) for item, name in zip(files, names)},
            "fileSizes": {name: item.stat().st_size for item, name in zip(files, names)},
        }
    return {
        "schemaVersion": 3,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "userHome": str(user_home),
        "protectedPaths": list(PROTECTED_RELATIVE_PATHS),
        "entries": entries,
        "semantics": {
            "auth": auth_semantics(user_home / ".codex" / "auth.json"),
            "config": config_semantics(user_home / ".codex" / "config.toml", user_home),
            "ssh": ssh_semantics(user_home),
            "ccSwitch": cc_switch_semantics(user_home),
            "projects": project_state_semantics(project_roots),
        },
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def manifest_health_failures(manifest: dict) -> list[str]:
    failures: list[str] = []
    entries = manifest.get("entries", {})
    for relative, entry in entries.items():
        if entry.get("sqliteCounts", {}).get("unreadable"):
            failures.append(f"protected SQLite is unreadable: {relative}")
    semantics = manifest.get("semantics", {})
    if not semantics.get("auth", {}).get("readable"):
        failures.append("auth.json is missing, empty, or invalid")
    failures.extend(config_health_failures(semantics.get("config", {})))
    cc_switch = semantics.get("ccSwitch", {})
    if cc_switch.get("settings", {}).get("exists") and not cc_switch.get("settings", {}).get("readable"):
        failures.append("CC Switch settings.json is unreadable")
    if cc_switch.get("database", {}).get("exists") and not cc_switch.get("database", {}).get("readable"):
        failures.append("CC Switch database is unreadable")
    return failures


def config_health_failures(config: dict) -> list[str]:
    failures: list[str] = []
    if not config.get("readable"):
        failures.append("config.toml is missing, empty, or invalid")
    for key, dependency in config.get("externalDependencies", {}).items():
        if not dependency.get("exists"):
            failures.append(f"config external dependency is missing: {key}")
        elif not dependency.get("validCatalog"):
            failures.append(f"config external dependency is invalid: {key}")
    return failures


def copy_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
    except sqlite3.Error as error:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"SQLite online backup failed for {source}") from error


def copy_protected(user_home: Path, backup_root: Path, relatives=PROTECTED_RELATIVE_PATHS) -> None:
    payload_root = backup_root / "payload"
    for relative in relatives:
        source = user_home / relative
        destination = payload_root / relative
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, destination, copy_function=shutil.copy2, dirs_exist_ok=True)
        elif source.suffix in {".sqlite", ".db"}:
            copy_sqlite(source, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def copy_project_state(project_roots: tuple[Path, ...], backup_root: Path) -> None:
    index: dict[str, str] = {}
    for number, root in enumerate(project_roots, start=1):
        resolved = root.expanduser().resolve()
        if not resolved.exists():
            continue
        destination_root = backup_root / "project-payload" / f"project-{number:03d}"
        index[str(resolved)] = destination_root.relative_to(backup_root).as_posix()
        for child in resolved.iterdir():
            if child.is_file() and child.name in PROJECT_STATE_NAMES:
                destination_root.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, destination_root / child.name)
            elif child.is_dir() and child.name in PROJECT_STATE_DIRS:
                shutil.copytree(child, destination_root / child.name, copy_function=shutil.copy2, dirs_exist_ok=True)
    write_json(backup_root / "project-payload-index.json", {"projects": index})


def marketplace_change_allowed(
    key: str,
    new_config: dict,
    approved_marketplaces: dict[str, str],
) -> bool:
    for name, expected_root in approved_marketplaces.items():
        expected = str(expected_root).removeprefix("\\\\?\\")
        if not re.match(r"^[A-Za-z]:[\\/]", expected):
            return False
        prefix = f"marketplaces.{name}."
        if not key.startswith(prefix):
            continue
        leaf = key[len(prefix):]
        if leaf not in {"source", "source_type", "last_updated"}:
            return False
        safe_values = new_config.get("safeValues", {})
        if leaf == "source":
            actual = str(safe_values.get(key, "")).removeprefix("\\\\?\\")
            return bool(re.match(r"^[A-Za-z]:[\\/]", actual)) and actual.casefold() == expected.casefold()
        if leaf == "source_type":
            return safe_values.get(key) == "local"
        return True
    return False


def compare_manifests(
    before: dict,
    after: dict,
    approved_marketplaces: dict[str, str] | None = None,
) -> dict:
    approved_marketplaces = approved_marketplaces or {}
    failures: list[str] = manifest_health_failures(after)
    warnings: list[str] = []
    before_entries = before["entries"]
    after_entries = after["entries"]
    for relative, old in before_entries.items():
        new = after_entries.get(relative, {"exists": False})
        if old.get("exists") and not new.get("exists"):
            failures.append(f"protected path disappeared: {relative}")
            continue
        if not old.get("exists"):
            continue
        if old.get("kind") == "file":
            if old.get("size", 0) > 0 and new.get("size", 0) == 0:
                failures.append(f"protected file became empty: {relative}")
            for table, old_count in old.get("sqliteCounts", {}).items():
                new_count = new.get("sqliteCounts", {}).get(table, 0)
                if table != "unreadable" and new_count < old_count:
                    failures.append(f"SQLite row count decreased: {relative}:{table} {old_count}->{new_count}")
            is_database = relative.endswith((".sqlite", ".db"))
            semantically_compared = relative in {
                ".codex/auth.json",
                ".codex/config.toml",
                ".cc-switch/settings.json",
                ".cc-switch/cc-switch.db",
            }
            appendable = relative == ".codex/session_index.jsonl"
            if not is_database and not semantically_compared and not appendable and old.get("sha256") != new.get("sha256"):
                failures.append(f"protected file content changed: {relative}")
        elif old.get("kind") == "directory":
            if new.get("fileCount", 0) < old.get("fileCount", 0):
                failures.append(
                    f"protected directory file count decreased: {relative} "
                    f"{old.get('fileCount', 0)}->{new.get('fileCount', 0)}"
                )
            if new.get("privateKeyCount", 0) < old.get("privateKeyCount", 0):
                failures.append(f"SSH private key count decreased under {relative}")
            if new.get("sessionJsonlCount", 0) < old.get("sessionJsonlCount", 0):
                failures.append(f"Codex session JSONL count decreased under {relative}")
            old_hashes = old.get("fileSha256", {})
            new_hashes = new.get("fileSha256", {})
            old_sizes = old.get("fileSizes", {})
            removed = sorted(set(old_hashes) - set(new_hashes))
            changed = sorted(
                name for name in set(old_hashes) & set(new_hashes) if old_hashes[name] != new_hashes[name]
            )
            if removed:
                message = f"protected directory files disappeared under {relative}: " + ", ".join(removed)
                (warnings if relative == "AppData/Roaming/Codex" else failures).append(message)
            if relative in {".codex/sessions", ".codex/archived_sessions"}:
                for name in changed:
                    current = Path(after["userHome"]) / name
                    old_size = int(old_sizes.get(name, 0))
                    if not current.exists() or current.stat().st_size < old_size:
                        failures.append(f"Codex session file was truncated: {name}")
                        continue
                    digest = hashlib.sha256()
                    with current.open("rb") as handle:
                        remaining = old_size
                        while remaining:
                            chunk = handle.read(min(1024 * 1024, remaining))
                            if not chunk:
                                break
                            digest.update(chunk)
                            remaining -= len(chunk)
                    if remaining or digest.hexdigest() != old_hashes[name]:
                        failures.append(f"Codex session existing content was rewritten: {name}")
            elif changed:
                message = f"protected directory existing files changed under {relative}: " + ", ".join(changed)
                (warnings if relative == "AppData/Roaming/Codex" else failures).append(message)
    for relative in CRITICAL_NONEMPTY:
        root_key = next((key for key in PROTECTED_RELATIVE_PATHS if relative == key or relative.startswith(key + "/")), None)
        if root_key and before_entries.get(root_key, {}).get("exists"):
            target = Path(after["userHome"]) / relative
            if not target.exists() or (target.is_file() and target.stat().st_size == 0):
                failures.append(f"critical file missing or empty: {relative}")
    old_semantics = before.get("semantics", {})
    new_semantics = after.get("semantics", {})
    old_auth = old_semantics.get("auth", {})
    new_auth = new_semantics.get("auth", {})
    if old_auth.get("readable") and not new_auth.get("readable"):
        failures.append("user auth.json is no longer valid non-empty JSON")
    if old_auth.get("fingerprint") and old_auth.get("fingerprint") != new_auth.get("fingerprint"):
        failures.append("user auth.json content changed")

    old_config = old_semantics.get("config", {})
    new_config = new_semantics.get("config", {})
    if old_config.get("readable") and not new_config.get("readable"):
        failures.append("user config.toml is no longer valid TOML")
    old_keys = old_config.get("keys", {})
    new_keys = new_config.get("keys", {})
    config_changes = sorted(
        key for key in set(old_keys) | set(new_keys) if old_keys.get(key) != new_keys.get(key)
    )
    disallowed = [
        key
        for key in config_changes
        if key.split(".")[-1] not in APPROVED_CONFIG_CHANGES
        and not marketplace_change_allowed(key, new_config, approved_marketplaces)
    ]
    if disallowed:
        failures.append("unapproved config.toml changes: " + ", ".join(disallowed))

    old_ssh = old_semantics.get("ssh", {})
    new_ssh = new_semantics.get("ssh", {})
    if old_ssh.get("configSha256") != new_ssh.get("configSha256"):
        failures.append("SSH config content changed")
    if old_ssh.get("privateKeys", {}) != new_ssh.get("privateKeys", {}):
        failures.append("SSH private key names or contents changed")
    if old_ssh.get("hosts", []) != new_ssh.get("hosts", []):
        failures.append("SSH Host entries changed")

    old_cc = old_semantics.get("ccSwitch", {})
    new_cc = new_semantics.get("ccSwitch", {})
    if old_cc:
        failures.extend(compare_cc_switch_semantics(old_cc, new_cc))
    old_projects = old_semantics.get("projects", {})
    new_projects = new_semantics.get("projects", {})
    for root, old_project in old_projects.items():
        new_project = new_projects.get(root, {"exists": False, "files": {}})
        if old_project.get("exists") and not new_project.get("exists"):
            failures.append(f"project root disappeared: {root}")
            continue
        old_files = old_project.get("files", {})
        new_files = new_project.get("files", {})
        removed = sorted(set(old_files) - set(new_files))
        changed = sorted(key for key in set(old_files) & set(new_files) if old_files[key] != new_files[key])
        if removed:
            failures.append(f"project memory/planning files disappeared under {root}: " + ", ".join(removed))
        if changed:
            failures.append(f"project memory/planning files changed under {root}: " + ", ".join(changed))
    return {"ok": not failures, "failures": sorted(set(failures)), "warnings": warnings}


def powershell_json(script: str) -> object:
    candidates = [
        Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"),
        Path("powershell.exe"),
    ]
    executable = next((str(item) for item in candidates if item.exists()), "powershell.exe")
    completed = subprocess.run(
        [executable, "-NoProfile", "-Command", script],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    text = completed.stdout.strip()
    return json.loads(text) if text else None


def detect_app_version(patched_root: Path | None) -> dict:
    script = r"""
$pkg = Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | Select-Object -First 1
if (-not $pkg) { throw 'OpenAI.Codex is not installed' }
$asar = Join-Path $pkg.InstallLocation 'app\resources\app.asar'
[pscustomobject]@{
  packageFullName = $pkg.PackageFullName
  packageVersion = $pkg.Version.ToString()
  installLocation = $pkg.InstallLocation
  sourceAsar = $asar
  sourceAsarSha256 = (Get-FileHash -LiteralPath $asar -Algorithm SHA256).Hash
} | ConvertTo-Json -Compress
"""
    result = dict(powershell_json(script))
    report_path = patched_root / "build-report.json" if patched_root else None
    patched = None
    if report_path and report_path.exists():
        try:
            patched = json.loads(report_path.read_text("utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            patched = None
    result["patchedReport"] = {
        "exists": bool(patched),
        "packageFullName": (patched or {}).get("PackageFullName") or (patched or {}).get("packageFullName"),
        "sourceAsarSha256": (patched or {}).get("SourceAsarSha256") or (patched or {}).get("sourceAsarSha256"),
    }
    result["updateDetected"] = not patched or (
        str(result["packageFullName"]) != str(result["patchedReport"]["packageFullName"])
        or str(result["sourceAsarSha256"]).lower()
        != str(result["patchedReport"]["sourceAsarSha256"] or "").lower()
    )
    return result


def extract_top_level_toml_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            break
        match = re.match(r"([A-Za-z0-9_.-]+)\s*=", stripped)
        if match:
            keys.add(match.group(1))
    return keys


def toml_contract(text: str) -> dict:
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {"readable": False, "keys": [], "modelProvider": None, "fingerprint": None}
    flattened = flatten_mapping(parsed)
    return {
        "readable": True,
        "keys": sorted(flattened),
        "keyFingerprints": {key: fingerprint_value(value) for key, value in flattened.items()},
        "modelProvider": flattened.get("model_provider"),
        "fingerprint": fingerprint_value(flattened),
    }


def compare_cc_switch_semantics(old: dict, new: dict) -> list[str]:
    failures: list[str] = []
    if old.get("settings") != new.get("settings"):
        failures.append("CC Switch settings.json semantic configuration changed")
    old_db = old.get("database", {})
    new_db = new.get("database", {})
    if old_db.get("exists") and not new_db.get("readable"):
        failures.append("CC Switch database is no longer readable")
        return failures
    old_common = old_db.get("commonConfig", {}).get("keyFingerprints", {})
    new_common = new_db.get("commonConfig", {}).get("keyFingerprints", {})
    changed = {key for key in set(old_common) | set(new_common) if old_common.get(key) != new_common.get(key)}
    disallowed = sorted(key for key in changed if key.split(".")[-1] not in APPROVED_CONFIG_CHANGES)
    if disallowed:
        failures.append("unapproved CC Switch common_config_codex changes: " + ", ".join(disallowed))
    if old_db.get("providers") != new_db.get("providers"):
        failures.append("CC Switch Codex provider templates changed")
    return failures


def cc_switch_semantics(user_home: Path) -> dict:
    cc_dir = user_home / ".cc-switch"
    settings_summary: dict[str, object] = {"exists": False}
    settings_path = cc_dir / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text("utf-8-sig"))
            settings_summary = {
                "exists": True,
                "readable": isinstance(settings, dict),
                "fingerprint": fingerprint_value(settings),
                "preserveCodexOfficialAuthOnSwitch": settings.get("preserveCodexOfficialAuthOnSwitch"),
                "unifyCodexSessionHistory": settings.get("unifyCodexSessionHistory"),
            }
        except (OSError, UnicodeError, json.JSONDecodeError):
            settings_summary = {"exists": True, "readable": False}

    database_summary: dict[str, object] = {"exists": False, "readable": False}
    db_path = cc_dir / "cc-switch.db"
    if db_path.exists():
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
                common_row = db.execute("select value from settings where key='common_config_codex'").fetchone()
                common = toml_contract(str(common_row[0])) if common_row and common_row[0] else {}
                providers = []
                for provider_id, category, current, config in db.execute(
                    "select id,category,is_current,settings_config from providers where app_type='codex' order by id"
                ):
                    config_contract = {"present": bool(config), "readable": False}
                    if config:
                        try:
                            parsed = json.loads(config)
                            text = parsed.get("config") or parsed.get("configToml") or ""
                            config_contract = {"present": True, **toml_contract(text)}
                        except json.JSONDecodeError:
                            pass
                    providers.append(
                        {
                            "id": str(provider_id),
                            "category": category,
                            "isCurrent": bool(current),
                            "config": config_contract,
                        }
                    )
                database_summary = {
                    "exists": True,
                    "readable": True,
                    "commonConfig": common,
                    "providers": providers,
                }
        except sqlite3.Error:
            database_summary = {"exists": True, "readable": False}
    return {"settings": settings_summary, "database": database_summary}


def validate_ssh_hosts(user_home: Path, ssh_executable: Path | None = None) -> dict:
    hosts = parse_ssh_hosts(user_home / ".ssh" / "config")
    if ssh_executable is None:
        candidates = (
            Path("/mnt/c/Windows/System32/OpenSSH/ssh.exe"),
            Path("C:/Windows/System32/OpenSSH/ssh.exe"),
        )
        ssh_executable = next((item for item in candidates if item.exists()), None)
    if ssh_executable is None:
        return {"ok": False, "failures": ["Windows OpenSSH ssh.exe was not found"], "hosts": {}}
    config_path = user_home / ".ssh" / "config"
    config_argument = str(config_path)
    if str(ssh_executable).startswith("/mnt/") and str(config_path).startswith("/mnt/"):
        converted = subprocess.run(
            ["wslpath", "-w", str(config_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if converted.returncode == 0:
            config_argument = converted.stdout.strip()
    results: dict[str, dict] = {}
    failures: list[str] = []
    for host in hosts:
        completed = subprocess.run(
            [str(ssh_executable), "-F", config_argument, "-G", host],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        parsed = {}
        if completed.returncode == 0:
            for line in completed.stdout.splitlines():
                key, _, value = line.partition(" ")
                if key in {"hostname", "user", "port", "identityfile", "proxyjump"}:
                    parsed.setdefault(key, []).append(value)
        else:
            failures.append(f"SSH Host cannot be resolved: {host}")
        results[host] = {"ok": completed.returncode == 0, "resolved": parsed}
    return {"ok": not failures, "failures": failures, "hosts": results}


def scan_session_providers(codex_dir: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    for root_name in ("sessions", "archived_sessions"):
        root = codex_dir / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        if '"session_meta"' not in line:
                            continue
                        payload = json.loads(line)
                        meta = payload.get("payload", payload)
                        provider = meta.get("model_provider") or meta.get("modelProvider")
                        if provider:
                            counts[str(provider)] += 1
                        break
            except (OSError, json.JSONDecodeError):
                counts["<unreadable>"] += 1
    return counts


def audit_cc_switch(user_home: Path, target: str) -> dict:
    codex_dir = user_home / ".codex"
    cc_dir = user_home / ".cc-switch"
    state_counts: Counter[str] = Counter()
    state_db = codex_dir / "state_5.sqlite"
    if state_db.exists():
        with sqlite3.connect(f"file:{state_db}?mode=ro", uri=True) as db:
            for provider, count in db.execute(
                "select coalesce(model_provider,'<NULL>'),count(*) from threads group by model_provider"
            ):
                state_counts[str(provider)] = int(count)
    jsonl_counts = scan_session_providers(codex_dir)
    common_keys: set[str] = set()
    provider_rows: list[dict] = []
    cc_db = cc_dir / "cc-switch.db"
    if cc_db.exists():
        with sqlite3.connect(f"file:{cc_db}?mode=ro", uri=True) as db:
            row = db.execute("select value from settings where key='common_config_codex'").fetchone()
            if row and row[0]:
                common_keys = extract_top_level_toml_keys(str(row[0]))
            for provider_id, category, current, config in db.execute(
                "select id,category,is_current,settings_config from providers where app_type='codex'"
            ):
                config_keys: set[str] = set()
                active_provider = None
                try:
                    parsed = json.loads(config or "{}")
                    config_text = parsed.get("config") or parsed.get("configToml") or ""
                    if isinstance(config_text, str):
                        config_keys = extract_top_level_toml_keys(config_text)
                        match = re.search(r"(?m)^model_provider\s*=\s*[\"']([^\"']+)", config_text)
                        active_provider = match.group(1) if match else None
                except json.JSONDecodeError:
                    pass
                provider_rows.append(
                    {
                        "id": provider_id,
                        "category": category,
                        "isCurrent": bool(current),
                        "modelProvider": active_provider,
                        "hasConfig": bool(config),
                        "configKeys": sorted(config_keys & (REQUIRED_COMMON_CONFIG_KEYS | {"model_provider"})),
                    }
                )
    preserve_auth = None
    unify_history = None
    settings_path = cc_dir / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text("utf-8-sig"))
        preserve_auth = settings.get("preserveCodexOfficialAuthOnSwitch")
        unify_history = settings.get("unifyCodexSessionHistory")
    non_target_state = {key: value for key, value in state_counts.items() if key != target}
    non_target_jsonl = {key: value for key, value in jsonl_counts.items() if key != target}
    missing_common = sorted(REQUIRED_COMMON_CONFIG_KEYS - common_keys)
    current_providers = [item for item in provider_rows if item["isCurrent"]]
    invalid_current = [
        item["id"] for item in current_providers if item.get("modelProvider") != target
    ]
    failures = []
    if non_target_state:
        failures.append("state_5.sqlite contains non-custom model_provider buckets")
    if non_target_jsonl:
        failures.append("session JSONL contains non-custom model_provider buckets")
    if missing_common:
        failures.append("cc-switch common_config_codex is missing required keys")
    if preserve_auth is not True:
        failures.append("preserveCodexOfficialAuthOnSwitch is not true")
    if not current_providers:
        failures.append("cc-switch has no current Codex provider")
    if invalid_current:
        failures.append("current cc-switch provider template does not use the target model_provider")
    return {
        "ok": not failures,
        "target": target,
        "failures": failures,
        "stateProviderCounts": dict(state_counts),
        "jsonlProviderCounts": dict(jsonl_counts),
        "nonTargetStateProviderCounts": non_target_state,
        "nonTargetJsonlProviderCounts": non_target_jsonl,
        "commonConfigRequiredKeys": sorted(REQUIRED_COMMON_CONFIG_KEYS),
        "commonConfigMissingKeys": missing_common,
        "preserveCodexOfficialAuthOnSwitch": preserve_auth,
        "unifyCodexSessionHistory": unify_history,
        "providers": provider_rows,
        "currentProviderIds": [item["id"] for item in current_providers],
        "invalidCurrentProviderIds": invalid_current,
    }


def lint_launcher(arguments: str) -> dict:
    found = [item for item in FORBIDDEN_LAUNCH_ARGUMENTS if item.lower() in arguments.lower()]
    return {"ok": not found, "forbiddenArgumentsFound": found}


def command_manifest(args: argparse.Namespace) -> int:
    manifest = build_manifest(args.user_home, tuple(getattr(args, "project_root", ())))
    if args.output:
        write_json(args.output, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def command_config_health(args: argparse.Namespace) -> int:
    config = config_semantics(args.user_home / ".codex" / "config.toml", args.user_home)
    failures = config_health_failures(config)
    result = {
        "ok": not failures,
        "configReadable": config.get("readable", False),
        "externalDependencies": config.get("externalDependencies", {}),
        "failures": failures,
    }
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


def command_snapshot(args: argparse.Namespace) -> int:
    destination = args.backup_root / now_stamp()
    destination.mkdir(parents=True, exist_ok=False)
    project_roots = tuple(getattr(args, "project_root", ()))
    manifest = build_manifest(args.user_home, project_roots)
    health_failures = manifest_health_failures(manifest)
    write_json(destination / "manifest.json", manifest)
    if health_failures:
        result = {"ok": False, "snapshot": str(destination), "failures": health_failures}
        write_json(destination / "snapshot-report.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    try:
        copy_protected(args.user_home, destination)
        copy_project_state(project_roots, destination)
    except (OSError, RuntimeError) as error:
        result = {"ok": False, "snapshot": str(destination), "failures": [str(error)]}
        write_json(destination / "snapshot-report.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    write_json(destination / "snapshot-report.json", {"ok": True, "snapshot": str(destination)})
    print(json.dumps({"ok": True, "snapshot": str(destination)}, ensure_ascii=False, indent=2))
    return 0


def manifest_signature(manifest: dict, relatives=CHECKPOINT_RELATIVE_PATHS) -> str:
    stable = {key: manifest["entries"].get(key) for key in relatives}
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def command_checkpoint(args: argparse.Namespace) -> int:
    args.backup_root.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(args.user_home, tuple(getattr(args, "project_root", ())))
    signature = manifest_signature(manifest)
    signature_path = args.backup_root / "latest-signature.txt"
    previous = signature_path.read_text("ascii").strip() if signature_path.exists() else ""
    if previous == signature:
        result = {"ok": True, "changed": False, "signature": signature}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    destination = args.backup_root / now_stamp()
    destination.mkdir(parents=True, exist_ok=False)
    write_json(destination / "manifest.json", manifest)
    copy_protected(args.user_home, destination, CHECKPOINT_RELATIVE_PATHS)
    signature_path.write_text(signature + "\n", encoding="ascii")
    result = {"ok": True, "changed": True, "signature": signature, "checkpoint": str(destination)}
    write_json(destination / "checkpoint-report.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_verify(args: argparse.Namespace) -> int:
    before = json.loads(args.baseline.read_text("utf-8"))
    project_roots = tuple(Path(item) for item in before.get("semantics", {}).get("projects", {}))
    after = build_manifest(args.user_home, project_roots)
    approved_marketplaces = {}
    for item in args.allow_marketplace_root:
        name, separator, root = item.partition("=")
        if not separator or not name or not root:
            raise ValueError("--allow-marketplace-root must use NAME=WINDOWS_PATH")
        normalized = root.removeprefix("\\\\?\\")
        if not re.match(r"^[A-Za-z]:[\\/]", normalized):
            raise ValueError("--allow-marketplace-root requires an absolute native Windows path")
        approved_marketplaces[name] = root
    result = compare_manifests(before, after, approved_marketplaces)
    result["baseline"] = str(args.baseline)
    result["approvedMarketplaceRoots"] = approved_marketplaces
    result["categories"] = {
        "userConfiguration": {
            "ok": not any(
                "auth.json" in item or "config.toml" in item or "config external dependency" in item
                for item in result["failures"]
            ),
            "safeValues": after.get("semantics", {}).get("config", {}).get("safeValues", {}),
            "secretKeysPresent": after.get("semantics", {}).get("config", {}).get("secretKeysPresent", []),
        },
        "sshConnections": validate_ssh_hosts(args.user_home),
        "projectMemoryAndPlanning": {
            "ok": not any(
                any(name in item for name in ("state_5.sqlite", "memories_1.sqlite", "goals_1.sqlite", "logs_2.sqlite", "codex-dev.db", "sessions", "project memory/planning", "project root"))
                for item in result["failures"]
            )
        },
        "ccSwitch": audit_cc_switch(args.user_home, args.cc_switch_target),
    }
    for category in result["categories"].values():
        if not category.get("ok", False):
            result["ok"] = False
            result["failures"].extend(category.get("failures", []))
    result["failures"] = sorted(set(result["failures"]))
    if args.output:
        write_json(args.output, {**result, "after": after})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    manifest = sub.add_parser("manifest")
    snapshot = sub.add_parser("snapshot")
    checkpoint = sub.add_parser("checkpoint")
    verify = sub.add_parser("verify")
    config_health = sub.add_parser("config-health")
    detect = sub.add_parser("detect")
    audit = sub.add_parser("audit-cc-switch")
    lint = sub.add_parser("lint-launcher")
    for item in (manifest, snapshot, checkpoint, verify, config_health, audit):
        item.add_argument("--user-home", type=Path, required=True)
    for item in (manifest, snapshot, checkpoint):
        item.add_argument("--project-root", type=Path, action="append", default=[])
    manifest.add_argument("--output", type=Path)
    snapshot.add_argument("--backup-root", type=Path, required=True)
    checkpoint.add_argument("--backup-root", type=Path, required=True)
    verify.add_argument("--baseline", type=Path, required=True)
    verify.add_argument("--output", type=Path)
    verify.add_argument("--cc-switch-target", default="custom")
    verify.add_argument("--allow-marketplace-root", action="append", default=[])
    config_health.add_argument("--output", type=Path)
    detect.add_argument("--patched-root", type=Path)
    audit.add_argument("--target", default="custom")
    lint.add_argument("--arguments", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "manifest":
        return command_manifest(args)
    if args.command == "snapshot":
        return command_snapshot(args)
    if args.command == "checkpoint":
        return command_checkpoint(args)
    if args.command == "verify":
        return command_verify(args)
    if args.command == "config-health":
        return command_config_health(args)
    if args.command == "detect":
        result = detect_app_version(args.patched_root)
    elif args.command == "audit-cc-switch":
        result = audit_cc_switch(args.user_home, args.target)
    else:
        result = lint_launcher(args.arguments)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Force Codex history and cc-switch Codex provider templates into one bucket.

Codex groups resumable history by `model_provider`.  cc-switch releases based
on older Codex behavior may store each third-party provider under a different
`model_provider` id, so switching providers makes history appear fragmented.

This script normalizes:
- Codex JSONL session metadata under ~/.codex/sessions and archived_sessions
- Codex state_5.sqlite `threads.model_provider`
- live ~/.codex/config.toml
- cc-switch provider template JSON stored in ~/.cc-switch/cc-switch.db

It defaults to a dry run.  Use `--apply --yes` after closing running Codex
processes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_TARGET = "custom"
DEFAULT_CODEX_DIR = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
DEFAULT_CC_SWITCH_DB = Path("~/.cc-switch/cc-switch.db").expanduser()

RESERVED_CODEX_MODEL_PROVIDERS = {
    "amazon-bedrock",
    "lmstudio",
    "ollama",
    "ollama-chat",
    "openai",
    "oss",
}

KNOWN_CC_SWITCH_LEGACY_CODEX_MODEL_PROVIDERS = {
    "ccswitch",
    "aicodemirror",
    "aicoding",
    "aigocode",
    "aihubmix",
    "ark_agentplan",
    "bailian",
    "bailing",
    "byteplus",
    "claudecn",
    "compshare",
    "compshare_coding",
    "crazyrouter",
    "ctok",
    "cubence",
    "deepseek",
    "dmxapi",
    "doubaoseed",
    "eflowcode",
    "kimi",
    "lemondata",
    "longcat",
    "micu",
    "minimax",
    "minimax_en",
    "modelscope",
    "novita",
    "nvidia",
    "openrouter",
    "packycode",
    "patewayai",
    "pipellm",
    "qianfan_coding",
    "relaxycode",
    "rightcode",
    "runapi",
    "shengsuanyun",
    "siliconflow",
    "siliconflow_en",
    "sssaicode",
    "stepfun",
    "stepfun_en",
    "therouter",
    "xiaomi_mimo",
    "xiaomi_mimo_token_plan",
    "zhipu_glm",
    "zhipu_glm_en",
}


@dataclass
class ConfigInfo:
    active_provider: str | None = None
    provider_ids: list[str] = field(default_factory=list)
    profile_providers: list[str] = field(default_factory=list)
    changed: bool = False
    source_provider: str | None = None


@dataclass
class JsonlPlan:
    files_scanned: int = 0
    session_meta_lines: int = 0
    files_to_change: int = 0
    lines_to_change: int = 0
    provider_counts: Counter[str] = field(default_factory=Counter)
    migrate_counts: Counter[str] = field(default_factory=Counter)


@dataclass
class SqlitePlan:
    exists: bool = False
    total_rows: int = 0
    rows_to_change: int = 0
    provider_counts: Counter[str] = field(default_factory=Counter)
    migrate_counts: Counter[str] = field(default_factory=Counter)


@dataclass
class ProviderTemplatePlan:
    provider_id: str
    category: str | None
    active_provider: str | None
    provider_ids: list[str]
    will_change: bool
    source_provider: str | None
    reason: str = ""


def log(message: str) -> None:
    print(message, flush=True)


def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def is_safe_provider_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", value))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unify Codex model_provider history and cc-switch templates into one bucket."
    )
    parser.add_argument("--target", default=DEFAULT_TARGET, help="target bucket id, default: custom")
    parser.add_argument("--codex-dir", type=Path, default=DEFAULT_CODEX_DIR)
    parser.add_argument("--cc-switch-db", type=Path, default=DEFAULT_CC_SWITCH_DB)
    parser.add_argument(
        "--source-provider",
        action="append",
        default=[],
        help="source provider id to migrate; repeatable. Default: trusted cc-switch third-party buckets only.",
    )
    parser.add_argument(
        "--all-non-target-providers",
        action="store_true",
        help="migrate every non-empty non-target model_provider bucket except --exclude-provider. This can rewrite official OpenAI history.",
    )
    parser.add_argument(
        "--exclude-provider",
        action="append",
        default=[],
        help="provider id to leave untouched when --source-provider is not set; repeatable.",
    )
    parser.add_argument("--skip-history", action="store_true", help="skip JSONL and state DB history")
    parser.add_argument("--skip-live-config", action="store_true", help="skip ~/.codex/config.toml")
    parser.add_argument("--skip-cc-switch", action="store_true", help="skip cc-switch provider templates")
    parser.add_argument(
        "--include-official-provider-templates",
        action="store_true",
        help="also normalize cc-switch codex providers whose category is official if they have a config blob",
    )
    parser.add_argument(
        "--allow-running-codex",
        action="store_true",
        help="allow writes while a codex process is running. Use only when you accept possible races.",
    )
    parser.add_argument(
        "--kill-running-codex",
        action="store_true",
        help="terminate running codex processes before --apply so new config and keys are not shadowed by in-memory state.",
    )
    parser.add_argument("--backup-root", type=Path, help="backup directory for --apply")
    parser.add_argument("--apply", action="store_true", help="write changes. Omit for dry-run.")
    parser.add_argument("--yes", action="store_true", help="required with --apply")
    return parser.parse_args()


def should_migrate_provider(
    provider: str | None,
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
) -> bool:
    if not provider:
        return False
    provider = provider.strip()
    if not provider or provider == target:
        return False
    if provider in excluded_providers:
        return False
    if source_providers:
        return provider in source_providers
    if all_non_target_providers:
        return True
    return False


def provider_is_reserved(provider_id: str) -> bool:
    return provider_id.strip().lower() in RESERVED_CODEX_MODEL_PROVIDERS


def provider_is_known_legacy(provider_id: str) -> bool:
    return provider_id.strip().lower() in KNOWN_CC_SWITCH_LEGACY_CODEX_MODEL_PROVIDERS


def add_provider_aliases(targets: set[str], provider_id: str, target: str) -> None:
    provider_id = provider_id.strip()
    if not provider_id or provider_id == target or provider_is_reserved(provider_id):
        return
    targets.add(provider_id)
    swapped_to_underscore = provider_id.replace("-", "_")
    swapped_to_hyphen = provider_id.replace("_", "-")
    for alias in (swapped_to_underscore, swapped_to_hyphen):
        if alias and alias != target and not provider_is_reserved(alias):
            targets.add(alias)


def infer_source_providers_from_cc_switch(db_path: Path, target: str, include_official: bool) -> set[str]:
    inferred: set[str] = set()
    if not db_path.exists():
        return inferred

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "providers"):
            return inferred
        for row in conn.execute(
            "SELECT id, category, settings_config FROM providers WHERE app_type='codex' ORDER BY id"
        ):
            provider_id = str(row["id"] or "").strip()
            category = row["category"]
            if category == "official" and not include_official:
                continue
            add_provider_aliases(inferred, provider_id, target)
            try:
                settings = json.loads(row["settings_config"])
            except Exception:
                continue
            config_text = settings.get("config") if isinstance(settings, dict) else None
            if not isinstance(config_text, str) or not config_text.strip():
                continue
            active = top_level_model_provider(config_text)
            for candidate in [active, *provider_ids_from_config_text(config_text), *profile_model_providers(config_text)]:
                if (
                    candidate
                    and candidate != target
                    and not provider_is_reserved(candidate)
                    and (provider_is_known_legacy(candidate) or not provider_is_reserved(provider_id))
                ):
                    add_provider_aliases(inferred, candidate, target)
            normalized_source = normalized_legacy_provider_name_from_config(config_text, target)
            if normalized_source:
                add_provider_aliases(inferred, normalized_source, target)
    finally:
        conn.close()
    return inferred


def infer_source_providers_from_codex(codex_dir: Path, target: str) -> set[str]:
    inferred: set[str] = set()

    config_path = codex_dir / "config.toml"
    if config_path.exists():
        try:
            config_text = config_path.read_text(encoding="utf-8")
        except OSError:
            config_text = ""
        for candidate in [
            top_level_model_provider(config_text),
            *provider_ids_from_config_text(config_text),
            *profile_model_providers(config_text),
        ]:
            if candidate and candidate != target and not provider_is_reserved(candidate):
                add_provider_aliases(inferred, candidate, target)
        normalized_source = normalized_legacy_provider_name_from_config(config_text, target)
        if normalized_source:
            add_provider_aliases(inferred, normalized_source, target)

    for dirname in ("sessions", "archived_sessions"):
        root = codex_dir / dirname
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        if '"session_meta"' not in line or '"model_provider"' not in line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        if obj.get("type") != "session_meta":
                            continue
                        provider = (obj.get("payload") or {}).get("model_provider")
                        if isinstance(provider, str) and provider != target and not provider_is_reserved(provider):
                            add_provider_aliases(inferred, provider, target)
            except OSError:
                continue

    state_db = codex_dir / "state_5.sqlite"
    if state_db.exists():
        try:
            conn = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
            try:
                if table_exists(conn, "threads") and column_exists(conn, "threads", "model_provider"):
                    for (provider,) in conn.execute(
                        "SELECT DISTINCT model_provider FROM threads WHERE model_provider IS NOT NULL"
                    ):
                        if (
                            isinstance(provider, str)
                            and provider.strip()
                            and provider != target
                            and not provider_is_reserved(provider)
                        ):
                            add_provider_aliases(inferred, provider, target)
            finally:
                conn.close()
        except sqlite3.Error:
            pass

    return inferred


def infer_template_source_providers(provider_id: str, config_text: str, target: str) -> set[str]:
    inferred: set[str] = set()
    provider_id = provider_id.strip()
    add_provider_aliases(inferred, provider_id, target)

    active = top_level_model_provider(config_text)
    for candidate in [active, *provider_ids_from_config_text(config_text), *profile_model_providers(config_text)]:
        if candidate and candidate != target and not provider_is_reserved(candidate):
            add_provider_aliases(inferred, candidate, target)

    normalized_source = normalized_legacy_provider_name_from_config(config_text, target)
    if normalized_source:
        add_provider_aliases(inferred, normalized_source, target)
    return inferred


def command_output(args: list[str]) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return ""


@dataclass
class ProcessInfo:
    pid: int
    ppid: int
    comm: str
    args: str

    def display(self) -> str:
        return f"{self.pid} {self.ppid} {self.comm} {self.args}".strip()


def running_codex_processes() -> list[ProcessInfo]:
    output = command_output(["ps", "-eo", "pid=,ppid=,comm=,args="])
    current_pid = os.getpid()
    matches: list[ProcessInfo] = []
    for line in output.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        if pid == current_pid:
            continue
        comm = parts[2]
        args = parts[3] if len(parts) > 3 else ""
        exe_name = ""
        try:
            argv = shlex.split(args)
            exe_name = Path(argv[0]).name if argv else ""
        except Exception:
            exe_name = args.split(None, 1)[0].rsplit("/", 1)[-1] if args else ""
        if comm == "codex" or exe_name == "codex":
            matches.append(ProcessInfo(pid=pid, ppid=ppid, comm=comm, args=args))
    return matches


def terminate_processes(processes: list[ProcessInfo], timeout_seconds: float = 5.0) -> list[ProcessInfo]:
    if not processes:
        return []

    current_pid = os.getpid()
    targets = [proc for proc in processes if proc.pid != current_pid]
    for proc in targets:
        try:
            os.kill(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        remaining = running_codex_processes()
        remaining_pids = {proc.pid for proc in remaining}
        if not any(proc.pid in remaining_pids for proc in targets):
            return []
        time.sleep(0.2)

    remaining = running_codex_processes()
    remaining_by_pid = {proc.pid: proc for proc in remaining}
    stubborn = [remaining_by_pid[proc.pid] for proc in targets if proc.pid in remaining_by_pid]
    for proc in stubborn:
        try:
            os.kill(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(0.2)
    remaining = running_codex_processes()
    remaining_by_pid = {proc.pid: proc for proc in remaining}
    return [remaining_by_pid[proc.pid] for proc in targets if proc.pid in remaining_by_pid]


def ensure_backup_root(args: argparse.Namespace) -> Path:
    if args.backup_root:
        root = args.backup_root.expanduser()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = args.cc_switch_db.expanduser().parent / "backups" / f"manual-codex-provider-bucket-{stamp}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def copy_backup(source: Path, backup_root: Path, label: str, relative_root: Path | None = None) -> Path:
    if relative_root:
        try:
            rel = source.resolve().relative_to(relative_root.resolve())
        except ValueError:
            rel = Path(source.name)
    else:
        rel = Path(source.name)
    dest = backup_root / label / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return dest


def backup_sqlite_online(db_path: Path, backup_root: Path, label: str) -> Path:
    dest = backup_root / label / db_path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dest


def parse_toml_header_path(line: str) -> list[str] | None:
    stripped = line.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None
    if stripped.startswith("[["):
        return None
    inner = stripped[1:-1].strip()
    if not inner:
        return None

    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    escaped = False
    for ch in inner:
        if quote:
            buf.append(ch)
            if quote == '"' and ch == "\\" and not escaped:
                escaped = True
                continue
            if ch == quote and not escaped:
                quote = None
            escaped = False
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue
        if ch == ".":
            parts.append(unquote_toml_key("".join(buf).strip()))
            buf = []
            continue
        buf.append(ch)
    parts.append(unquote_toml_key("".join(buf).strip()))
    return parts


def is_toml_header(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")


def unquote_toml_key(key: str) -> str:
    if len(key) >= 2 and key[0] == key[-1] == '"':
        try:
            return json.loads(key)
        except Exception:
            return key[1:-1]
    if len(key) >= 2 and key[0] == key[-1] == "'":
        return key[1:-1]
    return key


def toml_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return json.dumps(key, ensure_ascii=False)


def format_toml_path(parts: Iterable[str]) -> str:
    return ".".join(toml_key(part) for part in parts)


def provider_ids_from_config_text(text: str) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        path = parse_toml_header_path(line)
        if not path or len(path) < 2 or path[0] != "model_providers":
            continue
        provider_id = path[1]
        if provider_id not in seen:
            ids.append(provider_id)
            seen.add(provider_id)
    return ids


def top_level_model_provider(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            return None
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() != "model_provider":
            continue
        match = re.match(r"\s*(['\"])(.*?)\1", value.strip())
        return match.group(2).strip() if match else None
    return None


def profile_model_providers(text: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    in_profile = False
    for line in text.splitlines():
        path = parse_toml_header_path(line)
        if path is not None:
            in_profile = len(path) >= 2 and path[0] == "profiles"
            continue
        if not in_profile:
            continue
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() != "model_provider":
            continue
        match = re.match(r"\s*(['\"])(.*?)\1", value.strip())
        if match:
            provider = match.group(2).strip()
            if provider and provider not in seen:
                values.append(provider)
                seen.add(provider)
    return values


def normalized_legacy_provider_name_from_config(text: str, target: str) -> str | None:
    if top_level_model_provider(text) != target:
        return None
    lines = text.splitlines()
    in_target_provider = False
    for line in lines:
        path = parse_toml_header_path(line)
        if path is not None:
            in_target_provider = path == ["model_providers", target]
            continue
        if not in_target_provider:
            continue
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() != "name":
            continue
        match = re.match(r"\s*(['\"])(.*?)\1", value.strip())
        if not match:
            return None
        raw_name = match.group(2).strip()
        lowered = raw_name.lower()
        if lowered in KNOWN_CC_SWITCH_LEGACY_CODEX_MODEL_PROVIDERS:
            return lowered
        if is_safe_provider_id(raw_name) and not provider_is_reserved(raw_name) and raw_name != target:
            return raw_name
        aliases = {
            "e-flowcode": "eflowcode",
            "pipellm": "pipellm",
        }
        return aliases.get(lowered)
    return None


def set_top_level_model_provider(text: str, target: str) -> str:
    lines = text.splitlines()
    first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
    replacement = f'model_provider = "{target}"'
    for i in range(first_table):
        stripped = lines[i].strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key == "model_provider":
            lines[i] = replacement
            return "\n".join(lines).rstrip() + "\n"

    insert_at = first_table
    while insert_at > 0 and not lines[insert_at - 1].strip():
        insert_at -= 1
    if insert_at > 0 and insert_at < len(lines) and lines[insert_at - 1].strip():
        lines.insert(insert_at, replacement)
    else:
        lines.insert(insert_at, replacement)
    return "\n".join(lines).rstrip() + "\n"


def path_has_prefix(path: list[str] | None, prefix: list[str]) -> bool:
    return bool(path) and len(path) >= len(prefix) and path[: len(prefix)] == prefix


def remove_model_provider_sections(text: str, provider_id: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    prefix = ["model_providers", provider_id]
    while i < len(lines):
        path = parse_toml_header_path(lines[i])
        if path_has_prefix(path, prefix):
            i += 1
            while i < len(lines) and not is_toml_header(lines[i]):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return compact_blank_lines(out)


def copy_model_provider_sections(text: str, source: str, target: str) -> list[str]:
    lines = text.splitlines()
    copied: list[str] = []
    i = 0
    prefix = ["model_providers", source]
    while i < len(lines):
        path = parse_toml_header_path(lines[i])
        if path_has_prefix(path, prefix):
            new_path = ["model_providers", target] + path[2:]
            copied.append(f"[{format_toml_path(new_path)}]")
            i += 1
            while i < len(lines) and not is_toml_header(lines[i]):
                copied.append(lines[i])
                i += 1
            while copied and not copied[-1].strip():
                copied.pop()
            copied.append("")
            continue
        i += 1
    while copied and not copied[-1].strip():
        copied.pop()
    return copied


def rewrite_profile_model_provider_refs(
    text: str,
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_profile = False
    for line in lines:
        path = parse_toml_header_path(line)
        if path is not None:
            in_profile = len(path) >= 2 and path[0] == "profiles"
            out.append(line)
            continue
        if in_profile and "=" in line and not line.strip().startswith("#"):
            stripped = line.strip()
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key == "model_provider":
                match = re.match(r"\s*(['\"])(.*?)\1", value.strip())
                provider = match.group(2).strip() if match else None
                if should_migrate_provider(
                    provider,
                    target,
                    source_providers,
                    excluded_providers,
                    all_non_target_providers,
                ):
                    out.append(f'model_provider = "{target}"')
                    continue
        out.append(line)
    return "\n".join(out).rstrip() + "\n"


def compact_blank_lines(lines: list[str]) -> str:
    out: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and (previous_blank or not out):
            previous_blank = True
            continue
        out.append(line)
        previous_blank = blank
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out).rstrip() + "\n"


def choose_source_provider(active: str | None, provider_ids: list[str], target: str) -> str | None:
    provider_set = set(provider_ids)
    if active and active != target and active in provider_set:
        return active
    if target in provider_set:
        return None
    non_target = [provider_id for provider_id in provider_ids if provider_id != target]
    if len(non_target) == 1:
        return non_target[0]
    return None


def migratable_provider_ids(
    provider_ids: list[str],
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
) -> list[str]:
    return [
        provider_id
        for provider_id in provider_ids
        if should_migrate_provider(
            provider_id,
            target,
            source_providers,
            excluded_providers,
            all_non_target_providers,
        )
    ]


def choose_source_provider_for_migration(
    active: str | None,
    provider_ids: list[str],
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
) -> str | None:
    provider_set = set(provider_ids)
    if active and active in provider_set and should_migrate_provider(
        active,
        target,
        source_providers,
        excluded_providers,
        all_non_target_providers,
    ):
        return active

    candidates = migratable_provider_ids(
        provider_ids,
        target,
        source_providers,
        excluded_providers,
        all_non_target_providers,
    )
    if len(candidates) == 1:
        return candidates[0]
    if target in provider_set:
        return None
    return None


def normalize_codex_config_text(
    text: str,
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
) -> tuple[str, ConfigInfo]:
    original = text
    active = top_level_model_provider(text)
    provider_ids = provider_ids_from_config_text(text)
    profile_providers = profile_model_providers(text)
    source = choose_source_provider_for_migration(
        active,
        provider_ids,
        target,
        source_providers,
        excluded_providers,
        all_non_target_providers,
    )

    if not text.strip():
        return text, ConfigInfo(active, provider_ids, profile_providers, False, None)

    if should_migrate_provider(active, target, source_providers, excluded_providers, all_non_target_providers):
        text = set_top_level_model_provider(text, target)
    if source:
        copied = copy_model_provider_sections(original, source, target)
        if copied:
            text = remove_model_provider_sections(text, target).rstrip() + "\n\n" + "\n".join(copied).rstrip() + "\n"
    for provider_id in migratable_provider_ids(
        provider_ids,
        target,
        source_providers,
        excluded_providers,
        all_non_target_providers,
    ):
        text = remove_model_provider_sections(text, provider_id)
    text = rewrite_profile_model_provider_refs(
        text,
        target,
        source_providers,
        excluded_providers,
        all_non_target_providers,
    )
    text = compact_blank_lines(text.splitlines())
    return text, ConfigInfo(active, provider_ids, profile_providers, text != original, source)


def atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def scan_jsonl_history(
    codex_dir: Path,
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
) -> JsonlPlan:
    plan = JsonlPlan()
    for dirname in ("sessions", "archived_sessions"):
        root = codex_dir / dirname
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            plan.files_scanned += 1
            file_changes = 0
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        if obj.get("type") != "session_meta":
                            continue
                        provider = (obj.get("payload") or {}).get("model_provider")
                        if isinstance(provider, str) and provider:
                            plan.session_meta_lines += 1
                            plan.provider_counts[provider] += 1
                            if should_migrate_provider(
                                provider,
                                target,
                                source_providers,
                                excluded_providers,
                                all_non_target_providers,
                            ):
                                plan.lines_to_change += 1
                                plan.migrate_counts[provider] += 1
                                file_changes += 1
            except FileNotFoundError:
                continue
            if file_changes:
                plan.files_to_change += 1
    return plan


def rewrite_jsonl_history(
    codex_dir: Path,
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
    backup_root: Path,
) -> tuple[int, int]:
    changed_files = 0
    changed_lines = 0
    for dirname in ("sessions", "archived_sessions"):
        root = codex_dir / dirname
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            before = path.stat()
            text = path.read_text(encoding="utf-8")
            out: list[str] = []
            file_changed = False
            file_changed_lines = 0
            for segment in text.splitlines(keepends=True):
                newline = "\n" if segment.endswith("\n") else ""
                line = segment[:-1] if newline else segment
                try:
                    obj = json.loads(line)
                except Exception:
                    out.append(segment)
                    continue
                if obj.get("type") == "session_meta":
                    payload = obj.get("payload")
                    provider = payload.get("model_provider") if isinstance(payload, dict) else None
                    if isinstance(provider, str) and should_migrate_provider(
                        provider,
                        target,
                        source_providers,
                        excluded_providers,
                        all_non_target_providers,
                    ):
                        payload["model_provider"] = target
                        out.append(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + newline)
                        file_changed = True
                        file_changed_lines += 1
                        continue
                out.append(segment)

            if not file_changed:
                continue
            after = path.stat()
            if before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size:
                die(f"Codex session file changed during migration: {path}")
            copy_backup(path, backup_root, "codex-jsonl", codex_dir)
            atomic_write_text(path, "".join(out), before.st_mode & 0o777)
            changed_files += 1
            changed_lines += file_changed_lines
    return changed_files, changed_lines


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def state_where_clause(
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
) -> tuple[str, list[str]]:
    parts = ["model_provider IS NOT NULL", "TRIM(model_provider) != ''", "model_provider != ?"]
    params: list[str] = [target]
    if source_providers:
        placeholders = ",".join("?" for _ in source_providers)
        parts.append(f"model_provider IN ({placeholders})")
        params.extend(sorted(source_providers))
    elif all_non_target_providers and excluded_providers:
        placeholders = ",".join("?" for _ in excluded_providers)
        parts.append(f"model_provider NOT IN ({placeholders})")
        params.extend(sorted(excluded_providers))
    elif not all_non_target_providers:
        parts.append("1 = 0")
    return " AND ".join(parts), params


def scan_state_db(
    db_path: Path,
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
) -> SqlitePlan:
    plan = SqlitePlan(exists=db_path.exists())
    if not db_path.exists():
        return plan
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        if not table_exists(conn, "threads") or not column_exists(conn, "threads", "model_provider"):
            return plan
        for provider, count in conn.execute(
            "SELECT model_provider, COUNT(*) FROM threads GROUP BY model_provider"
        ):
            provider = provider or ""
            plan.provider_counts[provider] = count
            plan.total_rows += count
            if should_migrate_provider(
                provider,
                target,
                source_providers,
                excluded_providers,
                all_non_target_providers,
            ):
                plan.migrate_counts[provider] += count
                plan.rows_to_change += count
    finally:
        conn.close()
    return plan


def migrate_state_db(
    db_path: Path,
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
    backup_root: Path,
) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        if not table_exists(conn, "threads") or not column_exists(conn, "threads", "model_provider"):
            return 0
        where_sql, params = state_where_clause(
            target,
            source_providers,
            excluded_providers,
            all_non_target_providers,
        )
        rows = conn.execute(f"SELECT COUNT(*) FROM threads WHERE {where_sql}", params).fetchone()[0]
        if rows == 0:
            return 0
        backup_sqlite_online(db_path, backup_root, "codex-state")
        changed = conn.execute(
            f"UPDATE threads SET model_provider=? WHERE {where_sql}",
            [target] + params,
        ).rowcount
        conn.commit()
        return int(changed)
    finally:
        conn.close()


def normalize_live_config(
    codex_dir: Path,
    target: str,
    source_providers: set[str],
    excluded_providers: set[str],
    all_non_target_providers: bool,
    apply: bool,
    backup_root: Path | None,
) -> ConfigInfo:
    path = codex_dir / "config.toml"
    if not path.exists():
        return ConfigInfo()
    text = path.read_text(encoding="utf-8")
    new_text, info = normalize_codex_config_text(
        text,
        target,
        source_providers,
        excluded_providers,
        all_non_target_providers,
    )
    if apply and info.changed:
        assert backup_root is not None
        copy_backup(path, backup_root, "codex-config", codex_dir)
        atomic_write_text(path, new_text, path.stat().st_mode & 0o777)
    return info


def scan_cc_switch_templates(
    db_path: Path,
    target: str,
    include_official: bool,
    all_non_target_providers: bool,
) -> list[ProviderTemplatePlan]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    plans: list[ProviderTemplatePlan] = []
    try:
        if not table_exists(conn, "providers"):
            return plans
        for row in conn.execute(
            "SELECT id, category, settings_config FROM providers WHERE app_type='codex' ORDER BY id"
        ):
            provider_id = row["id"]
            category = row["category"]
            if category == "official" and not include_official:
                plans.append(ProviderTemplatePlan(provider_id, category, None, [], False, None, "official skipped"))
                continue
            try:
                settings = json.loads(row["settings_config"])
            except Exception:
                plans.append(ProviderTemplatePlan(provider_id, category, None, [], False, None, "invalid JSON"))
                continue
            config_text = settings.get("config") if isinstance(settings, dict) else None
            if not isinstance(config_text, str) or not config_text.strip():
                plans.append(ProviderTemplatePlan(provider_id, category, None, [], False, None, "empty config"))
                continue
            template_sources = infer_template_source_providers(provider_id, config_text, target)
            new_text, info = normalize_codex_config_text(
                config_text,
                target,
                template_sources,
                set(),
                all_non_target_providers,
            )
            plans.append(
                ProviderTemplatePlan(
                    provider_id,
                    category,
                    info.active_provider,
                    info.provider_ids,
                    new_text != config_text,
                    info.source_provider,
                )
            )
    finally:
        conn.close()
    return plans


def migrate_cc_switch_templates(
    db_path: Path,
    target: str,
    include_official: bool,
    all_non_target_providers: bool,
    backup_root: Path,
) -> int:
    if not db_path.exists():
        return 0
    backup_sqlite_online(db_path, backup_root, "cc-switch-db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    changed = 0
    try:
        if not table_exists(conn, "providers"):
            return 0
        columns = table_columns(conn, "providers")
        has_updated_at = "updated_at" in columns
        rows = conn.execute(
            "SELECT id, category, settings_config FROM providers WHERE app_type='codex' ORDER BY id"
        ).fetchall()
        for row in rows:
            provider_id = row["id"]
            category = row["category"]
            if category == "official" and not include_official:
                continue
            try:
                settings = json.loads(row["settings_config"])
            except Exception:
                continue
            if not isinstance(settings, dict):
                continue
            config_text = settings.get("config")
            if not isinstance(config_text, str) or not config_text.strip():
                continue
            template_sources = infer_template_source_providers(provider_id, config_text, target)
            new_text, _info = normalize_codex_config_text(
                config_text,
                target,
                template_sources,
                set(),
                all_non_target_providers,
            )
            if new_text == config_text:
                continue
            settings["config"] = new_text
            settings_json = json.dumps(settings, ensure_ascii=False, separators=(",", ":"))
            if has_updated_at:
                conn.execute(
                    "UPDATE providers SET settings_config=?, updated_at=? WHERE app_type='codex' AND id=?",
                    (settings_json, int(time.time() * 1000), provider_id),
                )
            else:
                conn.execute(
                    "UPDATE providers SET settings_config=? WHERE app_type='codex' AND id=?",
                    (settings_json, provider_id),
                )
            changed += 1
        conn.commit()
    finally:
        conn.close()
    return changed


def print_counter(title: str, counts: Counter[str]) -> None:
    if not counts:
        log(f"{title}: none")
        return
    log(title + ":")
    for provider, count in counts.most_common():
        log(f"  {provider}: {count}")


def main() -> None:
    args = parse_args()
    args.codex_dir = args.codex_dir.expanduser()
    args.cc_switch_db = args.cc_switch_db.expanduser()
    target = args.target.strip()
    if not is_safe_provider_id(target):
        die(f"invalid --target provider id: {target}")
    source_providers = {p.strip() for p in args.source_provider if p.strip()}
    excluded_providers = {p.strip() for p in args.exclude_provider if p.strip()}
    if not source_providers and not args.all_non_target_providers:
        source_providers = infer_source_providers_from_cc_switch(
            args.cc_switch_db,
            target,
            args.include_official_provider_templates,
        )
        source_providers |= infer_source_providers_from_codex(args.codex_dir, target)
        excluded_providers |= RESERVED_CODEX_MODEL_PROVIDERS
        excluded_providers.add(target)

    if args.apply and not args.yes:
        die("--apply requires --yes")

    if args.kill_running_codex and not args.apply:
        die("--kill-running-codex only makes sense with --apply")
    if args.kill_running_codex and args.allow_running_codex:
        die("--kill-running-codex conflicts with --allow-running-codex")

    running = running_codex_processes()
    if running and args.apply and args.kill_running_codex:
        log("Terminating running Codex processes before migration:")
        for proc in running:
            log(f"  {proc.display()}")
        survivors = terminate_processes(running)
        if survivors:
            for proc in survivors:
                log(f"  still running: {proc.display()}")
            die("failed to terminate all running Codex processes", code=2)
        running = []

    if running and args.apply and not args.allow_running_codex:
        log("Codex appears to be running:")
        for proc in running:
            log(f"  {proc.display()}")
        die(
            "close running Codex processes before --apply, or pass --kill-running-codex from an external shell",
            code=2,
        )

    backup_root: Path | None = None
    if args.apply:
        backup_root = ensure_backup_root(args)
        log(f"Backup root: {backup_root}")

    log(f"Mode: {'apply' if args.apply else 'dry-run'}")
    log(f"Target bucket: {target}")
    if source_providers:
        source_label = "explicit/inferred"
        if args.source_provider:
            source_label = "explicit"
        log(f"Source providers ({source_label}): {', '.join(sorted(source_providers))}")
    else:
        suffix = f"; excluded: {', '.join(sorted(excluded_providers))}" if excluded_providers else ""
        if args.all_non_target_providers:
            log(f"Source providers: all non-empty non-target providers{suffix}")
        else:
            log(f"Source providers: none inferred{suffix}")

    if not args.skip_live_config:
        info = normalize_live_config(
            args.codex_dir,
            target,
            source_providers,
            excluded_providers,
            args.all_non_target_providers,
            args.apply,
            backup_root,
        )
        log("")
        log("Live Codex config:")
        log(f"  path: {args.codex_dir / 'config.toml'}")
        log(f"  active model_provider: {info.active_provider}")
        log(f"  model_provider tables: {info.provider_ids}")
        log(f"  profile model_provider refs: {info.profile_providers}")
        log(f"  source table copied to {target}: {info.source_provider}")
        log(f"  {'changed' if info.changed else 'already ok / no change'}")

    if not args.skip_history:
        log("")
        jsonl_plan = scan_jsonl_history(
            args.codex_dir,
            target,
            source_providers,
            excluded_providers,
            args.all_non_target_providers,
        )
        log("Codex JSONL history:")
        log(f"  files scanned: {jsonl_plan.files_scanned}")
        log(f"  session_meta lines: {jsonl_plan.session_meta_lines}")
        log(f"  files to change: {jsonl_plan.files_to_change}")
        log(f"  lines to change: {jsonl_plan.lines_to_change}")
        print_counter("  current providers", jsonl_plan.provider_counts)
        print_counter("  providers to migrate", jsonl_plan.migrate_counts)
        if args.apply and jsonl_plan.lines_to_change:
            assert backup_root is not None
            files, lines = rewrite_jsonl_history(
                args.codex_dir,
                target,
                source_providers,
                excluded_providers,
                args.all_non_target_providers,
                backup_root,
            )
            log(f"  applied: rewrote {lines} lines in {files} files")

        state_db = args.codex_dir / "state_5.sqlite"
        sqlite_plan = scan_state_db(
            state_db,
            target,
            source_providers,
            excluded_providers,
            args.all_non_target_providers,
        )
        log("")
        log("Codex state DB:")
        log(f"  path: {state_db}")
        log(f"  exists: {sqlite_plan.exists}")
        log(f"  rows total: {sqlite_plan.total_rows}")
        log(f"  rows to change: {sqlite_plan.rows_to_change}")
        print_counter("  current providers", sqlite_plan.provider_counts)
        print_counter("  providers to migrate", sqlite_plan.migrate_counts)
        if args.apply and sqlite_plan.rows_to_change:
            assert backup_root is not None
            rows = migrate_state_db(
                state_db,
                target,
                source_providers,
                excluded_providers,
                args.all_non_target_providers,
                backup_root,
            )
            log(f"  applied: updated {rows} rows")

    if not args.skip_cc_switch:
        log("")
        plans = scan_cc_switch_templates(
            args.cc_switch_db,
            target,
            args.include_official_provider_templates,
            args.all_non_target_providers,
        )
        log("cc-switch Codex provider templates:")
        log(f"  db: {args.cc_switch_db}")
        log(f"  providers scanned: {len(plans)}")
        for plan in plans:
            status = "change" if plan.will_change else "ok"
            detail = plan.reason or f"active={plan.active_provider}, tables={plan.provider_ids}, source={plan.source_provider}"
            log(f"  {status}: {plan.provider_id} ({detail})")
        if args.apply and any(plan.will_change for plan in plans):
            assert backup_root is not None
            changed = migrate_cc_switch_templates(
                args.cc_switch_db,
                target,
                args.include_official_provider_templates,
                args.all_non_target_providers,
                backup_root,
            )
            log(f"  applied: updated {changed} provider templates")

    if args.apply:
        log("")
        log("Apply complete. Start a new Codex process before checking the UI; existing sessions keep old in-memory config.")
    else:
        log("")
        log("Dry-run only. Re-run with --apply --yes after closing Codex to write changes.")


if __name__ == "__main__":
    main()

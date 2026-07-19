#!/usr/bin/env python3
"""Configure native Win11 Codex App for ChatGPT subscription usage.

Win11 Codex App should use the stable ``custom`` history bucket while routing
requests through the official ChatGPT/Codex backend, not relay providers such as
dragtokens/subrouter.  This keeps resume history unified without spending from
the old relay billing path.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROVIDER = "custom"
DEFAULT_BASE_URL = "https://chatgpt.com/backend-api/codex"


@dataclass
class CcSwitchResult:
    path: Path
    status: str
    current_before: list[str]
    current_after: list[str]


def split_key(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def is_table(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")


def quote(value: str) -> str:
    return json.dumps(value)


def compact_blank_lines(lines: list[str]) -> list[str]:
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
    return out


def remove_table(lines: list[str], table: str) -> list[str]:
    out: list[str] = []
    i = 0
    header = f"[{table}]"
    while i < len(lines):
        if lines[i].strip() == header:
            i += 1
            while i < len(lines) and not is_table(lines[i]):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def patch_features(lines: list[str], values: dict[str, str]) -> list[str]:
    features_idx = next((i for i, line in enumerate(lines) if line.strip() == "[features]"), None)
    managed = set(values) | {"codex_hooks", "remote_connections", "service_tier"}

    if features_idx is None:
        insert_at = next((i for i, line in enumerate(lines) if is_table(line)), len(lines))
        block = ["[features]", *[f"{key} = {value}" for key, value in values.items()], ""]
        return lines[:insert_at] + block + lines[insert_at:]

    out = lines[: features_idx + 1]
    seen: set[str] = set()
    i = features_idx + 1
    while i < len(lines) and not is_table(lines[i]):
        key = split_key(lines[i])
        if key in managed:
            if key in values and key not in seen:
                out.append(f"{key} = {values[key]}")
                seen.add(key)
            i += 1
            continue
        out.append(lines[i])
        i += 1

    for key, value in values.items():
        if key not in seen:
            out.append(f"{key} = {value}")
    if i < len(lines) and out and out[-1].strip():
        out.append("")
    out.extend(lines[i:])
    return out


def patch_config(
    codex_home: Path,
    provider_id: str,
    base_url: str,
    model: str,
    reasoning_effort: str,
    service_tier: str,
    stream_idle_timeout_ms: int,
    stream_max_retries: int,
    approval_policy: str,
    sandbox_mode: str,
    approvals_reviewer: str,
) -> bool:
    config = codex_home / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    original = config.read_text(encoding="utf-8") if config.exists() else ""
    lines = original.splitlines()

    first_table = next((i for i, line in enumerate(lines) if is_table(line)), len(lines))
    managed_top = {
        "approval_policy": quote(approval_policy),
        "sandbox_mode": quote(sandbox_mode),
        "approvals_reviewer": quote(approvals_reviewer),
        "model": quote(model),
        "model_reasoning_effort": quote(reasoning_effort),
        "service_tier": quote(service_tier),
        "stream_idle_timeout_ms": str(stream_idle_timeout_ms),
        "stream_max_retries": str(stream_max_retries),
        "model_provider": quote(provider_id),
    }

    preamble = []
    for line in lines[:first_table]:
        key = split_key(line)
        if key in managed_top:
            continue
        preamble.append(line)
    if preamble and preamble[-1].strip():
        preamble.append("")
    preamble.extend(f"{key} = {value}" for key, value in managed_top.items())

    rest = remove_table(lines[first_table:], f"model_providers.{provider_id}")
    rest = patch_features(
        rest,
        {
            "fast_mode": "true",
            "hooks": "true",
            "memories": "true",
            "goals": "true",
            "terminal_resize_reflow": "true",
            "remote_control": "true",
        },
    )

    provider_block = [
        f"[model_providers.{provider_id}]",
        quote_assignment("name", "OpenAI ChatGPT subscription custom bucket"),
        quote_assignment("base_url", base_url),
        "requires_openai_auth = true",
        "supports_websockets = true",
        f"stream_idle_timeout_ms = {stream_idle_timeout_ms}",
        f"stream_max_retries = {stream_max_retries}",
    ]

    new_lines = compact_blank_lines(preamble + [""] + rest)
    if new_lines and new_lines[-1].strip():
        new_lines.append("")
    new_lines.extend(provider_block)
    new_text = "\n".join(compact_blank_lines(new_lines)).rstrip() + "\n"

    if new_text != original:
        backup = config.with_name(config.name + ".win11-subscription-backup")
        if config.exists() and not backup.exists():
            backup.write_text(original, encoding="utf-8")
        config.write_text(new_text, encoding="utf-8")
        return True
    return False


def quote_assignment(key: str, value: str) -> str:
    return f"{key} = {quote(value)}"


def default_codex_home() -> Path:
    if os.environ.get("CODEX_HOME"):
        return Path(os.environ["CODEX_HOME"]).expanduser()
    if os.environ.get("USERPROFILE"):
        return Path(os.environ["USERPROFILE"]) / ".codex"
    return Path.home() / ".codex"


def default_cc_switch_db() -> Path:
    if os.environ.get("CC_SWITCH_DB_PATH"):
        return Path(os.environ["CC_SWITCH_DB_PATH"]).expanduser()
    if os.environ.get("USERPROFILE"):
        return Path(os.environ["USERPROFILE"]) / ".cc-switch" / "cc-switch.db"
    return Path.home() / ".cc-switch" / "cc-switch.db"


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def current_codex_providers(conn: sqlite3.Connection) -> list[str]:
    if not table_columns(conn, "providers"):
        return []
    return [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM providers WHERE app_type='codex' AND is_current=1 ORDER BY name"
        )
    ]


def enforce_cc_switch_official(db_path: Path) -> CcSwitchResult:
    if not db_path.exists():
        return CcSwitchResult(db_path, "skipped: cc-switch DB missing", [], [])

    conn = sqlite3.connect(db_path)
    try:
        columns = table_columns(conn, "providers")
        if not {"id", "app_type", "name", "category", "is_current"}.issubset(columns):
            return CcSwitchResult(db_path, "skipped: unsupported providers schema", [], [])

        before = current_codex_providers(conn)
        rows = conn.execute(
            """
            SELECT id, name, category
            FROM providers
            WHERE app_type='codex'
            ORDER BY
              CASE WHEN category='official' THEN 0 ELSE 1 END,
              CASE WHEN lower(name) LIKE '%official%' THEN 0 ELSE 1 END,
              name
            """
        ).fetchall()
        official = [
            row
            for row in rows
            if str(row[2] or "").lower() == "official"
            or re.search(r"\bofficial\b", str(row[1] or ""), re.I)
        ]
        if not official:
            return CcSwitchResult(db_path, "warning: no official Codex provider found", before, before)

        provider_id = official[0][0]
        has_updated_at = "updated_at" in columns
        conn.execute("UPDATE providers SET is_current=0 WHERE app_type='codex'")
        if has_updated_at:
            conn.execute(
                "UPDATE providers SET is_current=1, updated_at=? WHERE app_type='codex' AND id=?",
                (int(time.time() * 1000), provider_id),
            )
        else:
            conn.execute(
                "UPDATE providers SET is_current=1 WHERE app_type='codex' AND id=?",
                (provider_id,),
            )
        conn.commit()
        after = current_codex_providers(conn)
        status = "updated" if before != after else "already current"
        return CcSwitchResult(db_path, status, before, after)
    finally:
        conn.close()


def auth_summary(codex_home: Path) -> str:
    auth_path = codex_home / "auth.json"
    if not auth_path.exists():
        return "auth.json missing"
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception:
        return "auth.json unreadable"
    mode = data.get("auth_mode")
    has_tokens = isinstance(data.get("tokens"), dict)
    has_api_key = bool(data.get("OPENAI_API_KEY"))
    return f"auth_mode={mode!r}, tokens={has_tokens}, api_key={has_api_key}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure native Win11 Codex App for subscription-backed custom bucket usage."
    )
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
    parser.add_argument("--cc-switch-db", type=Path, default=default_cc_switch_db())
    parser.add_argument("--provider-id", default=os.environ.get("CODEX_MODEL_PROVIDER_ID", DEFAULT_PROVIDER))
    parser.add_argument("--base-url", default=os.environ.get("CODEX_SUBSCRIPTION_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.environ.get("CODEX_MODEL", "gpt-5.5"))
    parser.add_argument("--model-reasoning-effort", default=os.environ.get("CODEX_MODEL_REASONING_EFFORT", "high"))
    parser.add_argument("--service-tier", default=os.environ.get("CODEX_SERVICE_TIER", "priority"))
    parser.add_argument(
        "--stream-idle-timeout-ms",
        type=int,
        default=int(os.environ.get("CODEX_STREAM_IDLE_TIMEOUT_MS", "1800000")),
    )
    parser.add_argument(
        "--stream-max-retries",
        type=int,
        default=int(os.environ.get("CODEX_STREAM_MAX_RETRIES", "20")),
    )
    parser.add_argument("--approval-policy", default=os.environ.get("CODEX_APPROVAL_POLICY", "on-request"))
    parser.add_argument("--sandbox-mode", default=os.environ.get("CODEX_SANDBOX_MODE", "workspace-write"))
    parser.add_argument("--approvals-reviewer", default=os.environ.get("CODEX_APPROVALS_REVIEWER", "guardian_subagent"))
    parser.add_argument(
        "--skip-cc-switch-official",
        action="store_true",
        help="Do not force cc-switch Codex current provider to the official/subscription provider.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.provider_id):
        raise SystemExit(f"invalid provider id: {args.provider_id}")
    if args.stream_idle_timeout_ms <= 0:
        raise SystemExit("--stream-idle-timeout-ms must be positive")
    if args.stream_max_retries <= 0:
        raise SystemExit("--stream-max-retries must be positive")

    codex_home = args.codex_home.expanduser()
    changed = patch_config(
        codex_home=codex_home,
        provider_id=args.provider_id,
        base_url=args.base_url,
        model=args.model,
        reasoning_effort=args.model_reasoning_effort,
        service_tier=args.service_tier,
        stream_idle_timeout_ms=args.stream_idle_timeout_ms,
        stream_max_retries=args.stream_max_retries,
        approval_policy=args.approval_policy,
        sandbox_mode=args.sandbox_mode,
        approvals_reviewer=args.approvals_reviewer,
    )
    state = "updated" if changed else "already current"
    print(f"Win11 Codex subscription config {state}: {codex_home / 'config.toml'}")
    print(f"  provider bucket: {args.provider_id}")
    print(f"  base_url: {args.base_url}")
    print(f"  {auth_summary(codex_home)}")

    if not args.skip_cc_switch_official:
        result = enforce_cc_switch_official(args.cc_switch_db.expanduser())
        print(f"cc-switch Codex official provider: {result.status}: {result.path}")
        print(f"  current before: {result.current_before or 'none'}")
        print(f"  current after: {result.current_after or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

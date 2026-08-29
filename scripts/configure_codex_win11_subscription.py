#!/usr/bin/env python3
"""Configure native Win11 Codex App for the custom Codex bearer-token mode.

Win11 Codex App should use the stable ``custom`` history bucket while routing
requests through the operator-managed Codex backend.  This path is distinct
from Linux/WSL API-key providers: auth.json keeps a ChatGPT token placeholder,
OPENAI_API_KEY stays null, and the live credential is stored as
experimental_bearer_token in config.toml and cc-switch's Codex provider.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from codex_target_guard import GateFailure, validate_write_target


DEFAULT_PROVIDER = "custom"
DEFAULT_BASE_URL = "http://15.204.46.107:8080"
DEFAULT_BEARER_TOKEN_FILE = "win11-custom-bearer-token"
PLACEHOLDER_TOKENS = {
    "id_token": "placeholder",
    "access_token": "placeholder",
    "refresh_token": "placeholder",
    "account_id": "placeholder",
}


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
    bearer_token: str,
    model: str,
    reasoning_effort: str,
    service_tier: str,
    stream_idle_timeout_ms: int,
    stream_max_retries: int,
    model_context_window: int,
    model_auto_compact_token_limit: int,
    model_auto_compact_token_limit_scope: str,
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
        "model_provider": quote(provider_id),
        "experimental_bearer_token": quote(bearer_token),
        "model_context_window": str(model_context_window),
        "model_auto_compact_token_limit": str(model_auto_compact_token_limit),
        "model_auto_compact_token_limit_scope": quote(model_auto_compact_token_limit_scope),
    }
    # Current standalone Codex rejects stream timeout/retry keys at the top
    # level under --strict-config. Keep them provider-scoped and remove stale
    # top-level copies left by older agent-tools releases.
    managed_top_keys = set(managed_top) | {
        "stream_idle_timeout_ms",
        "stream_max_retries",
    }

    preamble = []
    for line in lines[:first_table]:
        key = split_key(line)
        if key in managed_top_keys:
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
        'wire_api = "responses"',
        quote_assignment("experimental_bearer_token", bearer_token),
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


def patch_auth(codex_home: Path) -> bool:
    auth_path = codex_home / "auth.json"
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    original = auth_path.read_text(encoding="utf-8") if auth_path.exists() else ""
    data = {}
    if original.strip():
        try:
            data = json.loads(original)
        except Exception:
            data = {}
    data["auth_mode"] = "chatgpt"
    data["OPENAI_API_KEY"] = None
    data["tokens"] = data.get("tokens") if isinstance(data.get("tokens"), dict) else PLACEHOLDER_TOKENS.copy()
    for key, value in PLACEHOLDER_TOKENS.items():
        data["tokens"].setdefault(key, value)
    new_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if new_text != original:
        backup = auth_path.with_name(auth_path.name + ".win11-bearer-mode-backup")
        if auth_path.exists() and not backup.exists():
            backup.write_text(original, encoding="utf-8")
        auth_path.write_text(new_text, encoding="utf-8")
        return True
    return False


def quote_assignment(key: str, value: str) -> str:
    return f"{key} = {quote(value)}"


def bearer_token_from_config(codex_home: Path) -> str | None:
    config_path = codex_home / "config.toml"
    if not config_path.exists():
        return None
    text = config_path.read_text(encoding="utf-8")
    match = re.search(r'(?m)^experimental_bearer_token\s*=\s*["\']([^"\']+)["\']', text)
    return match.group(1) if match else None


def bearer_token_from_cc_switch(db_path: Path) -> str | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        columns = table_columns(conn, "providers")
        if not {"app_type", "is_current", "settings_config"}.issubset(columns):
            return None
        rows = conn.execute(
            """
            SELECT settings_config
            FROM providers
            WHERE app_type='codex'
            ORDER BY is_current DESC
            """
        ).fetchall()
        for (raw,) in rows:
            try:
                settings = json.loads(raw or "{}")
            except Exception:
                continue
            config = str(settings.get("config") or "")
            match = re.search(r'(?m)^experimental_bearer_token\s*=\s*["\']([^"\']+)["\']', config)
            if match:
                return match.group(1)
    finally:
        conn.close()
    return None


def resolve_bearer_token(codex_home: Path, cc_switch_db: Path, arg_value: str | None) -> str:
    candidates = [
        arg_value,
        os.environ.get("CODEX_EXPERIMENTAL_BEARER_TOKEN"),
        bearer_token_from_config(codex_home),
        bearer_token_from_cc_switch(cc_switch_db),
    ]
    token_file = codex_home / DEFAULT_BEARER_TOKEN_FILE
    if token_file.exists():
        candidates.append(token_file.read_text(encoding="utf-8").strip())
    for candidate in candidates:
        if candidate:
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(candidate.strip() + "\n", encoding="utf-8")
            try:
                token_file.chmod(0o600)
            except OSError:
                pass
            return candidate.strip()
    raise SystemExit(
        "missing Win11 bearer token; set CODEX_EXPERIMENTAL_BEARER_TOKEN once "
        f"or write it to {token_file}"
    )


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


def validate_win11_target_paths(codex_home: Path, cc_switch_db: Path) -> None:
    """Require native Win11 before this bearer-token helper can write."""

    try:
        validate_write_target(
            codex_home.expanduser(),
            cc_switch_db.expanduser(),
            requested_platform="win11",
        )
    except GateFailure as exc:
        print(f"CODEX_TARGET_GUARD=RED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


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


def cc_switch_provider_config(
    provider_id: str,
    name: str,
    base_url: str,
    bearer_token: str,
    model_context_window: int,
    model_auto_compact_token_limit: int,
    model_auto_compact_token_limit_scope: str,
) -> str:
    display_name = name or provider_id
    return "\n".join(
        [
            'model_provider = "custom"',
            f"model_context_window = {model_context_window}",
            f"model_auto_compact_token_limit = {model_auto_compact_token_limit}",
            quote_assignment("model_auto_compact_token_limit_scope", model_auto_compact_token_limit_scope),
            "",
            "[model_providers.custom]",
            quote_assignment("name", display_name),
            quote_assignment("base_url", base_url),
            "requires_openai_auth = true",
            "supports_websockets = true",
            "stream_idle_timeout_ms = 1800000",
            "stream_max_retries = 20",
            'wire_api = "responses"',
            quote_assignment("experimental_bearer_token", bearer_token),
            "",
        ]
    )


def enforce_cc_switch_custom_bearer(
    db_path: Path,
    provider_id: str,
    base_url: str,
    bearer_token: str,
    model_context_window: int,
    model_auto_compact_token_limit: int,
    model_auto_compact_token_limit_scope: str,
) -> CcSwitchResult:
    if not db_path.exists():
        return CcSwitchResult(db_path, "skipped: cc-switch DB missing", [], [])

    conn = sqlite3.connect(str(db_path))
    try:
        columns = table_columns(conn, "providers")
        if not {"id", "app_type", "name", "category", "is_current", "settings_config"}.issubset(columns):
            return CcSwitchResult(db_path, "skipped: unsupported providers schema", [], [])

        before = current_codex_providers(conn)
        row = conn.execute(
            "SELECT name FROM providers WHERE app_type='codex' AND id=?",
            (provider_id,),
        ).fetchone()
        name = str(row[0]) if row else "dragtokens"
        settings = {
            "auth": {
                "auth_mode": "chatgpt",
                "OPENAI_API_KEY": None,
                "tokens": PLACEHOLDER_TOKENS.copy(),
            },
            "config": cc_switch_provider_config(
                provider_id,
                name,
                base_url,
                bearer_token,
                model_context_window,
                model_auto_compact_token_limit,
                model_auto_compact_token_limit_scope,
            ),
        }
        has_updated_at = "updated_at" in columns
        if row:
            if has_updated_at:
                conn.execute(
                    """
                    UPDATE providers
                    SET name=?, category='custom', settings_config=?, is_current=1, updated_at=?
                    WHERE app_type='codex' AND id=?
                    """,
                    (name, json.dumps(settings, ensure_ascii=False), int(time.time() * 1000), provider_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE providers
                    SET name=?, category='custom', settings_config=?, is_current=1
                    WHERE app_type='codex' AND id=?
                    """,
                    (name, json.dumps(settings, ensure_ascii=False), provider_id),
                )
        else:
            cols = table_columns(conn, "providers")
            values = {
                "id": provider_id,
                "app_type": "codex",
                "name": name,
                "settings_config": json.dumps(settings, ensure_ascii=False),
                "website_url": "",
                "category": "custom",
                "created_at": int(time.time() * 1000),
                "sort_index": 0,
                "notes": None,
                "icon": "openai",
                "icon_color": "#00A67E",
                "meta": "{}",
                "is_current": 1,
                "in_failover_queue": 0,
                "cost_multiplier": "1.0",
                "limit_daily_usd": None,
                "limit_monthly_usd": None,
                "provider_type": None,
            }
            insert_cols = [col for col in values if col in cols]
            conn.execute(
                f"INSERT INTO providers ({','.join(insert_cols)}) VALUES ({','.join('?' for _ in insert_cols)})",
                [values[col] for col in insert_cols],
            )
        conn.execute("UPDATE providers SET is_current=0 WHERE app_type='codex' AND id<>?", (provider_id,))
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
        description="Configure native Win11 Codex App for custom bearer-token usage."
    )
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
    parser.add_argument("--cc-switch-db", type=Path, default=default_cc_switch_db())
    parser.add_argument("--provider-id", default=os.environ.get("CODEX_MODEL_PROVIDER_ID", DEFAULT_PROVIDER))
    parser.add_argument("--base-url", default=os.environ.get("CODEX_CUSTOM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--bearer-token", default=None)
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
    parser.add_argument(
        "--model-context-window",
        type=int,
        default=int(os.environ.get("CODEX_MODEL_CONTEXT_WINDOW", "500000")),
    )
    parser.add_argument(
        "--model-auto-compact-token-limit",
        type=int,
        default=int(os.environ.get("CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT", "430000")),
    )
    parser.add_argument(
        "--model-auto-compact-token-limit-scope",
        default=os.environ.get("CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE", "total"),
    )
    parser.add_argument("--approval-policy", default=os.environ.get("CODEX_APPROVAL_POLICY", "on-request"))
    parser.add_argument("--sandbox-mode", default=os.environ.get("CODEX_SANDBOX_MODE", "workspace-write"))
    parser.add_argument("--approvals-reviewer", default=os.environ.get("CODEX_APPROVALS_REVIEWER", "guardian_subagent"))
    parser.add_argument(
        "--skip-cc-switch-custom",
        action="store_true",
        help="Do not force cc-switch Codex current provider to the custom bearer-token provider.",
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
    if args.model_context_window <= 0:
        raise SystemExit("--model-context-window must be positive")
    if not 0 < args.model_auto_compact_token_limit < args.model_context_window:
        raise SystemExit("--model-auto-compact-token-limit must be positive and below the context window")
    if args.model_auto_compact_token_limit_scope not in {"total", "body_after_prefix"}:
        raise SystemExit("--model-auto-compact-token-limit-scope must be total or body_after_prefix")

    codex_home = args.codex_home.expanduser()
    cc_switch_db = args.cc_switch_db.expanduser()
    validate_win11_target_paths(codex_home, cc_switch_db)
    bearer_token = resolve_bearer_token(codex_home, cc_switch_db, args.bearer_token)
    changed = patch_config(
        codex_home=codex_home,
        provider_id=args.provider_id,
        base_url=args.base_url,
        bearer_token=bearer_token,
        model=args.model,
        reasoning_effort=args.model_reasoning_effort,
        service_tier=args.service_tier,
        stream_idle_timeout_ms=args.stream_idle_timeout_ms,
        stream_max_retries=args.stream_max_retries,
        model_context_window=args.model_context_window,
        model_auto_compact_token_limit=args.model_auto_compact_token_limit,
        model_auto_compact_token_limit_scope=args.model_auto_compact_token_limit_scope,
        approval_policy=args.approval_policy,
        sandbox_mode=args.sandbox_mode,
        approvals_reviewer=args.approvals_reviewer,
    )
    auth_changed = patch_auth(codex_home)
    state = "updated" if changed else "already current"
    auth_state = "updated" if auth_changed else "already current"
    print(f"Win11 Codex bearer-token config {state}: {codex_home / 'config.toml'}")
    print(f"  provider bucket: {args.provider_id}")
    print(f"  base_url: {args.base_url}")
    print("  experimental_bearer_token: configured")
    print(f"Win11 Codex auth placeholder {auth_state}: {codex_home / 'auth.json'}")
    print(f"  {auth_summary(codex_home)}")

    if not args.skip_cc_switch_custom:
        result = enforce_cc_switch_custom_bearer(
            cc_switch_db,
            args.provider_id,
            args.base_url,
            bearer_token,
            args.model_context_window,
            args.model_auto_compact_token_limit,
            args.model_auto_compact_token_limit_scope,
        )
        print(f"cc-switch Codex custom provider: {result.status}: {result.path}")
        print(f"  current before: {result.current_before or 'none'}")
        print(f"  current after: {result.current_after or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

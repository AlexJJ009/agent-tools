#!/usr/bin/env python3
"""Enable Codex Fast defaults in App/CLI config files.

This script intentionally edits Codex config only. It does not patch Electron
app.asar bundles because Windows Store and macOS app packages are signed and
version-sensitive.
"""

import argparse
import json
import os
import platform
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from codex_target_guard import GateFailure, validate_write_target

DEFAULT_MODEL_CONTEXT_WINDOW = 500000
DEFAULT_MODEL_AUTO_COMPACT_TOKEN_LIMIT = 430000
DEFAULT_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE = "total"


def split_key(line):
    stripped = line.strip()
    if stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def is_table(line):
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")


def quote_value(value):
    return json.dumps(value)


def compact_blank_lines(lines):
    out = []
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


def patch_config(
    path,
    service_tier,
    fast_mode,
    model_context_window=DEFAULT_MODEL_CONTEXT_WINDOW,
    model_auto_compact_token_limit=DEFAULT_MODEL_AUTO_COMPACT_TOKEN_LIMIT,
    model_auto_compact_token_limit_scope=DEFAULT_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE,
):
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()

    first_table = next((i for i, line in enumerate(lines) if is_table(line)), len(lines))
    managed_top = {
        "service_tier": quote_value(service_tier),
        "model_context_window": str(model_context_window),
        "model_auto_compact_token_limit": str(model_auto_compact_token_limit),
        "model_auto_compact_token_limit_scope": quote_value(model_auto_compact_token_limit_scope),
    }
    preamble = [
        line for line in lines[:first_table] if split_key(line) not in set(managed_top)
    ]

    insert_at = len(preamble)
    while insert_at > 0 and not preamble[insert_at - 1].strip():
        insert_at -= 1
    preamble = preamble[:insert_at] + [
        f"{key} = {value}" for key, value in managed_top.items()
    ] + preamble[insert_at:]

    out = preamble + lines[first_table:]
    features_idx = None
    for idx, line in enumerate(out):
        if line.strip() == "[features]":
            features_idx = idx
            break

    if features_idx is None:
        if out and out[-1].strip():
            out.append("")
        out.extend(["[features]", f"fast_mode = {fast_mode}"])
    else:
        idx = features_idx + 1
        found = False
        while idx < len(out) and not is_table(out[idx]):
            if split_key(out[idx]) in {"fast_mode", "service_tier"}:
                if split_key(out[idx]) == "fast_mode":
                    out[idx] = f"fast_mode = {fast_mode}"
                    found = True
                else:
                    out.pop(idx)
                    continue
            idx += 1
        if not found:
            out.insert(features_idx + 1, f"fast_mode = {fast_mode}")

    new_text = "\n".join(compact_blank_lines(out)).rstrip() + "\n"
    if new_text != text:
        backup = path.with_name(path.name + ".fastmode-app-backup")
        if path.exists() and not backup.exists():
            backup.write_text(text, encoding="utf-8")
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def default_codex_home():
    if os.environ.get("CODEX_HOME"):
        return Path(os.environ["CODEX_HOME"]).expanduser()
    if platform.system() == "Windows":
        return Path(os.environ["USERPROFILE"]) / ".codex"
    return Path.home() / ".codex"


def detect_wsl_windows_codex_home():
    user_profile = os.environ.get("USERPROFILE")
    if user_profile and user_profile.startswith("/mnt/"):
        candidate = Path(user_profile) / ".codex"
        if candidate.exists():
            return candidate

    users = Path("/mnt/c/Users")
    if not users.exists():
        return None

    for candidate in sorted(users.glob("*/.codex")):
        if (candidate / "config.toml").exists() or (candidate / "auth.json").exists():
            return candidate
    return None


def auth_summary(codex_home):
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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Enable Codex Fast defaults for CLI/App config.toml files."
    )
    parser.add_argument(
        "--codex-home",
        action="append",
        type=Path,
        default=[],
        help="Codex home to patch. Repeatable. Defaults to CODEX_HOME or ~/.codex.",
    )
    parser.add_argument(
        "--include-wsl-windows",
        action="store_true",
        help="Legacy option; a WSL process now rejects mounted Windows profiles.",
    )
    parser.add_argument(
        "--service-tier",
        default=os.environ.get("CODEX_SERVICE_TIER", "priority"),
        choices=["auto", "default", "fast", "priority"],
    )
    parser.add_argument(
        "--fast-mode",
        default=os.environ.get("CODEX_FEATURE_FAST_MODE", "true"),
        choices=["true", "false"],
    )
    parser.add_argument(
        "--model-context-window",
        type=int,
        default=int(os.environ.get("CODEX_MODEL_CONTEXT_WINDOW", str(DEFAULT_MODEL_CONTEXT_WINDOW))),
    )
    parser.add_argument(
        "--model-auto-compact-token-limit",
        type=int,
        default=int(
            os.environ.get(
                "CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT",
                str(DEFAULT_MODEL_AUTO_COMPACT_TOKEN_LIMIT),
            )
        ),
    )
    parser.add_argument(
        "--model-auto-compact-token-limit-scope",
        default=os.environ.get(
            "CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE",
            DEFAULT_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE,
        ),
        choices=["total", "body_after_prefix"],
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.model_context_window <= 0:
        print("CODEX_TARGET_GUARD=RED: --model-context-window must be positive", file=sys.stderr)
        return 2
    if args.model_auto_compact_token_limit <= 0:
        print("CODEX_TARGET_GUARD=RED: --model-auto-compact-token-limit must be positive", file=sys.stderr)
        return 2
    if args.model_auto_compact_token_limit >= args.model_context_window:
        print(
            "CODEX_TARGET_GUARD=RED: --model-auto-compact-token-limit must be lower than --model-context-window",
            file=sys.stderr,
        )
        return 2
    homes = list(args.codex_home) if args.codex_home else [default_codex_home()]

    if args.include_wsl_windows:
        win_home = detect_wsl_windows_codex_home()
        if win_home is not None and win_home not in homes:
            homes.append(win_home)

    seen = set()
    targets = []
    for home in homes:
        home = home.expanduser()
        try:
            home = home.resolve()
        except FileNotFoundError:
            home = home.absolute()
        if home in seen:
            continue
        seen.add(home)
        try:
            validate_write_target(home)
        except GateFailure as exc:
            print(f"CODEX_TARGET_GUARD=RED: {exc}", file=sys.stderr)
            return 2
        targets.append(home)

    # Validate every requested target before touching any one of them.  This
    # keeps a mixed WSL/Windows invocation from partially updating the Unix
    # profile before rejecting the mounted Windows profile.
    for home in targets:
        config = home / "config.toml"
        changed = patch_config(
            config,
            args.service_tier,
            args.fast_mode,
            args.model_context_window,
            args.model_auto_compact_token_limit,
            args.model_auto_compact_token_limit_scope,
        )
        state = "updated" if changed else "already current"
        print(f"Codex App/CLI Fast config {state}: {config}")
        print(f"  {auth_summary(home)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

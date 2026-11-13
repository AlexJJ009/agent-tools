#!/usr/bin/env bash
# cc-switch: update the CLI, normalize its Codex provider templates, and apply
# the current Codex provider to config.toml. Run it before setup/codex.sh.
set -euo pipefail

SETUP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SETUP_DIR/lib.sh"

INSTALL_CC_SWITCH_CLI_UPDATE="${INSTALL_CC_SWITCH_CLI_UPDATE:-1}"
INSTALL_CC_SWITCH_TEMPLATES=1
INSTALL_CC_SWITCH_SYNC=1
CC_SWITCH_UPDATE_PROXY_MODE="${CC_SWITCH_UPDATE_PROXY_MODE:-auto}"
CC_SWITCH_UPDATE_CONNECT_TIMEOUT="${CC_SWITCH_UPDATE_CONNECT_TIMEOUT:-10}"
CC_SWITCH_UPDATE_MAX_TIME="${CC_SWITCH_UPDATE_MAX_TIME:-180}"
CC_SWITCH_UPDATE_RETRY="${CC_SWITCH_UPDATE_RETRY:-3}"
CC_SWITCH_UPDATE_RETRY_DELAY="${CC_SWITCH_UPDATE_RETRY_DELAY:-2}"
CC_SWITCH_UPDATE_SPEED_LIMIT="${CC_SWITCH_UPDATE_SPEED_LIMIT:-10240}"
CC_SWITCH_UPDATE_SPEED_TIME="${CC_SWITCH_UPDATE_SPEED_TIME:-30}"
CC_SWITCH_UPDATE_PROXY_TEST_URL="${CC_SWITCH_UPDATE_PROXY_TEST_URL:-https://github.com/saladday/cc-switch-cli/releases/latest/download/install.sh}"
CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS=""

cc_switch_version() {
  local output

  if ! command -v cc-switch >/dev/null 2>&1; then
    return 1
  fi

  if output="$(cc-switch --version 2>&1)"; then
    printf '%s\n' "$output" | head -n 1
    return 0
  fi

  return 2
}

cleanup_cc_switch_update_tmp() {
  if [[ -n "${CC_SWITCH_UPDATE_TMP_DIR:-}" && -d "$CC_SWITCH_UPDATE_TMP_DIR" ]]; then
    rm -rf "$CC_SWITCH_UPDATE_TMP_DIR"
  fi
}

probe_cc_switch_update_proxy_url() {
  local proxy_url="$1"
  local status

  status="$(
    curl -sS -o /dev/null -w '%{http_code}' \
      --connect-timeout "$CODEX_PROXY_CONNECT_TIMEOUT" \
      --max-time "$CODEX_PROXY_MAX_TIME" \
      -x "$proxy_url" \
      "$CC_SWITCH_UPDATE_PROXY_TEST_URL" 2>/dev/null || true
  )"

  case "$status" in
    200|301|302)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

select_cc_switch_update_proxy_url() {
  local port proxy_url

  if [[ -n "${CODEX_PROXY_URL:-}" ]]; then
    if [[ "${CODEX_PROXY_SKIP_CHECK:-0}" == "1" ]] || probe_cc_switch_update_proxy_url "$CODEX_PROXY_URL"; then
      printf '%s\n' "$CODEX_PROXY_URL"
      return 0
    fi
    echo "cc-switch update proxy check failed for CODEX_PROXY_URL=$CODEX_PROXY_URL" >&2
    return 1
  fi

  for port in $CODEX_PROXY_PORTS; do
    proxy_url="http://${CODEX_PROXY_HOST}:${port}"
    if probe_cc_switch_update_proxy_url "$proxy_url"; then
      printf '%s\n' "$proxy_url"
      return 0
    fi
  done

  return 1
}

update_cc_switch_cli() {
  local tmp_dir installer proxy_url curl_args=() curl_config_lines=()

  if [[ "$INSTALL_CC_SWITCH_CLI_UPDATE" -eq 0 ]]; then
    echo "cc-switch update skipped (--no-update)."
    return
  fi

  if ! command -v curl >/dev/null 2>&1; then
    echo "cc-switch update skipped: curl is not on PATH." >&2
    return 1
  fi

  echo "Updating cc-switch-cli from latest GitHub release..."
  tmp_dir="$(mktemp -d)"
  CC_SWITCH_UPDATE_TMP_DIR="$tmp_dir"
  installer="$tmp_dir/install.sh"
  trap cleanup_cc_switch_update_tmp RETURN

  curl_args=(
    -fsSL
    --connect-timeout "$CC_SWITCH_UPDATE_CONNECT_TIMEOUT"
    --max-time "$CC_SWITCH_UPDATE_MAX_TIME"
    --retry "$CC_SWITCH_UPDATE_RETRY"
    --retry-delay "$CC_SWITCH_UPDATE_RETRY_DELAY"
  )
  curl_config_lines=(
    "connect-timeout = $CC_SWITCH_UPDATE_CONNECT_TIMEOUT"
    "max-time = $CC_SWITCH_UPDATE_MAX_TIME"
    "retry = $CC_SWITCH_UPDATE_RETRY"
    "retry-delay = $CC_SWITCH_UPDATE_RETRY_DELAY"
    "speed-limit = $CC_SWITCH_UPDATE_SPEED_LIMIT"
    "speed-time = $CC_SWITCH_UPDATE_SPEED_TIME"
  )
  if curl --help all 2>/dev/null | grep -q -- '--retry-all-errors'; then
    curl_args+=(--retry-all-errors)
    curl_config_lines+=(retry-all-errors)
  else
    echo "cc-switch update: curl does not support --retry-all-errors; using compatible retry options."
  fi
  printf '%s\n' "${curl_config_lines[@]}" >"$tmp_dir/.curlrc"

  case "$CC_SWITCH_UPDATE_PROXY_MODE" in
    auto|always|never)
      ;;
    *)
      echo "invalid cc-switch update proxy mode: $CC_SWITCH_UPDATE_PROXY_MODE" >&2
      exit 2
      ;;
  esac

  if [[ "$CC_SWITCH_UPDATE_PROXY_MODE" != "never" ]]; then
    if proxy_url="$(select_cc_switch_update_proxy_url 2>/dev/null)"; then
      echo "cc-switch update using proxy: $proxy_url"
    elif [[ "$CC_SWITCH_UPDATE_PROXY_MODE" == "always" ]]; then
      echo "cc-switch update proxy requested, but no reachable proxy was found." >&2
      echo "Set CODEX_PROXY_URL or CODEX_PROXY_HOST/CODEX_PROXY_PORTS for this host." >&2
      exit 1
    else
      proxy_url=""
      echo "cc-switch update using direct GitHub connection."
    fi
  fi

  if [[ -n "${proxy_url:-}" ]]; then
    HTTP_PROXY="$proxy_url" HTTPS_PROXY="$proxy_url" ALL_PROXY="$proxy_url" \
      http_proxy="$proxy_url" https_proxy="$proxy_url" all_proxy="$proxy_url" \
      curl "${curl_args[@]}" -o "$installer" \
      https://github.com/saladday/cc-switch-cli/releases/latest/download/install.sh
    HTTP_PROXY="$proxy_url" HTTPS_PROXY="$proxy_url" ALL_PROXY="$proxy_url" \
      http_proxy="$proxy_url" https_proxy="$proxy_url" all_proxy="$proxy_url" \
      CURL_HOME="$tmp_dir" CC_SWITCH_FORCE="${CC_SWITCH_FORCE:-1}" bash "$installer"
  else
    curl "${curl_args[@]}" -o "$installer" \
      https://github.com/saladday/cc-switch-cli/releases/latest/download/install.sh
    CURL_HOME="$tmp_dir" CC_SWITCH_FORCE="${CC_SWITCH_FORCE:-1}" bash "$installer"
  fi
  cleanup_cc_switch_update_tmp
  CC_SWITCH_UPDATE_TMP_DIR=""
  trap - RETURN
  hash -r 2>/dev/null || true

  if version="$(cc_switch_version)"; then
    echo "cc-switch version: $version"
  else
    echo "cc-switch update completed, but cc-switch is not usable on PATH yet." >&2
  fi
}

normalize_cc_switch_codex_provider_templates() {
  local db_path="${CC_SWITCH_DB_PATH:-$HOME/.cc-switch/cc-switch.db}"

  if [[ ! -f "$db_path" ]]; then
    return
  fi

  select_python_bin
  "$PYTHON_BIN" - "$db_path" "$CODEX_MODEL_PROVIDER_ID" "$CODEX_SERVICE_TIER" "$CODEX_MODEL_CONTEXT_WINDOW" "$CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT" "$CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE" <<'PY'
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

db_path = Path(sys.argv[1]).expanduser()
target = sys.argv[2]
service_tier = sys.argv[3]
context_window = sys.argv[4]
auto_compact_limit = sys.argv[5]
auto_compact_scope = sys.argv[6]
if not target or not re.fullmatch(r"[A-Za-z0-9_.-]+", target):
    raise SystemExit(f"invalid CODEX_MODEL_PROVIDER_ID: {target}")
if service_tier not in {"auto", "default", "fast", "priority"}:
    raise SystemExit(f"invalid CODEX_SERVICE_TIER: {service_tier}")
if not context_window.isdigit() or int(context_window) <= 0:
    raise SystemExit(f"invalid CODEX_MODEL_CONTEXT_WINDOW: {context_window}")
if not auto_compact_limit.isdigit() or int(auto_compact_limit) <= 0:
    raise SystemExit(f"invalid CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT: {auto_compact_limit}")
if int(auto_compact_limit) >= int(context_window):
    raise SystemExit("CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT must be lower than CODEX_MODEL_CONTEXT_WINDOW")
if auto_compact_scope not in {"total", "body_after_prefix"}:
    raise SystemExit(f"invalid CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE: {auto_compact_scope}")

def section_path(line):
    stripped = line.strip()
    if stripped.startswith("[[") or not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    return stripped[1:-1].strip().split(".")

def normalize_config(text):
    lines = text.splitlines()
    first_table = next(
        (i for i, line in enumerate(lines) if section_path(line) is not None),
        len(lines),
    )
    managed_top = {
        "service_tier": f'"{service_tier}"',
        "model_context_window": context_window,
        "model_auto_compact_token_limit": auto_compact_limit,
        "model_auto_compact_token_limit_scope": f'"{auto_compact_scope}"',
    }
    preamble = []
    for line in lines[:first_table]:
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in managed_top:
                continue
        preamble.append(line)
    while preamble and not preamble[-1].strip():
        preamble.pop()
    preamble.extend(f"{key} = {value}" for key, value in managed_top.items())
    if first_table < len(lines):
        preamble.append("")
    lines = preamble + lines[first_table:]
    out = []
    in_model_provider = False
    in_target_provider = False
    inserted_auth = False
    inserted_websockets = False

    def insert_auth():
        nonlocal inserted_auth
        while out and not out[-1].strip():
            out.pop()
        out.append("requires_openai_auth = true")
        inserted_auth = True

    def insert_websockets():
        nonlocal inserted_websockets
        while out and not out[-1].strip():
            out.pop()
        out.append("supports_websockets = true")
        inserted_websockets = True

    def insert_provider_defaults():
        if in_target_provider and not inserted_auth:
            insert_auth()
        if not inserted_websockets:
            insert_websockets()

    for line in lines:
        path_parts = section_path(line)
        if path_parts is not None:
            if in_model_provider:
                insert_provider_defaults()
            in_model_provider = len(path_parts) == 2 and path_parts[0] == "model_providers"
            in_target_provider = in_model_provider and path_parts[1] == target
            inserted_auth = False
            inserted_websockets = False
            out.append(line)
            continue

        if in_model_provider and "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if in_target_provider and key == "env_key":
                continue
            if in_target_provider and key == "requires_openai_auth":
                if not inserted_auth:
                    insert_auth()
                continue
            if key == "supports_websockets":
                if not inserted_websockets:
                    insert_websockets()
                continue

        out.append(line)

    if in_model_provider:
        insert_provider_defaults()

    cleaned = []
    previous_blank = False
    for line in out:
        blank = not line.strip()
        if blank and (previous_blank or not cleaned):
            previous_blank = True
            continue
        cleaned.append(line)
        previous_blank = blank
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned).rstrip() + "\n"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
try:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(providers)")}
    has_updated_at = "updated_at" in columns
    changed = 0
    rows = conn.execute(
        "SELECT id, settings_config FROM providers WHERE app_type='codex' ORDER BY id"
    ).fetchall()
    for row in rows:
        try:
            settings = json.loads(row["settings_config"])
        except Exception:
            continue
        if not isinstance(settings, dict):
            continue
        config_text = settings.get("config")
        if not isinstance(config_text, str) or not config_text.strip():
            continue
        new_config = normalize_config(config_text)
        if new_config == config_text:
            continue
        settings["config"] = new_config
        payload = json.dumps(settings, ensure_ascii=False, separators=(",", ":"))
        if has_updated_at:
            conn.execute(
                "UPDATE providers SET settings_config=?, updated_at=? WHERE app_type='codex' AND id=?",
                (payload, int(time.time() * 1000), row["id"]),
            )
        else:
            conn.execute(
                "UPDATE providers SET settings_config=? WHERE app_type='codex' AND id=?",
                (payload, row["id"]),
            )
        changed += 1
    conn.commit()
    if changed:
        print(f"Normalized cc-switch Codex provider auth in {changed} templates.")
finally:
    conn.close()
PY
}

sync_codex_config_from_cc_switch_current() {
  local output provider_id

  if [[ "${SYNC_CC_SWITCH_CODEX_CURRENT:-1}" == "0" ]]; then
    CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS="skipped: SYNC_CC_SWITCH_CODEX_CURRENT=0"
    echo "Codex config sync from cc-switch current provider skipped."
    return
  fi

  if ! command -v cc-switch >/dev/null 2>&1; then
    CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS="skipped: cc-switch is not on PATH"
    return
  fi

  if ! output="$(cc-switch provider current -a codex 2>/dev/null)"; then
    CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS="skipped: no current cc-switch Codex provider"
    return
  fi

  provider_id="$(
    printf '%s\n' "$output" |
      awk -F: '/^[[:space:]]*ID[[:space:]]*:/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}'
  )"
  if [[ -z "$provider_id" ]]; then
    CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS="skipped: could not parse current provider id"
    return
  fi
  if [[ ! "$provider_id" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "invalid cc-switch Codex provider id: $provider_id" >&2
    return 1
  fi

  echo "Syncing Codex config from cc-switch provider: $provider_id"
  cc-switch provider switch -a codex "$provider_id"
  normalize_codex_provider_auth
  CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS="synced: $provider_id"
}

usage() {
  cat <<'EOF'
Usage: setup/cc-switch.sh [options]

Runs every step below unless skipped.

Options:
  --no-update           Do not update cc-switch-cli from the latest GitHub release.
  --no-templates        Do not normalize the Codex provider templates in the
                        cc-switch database.
  --no-sync             Do not apply the current Codex provider to config.toml
                        (also skipped by SYNC_CC_SWITCH_CODEX_CURRENT=0).
  --update-proxy MODE   Proxy for the release download: auto|always|never.
                        Default: auto.
  --proxy-url URL       Use this proxy, e.g. http://127.0.0.1:7897.
  --proxy-ports LIST    Space-separated proxy ports to probe.
                        Default: "7897 7890 7891 10809 10808 8080".
  -h, --help            Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-update) INSTALL_CC_SWITCH_CLI_UPDATE=0; shift ;;
    --no-templates) INSTALL_CC_SWITCH_TEMPLATES=0; shift ;;
    --no-sync) INSTALL_CC_SWITCH_SYNC=0; shift ;;
    --update-proxy) CC_SWITCH_UPDATE_PROXY_MODE="${2:?--update-proxy needs a value}"; shift 2 ;;
    --proxy-url) CODEX_PROXY_URL="${2:?--proxy-url needs a value}"; shift 2 ;;
    --proxy-ports) CODEX_PROXY_PORTS="${2:?--proxy-ports needs a value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

update_cc_switch_cli
if [[ "$INSTALL_CC_SWITCH_CLI_UPDATE" -eq 1 ]]; then
  if version="$(cc_switch_version)"; then
    echo "cc-switch-cli updated: $version"
  else
    echo "cc-switch-cli update attempted, but cc-switch is not usable on PATH."
  fi
else
  echo "cc-switch-cli not updated (--no-update)."
fi
if [[ "$INSTALL_CC_SWITCH_TEMPLATES" -eq 1 ]]; then
  normalize_cc_switch_codex_provider_templates
fi
if [[ "$INSTALL_CC_SWITCH_SYNC" -eq 1 ]]; then
  sync_codex_config_from_cc_switch_current
  if [[ -n "$CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS" ]]; then
    echo "cc-switch Codex provider sync: $CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS"
  fi
fi

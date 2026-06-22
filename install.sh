#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${AGENT_TOOLS_HOME:-$SOURCE_DIR}"
SCHEDULE="17 * * * *"
MAX_DEPTH="3"
SCOPE="all"
DIRECTION="bidirectional"
PREFER="none"
MODE="symlink"
INSTALL_CRON=1
INSTALL_REGISTRY=1
REGISTRY_INIT_DB=0
INSTALL_CODEX_CONFIG=1
INSTALL_CODEX_HERE=1
INSTALL_GOAL_PLAN=1
INSTALL_CC_SWITCH_CLI_UPDATE="${INSTALL_CC_SWITCH_CLI_UPDATE:-1}"
CC_SWITCH_UPDATE_PROXY_MODE="${CC_SWITCH_UPDATE_PROXY_MODE:-auto}"
CC_SWITCH_UPDATE_CONNECT_TIMEOUT="${CC_SWITCH_UPDATE_CONNECT_TIMEOUT:-10}"
CC_SWITCH_UPDATE_MAX_TIME="${CC_SWITCH_UPDATE_MAX_TIME:-180}"
CC_SWITCH_UPDATE_RETRY="${CC_SWITCH_UPDATE_RETRY:-3}"
CC_SWITCH_UPDATE_RETRY_DELAY="${CC_SWITCH_UPDATE_RETRY_DELAY:-2}"
CC_SWITCH_UPDATE_SPEED_LIMIT="${CC_SWITCH_UPDATE_SPEED_LIMIT:-10240}"
CC_SWITCH_UPDATE_SPEED_TIME="${CC_SWITCH_UPDATE_SPEED_TIME:-30}"
CC_SWITCH_UPDATE_PROXY_TEST_URL="${CC_SWITCH_UPDATE_PROXY_TEST_URL:-https://github.com/saladday/cc-switch-cli/releases/latest/download/install.sh}"
INSTALL_CODEX_PROVIDER_BUCKET_MIGRATION=1
APPLY_CODEX_PROVIDER_BUCKET_MIGRATION="${AGENT_TOOLS_CODEX_PROVIDER_BUCKET_APPLY:-1}"
CODEX_PROVIDER_BUCKET_ALL_NON_TARGET="${AGENT_TOOLS_CODEX_PROVIDER_BUCKET_ALL_NON_TARGET:-1}"
CODEX_PROVIDER_BUCKET_ALLOW_RUNNING="${AGENT_TOOLS_CODEX_PROVIDER_BUCKET_ALLOW_RUNNING:-0}"
CODEX_PROVIDER_BUCKET_KILL_RUNNING="${AGENT_TOOLS_CODEX_PROVIDER_BUCKET_KILL_RUNNING:-1}"
INSTALL_CODEX_PROXY_WRAPPER="${INSTALL_CODEX_PROXY_WRAPPER:-auto}"
INSTALL_CODEX_REMOTE_CONTROL="${INSTALL_CODEX_REMOTE_CONTROL:-1}"
INSTALL_CODEX_APP_FAST_MODE="${INSTALL_CODEX_APP_FAST_MODE:-1}"
INSTALL_CODEX_DESKTOP_CONNECTION_FAST_MODE="${INSTALL_CODEX_DESKTOP_CONNECTION_FAST_MODE:-auto}"
CODEX_DESKTOP_CONNECTION_FAST_MODE_LAUNCH="${CODEX_DESKTOP_CONNECTION_FAST_MODE_LAUNCH:-0}"
CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_SCOPE="${CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_SCOPE:-both}"
CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_NAME="${CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_NAME:-Codex Fast Connections}"
INSTALL_CODEX_SQLITE_LOG_GUARD="${INSTALL_CODEX_SQLITE_LOG_GUARD:-1}"
CODEX_SQLITE_LOG_GUARD_MODE="${CODEX_SQLITE_LOG_GUARD_MODE:-enable}"
CODEX_SQLITE_LOG_GUARD_INCLUDE_WSL_WINDOWS="${CODEX_SQLITE_LOG_GUARD_INCLUDE_WSL_WINDOWS:-auto}"
CODEX_SQLITE_LOG_GUARD_VACUUM="${CODEX_SQLITE_LOG_GUARD_VACUUM:-0}"
INSTALL_CLAUDE_DESKTOP_SSH="${INSTALL_CLAUDE_DESKTOP_SSH:-1}"
CODEX_APP_FAST_MODE_INCLUDE_WSL_WINDOWS="${CODEX_APP_FAST_MODE_INCLUDE_WSL_WINDOWS:-auto}"
CODEX_STREAM_IDLE_TIMEOUT_MS="${CODEX_STREAM_IDLE_TIMEOUT_MS:-1800000}"
CODEX_STREAM_MAX_RETRIES="${CODEX_STREAM_MAX_RETRIES:-20}"
CODEX_MODEL_PROVIDER_ID="${CODEX_MODEL_PROVIDER_ID:-custom}"
CODEX_APPROVAL_POLICY="${CODEX_APPROVAL_POLICY:-on-request}"
CODEX_SANDBOX_MODE="${CODEX_SANDBOX_MODE:-workspace-write}"
CODEX_APPROVALS_REVIEWER="${CODEX_APPROVALS_REVIEWER:-guardian_subagent}"
CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
CODEX_MODEL_REASONING_EFFORT="${CODEX_MODEL_REASONING_EFFORT:-high}"
CODEX_SERVICE_TIER="${CODEX_SERVICE_TIER:-priority}"
CODEX_FEATURE_FAST_MODE="${CODEX_FEATURE_FAST_MODE:-true}"
CODEX_FEATURE_HOOKS="${CODEX_FEATURE_HOOKS:-true}"
CODEX_FEATURE_MEMORIES="${CODEX_FEATURE_MEMORIES:-true}"
CODEX_FEATURE_GOALS="${CODEX_FEATURE_GOALS:-true}"
CODEX_FEATURE_TERMINAL_RESIZE_REFLOW="${CODEX_FEATURE_TERMINAL_RESIZE_REFLOW:-true}"
CODEX_FEATURE_REMOTE_CONTROL="${CODEX_FEATURE_REMOTE_CONTROL:-true}"
CODEX_PROXY_HOST="${CODEX_PROXY_HOST:-127.0.0.1}"
CODEX_PROXY_PORTS="${CODEX_PROXY_PORTS:-7897 7890 7891 10809 10808 8080}"
CODEX_PROXY_TEST_URL="${CODEX_PROXY_TEST_URL:-https://chatgpt.com/backend-api/codex/responses}"
CODEX_PROXY_CONNECT_TIMEOUT="${CODEX_PROXY_CONNECT_TIMEOUT:-2}"
CODEX_PROXY_MAX_TIME="${CODEX_PROXY_MAX_TIME:-6}"
AGENT_CORE_DIR="${AGENT_CORE_HOME:-$HOME/agent-core}"
INSTALL_AGENT_CORE_ENTRIES=1
AGENT_CORE_ENTRIES_STATUS=""
GOAL_PLAN_STATUS=""
LOCAL_BIN_PATH_STATUS=""
CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS=""
CLAUDE_DESKTOP_SSH_STATUS=""
CODEX_DESKTOP_CONNECTION_FAST_MODE_STATUS=""
CODEX_SQLITE_LOG_GUARD_STATUS=""
SCAN_ROOTS=()
PYTHON_BIN="${PYTHON_BIN:-}"

select_python_bin() {
  local candidate

  if [[ -n "$PYTHON_BIN" ]]; then
    return
  fi

  for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" - <<'PY' >/dev/null 2>&1; then
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
      PYTHON_BIN="$candidate"
      return
    fi
  done

  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      echo "WARNING: no Python 3.10+ found; falling back to $PYTHON_BIN." >&2
      return
    fi
  done

  PYTHON_BIN="python"
  echo "WARNING: no Python executable found on PATH before selecting fallback: $PYTHON_BIN." >&2
}

configure_tmux_mouse_mode() {
  local tmux_conf="${TMUX_CONF:-$HOME/.tmux.conf}"

  select_python_bin
  "$PYTHON_BIN" - "$tmux_conf" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1]).expanduser()
begin = "# BEGIN agent-tools tmux mouse"
end = "# END agent-tools tmux mouse"
block = "\n".join([
    begin,
    "# Required on Linux/WSL2 servers so mouse-wheel scrolling works inside tmux.",
    "set -g mouse on",
    end,
])

path.parent.mkdir(parents=True, exist_ok=True)
text = path.read_text(encoding="utf-8") if path.exists() else ""

while True:
    start = text.find(begin)
    if start == -1:
        break
    stop = text.find(end, start)
    if stop == -1:
        break
    stop += len(end)
    text = text[:start].rstrip() + "\n\n" + text[stop:].lstrip()

new_text = text.rstrip()
if new_text:
    new_text += "\n\n"
new_text += block + "\n"

if new_text != (path.read_text(encoding="utf-8") if path.exists() else ""):
    path.write_text(new_text, encoding="utf-8")
PY

  if command -v tmux >/dev/null 2>&1; then
    tmux source-file "$tmux_conf" >/dev/null 2>&1 || true
    tmux set-option -g mouse on >/dev/null 2>&1 || true
  fi
}

configure_local_bin_path() {
  local local_bin="${LOCAL_BIN_DIR:-$HOME/.local/bin}"
  local profile="$HOME/.profile"
  local bashrc="$HOME/.bashrc"
  local zshrc="$HOME/.zshrc"
  local targets=("$profile")

  mkdir -p "$local_bin"

  [[ -f "$bashrc" ]] && targets+=("$bashrc")
  [[ -f "$zshrc" ]] && targets+=("$zshrc")

  select_python_bin
  "$PYTHON_BIN" - "$local_bin" "${targets[@]}" <<'PY'
from pathlib import Path
import sys

local_bin = Path(sys.argv[1]).expanduser()
targets = [Path(path).expanduser() for path in sys.argv[2:]]
begin = "# BEGIN agent-tools local bin"
end = "# END agent-tools local bin"
block = "\n".join([
    begin,
    "# Ensure agent-tools launchers such as codex-here are discoverable.",
    'if [ -d "$HOME/.local/bin" ]; then',
    '  case ":$PATH:" in',
    '    *":$HOME/.local/bin:"*) ;;',
    '    *) PATH="$HOME/.local/bin:$PATH" ;;',
    "  esac",
    "fi",
    "export PATH",
    end,
])

changed = []
for path in targets:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""

    while True:
        start = text.find(begin)
        if start == -1:
            break
        stop = text.find(end, start)
        if stop == -1:
            break
        stop += len(end)
        text = text[:start].rstrip() + "\n\n" + text[stop:].lstrip()

    new_text = text.rstrip()
    if new_text:
        new_text += "\n\n"
    new_text += block + "\n"

    old_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if new_text != old_text:
        path.write_text(new_text, encoding="utf-8")
        changed.append(str(path))

if changed:
    print("agent-tools PATH block updated:")
    for path in changed:
        print(f"  {path}")
else:
    print("agent-tools PATH block already current.")
print(f"agent-tools local bin: {local_bin}")
PY

  LOCAL_BIN_PATH_STATUS="$local_bin configured in ${targets[*]}"
  case ":$PATH:" in
    *":$local_bin:"*) ;;
    *) PATH="$local_bin:$PATH" ;;
  esac
  export PATH
  hash -r 2>/dev/null || true
}

run_script_as_root_if_available() {
  local -a args=()
  local arg

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --)
        shift
        break
        ;;
      *)
        args+=("$1")
        shift
        ;;
    esac
  done

  if [[ "$(id -u)" -eq 0 ]]; then
    bash -s -- "${args[@]}" "$@"
    return
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    sudo bash -s -- "${args[@]}" "$@"
    return
  fi

  if grep -qi microsoft /proc/version 2>/dev/null && [[ -x /mnt/c/Windows/System32/wsl.exe ]]; then
    /mnt/c/Windows/System32/wsl.exe -u root -- bash -s -- "${args[@]}" "$@"
    return
  fi

  return 1
}

resolve_existing_path() {
  local path="$1"

  if command -v realpath >/dev/null 2>&1; then
    realpath -e -- "$path" 2>/dev/null && return
  fi
  if command -v readlink >/dev/null 2>&1; then
    readlink -f -- "$path" 2>/dev/null && return
  fi
  printf '%s\n' "$path"
}

configure_claude_desktop_ssh() {
  local claude_cmd claude_target node_cmd node_target root_prefix part
  local env_file usr_local_bin claude_link node_link
  local status_parts=()

  if [[ "$INSTALL_CLAUDE_DESKTOP_SSH" -eq 0 ]]; then
    CLAUDE_DESKTOP_SSH_STATUS="skipped (--no-claude-desktop-ssh)"
    return
  fi

  claude_cmd="$(type -P claude 2>/dev/null || true)"
  if [[ -z "$claude_cmd" ]]; then
    CLAUDE_DESKTOP_SSH_STATUS="skipped: claude not installed on PATH"
    echo "Claude Desktop SSH compatibility skipped: claude is not on PATH."
    return
  fi

  if [[ ! -x "$claude_cmd" ]]; then
    CLAUDE_DESKTOP_SSH_STATUS="skipped: claude is not executable ($claude_cmd)"
    echo "Claude Desktop SSH compatibility skipped: claude is not executable at $claude_cmd." >&2
    return
  fi

  claude_target="$claude_cmd"
  case "$claude_cmd" in
    /run/user/*|/tmp/*|/var/tmp/*)
      claude_target="$(resolve_existing_path "$claude_cmd")"
      ;;
  esac

  if [[ -z "$claude_target" || ! -x "$claude_target" ]]; then
    CLAUDE_DESKTOP_SSH_STATUS="skipped: could not resolve stable claude target from $claude_cmd"
    echo "Claude Desktop SSH compatibility skipped: could not resolve a stable claude target from $claude_cmd." >&2
    return
  fi

  if [[ "$claude_target" == /run/user/* || "$claude_target" == /tmp/* || "$claude_target" == /var/tmp/* ]]; then
    CLAUDE_DESKTOP_SSH_STATUS="skipped: resolved claude target is temporary ($claude_target)"
    echo "Claude Desktop SSH compatibility skipped: resolved claude target is temporary: $claude_target." >&2
    return
  fi

  root_prefix="${AGENT_TOOLS_TEST_ROOT:-}"
  env_file="$root_prefix/etc/environment"
  usr_local_bin="$root_prefix/usr/local/bin"
  claude_link="$usr_local_bin/claude"
  node_link="$usr_local_bin/node"

  if ! run_script_as_root_if_available "$env_file" -- <<'SH'
set -eu
env_file="$1"
if [ -f "$env_file" ] && grep -q "^IS_SANDBOX=1$" "$env_file"; then
  exit 0
fi
timestamp=$(date +%Y%m%d-%H%M%S)
if [ -f "$env_file" ]; then
  cp -a "$env_file" "${env_file}.agent-tools-backup-${timestamp}"
fi
if [ -f "$env_file" ] && grep -q "^IS_SANDBOX=" "$env_file"; then
  sed -i "s/^IS_SANDBOX=.*/IS_SANDBOX=1/" "$env_file"
else
  mkdir -p "$(dirname "$env_file")"
  if [ -s "$env_file" ] && [ "$(tail -c 1 "$env_file" 2>/dev/null || true)" != "" ]; then
    printf "\n" >>"$env_file"
  fi
  printf "IS_SANDBOX=1\n" >>"$env_file"
fi
chmod 0644 "$env_file"
SH
  then
    CLAUDE_DESKTOP_SSH_STATUS="skipped: root/sudo required to write $env_file"
    echo "Claude Desktop SSH compatibility skipped: root or passwordless sudo is required to write $env_file." >&2
    return
  fi
  status_parts+=("IS_SANDBOX=1 in $env_file")

  if ! run_script_as_root_if_available "$claude_target" "$claude_link" -- <<'SH'
set -eu
target="$1"
link_path="$2"
mkdir -p "$(dirname "$link_path")"
if [ -e "$link_path" ] || [ -L "$link_path" ]; then
  current=$(readlink -f "$link_path" 2>/dev/null || true)
  wanted=$(readlink -f "$target" 2>/dev/null || true)
  if [ -n "$current" ] && [ -n "$wanted" ] && [ "$current" != "$wanted" ]; then
    timestamp=$(date +%Y%m%d-%H%M%S)
    mv "$link_path" "${link_path}.agent-tools-backup-${timestamp}"
  fi
fi
ln -sfn "$target" "$link_path"
chmod 0755 "$(dirname "$link_path")"
SH
  then
    CLAUDE_DESKTOP_SSH_STATUS="partial: IS_SANDBOX configured, but root/sudo required for $claude_link"
    echo "Claude Desktop SSH compatibility partially configured: root or passwordless sudo is required to write $claude_link." >&2
    return
  fi
  status_parts+=("$claude_link -> $claude_target")

  if ! env -i PATH="$usr_local_bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" IS_SANDBOX=1 "$claude_link" --version >/dev/null 2>&1 && [[ ! -x "$node_link" ]]; then
    node_cmd="$(type -P node 2>/dev/null || true)"
    if [[ -n "$node_cmd" ]]; then
      node_target="$node_cmd"
      case "$node_cmd" in
        /run/user/*|/tmp/*|/var/tmp/*)
          node_target="$(resolve_existing_path "$node_cmd")"
          ;;
      esac
      if [[ -n "$node_target" && -x "$node_target" && "$node_target" != /run/user/* && "$node_target" != /tmp/* && "$node_target" != /var/tmp/* ]]; then
        if run_script_as_root_if_available "$node_target" "$node_link" -- <<'SH'
set -eu
target="$1"
link_path="$2"
mkdir -p "$(dirname "$link_path")"
if [ ! -e "$link_path" ] && [ ! -L "$link_path" ]; then
  ln -s "$target" "$link_path"
fi
SH
        then
          status_parts+=("$node_link -> $node_target")
        else
          status_parts+=("node symlink skipped: root/sudo required")
        fi
      else
        status_parts+=("node symlink skipped: stable node target not found")
      fi
    else
      status_parts+=("node symlink skipped: node not on PATH")
    fi
  fi

  if ! env -i PATH="$usr_local_bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" IS_SANDBOX=1 "$claude_link" --version >/dev/null 2>&1; then
    status_parts+=("warning: $claude_link still failed with a minimal SSH-like PATH")
  fi

  if [[ -z "$root_prefix" && -f /etc/pam.d/sshd ]] && ! grep -q 'pam_env\.so' /etc/pam.d/sshd 2>/dev/null; then
    status_parts+=("warning: /etc/pam.d/sshd does not mention pam_env.so")
  fi

  CLAUDE_DESKTOP_SSH_STATUS=""
  for part in "${status_parts[@]}"; do
    if [[ -n "$CLAUDE_DESKTOP_SSH_STATUS" ]]; then
      CLAUDE_DESKTOP_SSH_STATUS+="; "
    fi
    CLAUDE_DESKTOP_SSH_STATUS+="$part"
  done
  echo "Claude Desktop SSH compatibility: $CLAUDE_DESKTOP_SSH_STATUS"
}

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
  local tmp_dir installer proxy_url curl_args=()

  if [[ "$INSTALL_CC_SWITCH_CLI_UPDATE" -eq 0 ]]; then
    echo "cc-switch update skipped (--no-cc-switch-update)."
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

  cat >"$tmp_dir/.curlrc" <<EOF
connect-timeout = $CC_SWITCH_UPDATE_CONNECT_TIMEOUT
max-time = $CC_SWITCH_UPDATE_MAX_TIME
retry = $CC_SWITCH_UPDATE_RETRY
retry-delay = $CC_SWITCH_UPDATE_RETRY_DELAY
retry-all-errors
speed-limit = $CC_SWITCH_UPDATE_SPEED_LIMIT
speed-time = $CC_SWITCH_UPDATE_SPEED_TIME
EOF

  curl_args=(
    -fsSL
    --connect-timeout "$CC_SWITCH_UPDATE_CONNECT_TIMEOUT"
    --max-time "$CC_SWITCH_UPDATE_MAX_TIME"
    --retry "$CC_SWITCH_UPDATE_RETRY"
    --retry-delay "$CC_SWITCH_UPDATE_RETRY_DELAY"
    --retry-all-errors
  )

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

normalize_codex_provider_auth() {
  local codex_config="${CODEX_HOME:-$HOME/.codex}/config.toml"

  select_python_bin
  "$PYTHON_BIN" - "$codex_config" "$CODEX_MODEL_PROVIDER_ID" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1]).expanduser()
target = sys.argv[2]
if not path.exists():
    raise SystemExit(0)
if not target or not re.fullmatch(r"[A-Za-z0-9_.-]+", target):
    raise SystemExit(f"invalid CODEX_MODEL_PROVIDER_ID: {target}")

text = path.read_text(encoding="utf-8")
lines = text.splitlines()
out = []
in_target_provider = False
inserted_auth = False

def section_path(line):
    stripped = line.strip()
    if stripped.startswith("[[") or not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    return stripped[1:-1].strip().split(".")

def insert_auth():
    global inserted_auth
    while out and not out[-1].strip():
        out.pop()
    out.append("requires_openai_auth = true")
    inserted_auth = True

for line in lines:
    path_parts = section_path(line)
    if path_parts is not None:
        if in_target_provider and not inserted_auth:
            insert_auth()
        in_target_provider = len(path_parts) >= 2 and path_parts[0] == "model_providers" and path_parts[1] == target
        inserted_auth = False
        out.append(line)
        continue

    if in_target_provider and "=" in line and not line.strip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key == "env_key":
            continue
        if key == "requires_openai_auth":
            if not inserted_auth:
                insert_auth()
            continue

    out.append(line)

if in_target_provider and not inserted_auth:
    insert_auth()

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

new_text = "\n".join(cleaned).rstrip() + "\n"
if new_text != text:
    path.write_text(new_text, encoding="utf-8")
PY
}

normalize_cc_switch_codex_provider_templates() {
  local db_path="${CC_SWITCH_DB_PATH:-$HOME/.cc-switch/cc-switch.db}"

  if [[ ! -f "$db_path" ]]; then
    return
  fi

  select_python_bin
  "$PYTHON_BIN" - "$db_path" "$CODEX_MODEL_PROVIDER_ID" <<'PY'
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

db_path = Path(sys.argv[1]).expanduser()
target = sys.argv[2]
if not target or not re.fullmatch(r"[A-Za-z0-9_.-]+", target):
    raise SystemExit(f"invalid CODEX_MODEL_PROVIDER_ID: {target}")

def section_path(line):
    stripped = line.strip()
    if stripped.startswith("[[") or not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    return stripped[1:-1].strip().split(".")

def normalize_config(text):
    lines = text.splitlines()
    out = []
    in_target_provider = False
    inserted_auth = False

    def insert_auth():
        nonlocal inserted_auth
        while out and not out[-1].strip():
            out.pop()
        out.append("requires_openai_auth = true")
        inserted_auth = True

    for line in lines:
        path_parts = section_path(line)
        if path_parts is not None:
            if in_target_provider and not inserted_auth:
                insert_auth()
            in_target_provider = (
                len(path_parts) >= 2 and path_parts[0] == "model_providers" and path_parts[1] == target
            )
            inserted_auth = False
            out.append(line)
            continue

        if in_target_provider and "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key == "env_key":
                continue
            if key == "requires_openai_auth":
                if not inserted_auth:
                    insert_auth()
                continue

        out.append(line)

    if in_target_provider and not inserted_auth:
        insert_auth()

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

check_codex_fast_mode() {
  local codex_config="${CODEX_HOME:-$HOME/.codex}/config.toml"

  select_python_bin
  "$PYTHON_BIN" - "$codex_config" "$CODEX_SERVICE_TIER" "$CODEX_FEATURE_FAST_MODE" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1]).expanduser()
expected_tier = sys.argv[2]
expected_fast_mode = sys.argv[3]

if not path.exists():
    print(f"WARNING: Codex Fast mode check skipped: missing {path}")
    raise SystemExit(0)

text = path.read_text(encoding="utf-8")
service_tier = None
fast_mode = None
in_features = False

for line in text.splitlines():
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        in_features = stripped == "[features]"
        continue
    if stripped.startswith("#") or "=" not in stripped:
        continue
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not in_features and key == "service_tier":
        match = re.match(r"(['\"])(.*?)\1", value)
        service_tier = match.group(2) if match else value
    if in_features and key == "fast_mode":
        fast_mode = value.split("#", 1)[0].strip().lower()

warnings = []
if service_tier != expected_tier:
    warnings.append(f'top-level service_tier is {service_tier!r}; expected "{expected_tier}"')
if fast_mode != expected_fast_mode:
    warnings.append(f'[features].fast_mode is {fast_mode!r}; expected {expected_fast_mode}')

if warnings:
    print("WARNING: Codex Fast mode is not fully enabled:")
    for warning in warnings:
        print(f"  - {warning}")
else:
    print(f"Codex Fast mode: service_tier={expected_tier}, fast_mode={expected_fast_mode}")
PY

  if ! command -v cc-switch >/dev/null 2>&1; then
    echo "WARNING: cc-switch not found on PATH; provider switching and custom bucket sync are not available."
  fi
}

configure_codex_app_fast_mode() {
  local script="$INSTALL_REAL/scripts/configure_codex_app_fast_mode.py"
  local args=()

  if [[ "$INSTALL_CODEX_APP_FAST_MODE" -eq 0 ]]; then
    echo "Codex App Fast mode config not changed (--no-codex-app-fast-mode)."
    return
  fi

  if [[ ! -f "$script" ]]; then
    echo "Codex App Fast mode config skipped: missing $script" >&2
    return 1
  fi

  select_python_bin

  case "$CODEX_APP_FAST_MODE_INCLUDE_WSL_WINDOWS" in
    auto)
      if grep -qi microsoft /proc/version 2>/dev/null && [[ -d /mnt/c/Users ]]; then
        args+=(--include-wsl-windows)
      fi
      ;;
    always)
      args+=(--include-wsl-windows)
      ;;
    never)
      ;;
    *)
      echo "invalid Codex App Fast mode WSL-Windows mode: $CODEX_APP_FAST_MODE_INCLUDE_WSL_WINDOWS" >&2
      exit 2
      ;;
  esac

  "$PYTHON_BIN" "$script" \
    --service-tier "$CODEX_SERVICE_TIER" \
    --fast-mode "$CODEX_FEATURE_FAST_MODE" \
    "${args[@]}"
}

configure_codex_sqlite_log_guard() {
  local script="$INSTALL_REAL/scripts/configure_codex_sqlite_log_guard.py"
  local args=()

  CODEX_SQLITE_LOG_GUARD_STATUS="skipped"

  if [[ "$INSTALL_CODEX_SQLITE_LOG_GUARD" -eq 0 ]]; then
    CODEX_SQLITE_LOG_GUARD_STATUS="skipped: disabled"
    echo "Codex SQLite log guard not changed (--no-codex-sqlite-log-guard)."
    return
  fi

  if [[ ! -f "$script" ]]; then
    CODEX_SQLITE_LOG_GUARD_STATUS="skipped: missing $script"
    echo "Codex SQLite log guard skipped: missing $script" >&2
    return 1
  fi

  case "$CODEX_SQLITE_LOG_GUARD_MODE" in
    enable|disable|status)
      ;;
    *)
      echo "invalid Codex SQLite log guard mode: $CODEX_SQLITE_LOG_GUARD_MODE (expected enable|disable|status)" >&2
      exit 2
      ;;
  esac

  case "$CODEX_SQLITE_LOG_GUARD_INCLUDE_WSL_WINDOWS" in
    auto)
      if grep -qi microsoft /proc/version 2>/dev/null && [[ -d /mnt/c/Users ]]; then
        args+=(--include-wsl-windows)
      fi
      ;;
    always)
      args+=(--include-wsl-windows)
      ;;
    never)
      ;;
    *)
      echo "invalid Codex SQLite log guard WSL-Windows mode: $CODEX_SQLITE_LOG_GUARD_INCLUDE_WSL_WINDOWS" >&2
      exit 2
      ;;
  esac

  if [[ "$CODEX_SQLITE_LOG_GUARD_VACUUM" -eq 1 ]]; then
    args+=(--vacuum)
  fi

  select_python_bin
  "$PYTHON_BIN" "$script" --mode "$CODEX_SQLITE_LOG_GUARD_MODE" "${args[@]}"
  CODEX_SQLITE_LOG_GUARD_STATUS="mode=${CODEX_SQLITE_LOG_GUARD_MODE}, wsl_windows=${CODEX_SQLITE_LOG_GUARD_INCLUDE_WSL_WINDOWS}, vacuum=${CODEX_SQLITE_LOG_GUARD_VACUUM}"
}

should_setup_codex_desktop_connection_fast_mode() {
  local mode="$INSTALL_CODEX_DESKTOP_CONNECTION_FAST_MODE"

  case "$mode" in
    always)
      return 0
      ;;
    never)
      return 1
      ;;
    auto)
      if [[ -x /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe ]]; then
        return 0
      fi
      if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]]; then
        return 0
      fi
      return 1
      ;;
    *)
      echo "invalid Codex Desktop Connection Fast mode: $mode (expected auto|always|never)" >&2
      return 2
      ;;
  esac
}

setup_codex_desktop_connection_fast_mode() {
  local script="$INSTALL_REAL/scripts/setup_codex_desktop_connection_fast_mode.py"
  local platform_arg="auto"
  local launch_arg=()
  local shortcut_args=()
  local rc

  CODEX_DESKTOP_CONNECTION_FAST_MODE_STATUS="skipped: mode=${INSTALL_CODEX_DESKTOP_CONNECTION_FAST_MODE}"

  if [[ "$INSTALL_CODEX_APP_FAST_MODE" -eq 0 ]]; then
    CODEX_DESKTOP_CONNECTION_FAST_MODE_STATUS="skipped: Codex App Fast mode config disabled"
    return
  fi

  if [[ ! -f "$script" ]]; then
    CODEX_DESKTOP_CONNECTION_FAST_MODE_STATUS="skipped: missing $script"
    echo "Codex Desktop Connection Fast mode setup skipped: missing $script." >&2
    return
  fi

  set +e
  should_setup_codex_desktop_connection_fast_mode
  rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    if [[ "$rc" -eq 2 ]]; then
      exit 2
    fi
    return
  fi

  if [[ -x /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe ]]; then
    platform_arg="win11"
  elif [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]]; then
    platform_arg="macos"
  fi

  if [[ "$CODEX_DESKTOP_CONNECTION_FAST_MODE_LAUNCH" -eq 1 ]]; then
    launch_arg=(--launch)
  fi
  shortcut_args=(
    --shortcut-scope "$CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_SCOPE"
    --shortcut-name "$CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_NAME"
  )

  select_python_bin
  if "$PYTHON_BIN" "$script" --platform "$platform_arg" "${launch_arg[@]}" "${shortcut_args[@]}"; then
    CODEX_DESKTOP_CONNECTION_FAST_MODE_STATUS="configured: platform=${platform_arg}, launch=${CODEX_DESKTOP_CONNECTION_FAST_MODE_LAUNCH}"
  else
    CODEX_DESKTOP_CONNECTION_FAST_MODE_STATUS="failed: platform=${platform_arg}"
    echo "Codex Desktop Connection Fast mode setup failed." >&2
    if [[ "$INSTALL_CODEX_DESKTOP_CONNECTION_FAST_MODE" == "always" ]]; then
      return 1
    fi
    return 0
  fi
}

sync_codex_config_from_cc_switch_current() {
  local output provider_id

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

configure_codex_defaults() {
  local codex_config="${CODEX_HOME:-$HOME/.codex}/config.toml"

  select_python_bin
  "$PYTHON_BIN" - "$codex_config" "$CODEX_STREAM_IDLE_TIMEOUT_MS" "$CODEX_STREAM_MAX_RETRIES" "$CODEX_MODEL_PROVIDER_ID" "$CODEX_APPROVAL_POLICY" "$CODEX_SANDBOX_MODE" "$CODEX_APPROVALS_REVIEWER" "$CODEX_MODEL" "$CODEX_MODEL_REASONING_EFFORT" "$CODEX_SERVICE_TIER" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1]).expanduser()
timeout = sys.argv[2]
retries = sys.argv[3]
provider_id = sys.argv[4]
approval_policy = sys.argv[5]
sandbox_mode = sys.argv[6]
approvals_reviewer = sys.argv[7]
model = sys.argv[8]
model_reasoning_effort = sys.argv[9]
service_tier = sys.argv[10]
if not timeout.isdigit() or int(timeout) <= 0:
    raise SystemExit(f"invalid CODEX_STREAM_IDLE_TIMEOUT_MS: {timeout}")
if not retries.isdigit() or int(retries) <= 0:
    raise SystemExit(f"invalid CODEX_STREAM_MAX_RETRIES: {retries}")
if not provider_id or not all(c.isalnum() or c in "-_." for c in provider_id):
    raise SystemExit(f"invalid CODEX_MODEL_PROVIDER_ID: {provider_id}")
ALLOWED_APPROVAL_POLICIES = {"on-request", "on-failure", "untrusted", "never"}
ALLOWED_SANDBOX_MODES = {"read-only", "workspace-write", "danger-full-access"}
ALLOWED_APPROVALS_REVIEWERS = {"user", "auto_review", "guardian_subagent"}
ALLOWED_REASONING_EFFORTS = {"minimal", "low", "medium", "high"}
ALLOWED_SERVICE_TIERS = {"auto", "default", "fast", "priority"}
if approval_policy not in ALLOWED_APPROVAL_POLICIES:
    raise SystemExit(f"invalid CODEX_APPROVAL_POLICY: {approval_policy}")
if sandbox_mode not in ALLOWED_SANDBOX_MODES:
    raise SystemExit(f"invalid CODEX_SANDBOX_MODE: {sandbox_mode}")
if approvals_reviewer not in ALLOWED_APPROVALS_REVIEWERS:
    raise SystemExit(f"invalid CODEX_APPROVALS_REVIEWER: {approvals_reviewer}")
if not model or not all(c.isalnum() or c in "-_." for c in model):
    raise SystemExit(f"invalid CODEX_MODEL: {model}")
if model_reasoning_effort not in ALLOWED_REASONING_EFFORTS:
    raise SystemExit(f"invalid CODEX_MODEL_REASONING_EFFORT: {model_reasoning_effort}")
if service_tier not in ALLOWED_SERVICE_TIERS:
    raise SystemExit(f"invalid CODEX_SERVICE_TIER: {service_tier}")

path.parent.mkdir(parents=True, exist_ok=True)
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()

first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
preamble = lines[:first_table]
rest = lines[first_table:]

managed_top_level = {
    "disable_response_storage",
    "stream_idle_timeout_ms",
    "stream_max_retries",
    "model_provider",
    "approval_policy",
    "sandbox_mode",
    "approvals_reviewer",
    "model",
    "model_reasoning_effort",
    "service_tier",
}

kept = []
for line in preamble:
    stripped = line.strip()
    key = stripped.split("=", 1)[0].strip() if "=" in stripped else None
    if key in managed_top_level:
        continue
    kept.append(line)

if kept and kept[-1].strip():
    kept.append("")
kept.append(f'approval_policy = "{approval_policy}"')
kept.append(f'sandbox_mode = "{sandbox_mode}"')
kept.append(f'approvals_reviewer = "{approvals_reviewer}"')
kept.append(f'model = "{model}"')
kept.append(f'model_reasoning_effort = "{model_reasoning_effort}"')
kept.append(f'service_tier = "{service_tier}"')
kept.append(f"stream_idle_timeout_ms = {timeout}")
kept.append(f"stream_max_retries = {retries}")
kept.append(f'model_provider = "{provider_id}"')

provider_header = f"[model_providers.{provider_id}]"
provider_sections_to_remove = {
    "model_providers.openai-no-ws",
    "model_providers.ccswitch",
}
reserved_provider_ids = {
    "amazon-bedrock",
    "lmstudio",
    "ollama",
    "ollama-chat",
    "openai",
    "oss",
}

def _toml_section_path(line):
    stripped = line.strip()
    if stripped.startswith("[[") or not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    return stripped[1:-1].strip()

def _is_toml_section(line):
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")

def _remove_model_provider_section(line):
    path = _toml_section_path(line)
    if not path:
        return False
    return any(path == section or path.startswith(section + ".") for section in provider_sections_to_remove)

def _has_third_party_model_provider(lines):
    for line in lines:
        path = _toml_section_path(line)
        if not path:
            continue
        parts = path.split(".")
        if len(parts) >= 2 and parts[0] == "model_providers":
            model_provider = parts[1]
            if model_provider != provider_id and model_provider not in reserved_provider_ids:
                return True
    return False

def _has_model_provider(lines, candidate):
    for line in lines:
        path = _toml_section_path(line)
        if not path:
            continue
        parts = path.split(".")
        if len(parts) >= 2 and parts[0] == "model_providers" and parts[1] == candidate:
            return True
    return False

has_third_party_model_provider = _has_third_party_model_provider(rest)
has_target_model_provider = _has_model_provider(rest, provider_id)
filtered_rest = []
i = 0
while i < len(rest):
    if _remove_model_provider_section(rest[i]):
        i += 1
        while i < len(rest) and not _is_toml_section(rest[i]):
            i += 1
        continue
    filtered_rest.append(rest[i])
    i += 1
rest = filtered_rest

if rest:
    kept.append("")
    kept.extend(rest)

if kept and kept[-1].strip():
    kept.append("")
if not has_target_model_provider and not has_third_party_model_provider:
    kept.extend([
        provider_header,
        'name = "OpenAI HTTPS no WebSocket"',
        'base_url = "https://chatgpt.com/backend-api/codex"',
        "requires_openai_auth = true",
        "supports_websockets = false",
        f"stream_idle_timeout_ms = {timeout}",
        f"stream_max_retries = {retries}",
    ])

# Collapse runs of 2+ blank lines into 1 and strip leading blanks. Idempotent
# across repeated runs so cosmetic gaps stop accumulating.
def _compact(lines):
    out = []
    prev_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and (prev_blank or not out):
            continue
        out.append(line)
        prev_blank = is_blank
    return out

kept = _compact(kept)

new_text = "\n".join(kept).rstrip() + "\n"
if new_text != text:
    path.write_text(new_text, encoding="utf-8")
PY
}

configure_codex_features() {
  local codex_config="${CODEX_HOME:-$HOME/.codex}/config.toml"

  select_python_bin
  "$PYTHON_BIN" - "$codex_config" \
      "$CODEX_FEATURE_FAST_MODE" \
      "$CODEX_FEATURE_HOOKS" \
      "$CODEX_FEATURE_MEMORIES" \
      "$CODEX_FEATURE_GOALS" \
      "$CODEX_FEATURE_TERMINAL_RESIZE_REFLOW" \
      "$CODEX_FEATURE_REMOTE_CONTROL" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1]).expanduser()

FEATURE_KEYS = [
    ("fast_mode", sys.argv[2]),
    ("hooks", sys.argv[3]),
    ("memories", sys.argv[4]),
    ("goals", sys.argv[5]),
    ("terminal_resize_reflow", sys.argv[6]),
    ("remote_control", sys.argv[7]),
]

ALLOWED_VALUES = {"true", "false"}
for name, value in FEATURE_KEYS:
    if value not in ALLOWED_VALUES:
        raise SystemExit(f"invalid CODEX_FEATURE_{name.upper()}: {value} (expected true|false)")

managed = {name for name, _ in FEATURE_KEYS} | {"codex_hooks", "remote_connections", "service_tier"}

path.parent.mkdir(parents=True, exist_ok=True)
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()

first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
lines = [
    line
    for i, line in enumerate(lines)
    if not (
        i < first_table
        and "=" in line.strip()
        and line.strip().split("=", 1)[0].strip() in {"remote_control", "remote_connections"}
    )
]

out = []
in_features = False
found_features = False
inserted = False

def feature_block():
    return [f"{name} = {value}" for name, value in FEATURE_KEYS]

for line in lines:
    stripped = line.strip()
    starts_table = stripped.startswith("[") and stripped.endswith("]")

    if starts_table and in_features:
        if out and out[-1].strip():
            out.append("")
        out.extend(feature_block())
        inserted = True
        in_features = False

    if stripped == "[features]":
        found_features = True
        in_features = True
        out.append(line)
        continue

    if in_features and "=" in stripped and not stripped.startswith("#"):
        key = stripped.split("=", 1)[0].strip()
        if key in managed:
            continue

    out.append(line)

if in_features and not inserted:
    if out and out[-1].strip():
        out.append("")
    out.extend(feature_block())
    inserted = True

if not found_features:
    if out and out[-1].strip():
        out.append("")
    out.append("[features]")
    out.extend(feature_block())

# Collapse runs of 2+ blank lines into 1 and strip leading blanks, then re-
# tighten table headers so each `[table]` line abuts its keys (no blank line
# right after the header).
def _compact(lines):
    cleaned = []
    prev_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and (prev_blank or not cleaned):
            continue
        cleaned.append(line)
        prev_blank = is_blank
    # Drop a single blank line that appears immediately after a table header.
    out = []
    for i, line in enumerate(cleaned):
        if i > 0 and not line.strip():
            prev = cleaned[i - 1].strip()
            if prev.startswith("[") and prev.endswith("]"):
                continue
        out.append(line)
    return out

out = _compact(out)

new_text = "\n".join(out).rstrip() + "\n"
if new_text != text:
    path.write_text(new_text, encoding="utf-8")
PY
}

configure_codex_project_hooks_features() {
  if [[ ${#SCAN_ROOTS[@]} -eq 0 ]]; then
    return
  fi

  select_python_bin
  "$PYTHON_BIN" - "$MAX_DEPTH" "${SCAN_ROOTS[@]}" <<'PY'
from pathlib import Path
import sys

max_depth = int(sys.argv[1])
roots = [Path(root).expanduser().resolve() for root in sys.argv[2:]]


def has_hooks_config(lines):
    return any(
        line.strip() == "[hooks]"
        or line.strip().startswith("[[hooks.")
        or line.strip().startswith("[hooks.")
        for line in lines
    )


def migrate_project_config(path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not has_hooks_config(lines) and "codex_hooks" not in text and "remote_control" not in text and "remote_connections" not in text:
        return False

    first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
    lines = [
        line
        for i, line in enumerate(lines)
        if not (
            i < first_table
            and "=" in line.strip()
            and line.strip().split("=", 1)[0].strip() in {"remote_control", "remote_connections"}
        )
    ]

    out = []
    in_features = False
    found_features = False
    inserted = False

    def feature_block():
        return ["hooks = true", "remote_control = true"]

    for line in lines:
        stripped = line.strip()
        starts_table = stripped.startswith("[") and stripped.endswith("]")

        if starts_table and in_features:
            if out and out[-1].strip():
                out.append("")
            out.extend(feature_block())
            inserted = True
            in_features = False

        if stripped == "[features]":
            found_features = True
            in_features = True
            out.append(line)
            continue

        if in_features and "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in {"codex_hooks", "hooks", "remote_control", "remote_connections"}:
                continue

        out.append(line)

    if in_features and not inserted:
        if out and out[-1].strip():
            out.append("")
        out.extend(feature_block())
        inserted = True

    if not found_features:
        insert_at = next((i for i, line in enumerate(out) if line.lstrip().startswith("[")), len(out))
        out = out[:insert_at] + ["[features]", "hooks = true", "remote_control = true", ""] + out[insert_at:]

    new_text = "\n".join(out).rstrip() + "\n"
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


changed = []
for root in roots:
    if not root.exists():
        continue
    for config_path in root.rglob(".codex/config.toml"):
        try:
            rel = config_path.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) - 2 > max_depth:
            continue
        if migrate_project_config(config_path):
            changed.append(str(config_path))

for path in changed:
    print(f"Codex project hooks feature migrated: {path}")
PY
}

run_codex_provider_bucket_migration() {
  local script="$INSTALL_REAL/migrate_codex_provider_bucket.py"
  local args=()
  local status

  if [[ ! -x "$script" ]]; then
    echo "Codex provider bucket migration skipped: missing $script" >&2
    return
  fi

  if [[ "$CODEX_PROVIDER_BUCKET_ALLOW_RUNNING" == "1" && "$CODEX_PROVIDER_BUCKET_KILL_RUNNING" == "1" ]]; then
    echo "Codex provider bucket migration skipped: allow-running and kill-running conflict." >&2
    return 2
  fi
  if [[ "$CODEX_PROVIDER_BUCKET_ALLOW_RUNNING" == "1" ]]; then
    args+=(--allow-running-codex)
  fi
  if [[ "$CODEX_PROVIDER_BUCKET_KILL_RUNNING" == "1" ]]; then
    args+=(--kill-running-codex)
  fi
  if [[ "$CODEX_PROVIDER_BUCKET_ALL_NON_TARGET" == "1" ]]; then
    args+=(--all-non-target-providers)
  fi

  if [[ "$APPLY_CODEX_PROVIDER_BUCKET_MIGRATION" == "1" ]]; then
    set +e
    "$PYTHON_BIN" "$script" --target "$CODEX_MODEL_PROVIDER_ID" --apply --yes "${args[@]}"
    status=$?
    set -e
    if [[ "$status" -eq 0 ]]; then
      return
    fi
    if [[ "$status" -ne 2 ]]; then
      return "$status"
    fi
    echo "Codex provider bucket migration apply was blocked, usually because Codex is running; falling back to dry-run." >&2
  fi

  "$PYTHON_BIN" "$script" --target "$CODEX_MODEL_PROVIDER_ID" "${args[@]}"
}

probe_codex_proxy_url() {
  local proxy_url="$1"
  local status

  if ! command -v curl >/dev/null 2>&1; then
    return 2
  fi

  status="$(
    curl -sS -o /dev/null -w '%{http_code}' \
      --connect-timeout "$CODEX_PROXY_CONNECT_TIMEOUT" \
      --max-time "$CODEX_PROXY_MAX_TIME" \
      -x "$proxy_url" \
      "$CODEX_PROXY_TEST_URL" 2>/dev/null || true
  )"

  case "$status" in
    200|204|301|302|401|404|405)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

select_codex_proxy_url() {
  local port proxy_url

  if [[ -n "${CODEX_PROXY_URL:-}" ]]; then
    if [[ "${CODEX_PROXY_SKIP_CHECK:-0}" == "1" ]] || probe_codex_proxy_url "$CODEX_PROXY_URL"; then
      printf '%s\n' "$CODEX_PROXY_URL"
      return 0
    fi
    echo "Codex proxy check failed for CODEX_PROXY_URL=$CODEX_PROXY_URL" >&2
    return 1
  fi

  for port in $CODEX_PROXY_PORTS; do
    proxy_url="http://${CODEX_PROXY_HOST}:${port}"
    if probe_codex_proxy_url "$proxy_url"; then
      printf '%s\n' "$proxy_url"
      return 0
    fi
  done

  return 1
}

configure_codex_proxy_wrapper() {
  local mode="$INSTALL_CODEX_PROXY_WRAPPER"
  local proxy_url real_bin target timestamp backup

  case "$mode" in
    auto|always|never)
      ;;
    *)
      echo "invalid Codex proxy wrapper mode: $mode" >&2
      exit 2
      ;;
  esac

  if [[ "$mode" == "never" ]]; then
    echo "Codex proxy wrapper not installed (mode=never)."
    return
  fi

  if ! proxy_url="$(select_codex_proxy_url)"; then
    if [[ "$mode" == "always" ]]; then
      echo "Codex proxy wrapper requested, but no reachable proxy was found." >&2
      echo "Set CODEX_PROXY_URL or CODEX_PROXY_HOST/CODEX_PROXY_PORTS for this host." >&2
      exit 1
    fi
    echo "Codex proxy wrapper not installed: no reachable proxy found in CODEX_PROXY_PORTS=[$CODEX_PROXY_PORTS]."
    return
  fi

  real_bin="${CODEX_REAL_BIN:-${CODEX_HOME:-$HOME/.codex}/packages/standalone/current/codex}"
  if [[ ! -x "$real_bin" ]]; then
    if [[ "$mode" == "always" ]]; then
      echo "Codex proxy wrapper requested, but standalone Codex binary is not executable: $real_bin" >&2
      echo "Install standalone Codex first or set CODEX_REAL_BIN." >&2
      exit 1
    fi
    echo "Codex proxy wrapper not installed: standalone Codex binary not found at $real_bin."
    echo "Install with: curl -fsSL https://chatgpt.com/codex/install.sh | sh"
    return
  fi

  target="${CODEX_WRAPPER_PATH:-$HOME/.local/bin/codex}"
  mkdir -p "$(dirname "$target")"

  timestamp="$(date +%Y%m%d-%H%M%S)"
  if [[ -e "$target" || -L "$target" ]]; then
    if grep -q "BEGIN agent-tools codex proxy wrapper" "$target" 2>/dev/null; then
      :
    else
      if [[ -L "$target" ]]; then
        backup="${target}.standalone-symlink-${timestamp}"
      else
        backup="${target}.backup-${timestamp}"
      fi
      mv "$target" "$backup"
      echo "Backed up existing Codex launcher: $backup"
    fi
  fi

  cat >"$target" <<EOF
#!/usr/bin/env bash
set -euo pipefail

# BEGIN agent-tools codex proxy wrapper
REAL_CODEX="\${CODEX_REAL_BIN:-$real_bin}"
CODEX_PROXY_URL="\${CODEX_PROXY_URL:-$proxy_url}"

export HTTP_PROXY="\$CODEX_PROXY_URL"
export HTTPS_PROXY="\$CODEX_PROXY_URL"
export http_proxy="\$CODEX_PROXY_URL"
export https_proxy="\$CODEX_PROXY_URL"
export WS_PROXY="\$CODEX_PROXY_URL"
export WSS_PROXY="\$CODEX_PROXY_URL"
export ws_proxy="\$CODEX_PROXY_URL"
export wss_proxy="\$CODEX_PROXY_URL"
export ALL_PROXY="\$CODEX_PROXY_URL"
export all_proxy="\$CODEX_PROXY_URL"
export CODEX_NETWORK_PROXY_ACTIVE=1

export NO_PROXY="\${NO_PROXY:-127.0.0.1,localhost,100.64.0.0/10,.local,beihang.edu.cn}"
export no_proxy="\${no_proxy:-\$NO_PROXY}"

exec "\$REAL_CODEX" "\$@"
# END agent-tools codex proxy wrapper
EOF
  chmod 0755 "$target"
  echo "Codex proxy wrapper: $target -> $real_bin via $proxy_url"
}

install_codex_here() {
  local source target timestamp backup

  source="$INSTALL_REAL/bin/codex-here"
  if [[ ! -f "$source" ]]; then
    echo "codex-here not installed: missing source script at $source" >&2
    return 1
  fi

  target="${CODEX_HERE_PATH:-$HOME/.local/bin/codex-here}"
  mkdir -p "$(dirname "$target")"

  timestamp="$(date +%Y%m%d-%H%M%S)"
  if [[ -e "$target" || -L "$target" ]]; then
    if grep -q "BEGIN agent-tools codex-here" "$target" 2>/dev/null; then
      rm -f "$target"
    else
      if [[ -L "$target" ]]; then
        backup="${target}.symlink-${timestamp}"
      else
        backup="${target}.backup-${timestamp}"
      fi
      mv "$target" "$backup"
      echo "Backed up existing codex-here launcher: $backup"
    fi
  fi

  install -m 0755 "$source" "$target"
  echo "codex-here launcher: $target -> codex -C \"\$PWD\""
}

backup_and_link() {
  local source="$1"
  local target="$2"
  local timestamp backup

  if [[ ! -e "$source" && ! -L "$source" ]]; then
    echo "missing source for link: $source" >&2
    return 1
  fi

  mkdir -p "$(dirname "$target")"

  if [[ -L "$target" ]]; then
    rm -f "$target"
  elif [[ -e "$target" ]]; then
    timestamp="$(date +%Y%m%d-%H%M%S)"
    if [[ -d "$target" ]]; then
      backup="${target}.backup-${timestamp}"
    else
      backup="${target}.backup-${timestamp}"
    fi
    mv "$target" "$backup"
    echo "Backed up existing goal-plan target: $backup"
  fi

  ln -s "$source" "$target"
}

install_codex_personal_marketplace_goal_plan() {
  local marketplace="$HOME/.agents/plugins/marketplace.json"
  local plugin_path="./plugins/goal-plan"

  mkdir -p "$(dirname "$marketplace")"
  select_python_bin
  "$PYTHON_BIN" - "$marketplace" "$plugin_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
plugin_path = sys.argv[2]

data = {}
if path.exists():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_name(path.name + ".invalid-backup")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        data = {}

data.setdefault("name", "personal")
data.setdefault("interface", {}).setdefault("displayName", "Personal")
plugins = data.setdefault("plugins", [])
plugins = [plugin for plugin in plugins if plugin.get("name") != "goal-plan"]
plugins.append({
    "name": "goal-plan",
    "source": {
        "source": "local",
        "path": plugin_path,
    },
    "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    },
    "category": "Developer Tools",
})
data["plugins"] = plugins

path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
}

install_goal_plan_tools() {
  GOAL_PLAN_STATUS="skipped"

  local source_root="$INSTALL_REAL/goal_plan"
  if [[ ! -d "$source_root" ]]; then
    GOAL_PLAN_STATUS="absent: no $source_root"
    echo "goal-plan tools not installed: missing $source_root" >&2
    return 0
  fi

  backup_and_link "$source_root/claude/skills/goal-plan" "$HOME/.claude/skills/goal-plan"
  backup_and_link "$source_root/claude/commands/goal-plan.md" "$HOME/.claude/commands/goal-plan.md"
  backup_and_link "$source_root/claude/agents/goal-plan-reviewer.md" "$HOME/.claude/agents/goal-plan-reviewer.md"

  backup_and_link "$source_root/codex/skills/goal-plan" "${CODEX_HOME:-$HOME/.codex}/skills/goal-plan"
  backup_and_link "$source_root/codex/plugins/goal-plan" "$HOME/plugins/goal-plan"
  install_codex_personal_marketplace_goal_plan

  if command -v codex >/dev/null 2>&1; then
    if codex plugin add goal-plan@personal >/dev/null 2>&1; then
      GOAL_PLAN_STATUS="installed: Claude /goal-plan + Codex skill/plugin"
    else
      GOAL_PLAN_STATUS="linked; codex plugin add goal-plan@personal failed"
      echo "goal-plan Codex plugin linked, but 'codex plugin add goal-plan@personal' failed." >&2
    fi
  else
    GOAL_PLAN_STATUS="linked; codex not on PATH, plugin add skipped"
    echo "goal-plan Codex plugin linked; codex is not on PATH, so plugin add was skipped." >&2
  fi
}

start_codex_remote_control() {
  if [[ "$INSTALL_CODEX_REMOTE_CONTROL" -eq 0 ]]; then
    echo "Codex remote control not started (--no-codex-remote-control)."
    return
  fi

  if ! command -v codex >/dev/null 2>&1; then
    echo "Codex remote control not started: codex is not on PATH." >&2
    return
  fi

  if codex remote-control start; then
    return
  fi

  echo "Codex remote control start failed." >&2
  echo "If this is an npm-only install, install standalone Codex first:" >&2
  echo "  curl -fsSL https://chatgpt.com/codex/install.sh | sh" >&2
}

verify_agent_core_entries() {
  AGENT_CORE_ENTRIES_STATUS="skipped"

  local install_script="$AGENT_CORE_DIR/scripts/install.sh"
  if [[ ! -x "$install_script" ]]; then
    AGENT_CORE_ENTRIES_STATUS="absent: no $install_script"
    return 0
  fi

  local claude_src="$AGENT_CORE_DIR/adapters/claude/CLAUDE.md"
  local codex_src="$AGENT_CORE_DIR/adapters/codex/AGENTS.md"
  local claude_dst="$HOME/.claude/CLAUDE.md"
  local codex_dst="$HOME/.codex/AGENTS.md"
  local skills_src_dir="$AGENT_CORE_DIR/skills"

  local missing=()
  local conflicts=()
  local pair dst src current expected skill_src skill_name

  for pair in "$claude_dst|$claude_src" "$codex_dst|$codex_src"; do
    dst="${pair%|*}"
    src="${pair#*|}"
    if [[ -L "$dst" ]]; then
      current="$(readlink -f -- "$dst" 2>/dev/null || true)"
      expected="$(readlink -f -- "$src" 2>/dev/null || true)"
      if [[ -z "$current" || "$current" != "$expected" ]]; then
        conflicts+=("$dst -> $(readlink -- "$dst") (expected target inside $AGENT_CORE_DIR)")
      fi
    elif [[ -e "$dst" ]]; then
      conflicts+=("$dst exists as a regular file, not a symlink")
    else
      missing+=("$dst")
    fi
  done

  if [[ -d "$skills_src_dir" ]]; then
    for skill_src in "$skills_src_dir"/*; do
      [[ -d "$skill_src" ]] || continue
      skill_name="$(basename -- "$skill_src")"
      for dst in "$HOME/.codex/skills/$skill_name" "$HOME/.claude/skills/$skill_name"; do
        if [[ -L "$dst" ]]; then
          current="$(readlink -f -- "$dst" 2>/dev/null || true)"
          expected="$(readlink -f -- "$skill_src" 2>/dev/null || true)"
          if [[ -z "$current" || "$current" != "$expected" ]]; then
            conflicts+=("$dst -> $(readlink -- "$dst") (expected target inside $skills_src_dir)")
          fi
        elif [[ -e "$dst" ]]; then
          conflicts+=("$dst exists as a regular file/directory, not a symlink")
        else
          missing+=("$dst")
        fi
      done
    done
  fi

  if [[ ${#conflicts[@]} -gt 0 ]]; then
    AGENT_CORE_ENTRIES_STATUS="conflict; not auto-running agent-core install.sh"
    printf '%s\n' "agent-core entries/skills have conflicts; not auto-running $install_script:" >&2
    local c
    for c in "${conflicts[@]}"; do
      printf '  %s\n' "$c" >&2
    done
    return 0
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    printf 'agent-core entries/skills missing; running %s\n' "$install_script"
    bash "$install_script"
    AGENT_CORE_ENTRIES_STATUS="installed via $install_script"
  else
    AGENT_CORE_ENTRIES_STATUS="entries and skills already linked to $AGENT_CORE_DIR"
  fi
}

usage() {
  cat <<'EOF'
Usage:
  install.sh [options]

Options:
  --install-dir PATH       Install/copy tools to PATH. Default: this directory.
  --root PATH              Add a scan root. Repeatable. Default: current directory.
  --max-depth N            Directory scan depth. Default: 3.
  --schedule CRON_EXPR     Cron schedule. Default: "17 * * * *".
  --scope VALUE            needs-sync|claude-only|codex-only|all. Default: all.
  --direction VALUE        claude-to-codex|codex-to-claude|bidirectional. Default: bidirectional.
  --prefer VALUE           none|claude|codex. Default: none.
  --mode VALUE             symlink|copy. Default: symlink.
  --no-codex-config        Do not patch Codex default config (approval policy,
                           sandbox mode, approvals reviewer, model + reasoning
                           effort, stream timeout/retry, model provider,
                           [features] block).
  --no-codex-here          Do not install ~/.local/bin/codex-here.
  --no-goal-plan           Do not install user-level goal-plan tools
                           (Claude /goal-plan + reviewer, Codex skill/plugin).
  --no-cc-switch-update    Do not update cc-switch-cli from the latest GitHub
                           release before Codex provider migration.
  --cc-switch-update-proxy MODE
                           Proxy mode for the cc-switch GitHub release update:
                           auto|always|never. Default: auto.
  --no-codex-provider-bucket-migration
                           Do not scan/migrate Codex history and cc-switch
                           provider templates to the custom model_provider bucket.
  --codex-provider-bucket-trusted-sources-only
                           Only migrate inferred cc-switch third-party buckets;
                           default is every non-target bucket, including openai.
  --apply-codex-provider-bucket-migration
                           Apply Codex provider bucket migration. This is the
                           default.
  --dry-run-codex-provider-bucket-migration
                           Scan only and do not write migration changes.
  --allow-running-codex-provider-bucket-migration
                           Allow applying the migration while Codex is running.
  --kill-running-codex-provider-bucket-migration
                           Terminate running Codex processes before applying.
                           This is the default.
  --no-kill-running-codex-provider-bucket-migration
                           Do not terminate Codex before migration; if Codex is
                           running, apply falls back to dry-run.
  --codex-proxy-wrapper MODE
                           Install Codex proxy wrapper: auto|always|never. Default: auto.
  --codex-proxy-url URL    Use a specific proxy URL, e.g. http://127.0.0.1:7897.
  --codex-proxy-ports LIST Space-separated proxy port candidates. Default: "7897 7890 7891 10809 10808 8080".
  --no-codex-remote-control
                           Do not run "codex remote-control start" after config.
  --no-codex-app-fast-mode
                           Do not patch Codex App/CLI Fast defaults in
                           config.toml.
  --codex-app-fast-wsl-windows MODE
                           Also patch the Windows Codex App home when running
                           from WSL: auto|always|never. Default: auto.
  --codex-desktop-connection-fast-mode MODE
                           Patch or prepare Codex Desktop so WSL/SSH
                           Connections preserve Fast serviceTier:
                           auto|always|never. Default: auto.
                           auto prepares a writable Win11 Store-app copy from
                           WSL and patches macOS Codex.app when writable.
  --no-codex-desktop-connection-fast-mode
                           Do not patch or prepare Codex Desktop bundles for
                           Connection Fast Mode.
  --launch-codex-desktop-fast-mode
                           Launch the prepared Codex Desktop after patching.
  --codex-desktop-fast-shortcut-scope MODE
                           Win11 shortcut locations: none|desktop|start-menu|both.
                           Default: both.
  --codex-desktop-fast-shortcut-name NAME
                           Win11 shortcut name. Default: Codex Fast Connections.
  --no-codex-sqlite-log-guard
                           Do not install the temporary logs_2.sqlite insert
                           guard for Codex SSD write amplification.
  --disable-codex-sqlite-log-guard
                           Remove the temporary logs_2.sqlite insert guard.
                           Use after OpenAI fixes the logging issue.
  --codex-sqlite-log-guard-wsl-windows MODE
                           Also patch Windows Codex homes when running from
                           WSL: auto|always|never. Default: auto.
  --codex-sqlite-log-guard-vacuum
                           Checkpoint WAL and VACUUM after guard changes.
                           Use only after stopping Codex processes.
  --no-claude-desktop-ssh  Do not configure existing Claude Code for Claude
                           Desktop SSH root/bypass compatibility.
  --no-registry            Do not install experiment-registry links.
  --registry-init-db       Initialize the local registry DB if missing.
  --no-cron                Write config but do not install crontab entry.
  --no-agent-core          Do not auto-verify or run ~/agent-core/scripts/install.sh.
  -h, --help               Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --root)
      SCAN_ROOTS+=("$2")
      shift 2
      ;;
    --max-depth)
      MAX_DEPTH="$2"
      shift 2
      ;;
    --schedule)
      SCHEDULE="$2"
      shift 2
      ;;
    --scope)
      SCOPE="$2"
      shift 2
      ;;
    --direction)
      DIRECTION="$2"
      shift 2
      ;;
    --prefer)
      PREFER="$2"
      shift 2
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --no-cron)
      INSTALL_CRON=0
      shift
      ;;
    --no-codex-config)
      INSTALL_CODEX_CONFIG=0
      shift
      ;;
    --no-codex-here)
      INSTALL_CODEX_HERE=0
      shift
      ;;
    --no-goal-plan)
      INSTALL_GOAL_PLAN=0
      shift
      ;;
    --no-cc-switch-update)
      INSTALL_CC_SWITCH_CLI_UPDATE=0
      shift
      ;;
    --cc-switch-update-proxy)
      CC_SWITCH_UPDATE_PROXY_MODE="$2"
      shift 2
      ;;
    --no-codex-provider-bucket-migration)
      INSTALL_CODEX_PROVIDER_BUCKET_MIGRATION=0
      shift
      ;;
    --codex-provider-bucket-trusted-sources-only)
      CODEX_PROVIDER_BUCKET_ALL_NON_TARGET=0
      shift
      ;;
    --apply-codex-provider-bucket-migration)
      APPLY_CODEX_PROVIDER_BUCKET_MIGRATION=1
      shift
      ;;
    --dry-run-codex-provider-bucket-migration)
      APPLY_CODEX_PROVIDER_BUCKET_MIGRATION=0
      shift
      ;;
    --allow-running-codex-provider-bucket-migration)
      CODEX_PROVIDER_BUCKET_ALLOW_RUNNING=1
      shift
      ;;
    --kill-running-codex-provider-bucket-migration)
      CODEX_PROVIDER_BUCKET_KILL_RUNNING=1
      APPLY_CODEX_PROVIDER_BUCKET_MIGRATION=1
      shift
      ;;
    --no-kill-running-codex-provider-bucket-migration)
      CODEX_PROVIDER_BUCKET_KILL_RUNNING=0
      shift
      ;;
    --codex-proxy-wrapper)
      INSTALL_CODEX_PROXY_WRAPPER="$2"
      shift 2
      ;;
    --codex-proxy-url)
      CODEX_PROXY_URL="$2"
      shift 2
      ;;
    --codex-proxy-ports)
      CODEX_PROXY_PORTS="$2"
      shift 2
      ;;
    --no-codex-remote-control)
      INSTALL_CODEX_REMOTE_CONTROL=0
      shift
      ;;
    --no-codex-app-fast-mode)
      INSTALL_CODEX_APP_FAST_MODE=0
      shift
      ;;
    --codex-app-fast-wsl-windows)
      CODEX_APP_FAST_MODE_INCLUDE_WSL_WINDOWS="$2"
      shift 2
      ;;
    --codex-desktop-connection-fast-mode)
      INSTALL_CODEX_DESKTOP_CONNECTION_FAST_MODE="$2"
      shift 2
      ;;
    --no-codex-desktop-connection-fast-mode)
      INSTALL_CODEX_DESKTOP_CONNECTION_FAST_MODE=never
      shift
      ;;
    --launch-codex-desktop-fast-mode)
      CODEX_DESKTOP_CONNECTION_FAST_MODE_LAUNCH=1
      shift
      ;;
    --codex-desktop-fast-shortcut-scope)
      CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_SCOPE="$2"
      shift 2
      ;;
    --codex-desktop-fast-shortcut-name)
      CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_NAME="$2"
      shift 2
      ;;
    --no-codex-sqlite-log-guard)
      INSTALL_CODEX_SQLITE_LOG_GUARD=0
      shift
      ;;
    --disable-codex-sqlite-log-guard)
      INSTALL_CODEX_SQLITE_LOG_GUARD=1
      CODEX_SQLITE_LOG_GUARD_MODE=disable
      shift
      ;;
    --codex-sqlite-log-guard-wsl-windows)
      CODEX_SQLITE_LOG_GUARD_INCLUDE_WSL_WINDOWS="$2"
      shift 2
      ;;
    --codex-sqlite-log-guard-vacuum)
      CODEX_SQLITE_LOG_GUARD_VACUUM=1
      shift
      ;;
    --no-claude-desktop-ssh)
      INSTALL_CLAUDE_DESKTOP_SSH=0
      shift
      ;;
    --no-registry)
      INSTALL_REGISTRY=0
      shift
      ;;
    --registry-init-db)
      REGISTRY_INIT_DB=1
      shift
      ;;
    --no-agent-core)
      INSTALL_AGENT_CORE_ENTRIES=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ${#SCAN_ROOTS[@]} -eq 0 ]]; then
  SCAN_ROOTS+=("$(pwd)")
fi

mkdir -p "$INSTALL_DIR"
SOURCE_REAL="$(cd "$SOURCE_DIR" && pwd -P)"
INSTALL_REAL="$(mkdir -p "$INSTALL_DIR" && cd "$INSTALL_DIR" && pwd -P)"

if [[ "$SOURCE_REAL" != "$INSTALL_REAL" ]]; then
  cp "$SOURCE_DIR/sync_agent_context.py" "$INSTALL_REAL/"
  cp "$SOURCE_DIR/sync_agent_context_cron.sh" "$INSTALL_REAL/"
  cp "$SOURCE_DIR/codex_project_memory.py" "$INSTALL_REAL/"
  cp "$SOURCE_DIR/migrate_codex_provider_bucket.py" "$INSTALL_REAL/"
  cp "$SOURCE_DIR/install.sh" "$INSTALL_REAL/"
  [[ -d "$SOURCE_DIR/bin" ]] && cp -R "$SOURCE_DIR/bin" "$INSTALL_REAL/"
  [[ -d "$SOURCE_DIR/scripts" ]] && cp -R "$SOURCE_DIR/scripts" "$INSTALL_REAL/"
  [[ -f "$SOURCE_DIR/README.md" ]] && cp "$SOURCE_DIR/README.md" "$INSTALL_REAL/"
  [[ -d "$SOURCE_DIR/docs" ]] && cp -R "$SOURCE_DIR/docs" "$INSTALL_REAL/"
  [[ -d "$SOURCE_DIR/experiment_registry" ]] && cp -R "$SOURCE_DIR/experiment_registry" "$INSTALL_REAL/"
  [[ -d "$SOURCE_DIR/goal_plan" ]] && cp -R "$SOURCE_DIR/goal_plan" "$INSTALL_REAL/"
  [[ -f "$SOURCE_DIR/agent_context_sync.config.example.json" ]] && cp "$SOURCE_DIR/agent_context_sync.config.example.json" "$INSTALL_REAL/"
fi

chmod +x "$INSTALL_REAL/sync_agent_context.py" "$INSTALL_REAL/sync_agent_context_cron.sh" "$INSTALL_REAL/codex_project_memory.py" "$INSTALL_REAL/migrate_codex_provider_bucket.py" "$INSTALL_REAL/install.sh"
if [[ -d "$INSTALL_REAL/bin" ]]; then
  chmod +x "$INSTALL_REAL"/bin/*
fi
if [[ -d "$INSTALL_REAL/scripts" ]]; then
  chmod +x "$INSTALL_REAL"/scripts/*
fi
if [[ -d "$INSTALL_REAL/experiment_registry" ]]; then
  chmod +x "$INSTALL_REAL/experiment_registry/install_registry_links.sh" "$INSTALL_REAL/experiment_registry/validate_registry_install.sh"
fi
mkdir -p "$INSTALL_REAL/logs"
configure_tmux_mouse_mode
configure_local_bin_path
configure_claude_desktop_ssh
update_cc_switch_cli
if [[ "$INSTALL_CODEX_HERE" -eq 1 ]]; then
  install_codex_here
fi
if [[ "$INSTALL_CODEX_CONFIG" -eq 1 ]]; then
  configure_codex_defaults
  normalize_cc_switch_codex_provider_templates
  sync_codex_config_from_cc_switch_current
  normalize_codex_provider_auth
  configure_codex_features
  configure_codex_app_fast_mode
  check_codex_fast_mode
  setup_codex_desktop_connection_fast_mode
  configure_codex_sqlite_log_guard
  configure_codex_project_hooks_features
  if [[ "$INSTALL_CODEX_PROVIDER_BUCKET_MIGRATION" -eq 1 ]]; then
    run_codex_provider_bucket_migration
  fi
  configure_codex_proxy_wrapper
  start_codex_remote_control
fi
if [[ "$INSTALL_AGENT_CORE_ENTRIES" -eq 1 ]]; then
  verify_agent_core_entries
fi
if [[ "$INSTALL_GOAL_PLAN" -eq 1 ]]; then
  install_goal_plan_tools
fi

select_python_bin

"$PYTHON_BIN" - "$INSTALL_REAL/agent_context_sync.config.json" "$MAX_DEPTH" "$SCOPE" "$DIRECTION" "$PREFER" "$MODE" "${SCAN_ROOTS[@]}" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
max_depth = int(sys.argv[2])
scope = sys.argv[3]
direction = sys.argv[4]
prefer = sys.argv[5]
mode = sys.argv[6]
roots = [str(Path(root).expanduser().resolve()) for root in sys.argv[7:]]

config = {
    "scan_roots": roots,
    "max_depth": max_depth,
    "scope": scope,
    "direction": direction,
    "prefer": prefer,
    "mode": mode,
    "include_config_only": False,
}
config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
PY

if [[ "$INSTALL_CRON" -eq 1 ]]; then
  CRON_CMD="$INSTALL_REAL/sync_agent_context_cron.sh"
  (crontab -l 2>/dev/null | grep -v 'sync_agent_context_cron.sh' || true; printf '%s %s\n' "$SCHEDULE" "$CRON_CMD") | crontab -
fi

if [[ "$INSTALL_REGISTRY" -eq 1 && -x "$INSTALL_REAL/experiment_registry/install_registry_links.sh" ]]; then
  REGISTRY_ARGS=()
  if [[ "$REGISTRY_INIT_DB" -eq 1 ]]; then
    REGISTRY_ARGS+=(--init-db)
  fi
  "$INSTALL_REAL/experiment_registry/install_registry_links.sh" "${REGISTRY_ARGS[@]}"
fi

echo "Installed agent context sync tools in $INSTALL_REAL"
echo "Config: $INSTALL_REAL/agent_context_sync.config.json"
echo "tmux mouse mode: ${TMUX_CONF:-$HOME/.tmux.conf}"
echo "agent-tools PATH: $LOCAL_BIN_PATH_STATUS"
echo "Claude Desktop SSH compatibility: $CLAUDE_DESKTOP_SSH_STATUS"
if [[ "$INSTALL_CC_SWITCH_CLI_UPDATE" -eq 1 ]]; then
  if version="$(cc_switch_version)"; then
    echo "cc-switch-cli updated: $version"
  else
    echo "cc-switch-cli update attempted, but cc-switch is not usable on PATH."
  fi
else
  echo "cc-switch-cli not updated (--no-cc-switch-update)."
fi
if [[ -n "$CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS" ]]; then
  echo "cc-switch Codex provider sync: $CC_SWITCH_CODEX_PROVIDER_SYNC_STATUS"
fi
if [[ "$INSTALL_CODEX_CONFIG" -eq 1 ]]; then
  echo "Codex approval policy: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_APPROVAL_POLICY}"
  echo "Codex sandbox mode: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_SANDBOX_MODE}"
  echo "Codex approvals reviewer: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_APPROVALS_REVIEWER}"
  echo "Codex model: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_MODEL} (reasoning: ${CODEX_MODEL_REASONING_EFFORT})"
  echo "Codex service tier: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_SERVICE_TIER}"
  echo "Codex stream idle timeout: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_STREAM_IDLE_TIMEOUT_MS} ms"
  echo "Codex stream max retries: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_STREAM_MAX_RETRIES}"
  echo "Codex model provider: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_MODEL_PROVIDER_ID} (HTTPS, no WebSocket)"
  echo "Codex [features]: fast_mode=${CODEX_FEATURE_FAST_MODE} hooks=${CODEX_FEATURE_HOOKS} memories=${CODEX_FEATURE_MEMORIES} goals=${CODEX_FEATURE_GOALS} terminal_resize_reflow=${CODEX_FEATURE_TERMINAL_RESIZE_REFLOW} remote_control=${CODEX_FEATURE_REMOTE_CONTROL}"
  echo "Codex App Fast mode config: enabled=${INSTALL_CODEX_APP_FAST_MODE}, wsl_windows=${CODEX_APP_FAST_MODE_INCLUDE_WSL_WINDOWS}"
  echo "Codex Desktop Connection Fast mode: mode=${INSTALL_CODEX_DESKTOP_CONNECTION_FAST_MODE}, status=${CODEX_DESKTOP_CONNECTION_FAST_MODE_STATUS}"
  echo "Codex Desktop Fast shortcut: scope=${CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_SCOPE}, name=${CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_NAME}"
  echo "Codex SQLite log guard: ${CODEX_SQLITE_LOG_GUARD_STATUS}"
  if [[ "$INSTALL_CODEX_PROVIDER_BUCKET_MIGRATION" -eq 1 ]]; then
    echo "Codex provider bucket migration: target=${CODEX_MODEL_PROVIDER_ID}, apply=${APPLY_CODEX_PROVIDER_BUCKET_MIGRATION}, all_non_target=${CODEX_PROVIDER_BUCKET_ALL_NON_TARGET}"
  else
    echo "Codex provider bucket migration not run (--no-codex-provider-bucket-migration)."
  fi
  echo "Codex proxy wrapper mode: $INSTALL_CODEX_PROXY_WRAPPER"
  echo "Codex proxy port candidates: $CODEX_PROXY_PORTS"
else
  echo "Codex App Fast mode config: enabled=${INSTALL_CODEX_APP_FAST_MODE}, wsl_windows=${CODEX_APP_FAST_MODE_INCLUDE_WSL_WINDOWS}"
  configure_codex_app_fast_mode
  check_codex_fast_mode
  setup_codex_desktop_connection_fast_mode
  configure_codex_sqlite_log_guard
  echo "Codex Desktop Connection Fast mode: mode=${INSTALL_CODEX_DESKTOP_CONNECTION_FAST_MODE}, status=${CODEX_DESKTOP_CONNECTION_FAST_MODE_STATUS}"
  echo "Codex Desktop Fast shortcut: scope=${CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_SCOPE}, name=${CODEX_DESKTOP_CONNECTION_FAST_MODE_SHORTCUT_NAME}"
  echo "Codex SQLite log guard: ${CODEX_SQLITE_LOG_GUARD_STATUS}"
  echo "Codex config not changed (--no-codex-config)."
fi
if [[ "$INSTALL_CODEX_HERE" -eq 1 ]]; then
  echo "codex-here: ${CODEX_HERE_PATH:-$HOME/.local/bin/codex-here}"
else
  echo "codex-here not installed (--no-codex-here)."
fi
if [[ "$INSTALL_CRON" -eq 1 ]]; then
  echo "Cron: $SCHEDULE $INSTALL_REAL/sync_agent_context_cron.sh"
else
  echo "Cron not installed (--no-cron)."
fi
if [[ "$INSTALL_REGISTRY" -eq 1 ]]; then
  echo "Experiment registry links checked from: $INSTALL_REAL/experiment_registry"
else
  echo "Experiment registry links not installed (--no-registry)."
fi
if [[ "$INSTALL_AGENT_CORE_ENTRIES" -eq 1 ]]; then
  echo "agent-core entries ($AGENT_CORE_DIR): ${AGENT_CORE_ENTRIES_STATUS}"
else
  echo "agent-core entries not checked (--no-agent-core)."
fi
if [[ "$INSTALL_GOAL_PLAN" -eq 1 ]]; then
  echo "goal-plan tools: ${GOAL_PLAN_STATUS}"
else
  echo "goal-plan tools not installed (--no-goal-plan)."
fi

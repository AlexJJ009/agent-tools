#!/usr/bin/env bash
# Shared helpers for scripts/install.sh and scripts/setup/*.sh. Source it; do not run it.

SOURCE_DIR="${SOURCE_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-}"
CODEX_TARGET_GUARD_STATUS=""

# Read by more than one script: Codex provider and context defaults (codex.sh,
# cc-switch.sh) and the proxy candidates the Codex wrapper and the cc-switch
# update both probe.
CODEX_MODEL_PROVIDER_ID="${CODEX_MODEL_PROVIDER_ID:-custom}"
CODEX_SERVICE_TIER="${CODEX_SERVICE_TIER:-priority}"
CODEX_MODEL_CONTEXT_WINDOW="${CODEX_MODEL_CONTEXT_WINDOW:-500000}"
CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT="${CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT:-430000}"
CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE="${CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE:-total}"
CODEX_PROXY_HOST="${CODEX_PROXY_HOST:-127.0.0.1}"
CODEX_PROXY_PORTS="${CODEX_PROXY_PORTS:-7897 7890 7891 10809 10808 8080}"
CODEX_PROXY_CONNECT_TIMEOUT="${CODEX_PROXY_CONNECT_TIMEOUT:-2}"
CODEX_PROXY_MAX_TIME="${CODEX_PROXY_MAX_TIME:-6}"

select_python_bin() {
  local candidate

  if [[ -n "$PYTHON_BIN" ]]; then
    return
  fi

  # Prefer 3.11+; 3.10 still works for the installer helpers.
  # uv-managed interpreters count when the system one is older;
  # glob them read-only, since running uv may write its cache before the guard.
  local minor uv_dir="${UV_PYTHON_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/uv/python}"
  local -a uv_pythons=()
  shopt -s nullglob
  uv_pythons=("$uv_dir"/cpython-3.*/bin/python3)
  shopt -u nullglob
  for minor in 11 10; do
    for candidate in python3.13 python3.12 python3.11 python3.10 python3 python ${uv_pythons[@]+"${uv_pythons[@]}"}; do
      if command -v "$candidate" >/dev/null 2>&1 && "$candidate" - "$minor" <<'PY' >/dev/null 2>&1; then
import sys
raise SystemExit(0 if sys.version_info >= (3, int(sys.argv[1])) else 1)
PY
        PYTHON_BIN="$candidate"
        if [[ "$minor" == 10 ]]; then
          echo "WARNING: no Python 3.11+ found; using $PYTHON_BIN." >&2
        fi
        return 0
      fi
    done
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

run_codex_target_guard() {
  local phase="$1"
  local script="${INSTALL_REAL:-$SOURCE_DIR}/scripts/codex_target_guard.py"
  local codex_home="${CODEX_HOME:-$HOME/.codex}"
  local cc_switch_db="${CC_SWITCH_DB_PATH:-$HOME/.cc-switch/cc-switch.db}"
  local -a args=(
    --platform auto
    --codex-home "$codex_home"
    --cc-switch-db "$cc_switch_db"
    --expected-user "$(id -un)"
    --path-only
    --skip-cc-switch-read-check
    --allow-missing-cc-switch
  )

  if [[ "$phase" == "before" ]]; then
    args+=(--allow-missing-config --allow-missing-cc-switch)
  fi
  if [[ ! -f "$script" && -f "$SOURCE_DIR/scripts/codex_target_guard.py" ]]; then
    script="$SOURCE_DIR/scripts/codex_target_guard.py"
  fi
  if [[ ! -f "$script" ]]; then
    echo "missing Codex target guard: $script" >&2
    return 1
  fi
  select_python_bin
  "$PYTHON_BIN" "$script" "${args[@]}"
  CODEX_TARGET_GUARD_STATUS="${phase}: PASS (${codex_home})"
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
in_model_provider = False
in_target_provider = False
inserted_auth = False
inserted_websockets = False

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

def insert_websockets():
    global inserted_websockets
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

new_text = "\n".join(cleaned).rstrip() + "\n"
if new_text != text:
    path.write_text(new_text, encoding="utf-8")
PY
}

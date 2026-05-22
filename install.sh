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
INSTALL_CODEX_PROXY_WRAPPER="${INSTALL_CODEX_PROXY_WRAPPER:-auto}"
INSTALL_CODEX_REMOTE_CONTROL="${INSTALL_CODEX_REMOTE_CONTROL:-1}"
CODEX_STREAM_IDLE_TIMEOUT_MS="${CODEX_STREAM_IDLE_TIMEOUT_MS:-1800000}"
CODEX_STREAM_MAX_RETRIES="${CODEX_STREAM_MAX_RETRIES:-20}"
CODEX_MODEL_PROVIDER_ID="${CODEX_MODEL_PROVIDER_ID:-openai-no-ws}"
CODEX_APPROVAL_POLICY="${CODEX_APPROVAL_POLICY:-on-request}"
CODEX_SANDBOX_MODE="${CODEX_SANDBOX_MODE:-workspace-write}"
CODEX_APPROVALS_REVIEWER="${CODEX_APPROVALS_REVIEWER:-guardian_subagent}"
CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
CODEX_MODEL_REASONING_EFFORT="${CODEX_MODEL_REASONING_EFFORT:-high}"
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
LOCAL_BIN_PATH_STATUS=""
SCAN_ROOTS=()
PYTHON_BIN="${PYTHON_BIN:-}"

select_python_bin() {
  if [[ -n "$PYTHON_BIN" ]]; then
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    PYTHON_BIN="python"
  fi
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
}

configure_codex_defaults() {
  local codex_config="${CODEX_HOME:-$HOME/.codex}/config.toml"

  select_python_bin
  "$PYTHON_BIN" - "$codex_config" "$CODEX_STREAM_IDLE_TIMEOUT_MS" "$CODEX_STREAM_MAX_RETRIES" "$CODEX_MODEL_PROVIDER_ID" "$CODEX_APPROVAL_POLICY" "$CODEX_SANDBOX_MODE" "$CODEX_APPROVALS_REVIEWER" "$CODEX_MODEL" "$CODEX_MODEL_REASONING_EFFORT" <<'PY'
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

path.parent.mkdir(parents=True, exist_ok=True)
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()

first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
preamble = lines[:first_table]
rest = lines[first_table:]

managed_top_level = {
    "stream_idle_timeout_ms",
    "stream_max_retries",
    "model_provider",
    "approval_policy",
    "sandbox_mode",
    "approvals_reviewer",
    "model",
    "model_reasoning_effort",
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
kept.append(f"stream_idle_timeout_ms = {timeout}")
kept.append(f"stream_max_retries = {retries}")
kept.append(f'model_provider = "{provider_id}"')

provider_header = f"[model_providers.{provider_id}]"
filtered_rest = []
i = 0
while i < len(rest):
    if rest[i].strip() == provider_header:
        i += 1
        while i < len(rest) and not rest[i].lstrip().startswith("["):
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
      "$CODEX_FEATURE_HOOKS" \
      "$CODEX_FEATURE_MEMORIES" \
      "$CODEX_FEATURE_GOALS" \
      "$CODEX_FEATURE_TERMINAL_RESIZE_REFLOW" \
      "$CODEX_FEATURE_REMOTE_CONTROL" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1]).expanduser()

FEATURE_KEYS = [
    ("hooks", sys.argv[2]),
    ("memories", sys.argv[3]),
    ("goals", sys.argv[4]),
    ("terminal_resize_reflow", sys.argv[5]),
    ("remote_control", sys.argv[6]),
]

ALLOWED_VALUES = {"true", "false"}
for name, value in FEATURE_KEYS:
    if value not in ALLOWED_VALUES:
        raise SystemExit(f"invalid CODEX_FEATURE_{name.upper()}: {value} (expected true|false)")

managed = {name for name, _ in FEATURE_KEYS} | {"codex_hooks", "remote_connections"}

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

  local missing=()
  local conflicts=()
  local pair dst src current expected

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

  if [[ ${#conflicts[@]} -gt 0 ]]; then
    AGENT_CORE_ENTRIES_STATUS="conflict; not auto-running agent-core install.sh"
    printf '%s\n' "agent-core entries have conflicts; not auto-running $install_script:" >&2
    local c
    for c in "${conflicts[@]}"; do
      printf '  %s\n' "$c" >&2
    done
    return 0
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    printf 'agent-core entries missing; running %s\n' "$install_script"
    bash "$install_script"
    AGENT_CORE_ENTRIES_STATUS="installed via $install_script"
  else
    AGENT_CORE_ENTRIES_STATUS="already linked to $AGENT_CORE_DIR"
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
  --codex-proxy-wrapper MODE
                           Install Codex proxy wrapper: auto|always|never. Default: auto.
  --codex-proxy-url URL    Use a specific proxy URL, e.g. http://127.0.0.1:7897.
  --codex-proxy-ports LIST Space-separated proxy port candidates. Default: "7897 7890 7891 10809 10808 8080".
  --no-codex-remote-control
                           Do not run "codex remote-control start" after config.
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
  cp "$SOURCE_DIR/install.sh" "$INSTALL_REAL/"
  [[ -d "$SOURCE_DIR/bin" ]] && cp -R "$SOURCE_DIR/bin" "$INSTALL_REAL/"
  [[ -f "$SOURCE_DIR/README.md" ]] && cp "$SOURCE_DIR/README.md" "$INSTALL_REAL/"
  [[ -d "$SOURCE_DIR/docs" ]] && cp -R "$SOURCE_DIR/docs" "$INSTALL_REAL/"
  [[ -d "$SOURCE_DIR/experiment_registry" ]] && cp -R "$SOURCE_DIR/experiment_registry" "$INSTALL_REAL/"
  [[ -f "$SOURCE_DIR/agent_context_sync.config.example.json" ]] && cp "$SOURCE_DIR/agent_context_sync.config.example.json" "$INSTALL_REAL/"
fi

chmod +x "$INSTALL_REAL/sync_agent_context.py" "$INSTALL_REAL/sync_agent_context_cron.sh" "$INSTALL_REAL/codex_project_memory.py" "$INSTALL_REAL/install.sh"
if [[ -d "$INSTALL_REAL/bin" ]]; then
  chmod +x "$INSTALL_REAL"/bin/*
fi
if [[ -d "$INSTALL_REAL/experiment_registry" ]]; then
  chmod +x "$INSTALL_REAL/experiment_registry/install_registry_links.sh" "$INSTALL_REAL/experiment_registry/validate_registry_install.sh"
fi
mkdir -p "$INSTALL_REAL/logs"
configure_tmux_mouse_mode
configure_local_bin_path
if [[ "$INSTALL_CODEX_HERE" -eq 1 ]]; then
  install_codex_here
fi
if [[ "$INSTALL_CODEX_CONFIG" -eq 1 ]]; then
  configure_codex_defaults
  configure_codex_features
  configure_codex_project_hooks_features
  configure_codex_proxy_wrapper
  start_codex_remote_control
fi
if [[ "$INSTALL_AGENT_CORE_ENTRIES" -eq 1 ]]; then
  verify_agent_core_entries
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
if [[ "$INSTALL_CODEX_CONFIG" -eq 1 ]]; then
  echo "Codex approval policy: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_APPROVAL_POLICY}"
  echo "Codex sandbox mode: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_SANDBOX_MODE}"
  echo "Codex approvals reviewer: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_APPROVALS_REVIEWER}"
  echo "Codex model: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_MODEL} (reasoning: ${CODEX_MODEL_REASONING_EFFORT})"
  echo "Codex stream idle timeout: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_STREAM_IDLE_TIMEOUT_MS} ms"
  echo "Codex stream max retries: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_STREAM_MAX_RETRIES}"
  echo "Codex model provider: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_MODEL_PROVIDER_ID} (HTTPS, no WebSocket)"
  echo "Codex [features]: hooks=${CODEX_FEATURE_HOOKS} memories=${CODEX_FEATURE_MEMORIES} goals=${CODEX_FEATURE_GOALS} terminal_resize_reflow=${CODEX_FEATURE_TERMINAL_RESIZE_REFLOW} remote_control=${CODEX_FEATURE_REMOTE_CONTROL}"
  echo "Codex proxy wrapper mode: $INSTALL_CODEX_PROXY_WRAPPER"
  echo "Codex proxy port candidates: $CODEX_PROXY_PORTS"
else
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

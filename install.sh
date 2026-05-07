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
CODEX_STREAM_IDLE_TIMEOUT_MS="${CODEX_STREAM_IDLE_TIMEOUT_MS:-900000}"
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

configure_codex_stream_idle_timeout() {
  local codex_config="${CODEX_HOME:-$HOME/.codex}/config.toml"

  select_python_bin
  "$PYTHON_BIN" - "$codex_config" "$CODEX_STREAM_IDLE_TIMEOUT_MS" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1]).expanduser()
timeout = sys.argv[2]
if not timeout.isdigit() or int(timeout) <= 0:
    raise SystemExit(f"invalid CODEX_STREAM_IDLE_TIMEOUT_MS: {timeout}")

path.parent.mkdir(parents=True, exist_ok=True)
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()

first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
preamble = lines[:first_table]
rest = lines[first_table:]

kept = []
for line in preamble:
    stripped = line.strip()
    key = stripped.split("=", 1)[0].strip() if "=" in stripped else None
    if key == "stream_idle_timeout_ms":
        continue
    kept.append(line)

if kept and kept[-1].strip():
    kept.append("")
kept.append(f"stream_idle_timeout_ms = {timeout}")

if rest:
    kept.append("")
    kept.extend(rest)

new_text = "\n".join(kept).rstrip() + "\n"
if new_text != text:
    path.write_text(new_text, encoding="utf-8")
PY
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
  --no-codex-config        Do not patch Codex stream idle timeout.
  --no-registry            Do not install experiment-registry links.
  --registry-init-db       Initialize the local registry DB if missing.
  --no-cron                Write config but do not install crontab entry.
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
    --no-registry)
      INSTALL_REGISTRY=0
      shift
      ;;
    --registry-init-db)
      REGISTRY_INIT_DB=1
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
  [[ -f "$SOURCE_DIR/README.md" ]] && cp "$SOURCE_DIR/README.md" "$INSTALL_REAL/"
  [[ -d "$SOURCE_DIR/docs" ]] && cp -R "$SOURCE_DIR/docs" "$INSTALL_REAL/"
  [[ -d "$SOURCE_DIR/experiment_registry" ]] && cp -R "$SOURCE_DIR/experiment_registry" "$INSTALL_REAL/"
  [[ -f "$SOURCE_DIR/agent_context_sync.config.example.json" ]] && cp "$SOURCE_DIR/agent_context_sync.config.example.json" "$INSTALL_REAL/"
fi

chmod +x "$INSTALL_REAL/sync_agent_context.py" "$INSTALL_REAL/sync_agent_context_cron.sh" "$INSTALL_REAL/codex_project_memory.py" "$INSTALL_REAL/install.sh"
if [[ -d "$INSTALL_REAL/experiment_registry" ]]; then
  chmod +x "$INSTALL_REAL/experiment_registry/install_registry_links.sh" "$INSTALL_REAL/experiment_registry/validate_registry_install.sh"
fi
mkdir -p "$INSTALL_REAL/logs"
configure_tmux_mouse_mode
if [[ "$INSTALL_CODEX_CONFIG" -eq 1 ]]; then
  configure_codex_stream_idle_timeout
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
if [[ "$INSTALL_CODEX_CONFIG" -eq 1 ]]; then
  echo "Codex stream idle timeout: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_STREAM_IDLE_TIMEOUT_MS} ms"
else
  echo "Codex config not changed (--no-codex-config)."
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

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
SCAN_ROOTS=()

configure_tmux_mouse_mode() {
  local tmux_conf="${TMUX_CONF:-$HOME/.tmux.conf}"

  python - "$tmux_conf" <<'PY'
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
  [[ -f "$SOURCE_DIR/agent_context_sync.config.example.json" ]] && cp "$SOURCE_DIR/agent_context_sync.config.example.json" "$INSTALL_REAL/"
fi

chmod +x "$INSTALL_REAL/sync_agent_context.py" "$INSTALL_REAL/sync_agent_context_cron.sh" "$INSTALL_REAL/codex_project_memory.py" "$INSTALL_REAL/install.sh"
mkdir -p "$INSTALL_REAL/logs"
configure_tmux_mouse_mode

python - "$INSTALL_REAL/agent_context_sync.config.json" "$MAX_DEPTH" "$SCOPE" "$DIRECTION" "$PREFER" "$MODE" "${SCAN_ROOTS[@]}" <<'PY'
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

echo "Installed agent context sync tools in $INSTALL_REAL"
echo "Config: $INSTALL_REAL/agent_context_sync.config.json"
echo "tmux mouse mode: ${TMUX_CONF:-$HOME/.tmux.conf}"
if [[ "$INSTALL_CRON" -eq 1 ]]; then
  echo "Cron: $SCHEDULE $INSTALL_REAL/sync_agent_context_cron.sh"
else
  echo "Cron not installed (--no-cron)."
fi

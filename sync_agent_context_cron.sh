#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TOOL="${AGENT_CONTEXT_SYNC_TOOL:-$SCRIPT_DIR/sync_agent_context.py}"
CONFIG="${AGENT_CONTEXT_SYNC_CONFIG:-$SCRIPT_DIR/agent_context_sync.config.json}"
LOG_DAYS="${AGENT_CONTEXT_SYNC_LOG_DAYS:-30}"
LOCK_FILE="/tmp/agent-context-sync.lock"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    PYTHON_BIN="python"
  fi
fi

# Logs are application data: they live in the data root, not the software install root.
if [[ -n "${AGENT_CONTEXT_SYNC_LOG_DIR:-}" ]]; then
  LOG_DIR="$AGENT_CONTEXT_SYNC_LOG_DIR"
elif data_root="$("$PYTHON_BIN" "$SCRIPT_DIR/scripts/install_layout.py" data-root 2>/dev/null)" && [[ -n "$data_root" ]]; then
  LOG_DIR="$data_root/logs"
else
  LOG_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/agent-tools/logs"
fi
if [[ ! "$LOG_DAYS" =~ ^[0-9]+$ ]]; then
  echo "AGENT_CONTEXT_SYNC_LOG_DAYS must be a whole number of days: $LOG_DAYS" >&2
  exit 2
fi

mkdir -p "$LOG_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  exit 0
fi

# Daily logs are kept for LOG_DAYS days; 0 keeps them all.
if [[ "$LOG_DAYS" -gt 0 ]]; then
  find "$LOG_DIR" -maxdepth 1 -type f -name 'sync-*.log' -mtime "+$((LOG_DAYS - 1))" -delete
fi

LOG_FILE="$LOG_DIR/sync-$(date +%Y%m%d).log"

{
  echo "[$(date -Is)] agent context sync start config=$CONFIG"
  "$PYTHON_BIN" "$TOOL" heartbeat --config "$CONFIG" "$@"
  echo "[$(date -Is)] agent context sync done"
} >>"$LOG_FILE" 2>&1

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TOOL="${AGENT_CONTEXT_SYNC_TOOL:-$SCRIPT_DIR/sync_agent_context.py}"
CONFIG="${AGENT_CONTEXT_SYNC_CONFIG:-$SCRIPT_DIR/agent_context_sync.config.json}"
LOG_DIR="${AGENT_CONTEXT_SYNC_LOG_DIR:-$SCRIPT_DIR/logs}"
LOCK_FILE="/tmp/agent-context-sync.lock"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    PYTHON_BIN="python"
  fi
fi

mkdir -p "$LOG_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  exit 0
fi

LOG_FILE="$LOG_DIR/sync-$(date +%Y%m%d).log"

{
  echo "[$(date -Is)] agent context sync start config=$CONFIG"
  "$PYTHON_BIN" "$TOOL" heartbeat --config "$CONFIG" "$@"
  echo "[$(date -Is)] agent context sync done"
} >>"$LOG_FILE" 2>&1

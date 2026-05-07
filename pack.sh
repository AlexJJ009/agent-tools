#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
PACKAGE_NAME="$(basename "$SCRIPT_DIR")"
OUT="${1:-$PARENT_DIR/agent-tools-portable.tar.gz}"

tar \
  --exclude="$PACKAGE_NAME/logs" \
  --exclude="$PACKAGE_NAME/__pycache__" \
  --exclude="*/__pycache__" \
  --exclude="*.pyc" \
  --exclude="*.sqlite" \
  --exclude="*.sqlite3" \
  --exclude="$PACKAGE_NAME/*.tar.gz" \
  -C "$PARENT_DIR" \
  -czf "$OUT" \
  "$PACKAGE_NAME"

echo "$OUT"

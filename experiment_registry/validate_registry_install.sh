#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DB_PATH="${EXPERIMENT_REGISTRY_DB:-/data-1/experiment_registry/experiment_registry.sqlite}"

"$SCRIPT_DIR/install_registry_links.sh" --check --db "$DB_PATH"

if [[ ! -f "$DB_PATH" ]]; then
  echo "missing_db: $DB_PATH" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/registry_cli.py" --db "$DB_PATH" summary >/dev/null
python3 "$SCRIPT_DIR/registry_cli.py" --db "$DB_PATH" query --list >/dev/null

echo "registry_install_ok: $DB_PATH"

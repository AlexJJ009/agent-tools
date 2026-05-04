#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DB_PATH="${EXPERIMENT_REGISTRY_DB:-/data-1/experiment_registry/experiment_registry.sqlite}"

# Historical name kept for compatibility. The canonical registry tooling now
# lives in agent-tools; deployment means installing project-local symlinks and
# optionally initializing the machine-local database.
exec "$SCRIPT_DIR/install_registry_links.sh" --init-db --db "$DB_PATH" "$@"

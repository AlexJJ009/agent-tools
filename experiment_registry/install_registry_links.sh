#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AGENT_TOOLS_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

DB_DIR="${EXPERIMENT_REGISTRY_DIR:-/data-1/experiment_registry}"
DB_PATH="${EXPERIMENT_REGISTRY_DB:-${DB_DIR}/experiment_registry.sqlite}"
INIT_DB=0
FORCE=0
CHECK_ONLY=0

DPO_REPO="${DPO_REPO:-/data-1/dpo-experiment}"
VERL_REPO="${VERL_REPO:-/data-1/verl07/verl}"

usage() {
  cat <<'EOF'
Usage:
  install_registry_links.sh [options]

Options:
  --init-db          Initialize the SQLite database if it does not exist.
  --db PATH          Registry database path. Default: /data-1/experiment_registry/experiment_registry.sqlite.
  --dpo-repo PATH    DPO repo path. Default: /data-1/dpo-experiment.
  --verl-repo PATH   verl repo path. Default: /data-1/verl07/verl.
  --force            Replace existing registry copies/directories with symlinks.
  --check            Only validate expected paths; do not modify.
  -h, --help         Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --init-db)
      INIT_DB=1
      shift
      ;;
    --db)
      DB_PATH="$2"
      DB_DIR="$(dirname "$DB_PATH")"
      shift 2
      ;;
    --dpo-repo)
      DPO_REPO="$2"
      shift 2
      ;;
    --verl-repo)
      VERL_REPO="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --check)
      CHECK_ONLY=1
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

link_path() {
  local target="$1"
  local link="$2"
  local parent
  parent="$(dirname "$link")"

  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    if [[ ! -L "$link" ]]; then
      echo "not_symlink: $link" >&2
      return 1
    fi
    local resolved
    resolved="$(readlink -f "$link")"
    if [[ "$resolved" != "$target" ]]; then
      echo "wrong_target: $link -> $resolved (expected $target)" >&2
      return 1
    fi
    echo "ok: $link -> $target"
    return 0
  fi

  mkdir -p "$parent"
  if [[ -L "$link" ]]; then
    local resolved
    resolved="$(readlink -f "$link")"
    if [[ "$resolved" == "$target" ]]; then
      echo "ok: $link -> $target"
      return 0
    fi
    if [[ "$FORCE" -eq 0 ]]; then
      echo "refusing to replace symlink with different target: $link -> $resolved" >&2
      return 1
    fi
    rm "$link"
  elif [[ -e "$link" ]]; then
    if [[ "$FORCE" -eq 0 ]]; then
      echo "exists_not_symlink: $link (use --force to replace)" >&2
      return 1
    fi
    rm -rf "$link"
  fi
  ln -s "$target" "$link"
  echo "linked: $link -> $target"
}

if [[ "$CHECK_ONLY" -eq 0 ]]; then
  mkdir -p "$DB_DIR"
fi

if [[ "$INIT_DB" -eq 1 ]]; then
  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    [[ -f "$DB_PATH" ]] || { echo "missing_db: $DB_PATH" >&2; exit 1; }
  elif [[ ! -f "$DB_PATH" ]]; then
    python3 "$SCRIPT_DIR/registry_cli.py" --db "$DB_PATH" init
  else
    echo "db_exists: $DB_PATH"
  fi
fi

link_path "$SCRIPT_DIR" "$DPO_REPO/experiment_registry"
link_path "$SCRIPT_DIR/skills/experiment-registry" "$DPO_REPO/.codex/skills/experiment-registry"
link_path "$SCRIPT_DIR/skills/experiment-registry" "$DPO_REPO/.claude/skills/experiment-registry"
link_path "$SCRIPT_DIR/skills/experiment-registry" "$VERL_REPO/.codex/skills/experiment-registry"
link_path "$SCRIPT_DIR/skills/experiment-registry" "$VERL_REPO/.claude/skills/experiment-registry"

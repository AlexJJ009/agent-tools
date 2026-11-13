#!/usr/bin/env bash
# Installs Agent Tools. Machine setup (Codex, cc-switch, host) lives in scripts/setup/.
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Empty: scripts/install_layout.py resolves the software install root (~/.local/lib/agent-tools).
INSTALL_DIR="${AGENT_TOOLS_HOME:-}"
INSTALL_AGENT_WT=1
INSTALL_LEARNING_SKILLS=1
CLAUDE_CODE_MODE="${CLAUDE_CODE_MODE:-never}"
AGENT_CORE_DIR="${AGENT_CORE_HOME:-$HOME/agent-core}"
INSTALL_AGENT_CORE_ENTRIES=1
AGENT_CORE_ENTRIES_STATUS=""
AGENT_WT_STATUS=""
CI_WATCH_STATUS=""
LOCAL_BIN_PATH_STATUS=""

# select_python_bin, run_codex_target_guard
source "$SOURCE_DIR/scripts/setup/lib.sh"

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
  case ":$PATH:" in
    *":$local_bin:"*) ;;
    *) PATH="$local_bin:$PATH" ;;
  esac
  export PATH
  hash -r 2>/dev/null || true
}

backup_and_link() {
  local source="$1"
  local target="$2"
  local timestamp backup

  if [[ ! -e "$source" && ! -L "$source" ]]; then
    echo "missing source for link: $source" >&2
    return 1
  fi

  mkdir -p "$(dirname "$target")"

  if [[ -L "$target" ]]; then
    rm -f "$target"
  elif [[ -e "$target" ]]; then
    timestamp="$(date +%Y%m%d-%H%M%S)"
    if [[ -d "$target" ]]; then
      backup="${target}.backup-${timestamp}"
    else
      backup="${target}.backup-${timestamp}"
    fi
    mv "$target" "$backup"
    echo "Backed up existing managed target: $backup"
  fi

  ln -s "$source" "$target"
}

install_agent_wt() {
  local launcher_source="$INSTALL_REAL/bin/agent-wt"
  local skill_source="$INSTALL_REAL/skills/manage-worktrees"
  local launcher_target="${AGENT_WT_PATH:-$HOME/.local/bin/agent-wt}"
  local codex_skill_target="${CODEX_HOME:-$HOME/.codex}/skills/manage-worktrees"

  if [[ ! -x "$launcher_source" ]]; then
    AGENT_WT_STATUS="failed: missing executable $launcher_source"
    echo "agent-wt not installed: missing executable $launcher_source" >&2
    return 1
  fi
  if [[ ! -f "$skill_source/SKILL.md" || ! -x "$skill_source/scripts/agent_wt.py" ]]; then
    AGENT_WT_STATUS="failed: incomplete Skill at $skill_source"
    echo "agent-wt not installed: incomplete Skill at $skill_source" >&2
    return 1
  fi

  select_python_bin
  "$PYTHON_BIN" "$skill_source/scripts/install_skill.py" --repo-root "$INSTALL_REAL" \
    --home "$HOME" --codex-home "${CODEX_HOME:-$HOME/.codex}" --platform unix \
    --known-source "$SOURCE_DIR/skills/manage-worktrees"
  backup_and_link "$launcher_source" "$launcher_target"
  AGENT_WT_STATUS="$launcher_target; Codex=$codex_skill_target"
}

install_ci_watch() {
  local launcher_source="$INSTALL_REAL/bin/ci-watch"
  local launcher_target="${CI_WATCH_PATH:-$HOME/.local/bin/ci-watch}"

  if [[ ! -x "$launcher_source" ]]; then
    CI_WATCH_STATUS="failed: missing executable $launcher_source"
    echo "ci-watch not installed: missing executable $launcher_source" >&2
    return 1
  fi

  backup_and_link "$launcher_source" "$launcher_target"
  CI_WATCH_STATUS="$launcher_target"
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
  local skills_src_dir="$AGENT_CORE_DIR/skills"

  local missing=()
  local conflicts=()
  local pair dst src current expected skill_src skill_name

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

  if [[ -d "$skills_src_dir" ]]; then
    for skill_src in "$skills_src_dir"/*; do
      [[ -d "$skill_src" ]] || continue
      skill_name="$(basename -- "$skill_src")"
      for dst in "$HOME/.codex/skills/$skill_name" "$HOME/.claude/skills/$skill_name"; do
        if [[ -L "$dst" ]]; then
          current="$(readlink -f -- "$dst" 2>/dev/null || true)"
          expected="$(readlink -f -- "$skill_src" 2>/dev/null || true)"
          if [[ -z "$current" || "$current" != "$expected" ]]; then
            conflicts+=("$dst -> $(readlink -- "$dst") (expected target inside $skills_src_dir)")
          fi
        elif [[ -e "$dst" ]]; then
          conflicts+=("$dst exists as a regular file/directory, not a symlink")
        else
          missing+=("$dst")
        fi
      done
    done
  fi

  if [[ ${#conflicts[@]} -gt 0 ]]; then
    AGENT_CORE_ENTRIES_STATUS="conflict; not auto-running agent-core install.sh"
    printf '%s\n' "agent-core entries/skills have conflicts; not auto-running $install_script:" >&2
    local c
    for c in "${conflicts[@]}"; do
      printf '  %s\n' "$c" >&2
    done
    return 0
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    printf 'agent-core entries/skills missing; running %s\n' "$install_script"
    bash "$install_script"
    AGENT_CORE_ENTRIES_STATUS="installed via $install_script"
  else
    AGENT_CORE_ENTRIES_STATUS="entries and skills already linked to $AGENT_CORE_DIR"
  fi
}

usage() {
  cat <<'EOF'
Usage:
  install.sh [options]

Installs Agent Tools: the install root, launchers on PATH, skills, agent-wt,
ci-watch and the optional Claude Code adapter. It does not configure Codex,
cc-switch or the host; run scripts/setup/{codex,cc-switch,host}.sh for that.

Options:
  --install-dir PATH       Install the software copy to PATH. Default:
                           $AGENT_TOOLS_INSTALL_ROOT or ~/.local/lib/agent-tools.
                           Refused when PATH and the data root overlap.
  --no-agent-wt            Do not install the agent-wt or ci-watch launchers,
                           or the current-scope Codex manage-worktrees Skill.
  --no-learning-skills     Do not link the learning/writing skills into ~/.agents/skills.
  --no-agent-core          Do not auto-verify or run ~/agent-core/scripts/install.sh.
  --claude-code MODE       never|existing|latest. Default: never. Opt in to
                           the Claude adapter (skill links, context view, no
                           hooks); latest also installs/updates the native CLI.
  --no-claude-code         Skip the optional Claude adapter (existing state kept).
  --no-registry            Compatibility no-op; registry installation was removed.
  --registry-init-db       Rejected; registry installation was removed.
  --check                  Install nothing. Byte-compare the install root and
                           managed skill copies against the source tree, flag
                           software left in the data root; exit 1 on any drift.
  -h, --help               Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --no-agent-wt)
      INSTALL_AGENT_WT=0
      shift
      ;;
    --no-learning-skills)
      INSTALL_LEARNING_SKILLS=0
      shift
      ;;
    --claude-code)
      CLAUDE_CODE_MODE="$2"
      shift 2
      ;;
    --no-claude-code)
      CLAUDE_CODE_MODE=never
      shift
      ;;
    --no-registry)
      :
      shift
      ;;
    --registry-init-db)
      echo "Experiment Registry installation was removed; --registry-init-db is unsupported." >&2
      exit 2
      ;;
    --no-agent-core)
      INSTALL_AGENT_CORE_ENTRIES=0
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

case "$CLAUDE_CODE_MODE" in
  never|existing|latest) ;;
  *) echo "invalid --claude-code mode: $CLAUDE_CODE_MODE" >&2; exit 2 ;;
esac
run_codex_target_guard before

# Software and application data stay in separate, non-overlapping roots.
select_python_bin
LAYOUT="$SOURCE_DIR/scripts/install_layout.py"
layout_args=(--source "$SOURCE_DIR")
[[ -n "$INSTALL_DIR" ]] && layout_args+=(--install-root "$INSTALL_DIR")
INSTALL_DIR="$("$PYTHON_BIN" "$LAYOUT" roots "${layout_args[@]}")"
DATA_ROOT="$("$PYTHON_BIN" "$LAYOUT" data-root)"

if [[ "${CHECK_ONLY:-0}" -eq 1 ]]; then
  SOURCE_REAL="$(cd "$SOURCE_DIR" && pwd -P)"
  export AGENT_TOOLS_INSTALL_ROOT="$INSTALL_DIR"
  claude_status=0
  select_python_bin
  if [[ "$CLAUDE_CODE_MODE" != never ]] && ! "$PYTHON_BIN" "$SOURCE_REAL/scripts/install_claude.py" --check; then
    claude_status=1
  fi
  if [[ "$INSTALL_LEARNING_SKILLS" -eq 1 ]] && ! "$PYTHON_BIN" "$SOURCE_REAL/scripts/install_skills.py" --check; then
    claude_status=1
  fi
  layout_status=0
  "$PYTHON_BIN" "$LAYOUT" check --source "$SOURCE_REAL" --install-root "$INSTALL_DIR" || layout_status=1
  [[ "$claude_status" -eq 0 && "$layout_status" -eq 0 ]]
  exit "$?"
fi

mkdir -p "$INSTALL_DIR"
SOURCE_REAL="$(cd "$SOURCE_DIR" && pwd -P)"
INSTALL_REAL="$(mkdir -p "$INSTALL_DIR" && cd "$INSTALL_DIR" && pwd -P)"

if [[ "$SOURCE_REAL" != "$INSTALL_REAL" ]]; then
  # Manifest sync: update changed files, delete files the previous install wrote
  # that are no longer shipped, and report (never delete) unmanaged files.
  "$PYTHON_BIN" "$LAYOUT" sync --source "$SOURCE_REAL" --install-root "$INSTALL_REAL"
fi
# The Python installers resolve the same install root.
export AGENT_TOOLS_INSTALL_ROOT="$INSTALL_REAL"

chmod +x "$INSTALL_REAL/scripts/install.sh"
if [[ -d "$INSTALL_REAL/bin" ]]; then
  chmod +x "$INSTALL_REAL"/bin/*
fi
if [[ -d "$INSTALL_REAL/scripts" ]]; then
  chmod +x "$INSTALL_REAL"/scripts/*
  chmod +x "$INSTALL_REAL"/scripts/setup/*.sh
fi

mkdir -p "$DATA_ROOT/logs"

configure_local_bin_path
if [[ "$INSTALL_AGENT_CORE_ENTRIES" -eq 1 ]]; then
  verify_agent_core_entries
fi
if [[ "$CLAUDE_CODE_MODE" != never ]]; then
  select_python_bin
  claude_args=(--agent-core-home "$AGENT_CORE_DIR")
  if [[ "$CLAUDE_CODE_MODE" == latest ]]; then
    claude_args+=(--install-cli)
  else
    command -v claude >/dev/null || { echo "Claude Code missing; use --claude-code latest" >&2; exit 1; }
    claude --version
  fi
  "$PYTHON_BIN" "$INSTALL_REAL/scripts/install_claude.py" "${claude_args[@]}"
fi
if [[ "$INSTALL_AGENT_WT" -eq 1 ]]; then
  install_agent_wt
  install_ci_watch
fi
select_python_bin
if [[ "$INSTALL_LEARNING_SKILLS" -eq 1 ]]; then
  "$PYTHON_BIN" "$INSTALL_REAL/scripts/install_skills.py" \
    || echo "WARNING: learning/writing skills were not linked into ~/.agents/skills." >&2
fi
# A Claude adapter from an earlier release registered hooks; migrate it even without --claude-code.
if [[ "$(uname -s)" == Linux && "$CLAUDE_CODE_MODE" == never && -f "$HOME/.local/state/agent-tools/claude/install.json" ]]; then
  "$PYTHON_BIN" "$INSTALL_REAL/scripts/install_claude.py" --agent-core-home "$AGENT_CORE_DIR" \
    || echo "WARNING: Claude adapter not migrated; retired hook entries may remain in ~/.claude/settings.json." >&2
fi

# All consumers now point at the install root; remove software left in the data
# root by earlier --install-dir <data root> installs. Data and unknown items stay.
"$PYTHON_BIN" "$INSTALL_REAL/scripts/install_layout.py" migrate --source "$SOURCE_REAL" --install-root "$INSTALL_REAL"

echo "Installed agent-tools in $INSTALL_REAL"
echo "Data root (logs): $DATA_ROOT"
echo "agent-tools PATH: $LOCAL_BIN_PATH_STATUS"
if [[ "$INSTALL_AGENT_WT" -eq 1 ]]; then
  echo "agent-wt: $AGENT_WT_STATUS"
  echo "ci-watch: $CI_WATCH_STATUS"
else
  echo "agent-wt not installed (--no-agent-wt)."
  echo "ci-watch not installed (--no-agent-wt)."
fi

if [[ "$INSTALL_AGENT_CORE_ENTRIES" -eq 1 ]]; then
  echo "agent-core entries ($AGENT_CORE_DIR): ${AGENT_CORE_ENTRIES_STATUS}"
else
  echo "agent-core entries not checked (--no-agent-core)."
fi

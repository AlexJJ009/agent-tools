#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT_DIR="$(dirname "$SOURCE_DIR")"
OUT="${1:-$PARENT_DIR/agent-tools-portable.tar.gz}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" - "$SOURCE_DIR" "$OUT" <<'PY'
import os
from pathlib import Path
import subprocess
import sys
import tarfile

source = Path(sys.argv[1])
output = Path(sys.argv[2]).resolve()


def private(path):
    parts = path.parts
    name = path.name
    if any(part in {'.git', '.codex', '.tmp', '.venv', 'venv', 'node_modules',
                    '__pycache__', '.pytest_cache', '.ruff_cache', 'logs'} for part in parts):
        return True
    if parts[:2] in {('docs', '_local'), ('.claude', 'worktrees')}:
        return True
    if name == '.DS_Store' or name.startswith('.codex.file.backup.'):
        return True
    if name.startswith('.env') and not name.endswith(('.example', '.sample', '.template')):
        return True
    if path.as_posix() in {'agent_context_sync.config.json', 'config/codex-fleet.targets.json',
                               'auth.json', 'config/auth.json', 'config/credentials.json'}:
        return True
    return name.endswith(('.pyc', '.pyo', '.sqlite', '.sqlite3', '.sqlite-wal', '.sqlite-shm',
                          '.sqlite-journal', '.sqlite3-wal', '.sqlite3-shm', '.sqlite3-journal',
                          '.tar.gz', '.pem', '.key'))


try:
    repository = subprocess.run(['git', '-C', str(source), 'rev-parse', '--show-toplevel'],
                                capture_output=True, text=True)
    in_checkout = repository.returncode == 0 and Path(repository.stdout.strip()).resolve() == source.resolve()
except FileNotFoundError:
    in_checkout = False

if in_checkout:
    # Current working-tree content includes unstaged moves and new source files,
    # while Git's ignore rules exclude machine-local configuration and evidence.
    listing = subprocess.run(['git', '-C', str(source), 'ls-files', '-z', '--cached',
                              '--others', '--exclude-standard'], check=True, capture_output=True)
    paths = {Path(os.fsdecode(name)) for name in listing.stdout.split(b'\0') if name}
else:
    # Extracted portable sources have no Git inventory or ignore engine.
    paths = set()
    for root, dirs, files in os.walk(source, followlinks=False):
        relative = Path(root).relative_to(source)
        for name in list(dirs):
            item = relative / name
            if private(item):
                dirs.remove(name)
            elif (source / item).is_symlink():
                paths.add(item)
                dirs.remove(name)
        paths.update(relative / name for name in files)

with tarfile.open(output, 'w:gz', dereference=False) as archive:
    for relative in sorted(paths):
        path = source / relative
        if private(relative) or path.resolve() == output:
            continue
        if path.is_file() or path.is_symlink():
            archive.add(path, arcname=str(Path(source.name) / relative), recursive=False)
print(output)
PY

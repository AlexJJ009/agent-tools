"""Material inventory: what agent-tools and its agents wrote, and what Cleaner can review.

The ledger is an inventory, not deletion authority. Deletion still goes through
`task process-cleanup` (workspace files) or `task retire` (task artifacts).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from . import materials
from .task_store import Store, TaskError, require
from .process_cleanup import _hash, _tree_digest, artifact_roots, workspace_info


def _under(path, parent):
    return path == parent or parent in path.parents


def _size(path):
    """(files, bytes) without following links; missing paths report zero."""
    try:
        if path.is_symlink() or path.is_file():
            return 1, path.lstat().st_size
        if not path.is_dir():
            return 0, 0
    except OSError:
        return 0, 0
    count = total = 0
    for current, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(current) / name).lstat().st_size
                count += 1
            except OSError:
                pass
    return count, total


def _tasks(store, workspace, task_id):
    rows = store.list(workspace)
    return [t for t in rows if task_id is None or t['task_id'] == task_id]


def _unrecorded(root, covered, min_depth):
    """Files under root not covered by a recorded path or ancestor; wholly unrecorded subtrees collapse to one row."""
    found = []

    def visit(directory, depth):
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            if child in covered or any(a in covered for a in child.parents):
                continue
            if child.is_dir() and not child.is_symlink():
                inside = any(_under(c, child) for c in covered)
                if not inside and depth + 1 >= min_depth:
                    files, size = _size(child)
                    found.append({'path': str(child), 'kind': 'dir', 'files': files, 'bytes': size})
                else:
                    visit(child, depth + 1)
            else:
                found.append({'path': str(child), 'kind': 'file', 'files': 1, 'bytes': _size(child)[1]})

    if root.is_dir() and not any(a in covered for a in [root, *root.parents]):
        visit(root, 0)
    return found


def inventory(store, workspace=None, task_id=None):
    workspace = Path(workspace).resolve() if workspace else None
    tasks = _tasks(store, str(workspace) if workspace else None, task_id) if (workspace or task_id) else []
    if task_id is not None:
        require(tasks, 'not_found', 'task not found' + (' in this workspace' if workspace else ''))
        workspace = workspace or Path(tasks[0]['workspace'])
    managed = artifact_roots(workspace) if workspace else []
    latest = {}
    for entry in materials.load(store.root):
        latest[entry['path']] = entry
    covered = {Path(p) for p, e in latest.items() if e['event'] != 'removed'}
    items = []
    for path, entry in latest.items():
        p = Path(path)
        if workspace and not (entry.get('workspace') == str(workspace) or _under(p, workspace) or any(_under(p, m) for m in managed)):
            continue
        if task_id and entry.get('task_id') != task_id:
            continue
        exists = p.exists() or p.is_symlink()
        if entry['event'] == 'removed' and not exists:
            continue
        files, size = _size(p)
        item = {k: entry.get(k) for k in ('path', 'kind', 'producer', 'purpose', 'task_id', 'workspace', 'at')}
        item.update(event=entry['event'], exists=exists, bytes=size)
        if entry.get('kind') == 'dir':
            item['files'] = files
        items.append(item)
    roots = []
    if workspace:
        roots.append((workspace / 'docs/_local', 2))
    roots += [(m, 2) for m in managed]  # manage-worktrees: <repo-parent>/_artifacts/<repo>/<branch-slug>/...
    roots += [(store.root / 'artifacts' / t['task_id'], 1) for t in tasks]
    unrecorded = [u for root, depth in roots for u in _unrecorded(root, covered, depth)]
    totals = {'recorded': len(items), 'recorded_bytes': sum(i['bytes'] for i in items if i['exists']),
              'unrecorded': len(unrecorded), 'unrecorded_bytes': sum(u['bytes'] for u in unrecorded)}
    return {'ledger': str(materials.ledger_path(store.root)), 'workspace': str(workspace) if workspace else None,
            'task_id': task_id, 'materials': sorted(items, key=lambda i: i['path']),
            'unrecorded': unrecorded, 'unrecorded_roots': [str(r) for r, _ in roots], 'totals': totals}


def render_markdown(value):
    def cell(text):
        return str(text if text is not None else '').replace('|', '\\|').replace('\n', ' ')
    lines = ['# Materials', '', f"Ledger: {value['ledger']}", '',
             '| Path | Event | Producer | Purpose | Exists | Size |', '|---|---|---|---|---|---|']
    for i in value['materials']:
        size = f"{i['bytes']} B" + (f" / {i['files']} files" if 'files' in i else '')
        lines.append('| ' + ' | '.join(cell(x) for x in (i['path'], i['event'], i['producer'], i['purpose'], i['exists'], size)) + ' |')
    lines += ['', '## Unrecorded under known roots', '']
    lines += [f"- {u['path']} ({u['kind']}, {u['files']} files, {u['bytes']} B)" for u in value['unrecorded']] or ['- none']
    t = value['totals']
    lines += ['', f"Totals: {t['recorded']} recorded ({t['recorded_bytes']} B); {t['unrecorded']} unrecorded ({t['unrecorded_bytes']} B)"]
    return '\n'.join(lines)


def cleanup_packet(store, args):
    """A process-cleanup packet whose digests are observed now; the cleanup run verifies them again."""
    task = store.read(args.task)
    info = workspace_info(task['workspace']['path'])
    workspace = Path(info['path'])
    paths = [Path(raw).expanduser().absolute() for raw in args.path]
    inside = [_under(p, workspace) and p != workspace for p in paths]
    # Outside the workspace the ledger, the task artifact directory or a managed artifact root
    # is the scope evidence; process-cleanup checks it again.
    external = not any(inside)
    require(external or all(inside), 'invalid_input', 'build separate packets for workspace and external paths')
    files, roots = [], set()
    for path in paths:
        name = str(path) if external else path.relative_to(workspace).as_posix()
        kind = 'dir' if path.is_dir() and not path.is_symlink() else 'file'
        entry = {'path': name, 'sha256': _tree_digest(path) if kind == 'dir' else _hash(path),
                 'disposition': 'delete' if kind == 'dir' else args.disposition, 'category': args.category}
        if kind == 'dir':
            entry['kind'] = 'dir'
        files.append(entry)
        roots.add(str(path.parent) if external else Path(name).parent.as_posix())
    require('.' not in roots, 'unsafe_path', 'workspace top-level entries need an explicit process-cleanup packet')
    packet = {'workspace': str(workspace), 'task_id': args.task, 'operation_id': args.operation_id,
              'authorization': {'quote': args.quote, 'source_ref': args.source_ref},
              'process_materials_reviewed': True, 'rationale': args.rationale,
              'process_roots': sorted(roots), 'files': files}
    if external:
        packet['storage'] = 'external'
    return packet


def parser():
    p = argparse.ArgumentParser(prog='agent-workflow materials', description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    rec = sub.add_parser('record', help='register a file or directory an agent wrote')
    rec.add_argument('--path', required=True, type=Path)
    rec.add_argument('--purpose', default='')
    rec.add_argument('--task')
    rec.add_argument('--workspace', type=Path)
    rec.add_argument('--session')
    rec.add_argument('--event', choices=materials.EVENTS, default='created')
    ls = sub.add_parser('list', help='inventory recorded materials plus unrecorded files under known roots')
    ls.add_argument('--workspace', type=Path)
    ls.add_argument('--task')
    ls.add_argument('--format', choices=('json', 'markdown'), default='json')
    pk = sub.add_parser('cleanup-packet', help='build a task process-cleanup packet for selected inventory paths')
    pk.add_argument('--task', required=True)
    pk.add_argument('--operation-id', required=True)
    pk.add_argument('--path', action='append', required=True, help='absolute inventory path; repeatable; workspace and external paths need separate packets')
    pk.add_argument('--disposition', choices=('delete', 'archive'), default='delete', help='files only; directories are deleted as a unit')
    pk.add_argument('--category', choices=('process-output', 'cache', 'obsolete-state'), default='process-output')
    pk.add_argument('--rationale', required=True)
    pk.add_argument('--quote', required=True, help='actual user authorization wording')
    pk.add_argument('--source-ref', required=True)
    for c in (rec, ls, pk):
        c.add_argument('--data-root', type=Path, help='absolute application data directory; overrides user config')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        store = Store(args.data_root)
        if args.action == 'record':
            path = args.path.expanduser().absolute()
            require(path.exists(), 'not_found', f'path does not exist: {path}')
            entry = materials.record(path, 'agent', args.purpose, args.event, workspace=args.workspace,
                                     task_id=args.task, session_id=args.session, root=store.root)
            require(entry is not None, 'storage_unavailable', 'ledger append failed')
            output = entry
        elif args.action == 'list':
            output = inventory(store, args.workspace, args.task)
            if args.format == 'markdown':
                print(render_markdown(output))
                return 0
        else:
            output = cleanup_packet(store, args)
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (TaskError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'error', 'code': getattr(exc, 'code', 'invalid_input'), 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())

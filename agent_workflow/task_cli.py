"""Task Runtime JSON interface; ordinary queries do not initialize storage."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from .task_store import Store, TaskError, fingerprint, workspace_info, require
from .process_cleanup import run_cleanup, read_cleanup, abort_cleanup, workspace_info as cleanup_workspace_info

ACTIONS = ('create', 'revise', 'result', 'submit', 'feedback', 'artifact', 'bind',
           'rebind', 'closeout', 'reopen', 'import', 'forget', 'prune', 'artifact-policy', 'retire')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='action', required=True)
    for name in (*ACTIONS, 'list', 'read', 'checklist', 'resolve', 'recover', 'fingerprint', 'artifact-read', 'location', 'abort', 'process-cleanup', 'process-cleanup-status', 'process-cleanup-abort', 'history'):
        c = commands.add_parser(name)
        c.add_argument('--data-root', type=Path, help='absolute application data directory; overrides user config')
        if name in ACTIONS or name == 'process-cleanup':
            c.add_argument('--input', required=True, type=Path, help='JSON operation packet; see docs/TASK_RUNTIME.md')
        if name in ('read', 'checklist', 'artifact-read', 'history'):
            c.add_argument('--task', required=True)
        if name in ('abort', 'process-cleanup-status', 'process-cleanup-abort'):
            c.add_argument('--task', required=True)
            c.add_argument('--operation', required=True)
        if name == 'recover':
            c.add_argument('--task', help='recover only this task; otherwise all pending local operations')
        if name == 'history':
            c.add_argument('--detail', action='store_true')
            c.add_argument('--limit', type=int, default=50)
            c.add_argument('--offset', type=int, default=0)
        if name in ('read', 'checklist'):
            c.add_argument('--detail', action='store_true')
            c.add_argument('--format', choices=('json', 'markdown'), default='json')
        if name in ('list', 'resolve', 'fingerprint'):
            c.add_argument('--workspace', type=Path, required=name != 'list')
        if name == 'resolve':
            c.add_argument('--session', required=True)
        if name == 'fingerprint':
            c.add_argument('--path', action='append', help='relative input path; omit for whole tracked/untracked worktree')
        if name == 'checklist':
            selection = c.add_mutually_exclusive_group()
            selection.add_argument('--item')
            selection.add_argument('--ordinal', type=int)
            selection.add_argument('--search')
        if name == 'artifact-read':
            c.add_argument('--name', required=True)
    return p


def render_markdown(value):
    """A current view, never a second persisted authority."""
    def cell(text):
        return str(text).replace('|', '\\|').replace('\n', '<br>')
    lines = ['# ' + value.get('title', 'Checklist'), '', 'Task: ' + value['task_id'],
             'Revision: ' + str(value['revision']), '']
    if value.get('recovery_pending'):
        lines += ['Recovery pending: task file or process cleanup is incomplete; run task recover.', '']
    if 'requirements' in value:
        lines += [value['requirements'], '']
    rows = value.get('items', value.get('criteria', []))
    lines += ['| ID | Requirement | Verification | Validity | User acceptance |', '|---|---|---|---|---|']
    lines += ['| ' + ' | '.join(cell(r.get(k, '')) for k in ('id', 'requirement', 'verification', 'validity', 'user_acceptance')) + ' |' for r in rows if not r.get('withdrawn')]
    return '\n'.join(lines)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        store = Store(args.data_root)
        if args.action in ACTIONS:
            output = store.mutate(args.action, json.loads(args.input.read_text()))
        elif args.action == 'process-cleanup':
            request = json.loads(args.input.read_text())
            require(isinstance(request, dict), 'invalid_input', 'request must be an object')
            def validate_task(packet):
                task = store.read(packet['task_id'])
                require(cleanup_workspace_info(packet['workspace']) == task['workspace'],
                        'workspace_mismatch', 'cleanup must use the task current workspace')
            output = run_cleanup(store.root, request, validate_task=validate_task)
        elif args.action == 'process-cleanup-status':
            output = read_cleanup(store.root, args.task, args.operation)
        elif args.action == 'process-cleanup-abort':
            output = abort_cleanup(store.root, args.task, args.operation)
        elif args.action == 'history':
            output = store.history(args.task, args.detail, args.limit, args.offset)
        elif args.action == 'list':
            output = store.list(args.workspace)
        elif args.action == 'read':
            output = store.read(args.task, args.detail)
        elif args.action == 'checklist':
            output = store.checklist(args.task, args.item, args.ordinal, args.search, args.detail)
        elif args.action == 'resolve':
            output = store.resolve(args.session, args.workspace)
        elif args.action == 'abort':
            output = store.abort(args.task, args.operation)
        elif args.action == 'recover':
            output = store.recover(args.task)
        elif args.action == 'fingerprint':
            workspace_info(args.workspace)
            output = {'input_digest': fingerprint(args.workspace, args.path), 'watched_paths': args.path}
        elif args.action == 'artifact-read':
            output = store.artifact_read(args.task, args.name)
        else:
            output = {'data_root': str(store.root), 'database': str(store.db), 'schema_version': 1}
        if getattr(args, 'format', 'json') == 'markdown':
            print(render_markdown(output))
        else:
            print(json.dumps(output, ensure_ascii=False))
        return 0
    except (TaskError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'error', 'code': getattr(exc, 'code', 'storage_unavailable' if isinstance(exc, (OSError, sqlite3.Error)) else 'invalid_input'), 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())

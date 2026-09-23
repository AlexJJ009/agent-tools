"""Local workflow checks. Gate evaluates authorization; it never launches a job."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from .contracts import ContractError, SCENARIOS, digest, load
from . import runtime, managed


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='preserve query and Agent-authored extraction/context')
    init.add_argument('--query', type=Path, required=True)
    init.add_argument('--repo', type=Path, default=Path.cwd())
    init.add_argument('--scenario', choices=sorted(SCENARIOS), required=True)
    init.add_argument('--context', type=Path, help='JSON project facts, extraction, bindings and verifiers; see documentation')
    init.add_argument('--mode', choices=['local', 'simulation'], default='local')
    init.add_argument('--slug', default='task')
    execute = sub.add_parser('execute', help='check and execute a registered local action from frozen inputs')
    execute.add_argument('--record', type=Path, required=True)
    execute.add_argument('--action', required=True)
    execute.add_argument('--simulation', action='store_true')
    execute.add_argument('--expected-digest', help='input identity saved at queue time')
    for name in ('check', 'review-brief', 'approve', 'gate', 'target', 'validate', 'revise', 'migrate', 'rollback', 'update', 'status', 'refresh'):
        command = sub.add_parser(name)
        command.add_argument('--record', type=Path, required=True)
        if name == 'update':
            command.add_argument('--event', type=Path, required=True)
        if name == 'rollback':
            command.add_argument('--output', type=Path, required=True)
        if name == 'revise':
            command.add_argument('--revision', type=Path, required=True)
        if name == 'check':
            command.add_argument('--phase', choices=['agent'], required=True)
            command.add_argument('--item', action='append', help='recheck only affected checklist IDs')
        if name == 'approve':
            command.add_argument('--sha', required=True)
            command.add_argument('--feedback', type=Path, required=True, help='actual user feedback plus candidate/target and per-item choices')
        if name in {'gate', 'approve'}:
            command.add_argument('--simulation', action='store_true')
        if name == 'gate':
            command.add_argument('--action', required=True, help='formal-run, completion, or a registered action ID')
            command.add_argument('--phase', help='phase for completion; defaults to the current phase')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'init':
            record = runtime.init(args.query, args.repo, args.scenario, load(args.context) if args.context else None, args.mode, args.slug)
            output = {'status': 'initialized', 'record': str(record)}
        elif args.command == 'execute':
            output = managed.execute(args.record, args.action, simulation=args.simulation, expected_digest=args.expected_digest)
            print(json.dumps(output, ensure_ascii=False))
            return 0 if output['status'] == 'pass' else 1
        elif args.command == 'gate' and runtime.read_record(args.record).get('schema_version') == 2:
            record = runtime.read_record(args.record)
            output = managed.gate_action(args.record, args.action, phase=args.phase or record['phase'], simulation=args.simulation)
            print(json.dumps(output, ensure_ascii=False))
            return 0 if output['status'] == 'pass' else 1
        else:
            with runtime.locked(args.record) as root:
                errors = []
                if args.command in {'migrate', 'rollback', 'update', 'status', 'refresh'}:
                    if args.command == 'migrate':
                        details = runtime.migrate(root)
                    elif args.command == 'rollback':
                        details = runtime.rollback(root, args.output)
                    elif args.command == 'update':
                        details = runtime.update(root, args.event)
                    elif args.command == 'status':
                        details = runtime.status(root)
                    else:
                        record = runtime.read_record(root)
                        runtime.refresh_views(root, record)
                        details = {'revision': record.get('revision', 0)}
                    print(json.dumps(dict(details, status='pass', command=args.command), ensure_ascii=False))
                    return 0
                if args.command == 'check':
                    errors = runtime.check(root, args.item)
                elif args.command == 'revise':
                    runtime.revise(root, args.revision)
                elif args.command == 'gate':
                    if args.action != 'formal-run':
                        raise ContractError('migrate to schema 2 for managed or completion gates')
                    errors = runtime.gate(root, args.simulation)
                elif args.command == 'review-brief':
                    output_path = runtime.review_brief(root)
                elif args.command == 'approve':
                    runtime.approve(root, args.sha, args.feedback, args.simulation)
                elif args.command == 'target':
                    target = runtime.current_target(runtime.read_record(root))
                    print(json.dumps({'target': target, 'target_digest': digest(target)}, ensure_ascii=False))
                    return 0
                else:
                    runtime.read_record(root)
                output = {'status': 'fail' if errors else 'pass', 'command': args.command, 'errors': errors}
                if args.command == 'review-brief':
                    output['path'] = str(output_path) if output_path else None
                if errors:
                    print(json.dumps(output, ensure_ascii=False))
                    return 1
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (ContractError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        output = {'status': 'error', 'command': args.command, 'error': str(exc)}
        if hasattr(args, 'record') and (args.record / 'checklist.yaml').is_file():
            runtime.append_event(args.record, args.command, 'error', output)
        print(json.dumps(output, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

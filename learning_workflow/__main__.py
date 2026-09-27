"""Explicit route records; the Main Agent supplies semantic decisions."""
import argparse
import json
from pathlib import Path
import sys
from . import runtime as r


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    p.add_argument('--version', action='version', version='learning-workflow 1.0')
    init = sub.add_parser('init', help='snapshot the request and an Agent-authored semantic decision')
    for name in ['query','decision','workspace']:
        init.add_argument('--'+name, type=Path, required=True)
    init.add_argument('--session-id',required=True)
    init.add_argument('--task-id')
    init.add_argument('--record',type=Path)
    inp = sub.add_parser('input',help='record a pending user input without classifying it')
    inp.add_argument('--query',type=Path,required=True)
    inp.add_argument('--input-id',required=True)
    classify = sub.add_parser('classify',help='apply an Agent decision using optimistic concurrency')
    classify.add_argument('--input-id',required=True)
    classify.add_argument('--decision',type=Path,required=True)
    classify.add_argument('--base-revision',type=int,required=True)
    show = sub.add_parser('show',help='read current state')
    validate = sub.add_parser('validate',help='validate structure and request snapshot integrity')
    check = sub.add_parser('check-action',help='check a declared action; does not execute arbitrary commands')
    check.add_argument('--action',choices=sorted(r.ACTIONS),required=True)
    check.add_argument('--target')
    check.add_argument('--base-revision',type=int,required=True)
    curate = sub.add_parser('curate',help='copy an explicit project artifact with a portable, deduplicated index')
    for name in ['source','destination']:
        curate.add_argument('--'+name,type=Path,required=True)
    for name in ['title','topic']:
        curate.add_argument('--'+name,required=True)
    curate.add_argument('--base-revision',type=int,required=True)
    bind = sub.add_parser('bind',help='bind this session/workspace to an existing route')
    bind.add_argument('--session-id',required=True)
    bind.add_argument('--workspace',type=Path,required=True)
    bind.add_argument('--state-root',type=Path)
    bind.add_argument('--on-stop',action='store_true')
    unbind = sub.add_parser('unbind',help='remove only this session/workspace hook binding')
    unbind.add_argument('--session-id',required=True)
    unbind.add_argument('--workspace',type=Path,required=True)
    unbind.add_argument('--state-root',type=Path)
    index = sub.add_parser('inspect-index',help='observe artifact/source availability without inventing sync')
    index.add_argument('--index',type=Path,required=True)
    index.add_argument('--source-root',type=Path)
    schema = sub.add_parser('decision-schema',help='show English field names and allowed values')
    for cmd in [inp,classify,show,validate,check,curate,bind]:
        cmd.add_argument('--record',type=Path,required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'init':
            result = r.init(args.query,r.load(args.decision),args.workspace,args.session_id,args.task_id,args.record)
        elif args.command == 'input':
            result = r.input_record(args.record,args.input_id,args.query)
        elif args.command == 'classify':
            result = r.classify(args.record,args.input_id,r.load(args.decision),args.base_revision)
        elif args.command in {'show','validate'}:
            with r.locked(args.record):
                result = r.read(args.record)
                if args.command == 'validate':
                    r.validate_project_scope(result['decision'], result['workspace_root'])
        elif args.command == 'check-action':
            result = r.check_action(args.record,args.action,args.target,args.base_revision)
        elif args.command == 'curate':
            result = r.curate(args.record,args.source,args.destination,args.title,args.topic,args.base_revision)
        elif args.command in {'bind','unbind'}:
            from . import hooks
            result = hooks.bind(args.record,args.session_id,args.workspace,args.state_root,args.on_stop) if args.command == 'bind' else hooks.unbind(args.session_id,args.workspace,args.state_root)
        elif args.command == 'inspect-index':
            result = r.inspect_index(args.index,args.source_root)
        else:
            result = {'required':sorted(r.REQUIRED),'optional':sorted(r.OPTIONAL),'activities':sorted(r.ACTIVITIES),
                      'interaction_modes':sorted(r.MODES),'workspace_contexts':['repository','readpapers','manuscript','other'],'actions':sorted(r.ACTIONS),
                      'example':{'activity':'delivery','interaction_mode':'direct','workspace_context':'repository','selected_skills':[],
                                 'excluded_actions':['unsolicited_exercises','zotero_mutation'],'material_refs':[],
                                 'output_targets':['src'],'rationale':'The user requested an implementation repair without teaching.',
                                 'unresolved':[],'next_stage':None,'development_record_ref':None},
                      'types':{'selected_skills':'list of skill-name strings','excluded_actions':'list of action-name strings','material_refs':'list of source-reference strings','output_targets':'list of file/directory path strings','unresolved':'list of blocker strings','next_stage':'null or {activity, continuation}','development_record_ref':'null or {path, revision}'},
                      'notes':'Main supplies intent. record contains a decision object; authoritative request refs are generated from snapshot bytes. ReadPapers roots and remote scopes require actual existing authority.'}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (r.RouteError,OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'rejected','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

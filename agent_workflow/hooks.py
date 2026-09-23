"""Native Codex hook adapter for explicitly bound workflow tasks.

The adapter registers observations and asks the canonical runtime about named
actions. It does not classify user intent or accept technical/business results.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import uuid

from . import runtime
from .contracts import ContractError, digest, load, require

EVENTS = {'SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop'}


def default_state_root():
    return Path.home() / '.local/state/agent-workflow/hooks'


def binding_key(session_id, workspace):
    return digest({'session_id': session_id, 'workspace': str(Path(workspace).resolve())})


@contextmanager
def binding_lock(state_root, key):
    directory = Path(state_root).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (key + '.lock')).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield directory / (key + '.json')


def bind(session_id, workspace, record, *, state_root=None, phase=None, on_stop=False):
    require(isinstance(session_id, str) and session_id.strip(), 'session id is required')
    workspace, root = Path(workspace).resolve(), Path(record).resolve()
    with runtime.locked(root):
        canonical = runtime.read_record(root)
        require(canonical['schema_version'] == 2, 'migrate to schema 2 before hook binding')
        require(Path(canonical['repo']).resolve() == workspace, 'binding workspace must match record repository')
        phase = phase or canonical['phase']
        require(phase in canonical['phases'], 'unknown binding phase')
    key = binding_key(session_id, workspace)
    with binding_lock(state_root or default_state_root(), key) as path:
        old = load(path) if path.exists() else None
        if old:
            require(old['record'] == str(root), 'session/workspace already bound to another record; unbind explicitly')
        data = old or {'session_id': session_id, 'workspace': str(workspace), 'record': str(root),
                       'inputs': {}, 'tools': {}, 'created_at': runtime.now()}
        data['phase'] = phase
        data['registered_actions'] = canonical['actions']
        if on_stop and (not data.get('stop_obligation') or data['stop_obligation']['phase'] != phase):
            data['stop_obligation'] = {'id': uuid.uuid4().hex, 'phase': phase, 'state': 'pending', 'attempts': 0}
        runtime.write(path, data)
    return {'status': 'bound', 'binding': str(path), 'record': str(root), 'phase': phase,
            'stop_registered': bool(data.get('stop_obligation'))}


def locate(event, state_root):
    session = event.get('session_id')
    if not isinstance(session, str) or not session or not event.get('cwd'):
        return None
    cwd = Path(event['cwd']).resolve()
    # Exact indexed lookups in the current workspace's ancestor chain only.
    for workspace in (cwd, *cwd.parents):
        key = binding_key(session, workspace)
        path = Path(state_root) / (key + '.json')
        if path.is_file():
            return key
    return None


def unbind(session_id, workspace, *, state_root=None):
    key = binding_key(session_id, workspace)
    with binding_lock(state_root or default_state_root(), key) as path:
        existed = path.exists()
        path.unlink(missing_ok=True)
    return {'status': 'unbound', 'binding_removed': existed}


def context(event_name, message):
    return {'hookSpecificOutput': {'hookEventName': event_name, 'additionalContext': message}}


def denied(reason):
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                   'permissionDecisionReason': reason}}


def parsed_command(event):
    if event.get('tool_name') != 'Bash':
        return None
    tool_input = event.get('tool_input')
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get('command')
    if not isinstance(command, str):
        return None
    try:
        return shlex.split(command)
    except ValueError:
        return None


def action_for(event, record, root):
    argv = parsed_command(event)
    if not argv:
        return None
    for action_id, action in record['actions'].items():
        if argv == action['argv']:
            return action_id, 'raw', False
    # The project adapter rechecks state independently at the real entry point.
    # Only inspect explicit workflow CLI invocations, never arbitrary shell text.
    start = None
    if Path(argv[0]).name == 'agent-workflow':
        start = 1
    elif len(argv) >= 3 and Path(argv[0]).name.startswith('python') and argv[1:3] == ['-m', 'agent_workflow.cli']:
        start = 3
    if start is None or argv[start:start + 1] not in (['execute'], ['managed-execute']):
        return None
    options = argv[start + 1:]
    try:
        target = options[options.index('--record') + 1]
        action_id = options[options.index('--action') + 1]
    except (ValueError, IndexError):
        return None
    if Path(target).resolve() == root and action_id in record['actions']:
        return action_id, 'entry', '--simulation' in options
    return None


def record_prompt(root, binding, event):
    prompt = event.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    prompt_bytes = prompt.encode('utf-8')
    fingerprint = hashlib.sha256(prompt_bytes).hexdigest()
    input_id = 'hook-input-' + digest({'session': event['session_id'], 'turn': event.get('turn_id'), 'prompt': fingerprint})[:24]
    if input_id in binding['inputs']:
        return input_id
    source_path = root / 'hook-inputs' / (input_id + '.txt')
    if source_path.exists():
        require(source_path.read_bytes() == prompt_bytes, 'hook input id reused for different bytes')
    else:
        runtime.write_bytes(source_path, prompt_bytes)
    # Only an Agent update can decide the affected scope or resolve this input.
    for attempt in range(3):
        with runtime.locked(root):
            record = runtime.read_record(root)
        if input_id in record['pending_inputs']:
            break
        update = {'id': input_id, 'base_revision': record['revision'], 'type': 'input.record',
                  'source': {'kind': 'user', 'actor': 'user', 'path': str(source_path),
                             'quote': prompt, 'sha256': fingerprint}, 'affects': [],
                  'payload': {'id': input_id, 'session_id': event['session_id'], 'turn_id': event.get('turn_id')}}
        try:
            runtime.update(root, update)
            break
        except ContractError as exc:
            if 'revision conflict' not in str(exc) or attempt == 2:
                raise
    binding['inputs'][input_id] = {'sha256': fingerprint, 'turn_id': event.get('turn_id')}
    return input_id


def process(event, *, state_root=None):
    name = event.get('hook_event_name')
    if name not in EVENTS or event.get('agent_id') or event.get('agent_type'):
        return {}
    state_root = Path(state_root or default_state_root()).resolve()
    key = locate(event, state_root)
    if key is None:
        return {}
    with binding_lock(state_root, key) as path:
        binding = load(path)
        root = Path(binding['record']).resolve()
        workspace = Path(binding['workspace']).resolve()
        require(binding['session_id'] == event['session_id'], 'session binding mismatch')
        require(Path(event['cwd']).resolve().is_relative_to(workspace), 'workspace binding mismatch')
        try:
            with runtime.locked(root):
                record = runtime.read_record(root)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            known = action_for(event, {'actions': binding.get('registered_actions', {})}, root)
            if name == 'PreToolUse' and known:
                return denied('Workflow state is unavailable for the registered action: ' + str(exc))
            return {'systemMessage': 'Workflow state is unavailable: ' + str(exc)}
        require(Path(record['repo']).resolve() == workspace, 'record workspace changed')
        binding['registered_actions'] = record['actions']
        output = {}
        if name == 'SessionStart':
            current = runtime.status(root)
            output = context(name, f'Workflow restored for this session: {root}. Phase: {binding["phase"]}. '
                             f'State revision: {current["revision"]}; unclassified inputs: {list(current["pending_inputs"])}. '
                             'Read this current record before dependent work; background job status remains an observation.')
        elif name == 'UserPromptSubmit':
            input_id = record_prompt(root, binding, event)
            if input_id:
                output = context(name, f'Workflow input {input_id} is recorded at {root}. Classify it using an '
                                 'input.resolve Agent update after applying any agreed changes. Unrelated reading may continue; '
                                 'registered actions wait for unresolved input classification. Do not infer user feedback.')
        elif name in {'PreToolUse', 'PostToolUse'}:
            tool_id = event.get('tool_use_id')
            if name == 'PreToolUse':
                matched = action_for(event, record, root)
                if matched:
                    action_id, entry, simulation = matched
                    from .managed import gate_action
                    try:
                        result = gate_action(root, action_id, simulation=simulation)
                    except (OSError, ValueError, KeyError, TypeError) as exc:
                        return denied('Workflow action ' + action_id + ' could not be evaluated: ' + str(exc))
                    if tool_id and entry == 'entry' and result['ready']:
                        binding['tools'][tool_id] = {'action_id': action_id, 'input_digest': digest(event.get('tool_input')),
                                                    'gate': result, 'turn_id': event.get('turn_id')}
                    if entry == 'raw':
                        output = denied('Registered workload ' + action_id + ' must use the guarded workflow entry: '
                                        'agent-workflow execute --record ' + str(root) + ' --action ' + action_id)
                    elif not result['ready']:
                        output = denied('Workflow action ' + action_id + ' cannot start: ' + '; '.join(result['errors']))
            elif tool_id in binding['tools']:
                before = binding['tools'][tool_id]
                require(before['input_digest'] == digest(event.get('tool_input')), 'tool input changed between hooks')
                detail = {'session_id': event['session_id'], 'turn_id': event.get('turn_id'),
                          'tool_use_id': tool_id, 'action_id': before['action_id'],
                          'tool_response': event.get('tool_response'), 'business_acceptance': 'not_inferred'}
                runtime.append_event(root, 'hook-post-tool', 'observed', detail)
                binding['tools'].pop(tool_id)
                output = context(name, f'Observed tool result for {before["action_id"]}; evidence is linked to tool {tool_id}. '
                                 'This does not mark checklist items checked or user results accepted.')
        elif name == 'Stop':
            obligation = binding.get('stop_obligation')
            if obligation and obligation['state'] == 'pending':
                from .managed import gate_action
                result = gate_action(root, 'completion', phase=obligation['phase'])
                if result['ready']:
                    obligation['state'] = 'satisfied'
                elif obligation['attempts'] == 0 and not event.get('stop_hook_active'):
                    obligation['attempts'] = 1
                    output = {'decision': 'block', 'reason': 'Workflow phase ' + obligation['phase'] + ' still has unmet obligations: '
                              + '; '.join(result['errors']) + '. Continue applicable work or report the specific blocker honestly. '
                              'This checks only the registered phase, not project completion or background job completion.'}
                else:
                    obligation['state'] = 'unmet_reported'
                    output = {'systemMessage': 'Workflow phase obligation remains unmet; bounded continuation exhausted. '
                              'Do not claim phase completion. ' + '; '.join(result['errors'])}
        runtime.write(path, binding)
        return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, default=None)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('hook')
    bind_parser = commands.add_parser('bind')
    bind_parser.add_argument('--session-id', required=True)
    bind_parser.add_argument('--workspace', type=Path, required=True)
    bind_parser.add_argument('--record', type=Path, required=True)
    bind_parser.add_argument('--phase')
    bind_parser.add_argument('--on-stop', action='store_true')
    unbind_parser = commands.add_parser('unbind')
    unbind_parser.add_argument('--session-id', required=True)
    unbind_parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args(argv)
    event = {}
    try:
        if args.command == 'hook':
            event = json.load(sys.stdin)
            output = process(event, state_root=args.state_root)
        elif args.command == 'bind':
            output = bind(args.session_id, args.workspace, args.record, state_root=args.state_root,
                          phase=args.phase, on_stop=args.on_stop)
        else:
            output = unbind(args.session_id, args.workspace, state_root=args.state_root)
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Known action failures are denied inside process(). Adapter discovery
        # errors remain visible without blocking unrelated reading.
        output = {'systemMessage': 'Workflow hook failed: ' + str(exc)}
        print(json.dumps(output, ensure_ascii=False))
        return 0 if args.command == 'hook' else 1


if __name__ == '__main__':
    raise SystemExit(main())

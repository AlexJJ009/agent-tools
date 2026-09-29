"""Retire legacy teaching Stop registrations in favor of the bound learning hook."""
import json
import os
import tempfile
from pathlib import Path
import re
import shlex
import tomllib


def teaching_handler(handler, directory):
    if not isinstance(handler,dict) or handler.get('type')!='command':
        return False
    try:
        argv=shlex.split(handler.get('command',''))
    except ValueError:
        return False
    # Recognize the interpreter's script argument, never a filename merely
    # mentioned as data (for example by echo, cat, or a different script).
    if argv and Path(argv[0]).name == 'env':
        argv = argv[1:]
    if len(argv) < 2 or not re.fullmatch(r'python(?:3(?:\.\d+)?)?', Path(argv[0]).name):
        return False
    script_index = 1
    while script_index < len(argv) and argv[script_index] in {'-B', '-u', '-I', '-E', '-s'}:
        script_index += 1
    if script_index >= len(argv) or argv[script_index].startswith('-'):
        return False
    path = (directory / argv[script_index]).resolve()
    project_filter = (directory / '.codex/teaching_stop_filter.py').resolve()
    return path == project_filter or (
        path.name == 'stop_validate.py'
        and path.parent.name == 'scripts'
        and path.parent.parent.name == 'teaching-reconstruction'
    )


def strip_teaching(groups,directory):
    kept=[]
    for group in groups:
        handlers=group.get('hooks',[]) if isinstance(group,dict) else []
        remaining=[h for h in handlers if not teaching_handler(h,directory)]
        if remaining==handlers:
            kept.append(group)
        elif remaining:
            kept.append(dict(group,hooks=remaining))
    return kept


def inline(value):
    if isinstance(value,dict):
        return '{ '+', '.join(json.dumps(k)+' = '+inline(v) for k,v in value.items())+' }'
    if isinstance(value,list):
        return '['+', '.join(inline(v) for v in value)+']'
    return json.dumps(value,ensure_ascii=False)


def prepare(home,project=None):
    """Read both host-loaded formats; return reviewable reversible edits, without writes."""
    edits=[]
    for directory in dict.fromkeys([Path(home),*([Path(project)] if project else [])]):
        for name in ('hooks.json','config.toml'):
            path=directory/'.codex'/name
            if not path.exists():
                continue
            before=path.read_text()
            data=json.loads(before) if name.endswith('json') else tomllib.loads(before)
            groups=data.get('hooks',{}).get('Stop',[])
            after_groups=strip_teaching(groups,directory)
            if groups==after_groups:
                continue
            if path.is_symlink():
                raise ValueError(f'teaching registration is a symlink; preserve it: {path}')
            replace_groups(path,groups,after_groups)
            edits.append({'path':str(path),'before':groups,'after':after_groups})
    return edits


def replace_groups(path,expected,replacement):
    text=path.read_text()
    data=json.loads(text) if path.suffix=='.json' else tomllib.loads(text)
    if data.get('hooks',{}).get('Stop',[])!=expected:
        raise ValueError(f'teaching registration changed; preserve it: {path}')
    if path.suffix=='.json':
        data['hooks']['Stop']=replacement
        return json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    match=re.search(r'(?m)^\[hooks\]\s*\n',text)
    if not match:
        raise ValueError(f'unsupported teaching TOML layout: {path}')
    start=re.search(r'(?m)^Stop\s*=',text[match.end():])
    if not start:
        raise ValueError(f'unsupported teaching TOML layout: {path}')
    a=match.end()+start.start()
    lines=text[a:].splitlines(keepends=True)
    for count in range(1,len(lines)+1):
        chunk=''.join(lines[:count])
        try:
            parsed=tomllib.loads(chunk)
        except tomllib.TOMLDecodeError:
            continue
        if parsed.get('Stop')==expected:
            return text[:a]+'Stop = '+inline(replacement)+'\n'+text[a+len(chunk):]
    raise ValueError(f'cannot isolate teaching registration: {path}')


def atomic_text(path,text):
    fd,temporary=tempfile.mkstemp(prefix='.teaching-hooks-',dir=path.parent)
    try:
        os.fchmod(fd,path.stat().st_mode & 0o777)
        with os.fdopen(fd,'w') as stream:
            stream.write(text)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply(edits,restore=False):
    old,new=('after','before') if restore else ('before','after')
    changes=[(Path(e['path']),replace_groups(Path(e['path']),e[old],e[new])) for e in edits]
    written=[]
    try:
        for path,text in changes:
            previous=path.read_text()
            atomic_text(path,text)
            written.append((path,previous))
    except Exception:
        for path,previous in reversed(written):
            atomic_text(path,previous)
        raise


def check(edits):
    for e in edits:
        replace_groups(Path(e['path']),e['after'],e['after'])

#!/usr/bin/env python3
"""Isolated subscription-Codex pilot. No graders or expected answers enter the sandbox."""
import argparse
import concurrent.futures
import ctypes
import math
import select
import struct
import threading
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME_MODULES = ('agent_workflow', 'learning_workflow')

def snapshot(workspace):
    out = {}
    root = Path(workspace)
    # os.walk does not follow directory symlinks; preserve dangling links as links.
    for dirname, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in ('.git', '__pycache__'))
        paths = [Path(dirname)/name for name in sorted(files)]
        paths += [Path(dirname)/name for name in dirs if (Path(dirname)/name).is_symlink()]
        dirs[:] = [d for d in dirs if not (Path(dirname)/d).is_symlink()]
        for path in paths:
            rel = str(path.relative_to(root))
            try:
                if path.is_symlink():
                    out[rel] = {'symlink': os.readlink(path)}
                    continue
                if not path.is_file():continue
                data = path.read_bytes()
                out[rel] = {'sha256': hashlib.sha256(data).hexdigest(), 'content': data.decode('utf-8', errors='replace') if len(data) < 300000 else None}
            except FileNotFoundError:
                continue
    return out

class FileObserver:
    """External inotify observer; log is never mounted into the model namespace."""
    MASK = 0x100 | 0x200 | 0x40 | 0x80 | 0x8 | 0x400 | 0x800
    def __init__(self, roots, log):
        self.roots=roots;self.log=Path(log);self.watches={};self.events=[];self.stop_event=threading.Event()
        self.lib=ctypes.CDLL(None,use_errno=True)
        self.fd=self.lib.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd<0:raise OSError(ctypes.get_errno(),'inotify_init1')
        for label, root in roots.items():self.watch_tree(label,Path(root))
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    def watch_tree(self,label,root):
        for dirname,dirs,_ in os.walk(root,followlinks=False):
            dirs[:]=[d for d in dirs if d!='.git' and not (Path(dirname)/d).is_symlink()]
            wd=self.lib.inotify_add_watch(self.fd,os.fsencode(dirname),self.MASK)
            if wd<0:raise OSError(ctypes.get_errno(),'inotify_add_watch')
            self.watches[wd]=(label,Path(dirname))
    def loop(self):
        with self.log.open('w') as stream:
            while not self.stop_event.is_set() or select.select([self.fd],[],[],0)[0]:
                if not select.select([self.fd],[],[],0.1)[0]:continue
                try:buf=os.read(self.fd,65536)
                except BlockingIOError:continue
                offset=0
                while offset<len(buf):
                    wd,mask,cookie,length=struct.unpack_from('iIII',buf,offset);offset+=16
                    name=os.fsdecode(buf[offset:offset+length].split(b'\0',1)[0]);offset+=length
                    item={'time_ns':time.time_ns(),'mask':mask,'cookie':cookie}
                    if mask & 0x4000:item['overflow']=True
                    if wd in self.watches:
                        label,parent=self.watches[wd];path=parent/name
                        item.update(root=label,path=str(path.relative_to(self.roots[label])))
                        if not path.is_symlink() and path.is_file():
                            try:item['observed_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                            except OSError:pass
                        if mask & (0x100|0x80) and mask & 0x40000000 and path.is_dir():
                            try:self.watch_tree(label,path)
                            except OSError as e:item['watch_error']=str(e)
                    self.events.append(item);stream.write(json.dumps(item)+'\n');stream.flush()
    def close(self):
        self.stop_event.set();self.thread.join(timeout=5);os.close(self.fd)
        return {'method':'inotify','events':self.events,'log':str(self.log),'scope':['workspace except .git','runtime data root'],'overflow':any(e.get('overflow') for e in self.events),'limitations':'New-directory watch registration has a small race; hashes reflect processing time and can be absent after deletion. This is event evidence, not proof that no unobserved file was ever created.'}

def validate_completion(events, exit_code, model):
    for event in events:
        item=event.get('item',{})
        message=item.get('message','') if item.get('type')=='error' else event.get('message','') if event.get('type')=='error' else ''
        lower=message.lower()
        if ('code-mode host' in lower or 'code-mode-host' in lower or 'code mode' in lower) and any(token in lower for token in ('failed to spawn','failed to initialize','unavailable','host executable was not found')):
            return 'code_mode_host_infrastructure'
    done=[e for e in events if e.get('type')=='turn.completed']
    messages=[e.get('item',{}).get('text','') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
    if exit_code!=0 or len(done)!=1 or any(e.get('type')=='turn.failed' for e in events):return 'cli_execution'
    if not messages or not messages[-1].strip():return 'missing_final_output'
    usage=done[0].get('usage') or {}
    nums=[usage.get(k) for k in ('input_tokens','output_tokens','cached_input_tokens')]
    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0 for v in nums):return 'invalid_token_usage'
    if nums[2]>nums[0]:return 'invalid_token_usage'
    observed=done[0].get('model')
    if observed and observed!=model:return 'serving_substitution'
    return None

def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def cli_assets(codex):
    """Runtime siblings shipped with this CLI; never mount the user's profile."""
    binary=Path(codex).resolve()
    candidates=[(binary.parent/'codex-code-mode-host','/opt/codex-code-mode-host')]
    for path,_ in candidates:
        if not path.is_file():raise RuntimeError('CLI runtime asset missing: '+str(path))
    return candidates

def sandbox_command(workspace, home, network=False, runtime=None, data=None, codex=None):
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-all']
    if network:
        cmd += ['--share-net']
    cmd += ['--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/etc', '--dir', '/home', '--bind', str(home), '/home/eval', '--bind', str(workspace), '/workspace', '--chdir', '/workspace']
    for path in ('/etc/ssl/certs', '/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf', '/etc/ld.so.cache'):
        if Path(path).exists():
            cmd += ['--ro-bind', path, path]
    if runtime:
        cmd += ['--ro-bind', str(runtime), '/opt/runtime']
    if data:
        cmd += ['--bind', str(data), '/data']
    if codex:
        cmd += ['--ro-bind', str(codex), '/opt/codex']
        for source,destination in cli_assets(codex):cmd += ['--ro-bind',str(source),destination]
    cmd += ['--clearenv', '--setenv', 'HOME', '/home/eval', '--setenv', 'CODEX_HOME', '/home/eval/.codex', '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'SHELL', '/bin/bash', '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'PYTHONPATH', '/opt/runtime:/opt/runtime/python-deps', '--setenv', 'XDG_DATA_HOME', '/home/eval/.local/share', '--setenv', 'XDG_CONFIG_HOME', '/home/eval/.config', '--setenv', 'GIT_CONFIG_GLOBAL', '/dev/null', '--setenv', 'GIT_CONFIG_NOSYSTEM', '1']
    if network:
        for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'):
            if os.environ.get(key):
                cmd += ['--setenv', key, os.environ[key]]
    return cmd

def run_check(code, workspace):
    workspace = Path(workspace).resolve()
    run = workspace.parent
    with tempfile.TemporaryDirectory(prefix='eval-check-') as temp:
        scratch=Path(temp);home=scratch/'home';home.mkdir()
        copied=scratch/'workspace'
        shutil.copytree(workspace,copied,symlinks=True,ignore=shutil.ignore_patterns('.git','__pycache__'))
        # Hidden checks may execute candidate code. Never let them mutate retained evidence.
        cmd = sandbox_command(copied,home,runtime=run/'runtime' if (run/'runtime').exists() else None)
        try:
            marker='EVAL_CHECK_STARTED_'+uuid.uuid4().hex
            bootstrap='import sys\nsys.stderr.write('+repr(marker+'\n')+');sys.stderr.flush()\nexec(compile('+repr(code)+', \"<hidden-check>\", \"exec\"))\n'
            p = subprocess.run(cmd + ['python3', '-'], input=bootstrap, capture_output=True, text=True, timeout=30)
            started=marker+'\n' in p.stderr
            stderr=p.stderr.replace(marker+'\n','',1)
            return {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': stderr, 'infra_error': not started}
        except subprocess.TimeoutExpired:
            return {'returncode': 124, 'stdout': '', 'stderr': 'check timeout', 'infra_error': True}
        except OSError as error:
            return {'returncode': 127, 'stdout': '', 'stderr': str(error), 'infra_error': True}

def prepare_test_dependencies(runtime):
    """Materialize pinned packages from the existing uv cache; no network or host install."""
    uv=shutil.which('uv')
    if not uv:raise RuntimeError('infra: uv unavailable for offline fixture dependencies')
    packages=['pytest==8.4.2','iniconfig==2.3.0','packaging==26.3','pluggy==1.6.0','pygments==2.21.0']
    result=subprocess.run([uv,'pip','install','--offline','--python','/usr/bin/python3','--target',str(runtime/'python-deps'),*packages],capture_output=True,text=True,timeout=60)
    if result.returncode:raise RuntimeError('infra: offline pytest dependencies unavailable: '+result.stderr)
    return {'source':'existing uv cache; offline', 'packages':packages}

def prepare_runtime(case, run, base):
    if case['id'] not in ('C06', 'C07', 'C11'):
        return None
    requirement = ('增加strip模式，逐行去除两端空白，保留空行和默认直通行为。不要修改input.txt，不联网、不发布。当前下一步先补并运行CPU边界测试再实现。' if case['id']=='C06' else '整理本轮给定fixture结果：CPU测试3 passed，AC-1已验证；用户还未查看实现，验收pending。不清理交付证据。')
    if case['id']=='C11':requirement=case['prompt']+' 授权来自本题实际user请求；task仅供本次隔离清理使用，不表示用户验收或closeout授权。'
    code = '''import json, subprocess
from pathlib import Path
from agent_workflow.task_store import fingerprint

def mutate(action, packet):
 p=Path('/tmp/packet.json');p.write_text(json.dumps(packet))
 r=subprocess.run(['python3','-m','agent_workflow.cli','task',action,'--data-root','/data','--input',str(p)],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stdout+r.stderr)
 return json.loads(r.stdout)
q=mutate('create',{'operation_id':'fixture-create','workspace':'/workspace','title':'pilot-fixture','requirements':REQUIREMENT,'criteria':[{'id':'AC-1','name':'current requirement','requirement':REQUIREMENT,'expected':'requirements fulfilled'}]})
task=q['task_id'];rev=q['revision']
q=mutate('bind',{'operation_id':'fixture-bind','task_id':task,'base_revision':rev,'workspace':'/workspace','session_id':'eval-fixture'})
if CASE=='C07':
 q=mutate('artifact',{'operation_id':'fixture-evidence','task_id':task,'base_revision':q['revision'],'name':'result.txt','content':Path('/workspace/result.txt').read_text(),'purpose':'given external test fixture evidence'})
 q=mutate('result',{'operation_id':'fixture-external-result','task_id':task,'base_revision':q['revision'],'item_id':'AC-1','source':'external','method':'provided fixture, not executed test','verification':'passed','returncode':0,'input_digest':fingerprint('/workspace'),'watched_paths':None,'evidence':['result.txt'],'stdout':'Given fixture: CPU tests 3 passed; not freshly executed.'})
print(json.dumps({'task_id':task}))
'''.replace('REQUIREMENT', repr(requirement)).replace("CASE=='C07'", repr(case['id'])+"=='C07'")
    p = subprocess.run(base+['python3','-'], input=code, capture_output=True, text=True, timeout=30)
    (run/'runtime-setup.txt').write_text(p.stdout+p.stderr)
    if p.returncode:
        raise RuntimeError('runtime setup failed: '+p.stderr[-2000:]+p.stdout[-1000:])
    return json.loads(p.stdout)['task_id']

def runtime_read(base, task):
    if not task: return None
    p=subprocess.run(base+['python3','-m','agent_workflow.cli','task','read','--data-root','/data','--task',task,'--detail'],capture_output=True,text=True,timeout=30)
    return json.loads(p.stdout) if p.returncode==0 else {'error':p.stderr+p.stdout}

def skill_plan(case, variant):
    setup=case.get('skill_setup')
    if setup is None:
        names=sorted(set(case.get('target_skills',[]))|{'work-report','retrieval-practice','task-routing','evidence-anchor','learning-artifact-compiler','teaching-dag-builder'}) if variant=='skills' else []
        return {'mode':'pilot','packages':names,'resources':[],'target':None}
    if setup.get('mode')!='target_ablation':raise ValueError('unsupported skill_setup mode')
    target=setup['target_skill'];shared=setup.get('shared_skills',[])
    if target in shared:raise ValueError('target cannot be shared')
    for name in [target,*shared]:
        if '/' in name or name in ('.','..') or not (ROOT/'skills'/name/'SKILL.md').is_file():raise ValueError('unknown/unsafe skill name')
    resources=list(setup.get('shared_resources',[]))
    # Direct sibling reference files are neutral common resources, not discoverable skills.
    for name in [target,*shared]:
        body=(ROOT/'skills'/name/'SKILL.md').read_text()
        for relative in re.findall(r'`(\.\./[^`]+)`',body):
            resource=(ROOT/'skills'/name/relative).resolve()
            if resource.is_file() and resource.is_relative_to(ROOT/'skills') and resource.name!='SKILL.md':
                source=str(resource.relative_to(ROOT))
                if source not in {r['source'] for r in resources}:resources.append({'source':source,'destination':source})
    for resource in resources:
        src=Path(resource['source']);dst=Path(resource['destination'])
        if src.is_absolute() or dst.is_absolute() or '..' in src.parts or '..' in dst.parts:raise ValueError('unsafe resource path')
        if dst.parts[:2]==('skills',target) or dst.name=='SKILL.md':raise ValueError('shared resource leaks target metadata')
        if src.parts[:2]==('skills',target) or not (ROOT/src).is_file():raise ValueError('resource must be existing non-target file')
        if not (ROOT/src).resolve().is_relative_to(ROOT):raise ValueError('resource escapes repository')
    return {'mode':'target_ablation','packages':sorted(shared+([target] if variant=='skills' else [])),'resources':resources,'target':target}

def expected_skill_manifest():
    path=os.environ.get('AGENT_TOOLS_EVAL_EXPECTED_SKILLS')
    return Path(path).resolve() if path else None


def verify_installed_skills(plan, home):
    """Optional regression gate: compare installed bytes to the authorized main commit."""
    path=expected_skill_manifest()
    if path is None:return
    expected=json.loads(path.read_text())
    if not expected.get('main_commit') or not isinstance(expected.get('files'),dict):
        raise RuntimeError('Invalid merged-main skill manifest')
    checked={}
    for name in plan['packages']:
        prefix='skills/'+name+'/'
        wanted={key[len(prefix):]:sha for key,sha in expected['files'].items() if key.startswith(prefix)}
        folder=home/'.agents/skills'/name
        actual={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
        if not wanted or actual!=wanted:raise RuntimeError('Installed skill differs from merged main: '+name)
        checked[name]=actual
    resources={}
    for item in plan.get('resources',[]):
        source=item['source'];target=home/'.agents'/item['destination']
        sha=hashlib.sha256(target.read_bytes()).hexdigest()
        if sha!=expected['files'].get(source):raise RuntimeError('Installed shared resource differs from merged main: '+source)
        resources[item['destination']]=sha
    plan['merged_main_copy_audit']={'main_commit':expected['main_commit'],
        'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'packages':checked,'resources':resources,'verified_before_model_start':True}


def source_manifest(case, variant):
    plan=skill_plan(case,variant)
    paths=[ROOT/'shared/writing/reader-facing-contract.md',ROOT/'docs/TASK_RUNTIME.md',ROOT/'scripts/codex_target_guard.py']
    for module in RUNTIME_MODULES:paths.extend((ROOT/module).rglob('*'))
    for name in plan['packages']:paths.extend((ROOT/'skills'/name).rglob('*'))
    if plan['mode']=='pilot' and variant=='skills':paths.extend((ROOT/'shared').rglob('*'))
    for resource in plan['resources']:paths.append(ROOT/resource['source'])
    hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc'}
    cli=Path(shutil.which('codex')).resolve()
    hashes['@codex_binary']=hashlib.sha256(cli.read_bytes()).hexdigest()
    expected=expected_skill_manifest()
    if expected is not None:hashes['@expected_skills:'+str(expected)]=hashlib.sha256(expected.read_bytes()).hexdigest()
    for asset,_ in cli_assets(cli):hashes['@cli_asset:'+str(asset)]=hashlib.sha256(asset.read_bytes()).hexdigest()
    return hashes

def setup_skills(case,variant,home):
    plan=skill_plan(case,variant);skillroot=home/'.agents/skills';ch=home/'.codex'
    if plan['mode']=='target_ablation':
        skillroot.mkdir(parents=True,exist_ok=True)
        for name in plan['packages']:shutil.copytree(ROOT/'skills'/name,skillroot/name,symlinks=False,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for resource in plan['resources']:
            dst=home/'.agents'/resource['destination'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/resource['source'],dst)
        catalog_names=plan['packages']
        instruction='Available common capabilities; use when relevant.'
        if variant=='skills':instruction+=' 本任务必须先读取并遵循目标 skill：/home/eval/.agents/skills/'+plan['target']+'/SKILL.md。这是显式调用。'
    elif variant=='skills':
        skillroot.mkdir(parents=True,exist_ok=True)
        for name in plan['packages']:
            src=ROOT/'skills'/name
            if src.exists():shutil.copytree(src,skillroot/name,symlinks=False,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT/'shared',home/'.agents/shared')
        catalog_names=case.get('target_skills',[]);instruction='Available task capabilities. Read and apply the relevant skill when the task matches its description.'
    else:return plan
    catalog='\n'.join('- '+n+': '+next((line.removeprefix('description: ') for line in (skillroot/n/'SKILL.md').read_text().splitlines() if line.startswith('description: ')), '')+' (file: /home/eval/.agents/skills/'+n+'/SKILL.md)' for n in catalog_names)
    if catalog or plan['mode']=='target_ablation':
        with (ch/'AGENTS.md').open('a') as stream:stream.write('\n'+instruction+'\n'+catalog+'\n')
    verify_installed_skills(plan,home)
    return plan

def observed_target_read(events,target):
    if not target:return {'status':'not_applicable','event_ids':[]}
    body=(ROOT/'skills'/target/'SKILL.md').read_text()
    samples=[body[i:i+120] for i in range(0,min(len(body),1000),120) if len(body[i:i+120])==120]
    matches=[]
    for event in events:
        item=event.get('item',{})
        if event.get('type')=='item.completed' and item.get('type')=='command_execution' and item.get('exit_code')==0 and any(sample in item.get('aggregated_output','') for sample in samples):matches.append(item.get('id'))
    return {'status':'read_output_observed' if matches else 'not_observed','event_ids':matches,'limitation':'Observes skill text in successful tool output; does not prove attention or compliance.'}

def run_case(case, variant, rep, output, model, timeout=300, effort='medium'):
    run=Path(output)/f"{case['id']}-{variant}-{rep}"
    case_hash=hashlib.sha256(json.dumps(case,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    harness_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    sources=source_manifest(case,variant)
    reuse_key={'case_sha256':case_hash,'harness_sha256':harness_hash,'model':model,'effort':effort,'timeout':timeout,'variant':variant,'rep':rep,'source_files':sources}
    reuse_hash=hashlib.sha256(json.dumps(reuse_key,sort_keys=True).encode()).hexdigest()
    candidates=[run,*sorted(run.parent.glob(run.name+'-attempt*'))] if run.parent.exists() else []
    for candidate in candidates:
        if (candidate/'result.json').exists():
            prior=json.loads((candidate/'result.json').read_text())
            if prior.get('status')=='ok' and prior.get('reuse_sha256')==reuse_hash:return prior
    if run.exists():
        attempt=2
        while run.with_name(run.name+f'-attempt{attempt}').exists():attempt+=1
        run=run.with_name(run.name+f'-attempt{attempt}')
    run.mkdir(parents=True, exist_ok=False)
    work=run/'workspace';home=run/'home';ch=home/'.codex';data=run/'data';runtime=run/'runtime'
    work.mkdir();ch.mkdir(parents=True,mode=0o700);data.mkdir();runtime.mkdir()
    guard=subprocess.run(['python3',str(ROOT/'scripts/codex_target_guard.py'),'--platform','auto','--codex-home',str(ch),'--cc-switch-db',str(home/'.cc-switch/cc-switch.db'),'--path-only','--allow-missing-config','--allow-missing-cc-switch','--skip-cc-switch-read-check','--json'],capture_output=True,text=True,env={**os.environ,'HOME':str(home),'CODEX_HOME':str(ch),'XDG_CONFIG_HOME':str(home/'.config')})
    if guard.returncode:raise RuntimeError('profile guard: '+guard.stdout+guard.stderr)
    (ch/'AGENTS.md').write_text((ROOT/'shared/writing/reader-facing-contract.md').read_text())
    for module in RUNTIME_MODULES:
        shutil.copytree(ROOT/module,runtime/module,ignore=shutil.ignore_patterns('__pycache__'))
    for name, content in case['fixtures']['files'].items():
        p=work/name
        if Path(name).is_absolute() or '..' in Path(name).parts: raise ValueError('unsafe fixture path')
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
    if case['id']=='C06': (work/'old-report.md').write_text('旧版本历史报告（非当前状态）：strip已完成。\n')
    target_skills=case.get('target_skills',[])
    plan=setup_skills(case,variant,home)
    injected=case.get('execution',{}).get('injected_rules')
    if injected:
        text=injected if isinstance(injected,str) else '\n'.join(injected)
        with (work/'AGENTS.md').open('a') as f:f.write('\n'+text+'\n')
    dependencies=prepare_test_dependencies(runtime) if case['id']=='C11' else None
    base=sandbox_command(work,home,runtime=runtime,data=data)
    if case['id']=='C11':
        preflight=subprocess.run(base+['python3','-B','-m','pytest','-p','no:cacheprovider','tests/test_data.py'],capture_output=True,text=True,timeout=30)
        (run/'fixture-preflight.txt').write_text(preflight.stdout+preflight.stderr)
        if preflight.returncode:raise RuntimeError('infra: C11 fixture pytest preflight failed: '+preflight.stdout+preflight.stderr)
    for args in [['git','init','-q'],['git','add','.'],['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-qm','fixture']]:
        p=subprocess.run(base+args,capture_output=True,text=True)
        if p.returncode:raise RuntimeError(p.stderr)
    (runtime/'docs').mkdir()
    shutil.copyfile(ROOT/'docs/TASK_RUNTIME.md',runtime/'docs/TASK_RUNTIME.md')
    task=prepare_runtime(case,run,base)
    before=snapshot(work);rb=runtime_read(base,task)
    prompt=case['prompt']
    turns=case.get('turns',[])
    if len(turns)>1:prompt='此前对话（作为给定上下文，继续回应最后一条用户请求）：\n'+ '\n\n'.join(t['role']+': '+t['content'] for t in turns)
    if task:prompt+='\n\n当前任务接口：python3 -m agent_workflow.cli task read --data-root /data --task '+task+'。可用checklist查询同一任务；实际runtime session绑定为eval-fixture。接口文档在/opt/runtime/docs/TASK_RUNTIME.md，变更包与状态可写/data；清理须保留当前用户授权原文。'
    (run/'prompt.txt').write_text(prompt)
    write_json(run/'before.json',before)
    codex=Path(shutil.which('codex')).resolve()
    cli_assets(codex)  # fail before creating a credential copy if the installation is incomplete
    auth=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'auth.json'
    shutil.copyfile(auth,ch/'auth.json');(ch/'auth.json').chmod(0o600)
    cli=sandbox_command(work,home,network=True,runtime=runtime,data=data,codex=codex)
    observer=FileObserver({'workspace':work,'runtime_data':data},run/'filesystem-events.jsonl') if case['id']=='C11' else None
    observer_before={'workspace':snapshot(work),'runtime_data':snapshot(data)} if observer else None
    start=time.monotonic();status='error';error=None;events=[];exit_code=None
    try:
        login=subprocess.run(cli+['/opt/codex','login','status'],capture_output=True,text=True,timeout=20)
        if login.returncode or 'Logged in using ChatGPT' not in login.stdout+login.stderr:raise RuntimeError('subscription authentication unavailable')
        args=cli+['/opt/codex','exec','--ignore-user-config','-c','model_provider="openai"','-c',f'model_reasoning_effort="{effort}"','-c','approval_policy="never"','--ephemeral','--json','--sandbox','workspace-write','--add-dir','/data','--skip-git-repo-check','--model',model,'-C','/workspace','-']
        if case.get('output_schema'):
            schema=run/'output-schema.json';write_json(schema,case['output_schema'])
            pos=len(cli);args[pos:pos]=['--ro-bind',str(schema),'/opt/output-schema.json']
            args[-1:-1]=['--output-schema','/opt/output-schema.json']
        with (run/'events.jsonl').open('w') as out,(run/'stderr.txt').open('w') as err:
            proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=out,stderr=err,text=True,start_new_session=True)
            try:proc.communicate(prompt,timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL);proc.communicate();error='timeout'
            exit_code=proc.returncode
        for line in (run/'events.jsonl').read_text().splitlines():
            try:events.append(json.loads(line))
            except ValueError:error='invalid_event_json'
        completed=[e for e in events if e.get('type')=='turn.completed']
        error=error or validate_completion(events,exit_code,model)
        if not error:status='ok'
    except Exception as e:error=str(e)
    finally:
        (ch/'auth.json').unlink(missing_ok=True)
        observation=observer.close() if observer else None
        if observation:
            observation['before']=observer_before
            observation['after']={'workspace':snapshot(work),'runtime_data':snapshot(data)}
    messages=[e['item'].get('text','') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
    completed=[e for e in events if e.get('type')=='turn.completed']
    result={'case_id':case['id'],'variant':variant,'rep':rep,'workspace':str(work),'status':status,'error':error,'exit_code':exit_code,'seconds':round(time.monotonic()-start,2),'output':messages[-1] if messages else '', 'events':events,'usage':completed[-1].get('usage') if completed else None,'model_requested':model,'model_observed':completed[-1].get('model') if completed else None,'target_skills':target_skills,'installed_skills':sorted(p.name for p in (home/'.agents/skills').iterdir() if (p/'SKILL.md').is_file()) if (home/'.agents/skills').exists() else [],'instruction_hashes':{str(p.relative_to(home)):hashlib.sha256(p.read_bytes()).hexdigest() for p in home.rglob('*.md') if p.is_file()},'before':before,'after':snapshot(work),'task_id':task,'runtime_before':rb,'runtime_after':runtime_read(base,task),'file_observation':observation,'test_dependencies':dependencies,'case_sha256':case_hash,'harness_sha256':harness_hash,'reuse_sha256':reuse_hash,'effort':effort,'timeout_seconds':timeout,'source_files':sources,'source_revision':subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip(),'skill_setup':plan,'target_load':observed_target_read(events,plan['target']) if variant=='skills' else {'status':'absent_by_design' if plan['mode']=='target_ablation' else 'not_applicable','event_ids':[]},'isolation':{'filesystem':'bubblewrap allowlist; no real HOME/repo/grader mounted','tools':'Codex workspace-write sandbox; network denied','cli_network':'enabled only for subscription transport','auth':'temporary 0600 copy removed after run; trusted CLI context can read it'}}
    (run/'output.txt').write_text(result['output']);write_json(run/'result.json',result)
    print(json.dumps({'case':case['id'],'variant':variant,'status':status,'seconds':result['seconds'],'error':error}),flush=True)
    return result

def run_prompt(prompt, output, model='gpt-5.5', timeout=300, effort='medium', case_id='judge'):
    case={'id':case_id,'prompt':prompt,'fixtures':{'files':{}},'target_skills':[]}
    return run_case(case, 'control', 1, output, model, timeout, effort)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',default='all');p.add_argument('--reps',type=int,default=1);p.add_argument('--variant',choices=['skills','control'],default='skills');p.add_argument('--output',type=Path,required=True);p.add_argument('--model',default='gpt-5.5');p.add_argument('--effort',default='medium');p.add_argument('--timeout',type=int,default=300);p.add_argument('--workers',type=int,default=2);p.add_argument('--dataset',type=Path,default=HERE/'cases.json')
    a=p.parse_args();out=a.output.resolve()
    if out.is_relative_to(ROOT):p.error('output must be outside source checkout')
    out.mkdir(parents=True,exist_ok=True)
    cases=json.loads(a.dataset.read_text())['cases'];ids=None if a.cases=='all' else set(a.cases.split(','));selected=[c for c in cases if ids is None or c['id'] in ids]
    if not selected or (ids and ids!={c['id'] for c in selected}):p.error('unknown/empty case selection')
    jobs=[(c,r) for c in selected for r in range(1,a.reps+1)]
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        fs=[pool.submit(run_case,c,a.variant,r,out,a.model,a.timeout,a.effort) for c,r in jobs]
        for f in concurrent.futures.as_completed(fs):
            try:results.append(f.result())
            except Exception as e:
                failure={'status':'harness_error','error':str(e)};results.append(failure);print(json.dumps(failure),flush=True)
    write_json(out/f'{a.variant}-results.json',results)
    return 0 if all(r['status']=='ok' for r in results) else 1

if __name__=='__main__':raise SystemExit(main())

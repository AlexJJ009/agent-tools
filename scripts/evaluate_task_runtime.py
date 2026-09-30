"""Opt-in, serial H03 interface comparison. Never runs in the original project.

Requires a working native Codex installation. Four runs, 180 seconds each;
records trajectories and actual usage. This is not a general model benchmark.
"""
import argparse
import hashlib
import shlex
import signal
import json, os, shutil, subprocess, sys, time, tomllib
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native', action='store_true', help='explicitly authorize four native model runs')
parser.add_argument('--output', type=Path, required=True, help='new absolute directory outside the source checkout')
parser.add_argument('--codex-home', type=Path, default=Path.home()/'.codex', help='read-only source of existing auth/provider configuration')
args=parser.parse_args()
if not args.native:
    parser.error('--native is required; this consumes model quota')
ROOT=Path(__file__).resolve().parents[1]
OUT=args.output
if not OUT.is_absolute() or OUT.resolve().is_relative_to(ROOT) or (OUT.exists() and any(OUT.iterdir())):
    parser.error('--output must be a new/empty absolute directory outside the source checkout')
OUT.mkdir(parents=True,exist_ok=True)
# Store also invokes Git in this process; isolate its environment as well.
for key in list(os.environ):
    if key.startswith('GIT_'):
        os.environ.pop(key)
os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
sys.path.insert(0,str(ROOT))
from agent_workflow.task_store import Store, criterion
live=args.codex_home.resolve()
config=tomllib.loads((live/'config.toml').read_text())
model=config['model']; provider=config['model_provider']
results=[]
for number,group in enumerate(('A','B','B','A'),1):
    run=OUT/f'h03-{number}-{group}'
    if (run/'result.json').exists():
        results.append(json.loads((run/'result.json').read_text()));continue
    home=run/'home'; ch=home/'.codex'; work=run/'workspace'
    ch.mkdir(parents=True,exist_ok=True,mode=0o700);work.mkdir(exist_ok=True)
    profile_env=os.environ.copy();profile_env.update(HOME=str(home),CODEX_HOME=str(ch),XDG_CONFIG_HOME=str(home/'.config'),XDG_DATA_HOME=str(home/'.local/share'))
    for key in list(profile_env):
        if key.startswith('GIT_'):
            profile_env.pop(key)
    profile_env.update(GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1')
    guard=subprocess.run([sys.executable,str(ROOT/'scripts/codex_target_guard.py'),'--platform','auto','--codex-home',str(ch),'--cc-switch-db',str(home/'.cc-switch/cc-switch.db'),'--path-only','--allow-missing-config','--allow-missing-cc-switch','--skip-cc-switch-read-check','--json'],capture_output=True,text=True,env=profile_env)
    if guard.returncode: raise RuntimeError(guard.stdout+guard.stderr)
    try:
        shutil.copyfile(live/'auth.json',ch/'auth.json');(ch/'auth.json').chmod(0o600)
        lines=[f'model = {json.dumps(model)}',f'model_provider = {json.dumps(provider)}','model_reasoning_effort = "medium"','approval_policy = "never"',f'[model_providers.{provider}]']
        for key,value in config['model_providers'][provider].items():
            lines.append(key+' = '+('true' if value is True else 'false' if value is False else json.dumps(value)))
        (ch/'config.toml').write_text('\n'.join(lines)+'\n');(ch/'config.toml').chmod(0o600)
        subprocess.run(['git','init','-q',str(work)],check=True,env=profile_env)
        (work/'converter.py').write_text('def convert(text):\n    return text.upper()\n')
        subprocess.run(['git','-C',str(work),'add','.'],check=True,env=profile_env)
        subprocess.run(['git','-C',str(work),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],check=True,env=profile_env)
        requirement='Add strip mode to the file converter. Preserve default uppercase behavior. Excluded: network, GPU, queue operations. Current next step: add CPU tests for strip mode before implementation. User acceptance is still pending.'
        criteria=[{'id':'AC-1','name':'strip mode','requirement':'Add --mode strip removing surrounding whitespace','expected':'stripped lines'}, {'id':'AC-2','name':'default behavior','requirement':'Keep uppercase as the default','expected':'uppercase lines'}]
        if group=='A':
            (work/'task.json').write_text(json.dumps({'title':'converter-resume','requirements':requirement,'criteria':[criterion(c) for c in criteria],'state':'draft'},indent=2))
            interface='Read task.json to recover the current task.'
        else:
            toolsdir=run/'tool';toolsdir.mkdir(exist_ok=True)
            shutil.copytree(ROOT/'agent_workflow',toolsdir/'agent_workflow',ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
            store=Store(run/'data');created=store.mutate('create',{'operation_id':'setup','workspace':str(work),'title':'converter-resume','requirements':requirement,'criteria':criteria})
            interface=f'Use this read-only task interface: PYTHONPATH={shlex.quote(str(toolsdir))} python3 -m agent_workflow.cli task read --data-root {shlex.quote(str(run / "data"))} --task {created["task_id"]}. Checklist queries support --item, --ordinal, --search.'
        prompt='You are resuming a development task in a new conversation. '+interface+' Inspect current code too. Do not implement changes or run network/GPU/queue commands. Return JSON with keys pending_ids (array of acceptance criterion IDs whose recorded verification is not passed and current, even if code appears to implement it), exclusions (array of the three forbidden categories), next_step (brief concrete action), user_accepted (boolean). Preserve all current requirements; do not infer acceptance. No extra prose.'
        (run/'prompt.txt').write_text(prompt)
        env=profile_env.copy();env.update(HOME=str(home),CODEX_HOME=str(ch),XDG_CONFIG_HOME=str(home/'.config'),XDG_DATA_HOME=str(home/'.local/share'))
        for key in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','AGENT_TOOLS_DATA_ROOT','PYTHONPATH'):env.pop(key,None)
        start=time.monotonic()
        command=[shutil.which('codex') or 'codex','exec','--ephemeral','--json','--sandbox','read-only','--ignore-rules','-C',str(work),'-o',str(run/'answer.txt'),prompt]
        try:
            with (run/'trajectory.jsonl').open('w') as out,(run/'stderr.txt').open('w') as err:
                proc=subprocess.Popen(command,stdout=out,stderr=err,env=env,start_new_session=True)
                try: code=proc.wait(timeout=180)
                except subprocess.TimeoutExpired:
                    import signal
                    os.killpg(proc.pid,signal.SIGTERM)
                    try: code=proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid,signal.SIGKILL)
                        code=proc.wait(timeout=15)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=15)
            answer=(run/'answer.txt').read_text() if (run/'answer.txt').exists() else ''
            try:
                data=json.loads(answer.strip().removeprefix('```json').removesuffix('```').strip())
                passed=set(data['pending_ids'])=={'AC-1','AC-2'} and data['user_accepted'] is False and all(any(word in x.lower() for x in data['exclusions']) for word in ('network','gpu','queue')) and isinstance(data.get('next_step'),str)
            except Exception:passed=False
            result={'group':group,'run':number,'exit_code':code,'seconds':round(time.monotonic()-start,2),'mechanical_pass':passed,'semantic_review':'pending: independently assess next_step against CPU-tests-before-implementation' ,'model':model,'budget_seconds':180,'scope':'H03 simplified cold read; not implementation or GPU acceptance'}
            events=[]
            for line in (run/'trajectory.jsonl').read_text().splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
            result['tool_hashes']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (run/'tool/agent_workflow').glob('*.py')} if group=='B' else {}
            result['usage']=[e.get('usage') for e in events if e.get('usage')]
            result['commands']=[e.get('item',{}).get('command') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='command_execution']
            (run/'result.json').write_text(json.dumps(result,indent=2));results.append(result)
            print(json.dumps(result),flush=True)
        finally:
            (ch/'auth.json').unlink(missing_ok=True)
            (ch/'config.toml').unlink(missing_ok=True)
    finally:
        (ch/'auth.json').unlink(missing_ok=True)
        (ch/'config.toml').unlink(missing_ok=True)
    if code!=0:
        print('Stop after harness failure; do not spend remaining runs.',flush=True);break
(OUT/'native-results.json').write_text(json.dumps(results,indent=2))

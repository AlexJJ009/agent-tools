"""Mechanism runtime adapter. Frozen pilot/challenge sources remain unchanged."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PILOT=HERE.parent/'skill-suite-pilot'
CHALLENGE=HERE.parent/'skill-suite-challenge'

def load(path,label):
    spec=importlib.util.spec_from_file_location(label+'_'+uuid.uuid4().hex,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

base=load(PILOT/'run_eval.py','mechanism_base')
write_json=base.write_json
snapshot=base.snapshot
run_check=base.run_check

def skill_plan(case,variant):
    if not case.get('skill_setup'):return base.skill_plan(case,variant)
    setup=case['skill_setup'];target=setup['target_skill'];shared=setup.get('shared_skills',[])
    if setup.get('mode')!='target_ablation' or target in shared:raise ValueError('invalid mechanism ablation')
    for name in [target,*shared]:
        if '/' in name or name in ('.','..') or not (ROOT/'skills'/name/'SKILL.md').is_file():raise ValueError('invalid skill')
    resources=list(setup.get('shared_resources',[]))
    for name in [target,*shared]:
        for relative in re.findall(r'`(\.\./[^`]+)`',(ROOT/'skills'/name/'SKILL.md').read_text()):
            path=(ROOT/'skills'/name/relative).resolve()
            if path.is_file() and path.is_relative_to(ROOT/'skills') and path.name!='SKILL.md':
                source=str(path.relative_to(ROOT))
                if source not in {r['source'] for r in resources}:resources.append({'source':source,'destination':source})
    for resource in resources:
        src=Path(resource['source']);dst=Path(resource['destination'])
        if src.is_absolute() or dst.is_absolute() or '..' in src.parts or '..' in dst.parts or dst.name=='SKILL.md' or src.name=='SKILL.md':raise ValueError('unsafe shared resource')
        if not (ROOT/src).resolve().is_relative_to(ROOT) or not (ROOT/src).is_file():raise ValueError('invalid shared resource')
        # Only actual reference/assets files may reside under the omitted target directory.
        if dst.parts[:2]==('skills',target) and (len(dst.parts)<4 or dst.parts[2] not in ('references','assets')):raise ValueError('target body may not be shared')
    return {'mode':'target_ablation','target':target,'packages':sorted(shared+([target] if variant=='skills' else [])),'resources':resources}

def observed_target_read(events,target):
    if not target:return {'status':'not_applicable','event_ids':[]}
    body=(ROOT/'skills'/target/'SKILL.md').read_text()
    samples=[body[i:i+240] for i in range(0,min(len(body),2000),240) if len(body[i:i+240])==240]
    matches=[]
    for event in events:
        item=event.get('item',{})
        if event.get('type')=='item.completed' and item.get('type')=='command_execution':
            output=item.get('aggregated_output','')
            if sum(sample in output for sample in samples)>=2:matches.append(item.get('id'))
    return {'status':'read_output_observed' if matches else 'not_observed','event_ids':matches,'limitation':'At least two fixed 240-character body fragments observed; a later shell-command failure does not erase prior read output. Does not prove attention.'}

def prepared_runtime(case,run,command):
    setup=case.get('execution',{}).get('runtime_setup')
    if not setup:return None
    if setup.get('kind')!='agent_workflow_task' or setup.get('acceptance')!='pending':raise ValueError('unsupported runtime setup')
    packet={'operation_id':'mechanism-create','workspace':'/workspace','title':setup['title'],'requirements':setup['requirements'],'criteria':setup['criteria']}
    script='''import json,subprocess
from pathlib import Path

def call(action,packet):
 p=Path('/tmp/runtime-packet.json');p.write_text(json.dumps(packet))
 r=subprocess.run(['python3','-m','agent_workflow.cli','task',action,'--data-root','/data','--input',str(p)],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stdout+r.stderr)
 return json.loads(r.stdout)
r=call('create',PACKET)
r=call('bind',{'operation_id':'mechanism-bind','task_id':r['task_id'],'base_revision':r['revision'],'workspace':'/workspace','session_id':'eval-fixture'})
print(json.dumps({'task_id':r['task_id']}))
'''.replace('PACKET',repr(packet))
    result=subprocess.run(command+['python3','-'],input=script,capture_output=True,text=True,timeout=30)
    (run/'runtime-setup.txt').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('mechanism runtime setup infrastructure: '+result.stdout+result.stderr)
    return json.loads(result.stdout)['task_id']

def runtime_read(command,task):
    if not task:return None
    result=base.runtime_read(command,task)
    for name,args in [('task_inventory',['list']),('history',['history','--task',task]),('checklist',['checklist','--task',task])]:
        p=subprocess.run(command+['python3','-m','agent_workflow.cli','task',*args,'--data-root','/data'],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError('runtime readback infrastructure: '+p.stdout+p.stderr)
        result['_'+name]=json.loads(p.stdout)
    return result

def runtime_initial_signature(raw):
    state=raw.get('runtime_before')
    if not state:return None
    semantic={k:state.get(k) for k in ('title','requirements','state','criteria','feedback','recovery','artifacts')}
    return hashlib.sha256(json.dumps(semantic,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def module_for_run():
    module=load(PILOT/'run_eval.py','isolated_mechanism_runner')
    module.skill_plan=skill_plan;module.prepare_runtime=prepared_runtime;module.runtime_read=runtime_read;module.observed_target_read=observed_target_read
    original_sources=module.source_manifest
    def sources(case,variant):
        out=original_sources(case,variant)
        for path in sorted(HERE.glob('*.py')):out['@mechanisms/'+path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        return out
    module.source_manifest=sources
    return module

def source_manifest(case,variant):return module_for_run().source_manifest(case,variant)

def run_case(case,variant,rep,output,model,timeout=300,effort='medium'):
    result=module_for_run().run_case(case,variant,rep,output,model,timeout,effort)
    result['runtime_initial_signature']=runtime_initial_signature(result)
    write_json(Path(result['workspace']).parent/'result.json',result)
    return result

if __name__=='__main__':
    driver=load(CHALLENGE/'run_challenge.py','mechanism_driver')
    driver.HERE=HERE
    import sys
    driver.runner=sys.modules[__name__]
    raise SystemExit(driver.main())

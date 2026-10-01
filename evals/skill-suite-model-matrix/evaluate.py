"""Frozen four-model, four-suite paired replay. Never substitutes a requested model."""
import argparse
import concurrent.futures
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
MODELS=('gpt-6.1-sol','gpt-6-sol','gpt-5.6-sol','gpt-6-luna')
JUDGE_MODEL='gpt-6.1-sol'
REPS=2
SUBJECT_TIMEOUT=420
JUDGE_TIMEOUT=300
SUITES={
    'challenge':{'directory':'skill-suite-challenge','runner':'run_eval.py','runner_directory':'skill-suite-pilot','score':['skill-suite-corrections/reviewed_challenge_v3.py','score'],'report':['skill-suite-corrections/reviewed_challenge_v3.py','report']},
    'mechanisms':{'directory':'skill-suite-mechanisms','runner':'run_mechanisms.py','score':['skill-suite-corrections/reviewed_mechanisms.py','score'],'report':['skill-suite-corrections/reviewed_mechanisms.py','report']},
    'source-discovery':{'directory':'skill-suite-source-discovery','runner':'run_source_discovery.py','score':['skill-suite-source-discovery/score_source_discovery.py'],'report':['skill-suite-source-discovery/report_source_discovery.py']},
    'artifact-followup':{'directory':'skill-suite-artifact-followup','runner':'run_source_discovery.py','runner_directory':'skill-suite-source-discovery','score':['skill-suite-artifact-followup/evaluate.py','score'],'report':['skill-suite-artifact-followup/evaluate.py','report']},
}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');os.replace(temp,path)

def dataset(suite):return json.loads((HERE.parent/SUITES[suite]['directory']/'cases.json').read_text())['cases']

def freeze_sources():
    directories=[ROOT/'skills',ROOT/'shared',ROOT/'agent_workflow',ROOT/'learning_workflow']
    directories += [HERE.parent/name for name in ['skill-suite-pilot','skill-suite-challenge','skill-suite-mechanisms','skill-suite-source-discovery','skill-suite-artifact-followup','skill-suite-corrections','skill-suite-model-matrix']]
    files={ROOT/'scripts/codex_target_guard.py',ROOT/'docs/TASK_RUNTIME.md'}
    for directory in directories:
        files.update(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    hashes={str(path.relative_to(ROOT)):sha(path) for path in sorted(files)}
    binary=Path(shutil.which('codex')).resolve();hashes['@codex_binary:'+str(binary)]=sha(binary)
    for asset in [binary.parent/'codex-code-mode-host']:
        if not asset.is_file():raise RuntimeError('CLI runtime asset missing: '+str(asset))
        hashes['@cli_asset:'+str(asset)]=sha(asset)
    return hashes

def verify_frozen(manifest):
    for name,expected in manifest['frozen_files'].items():
        path=Path(name.split(':',1)[1]) if name.startswith(('@codex_binary:','@cli_asset:')) else ROOT/name
        if not path.is_file() or sha(path)!=expected:raise RuntimeError('Frozen source changed: '+name)

def planned_manifest():
    cases={suite:dataset(suite) for suite in SUITES}
    return {'schema_version':'skill-model-matrix/1','models':list(MODELS),'judge_model':JUDGE_MODEL,'effort':'medium','subject_timeout_seconds':SUBJECT_TIMEOUT,'judge_timeout_seconds':JUDGE_TIMEOUT,'reps':REPS,'maximum_parallel_model_processes_per_invocation':6,'subject_case_count':sum(len(c) for c in cases.values()),'expected_subjects':len(MODELS)*sum(len(c) for c in cases.values())*2*REPS,'case_sha256':{suite:{c['id']:digest(c) for c in rows} for suite,rows in cases.items()},'frozen_files':freeze_sources(),'order':'each model/suite/case: skills/control then control/skills; separate cases may overlap','model_policy':'Exact requested model only; no fallback. Missing served-model field stays unverified.','source_revision':subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()}

def ensure_manifest(output,action):
    path=output/'matrix-manifest.json'
    if path.exists():
        manifest=json.loads(path.read_text());verify_frozen(manifest)
        if manifest['models']!=list(MODELS) or manifest['judge_model']!=JUDGE_MODEL or manifest['subject_timeout_seconds']!=SUBJECT_TIMEOUT or manifest.get('judge_timeout_seconds')!=JUDGE_TIMEOUT or manifest.get('effort')!='medium' or manifest.get('reps')!=REPS:raise RuntimeError('Matrix protocol differs from saved manifest')
        return manifest
    if action not in ('plan','run'):raise RuntimeError('Run or plan must freeze the matrix before scoring/reporting')
    manifest=planned_manifest();write(path,manifest);return manifest

def load_runner(suite):
    config=SUITES[suite];directory=HERE.parent/config.get('runner_directory',config['directory'])
    sys.path.insert(0,str(directory))
    spec=importlib.util.spec_from_file_location('matrix_runner_'+uuid.uuid4().hex,directory/config['runner'])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if suite=='artifact-followup':module.configure(HERE.parent/config['directory'])
    return module

def run_case_job(output,suite,model,cid):
    if model not in MODELS or suite not in SUITES:raise ValueError('Unsupported matrix selection')
    manifest=json.loads((output/'matrix-manifest.json').read_text());verify_frozen(manifest)
    case=next(c for c in dataset(suite) if c['id']==cid)
    if digest(case)!=manifest['case_sha256'][suite][cid]:raise RuntimeError('Frozen case changed')
    runner=load_runner(suite);runs=output/model/suite/'runs';pairs=[]
    for rep in range(1,REPS+1):
        order=['skills','control'] if rep%2 else ['control','skills'];results={};schedule=[]
        for arm in order:
            verify_frozen(manifest);start=time.time()
            raw=runner.run_case(case,arm,rep,runs,model,timeout=SUBJECT_TIMEOUT,effort='medium')
            if raw.get('model_requested')!=model:raise RuntimeError('Requested model mismatch; no substitution permitted')
            if raw.get('model_observed') and raw['model_observed']!=model:raise RuntimeError('Served model mismatch; no substitution permitted')
            if raw.get('effort')!='medium' or raw.get('timeout_seconds')!=SUBJECT_TIMEOUT:raise RuntimeError('Reused trial budget mismatch')
            raw['matrix_protocol']={'manifest_sha256':digest(manifest),'subject_model_requested':model,'judge_model_requested':JUDGE_MODEL,'served_model_verified':bool(raw.get('model_observed'))}
            write(Path(raw['workspace']).parent/'result.json',raw)
            results[arm]=raw;schedule.append({'arm':arm,'started_at_unix':start,'finished_at_unix':time.time()})
        a=results['control'];b=results['skills'];prefix='skills/'+case['target_skill']+'/'
        delta={key for key in set(a['source_files'])|set(b['source_files']) if a['source_files'].get(key)!=b['source_files'].get(key)}
        pair={'case_id':cid,'rep':rep,'subject_model':model,'suite':suite,'statuses':{arm:raw['status'] for arm,raw in results.items()},'same_fixture':a['before']==b['before'],'same_model_budget':all(a.get(key)==b.get(key) for key in ['model_requested','effort','timeout_seconds']),'target_only_source_difference':bool(delta) and all(key.startswith(prefix) for key in delta),'source_delta':sorted(delta),'installed_skills':{arm:raw['installed_skills'] for arm,raw in results.items()},'target_load':b.get('target_load'),'runtime_initial_signature':{arm:raw.get('runtime_initial_signature') for arm,raw in results.items()},'same_runtime_seed':not case.get('execution',{}).get('runtime_setup') or bool(a.get('runtime_initial_signature')) and a.get('runtime_initial_signature')==b.get('runtime_initial_signature'),'schedule':schedule,'raw_paths':{arm:str(Path(raw['workspace']).parent/'result.json') for arm,raw in results.items()}}
        write(runs/f'pair-{cid}-{rep}.json',pair);pairs.append(pair)
    return 0 if all(all(status=='ok' for status in p['statuses'].values()) for p in pairs) else 1

def selected(value,allowed):
    values=list(allowed) if value=='all' else value.split(',')
    if not values or len(values)!=len(set(values)) or any(v not in allowed for v in values):raise ValueError('Unknown or duplicate selection: '+value)
    return values

def stage_command(action,suite,model,output):
    config=SUITES[suite];location=output/model/suite
    raw=config[action];cmd=[sys.executable,str(HERE.parent/raw[0]),*raw[1:],'--runs',str(location/'runs')]
    if action=='score':cmd+=['--output',str(location/'scored'),'--model',JUDGE_MODEL,'--workers','1']
    else:cmd+=['--scored',str(location/'scored'),'--output',str(location/'report'),'--reps',str(REPS)]
    return cmd

def run_logged(command,log):
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('w') as stream:
        result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,text=True)
    return result.returncode

def refresh_report_model_text(output,model,suite):
    folder=output/model/suite/'report';path=folder/'RESULTS.md'
    if path.exists():
        text=path.read_text().replace('只记录实际请求的 gpt-5.5 / medium；',f'本组被测 Agent 请求 {model} / medium（420 秒预算），固定 Judge 请求 {JUDGE_MODEL} / medium（300 秒预算）；')
        calibration=output/'calibration/summary.json'
        calibration_note='独立运行的固定 Judge 请求 gpt-6.1-sol。'
        if calibration.exists():
            checks=json.loads(calibration.read_text())
            calibration_note+=f"预设校准样例 {checks.get('matched',0)}/{checks.get('count',0)} 与预期一致；这不是用户偏好标签，也不能保证全部真实样本判分正确。"
        else:calibration_note+='此输出目录没有预设校准摘要；不能声称已校准。'
        text=text.replace('它与被测 Agent 请求同一模型，未经过人工标签校准；',calibration_note)
        path.write_text(text)
    summary=folder/'summary.json'
    if summary.exists():
        data=json.loads(summary.read_text());data['model_matrix']={'subject_requested':model,'judge_requested':JUDGE_MODEL,'served_model_identity':'unverified unless explicitly present in original CLI event'};write(summary,data)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['plan','run','score','report','_case'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--models',default='all');parser.add_argument('--suites',default='all');parser.add_argument('--cases',default='all');parser.add_argument('--workers',type=int,default=6)
    parser.add_argument('--case-id');parser.add_argument('--subject-model');parser.add_argument('--suite')
    args=parser.parse_args();output=args.output.resolve()
    if output.is_relative_to(ROOT):parser.error('Output must be outside source checkout')
    if not 1<=args.workers<=6:parser.error('--workers must be 1..6')
    if args.action=='_case':return run_case_job(output,args.suite,args.subject_model,args.case_id)
    models=selected(args.models,MODELS);suites=selected(args.suites,SUITES)
    output.mkdir(parents=True,exist_ok=True);manifest=ensure_manifest(output,args.action)
    if args.action=='plan':print(json.dumps({'expected_subjects':manifest['expected_subjects'],'path':str(output/'matrix-manifest.json')},ensure_ascii=False));return 0
    jobs=[]
    if args.action=='run':
        wanted=None if args.cases=='all' else set(args.cases.split(','));found=set()
        case_index=0
        for suite in suites:
            for case in dataset(suite):
                if wanted is not None and case['id'] not in wanted:continue
                found.add(case['id'])
                rotation=case_index%len(models);case_index+=1
                for model in models[rotation:]+models[:rotation]:
                    key=(model,suite,case['id'])
                    cmd=[sys.executable,str(Path(__file__).resolve()),'_case','--output',str(output),'--subject-model',model,'--suite',suite,'--case-id',case['id']]
                    jobs.append((key,cmd,output/model/suite/'logs'/f"run-{case['id']}.log"))
        if wanted is not None and found!=wanted:parser.error('Case selection not in selected suites')
    else:
        for model in models:
            for suite in suites:jobs.append(((model,suite),stage_command(args.action,suite,model,output),output/model/suite/'logs'/f'{args.action}.log'))
    # Prevent an accidental second subject orchestrator from doubling concurrency.
    stage_lock=(output/f'.{args.action}.lock').open('a')
    try:fcntl.flock(stage_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('This matrix stage is already running: '+args.action)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(run_logged,cmd,log):(key,log) for key,cmd,log in jobs}
        for future in concurrent.futures.as_completed(futures):
            key,log=futures[future]
            try:code=future.result();error=None
            except Exception as e:code=1;error=str(e)
            if args.action=='report':refresh_report_model_text(output,key[0],key[1])
            record={'job':key,'exit_code':code,'error':error,'log':str(log)};results.append(record)
            write(output/'progress'/args.action/('-'.join(key)+'.json'),record)
            print(json.dumps(record,ensure_ascii=False),flush=True)
    write(output/f'{args.action}-index.json',results)
    stage_lock.close()
    return int(any(r['exit_code']!=0 for r in results))

if __name__=='__main__':raise SystemExit(main())

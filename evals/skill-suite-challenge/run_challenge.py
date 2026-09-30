#!/usr/bin/env python3
"""Paired explicit-skill ablation. Rep 1 A/B, rep 2 B/A; pairs run serially."""
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('pilot_runner',HERE.parent/'skill-suite-pilot/run_eval.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def compare_pair(case,a,b):
    target=case['skill_setup']['target_skill'];prefix='skills/'+target+'/'
    sources_a=a.get('source_files',{});sources_b=b.get('source_files',{})
    delta={key:{'skills':sources_a.get(key),'control':sources_b.get(key)} for key in set(sources_a)|set(sources_b) if sources_a.get(key)!=sources_b.get(key)}
    unexpected=[key for key in delta if not key.startswith(prefix)]
    return {'case_id':case['id'],'rep':a.get('rep',b.get('rep')),'target_skill':target,'source_delta':delta,'unexpected_source_delta':unexpected,'installed_skills':{'skills':a.get('installed_skills'),'control':b.get('installed_skills')},'target_only_source_difference':bool(delta) and not unexpected,'same_fixture':a.get('before')==b.get('before'),'same_model_budget':all(a.get(k)==b.get(k) for k in ('model_requested','effort','timeout_seconds')),'target_load':a.get('target_load'),'skills_result':str(Path(a['workspace']).parent/'result.json') if a.get('workspace') else None,'control_result':str(Path(b['workspace']).parent/'result.json') if b.get('workspace') else None,'statuses':{'skills':a['status'],'control':b['status']}}

def run_pair(case,rep,args,frozen):
    for path,sha in frozen.items():
        if digest(Path(path))!=sha:raise RuntimeError('frozen source changed: '+path)
    order=['skills','control'] if rep%2 else ['control','skills'];results={};schedule=[]
    for variant in order:
        # Verify grading assets and cases have not drifted while prior runs execute.
        for path,sha in frozen.items():
            if digest(Path(path))!=sha:raise RuntimeError('frozen source changed: '+path)
        start=time.time()
        results[variant]=runner.run_case(case,variant,rep,args.output,args.model,args.timeout,args.effort)
        schedule.append({'variant':variant,'started_at_unix':start,'finished_at_unix':time.time()})
    pair=compare_pair(case,results['skills'],results['control']);pair['schedule']=schedule
    runner.write_json(args.output/f"pair-{case['id']}-{rep}.json",pair)
    return pair

def run_case_pairs(case,args,frozen):
    pairs=[]
    for rep in range(1,args.reps+1):
        try:pairs.append(run_pair(case,rep,args,frozen))
        except Exception as error:
            failure={'case_id':case['id'],'rep':rep,'infra_error':str(error)}
            runner.write_json(args.output/f"pair-{case['id']}-{rep}-error.json",failure);pairs.append(failure)
    return pairs

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',default='all');parser.add_argument('--dataset',type=Path,default=HERE/'cases.json');parser.add_argument('--output',type=Path,required=True);parser.add_argument('--reps',type=int,default=2);parser.add_argument('--workers',type=int,default=3);parser.add_argument('--model',default='gpt-5.5');parser.add_argument('--effort',default='medium');parser.add_argument('--timeout',type=int,default=300)
    args=parser.parse_args();args.output=args.output.resolve()
    if args.output.is_relative_to(runner.ROOT):parser.error('output must be outside source checkout')
    if args.reps<1 or args.workers<1:parser.error('positive reps/workers required')
    dataset=json.loads(args.dataset.read_text());cases=dataset['cases'];ids=None if args.cases=='all' else set(args.cases.split(','));cases=[c for c in cases if ids is None or c['id'] in ids]
    if not cases or (ids and ids!={c['id'] for c in cases}):parser.error('unknown case selection')
    for case in cases:
        for variant in ('skills','control'):runner.skill_plan(case,variant)
        if not case.get('skill_setup'):parser.error('challenge requires explicit target ablation skill_setup')
    args.output.mkdir(parents=True,exist_ok=True)
    files=[Path(__file__).resolve(),Path(runner.__file__).resolve(),args.dataset.resolve()]
    files.extend(p for p in HERE.glob('*') if p.is_file() and p.suffix in ('.py','.json','.md'))
    frozen={str(p):digest(p) for p in files}
    # Both conditions' entire copied resource contents are frozen, not just git HEAD.
    resources={c['id']:{v:runner.source_manifest(c,v) for v in ('skills','control')} for c in cases}
    frozen.update({str(runner.ROOT/path):sha for conditions in resources.values() for source in conditions.values() for path,sha in source.items() if not path.startswith('@')})
    manifest={'schema_version':1,'design':'explicit target skill content ablation; not natural trigger evaluation','frozen_files':frozen,'resources':resources,'model':args.model,'effort':args.effort,'timeout':args.timeout,'reps':args.reps,'schedule':'rep odd skills/control; rep even control/skills; each pair serial, different cases concurrent; repetitions within each case serial','source_revision':runner.subprocess.run(['git','rev-parse','HEAD'],cwd=runner.ROOT,capture_output=True,text=True).stdout.strip()}
    previous=args.output/'manifest.json'
    if previous.exists() and json.loads(previous.read_text())!=manifest:parser.error('output manifest differs; use a fresh output directory')
    runner.write_json(previous,manifest)
    pairs=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(run_case_pairs,c,args,frozen):c['id'] for c in cases}
        for future in concurrent.futures.as_completed(jobs):
            cid=jobs[future]
            try:case_pairs=future.result()
            except Exception as error:case_pairs=[{'case_id':cid,'infra_error':str(error)}]
            for pair in case_pairs:
                pairs.append(pair);print(json.dumps({'pair':[cid,pair.get('rep')],'infra_error':pair.get('infra_error'),'statuses':pair.get('statuses')},ensure_ascii=False),flush=True)
    runner.write_json(args.output/'pairs.json',pairs)
    return 1 if any(p.get('infra_error') or any(s!='ok' for s in p.get('statuses',{}).values()) for p in pairs) else 0

if __name__=='__main__':raise SystemExit(main())

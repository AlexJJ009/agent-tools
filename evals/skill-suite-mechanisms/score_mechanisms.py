"""Score mechanism cases with frozen challenge judge plumbing and actual runtime checks."""
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_mechanisms as harness
import grade_mechanisms as grader
base=harness.load(harness.CHALLENGE/'score_challenge.py','mechanism_scorer')
base.HERE=HERE;base.harness=harness;base.grader=grader
ROOT=harness.ROOT
digest=base.digest
dump=base.dump
latest_trials=base.latest_trials
call_judge=base.call_judge

def grading_identity(case,raw,model='gpt-5.5'):
    files=[*HERE.glob('*.py'),harness.CHALLENGE/'grade_challenge.py',harness.CHALLENGE/'score_challenge.py',harness.PILOT/'grade_eval.py',harness.PILOT/'run_eval.py',ROOT/'shared/writing/reader-facing-contract.md']
    return digest({'case':case,'raw':raw,'judge_model_requested':model,'sources':{str(p.relative_to(ROOT)):p.read_text() for p in files}})

def task_ids(value):
    if isinstance(value,dict):return ({value['task_id']} if isinstance(value.get('task_id'),str) else set())|set().union(*(task_ids(v) for v in value.values()))
    if isinstance(value,list):return set().union(*(task_ids(v) for v in value))
    return set()

def score_one(case,path,raw,output,model):
    identity=grading_identity(case,raw,model);target=output/'grades'/f"{case['id']}-{raw['variant']}-{raw['rep']}-{identity[:12]}.json"
    if target.exists():return json.loads(target.read_text())
    if raw['case_sha256']!=digest(case):raise RuntimeError('Frozen case differs from execution')
    machine=grader.grade_programmatic(case,raw['before'],raw['after'],raw['events'],raw['workspace'],harness.run_check)
    machine.update(grader.grade_runtime(case,raw.get('runtime_before'),raw.get('runtime_after')))
    if case.get('execution',{}).get('runtime_setup'):
        before=raw.get('runtime_before') or {};after=raw.get('runtime_after') or {}
        if '_task_inventory' not in before or '_task_inventory' not in after:raise RuntimeError('runtime task inventory missing')
        a=task_ids(before['_task_inventory']);b=task_ids(after['_task_inventory'])
        machine[case['id']+'.no_new_task']={'passed':a==b=={before['task_id']},'scope':'guardrail','reason':'Task inventory remains the original isolated task; no replacement or extra task.','evidence':[json.dumps({'before':sorted(a),'after':sorted(b)})]}
    judged,jr=base.call_judge(case,raw['output'],raw['events'],raw['before'],raw['after'],machine,output/'judges'/identity[:16],model)
    verdict=grader.combine_verdict(case,machine,judged)
    record={'identity':identity,'case_id':case['id'],'variant':raw['variant'],'rep':raw['rep'],'raw_path':str(path),'case_sha256':digest(case),'verdict':verdict,'judge':judged,'judge_usage':jr.get('usage'),'judge_model_requested':model,'judge_model_observed':jr.get('model_observed'),'judge_path':str(output/'judges'/identity[:16])}
    dump(target,record)
    print(json.dumps({'graded':case['id'],'variant':raw['variant'],'rep':raw['rep'],'primary':verdict['primary_pass'],'guardrails':verdict['guardrails_pass'],'writing':verdict['writing_pass']}),flush=True)
    return record

base.grading_identity=grading_identity;base.score_one=score_one
if __name__=='__main__':raise SystemExit(base.main())

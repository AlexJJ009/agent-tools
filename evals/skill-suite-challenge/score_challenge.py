"""Score frozen challenge trials with separate semantic judges with arm labels withheld."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PILOT = HERE.parent / 'skill-suite-pilot'
sys.path.insert(0, str(PILOT))
sys.path.insert(0, str(HERE))
import run_eval as harness
import grade_challenge as grader


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def grading_identity(case, raw, model="gpt-5.5"):
    return digest({'case':case,'raw':raw,'judge_model_requested':model,
                   'writing_contract':(ROOT/'shared/writing/reader-facing-contract.md').read_text(),
                   'scorer':Path(__file__).read_text(),
                   'runner':(PILOT/'run_eval.py').read_text(),
                   'grader':(HERE/'grade_challenge.py').read_text(),
                   'shared_grader':(PILOT/'grade_eval.py').read_text()})


def latest_trials(runs):
    trials = {}
    paths = sorted(runs.glob('*/result.json'), key=lambda p:int(re.search(r'-attempt(\d+)$',p.parent.name).group(1)) if re.search(r'-attempt(\d+)$',p.parent.name) else 1)
    for path in paths:
        raw = json.loads(path.read_text())
        key = (raw.get('case_id'), raw.get('variant'), raw.get('rep'))
        trials[key] = (path, raw)
    return trials


def call_judge(case, output_text, events, before, after, machine, output, model):
    contract = (ROOT/'shared/writing/reader-facing-contract.md').read_text()
    prompt = grader.judge_prompt(case,output_text,events,before,after,machine,contract)
    jc = {'id':'judge-'+case['id'],'prompt':prompt,'fixtures':{'files':{}},
          'target_skills':[], 'output_schema':grader.judge_schema(case)}
    raw = harness.run_case(jc,'control',1,output,model,timeout=300)
    if raw['status']!='ok':
        raise RuntimeError('judge execution failed: '+str(raw.get('error')))
    text = raw['output'].strip()
    if text.startswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    result=json.loads(text)
    return result,raw


def score_one(case, path, raw, output, model):
    identity=grading_identity(case,raw,model)
    target=output/'grades'/f"{case['id']}-{raw['variant']}-{raw['rep']}-{identity[:12]}.json"
    if target.exists():return json.loads(target.read_text())
    if raw['case_sha256']!=digest(case):
        raise RuntimeError('Frozen case bytes differ from executed trial')
    machine=grader.grade_programmatic(case,raw['before'],raw['after'],raw['events'],raw['workspace'],harness.run_check)
    judged,jr=call_judge(case,raw['output'],raw['events'],raw['before'],raw['after'],machine,output/'judges'/identity[:16],model)
    verdict=grader.combine_verdict(case,machine,judged)
    record={'identity':identity,'case_id':case['id'],'variant':raw['variant'],'rep':raw['rep'],
            'raw_path':str(path),'case_sha256':digest(case),'verdict':verdict,'judge':judged,
            'judge_usage':jr.get('usage'),'judge_model_requested':model,
            'judge_model_observed':jr.get('model_observed'),'judge_path':str(output/'judges'/identity[:16])}
    dump(target,record)
    print(json.dumps({'graded':case['id'],'variant':raw['variant'],'rep':raw['rep'],
                      'primary':verdict['primary_pass'],'guardrails':verdict['guardrails_pass'],
                      'writing':verdict['writing_pass']}),flush=True)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',default='gpt-5.5')
    parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--cases',default='all')
    args=parser.parse_args()
    cases={c['id']:c for c in json.loads((HERE/'cases.json').read_text())['cases']}
    selected=set(cases) if args.cases=='all' else set(args.cases.split(','))
    records=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs={}
        for (cid,variant,rep),(path,raw) in latest_trials(args.runs).items():
            if cid not in selected:continue
            if raw.get('status')!='ok':
                errors.append({'case_id':cid,'variant':variant,'rep':rep,'failure_class':'execution','raw':str(path)});continue
            jobs[pool.submit(score_one,cases[cid],path,raw,args.output,args.model)]=(cid,variant,rep)
        for future in concurrent.futures.as_completed(jobs):
            try:records.append(future.result())
            except Exception as error:
                failure={'trial':jobs[future],'failure_class':'grading','error':str(error)}
                errors.append(failure);print(json.dumps(failure),flush=True)
    dump(args.output/'index.json',{'records':records,'errors':errors})
    return bool(errors)

if __name__=='__main__':raise SystemExit(main())

"""Grade completed isolated trials; save independent judge evidence and flow reports."""
import argparse
import concurrent.futures
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import grade_eval as grader
import run_eval as harness


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def judge(case, final, events, before, after, machine, output, model):
    contract = (ROOT/'shared/writing/reader-facing-contract.md').read_text()
    prompt = grader.judge_prompt(case, final, events, before, after, machine, contract)
    jc = {'id':'judge-'+case['id'], 'prompt':prompt, 'fixtures':{'files':{}},
          'target_skills':[], 'output_schema':grader.judge_schema(case)}
    result = harness.run_case(jc, 'control', 1, output, model, timeout=240)
    if result['status'] != 'ok':
        raise RuntimeError('judge execution: '+str(result['error']))
    text = result['output'].strip()
    if text.startswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    verdict = json.loads(text)
    return verdict, result


def score_one(path, cases, output, model):
    raw = json.loads(path.read_text())
    if raw['status'] != 'ok':
        return {'path':str(path),'status':'execution_error','error':raw.get('error')}
    case = cases[raw['case_id']]
    identity = digest({'case':case,'raw':raw,'grader':(HERE/'grade_eval.py').read_text()})
    target = output/'grades'/f"{raw['case_id']}-{raw['variant']}-{raw['rep']}-{identity[:12]}.json"
    if target.exists():
        return json.loads(target.read_text())
    machine = grader.grade_programmatic(case, raw['before'], raw['after'], raw['events'],
                                       raw['workspace'], harness.run_check)
    machine.update(grader.grade_runtime(case, raw.get('runtime_before'), raw.get('runtime_after')))
    events = list(raw['events'])
    if raw.get('task_id'):
        events.append({'type':'evaluator_runtime_readback', 'before':raw.get('runtime_before'),
                       'after':raw.get('runtime_after'), 'not_agent_action':True})
    jd, jr = judge(case, raw['output'], events, raw['before'], raw['after'], machine,
                   output/'judges'/identity[:16], model)
    combined = grader.combine_verdict(case, machine, jd)
    record = {'identity':identity,'status':'ok','raw_path':str(path),'case_id':case['id'],
              'variant':raw['variant'],'rep':raw['rep'],'flow':case['flow'],
              'verdict':combined,'judge':jd,'judge_usage':jr.get('usage'),
              'judge_model_requested':jr.get('model_requested'),
              'judge_model_observed':jr.get('model_observed'),
              'judge_path':str(output/'judges'/identity[:16]),'case_sha256':digest(case)}
    dump(target, record)
    print(json.dumps({'graded':case['id'],'variant':raw['variant'],'verdict':combined.get('task_pass',combined.get('passed'))}), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases',default='all')
    parser.add_argument('--model',default='gpt-5.5')
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    cases={c['id']:c for c in json.loads((HERE/'cases.json').read_text())['cases']}
    selected=set(cases) if args.cases=='all' else set(args.cases.split(','))
    latest={}
    for p in sorted(args.runs.glob('*/result.json'), key=lambda p:(int(re.search(r'-attempt(\d+)$',p.parent.name).group(1)) if re.search(r'-attempt(\d+)$',p.parent.name) else 1)):
        r=json.loads(p.read_text())
        if r.get('case_id') in selected and r.get('status')=='ok':
            latest[(r['case_id'],r['variant'],r['rep'])]=p
    paths=list(latest.values())
    if not paths:parser.error('no completed trials to grade')
    records=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(score_one,p,cases,args.output,args.model):p for p in paths}
        for future in concurrent.futures.as_completed(jobs):
            try:records.append(future.result())
            except Exception as exc:
                error={'path':str(jobs[future]),'failure_class':'grading_error','error':str(exc)}
                errors.append(error);print(json.dumps(error),flush=True)
    dump(args.output/'grading-index.json',{'records':records,'errors':errors})
    return bool(errors)

if __name__=='__main__':raise SystemExit(main())

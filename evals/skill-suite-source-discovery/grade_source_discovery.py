"""Dispatch declared source graders internally; preserve follow-up IDs at interfaces."""
import copy
import json
import run_source_discovery as runner
challenge=runner.load(runner.CHALLENGE/'grade_challenge.py','source_grader')
mechanisms=runner.load(runner.MECHANISMS/'grade_mechanisms.py','source_mechanism_grader')
judge_schema=challenge.judge_schema
combine_verdict=challenge.combine_verdict
calibration_assets=challenge.calibration_assets
WRITING_IDS=challenge.WRITING_IDS

def original_grader(case):
    design=case.get('followup_design',{});suite=design.get('source_grader_suite','challenge');cid=design.get('source_grader_case_id')
    roots={'challenge':runner.CHALLENGE,'mechanisms':runner.MECHANISMS}
    if suite not in roots or cid not in {c['id'] for c in json.loads((roots[suite]/'cases.json').read_text())['cases']}:raise ValueError('Unsupported predeclared source grader mapping')
    return (challenge if suite=='challenge' else mechanisms),cid

def judge_prompt(case,*args,**kwargs):
    grader,_=original_grader(case)
    return grader.judge_prompt(case,*args,**kwargs)

def grade_programmatic(case,before,after,events,workspace,run_check):
    grader,source_id=original_grader(case);mapped=copy.deepcopy(case);mapped['id']=source_id
    checks=grader.grade_programmatic(mapped,before,after,events,workspace,run_check)
    return {case['id']+key.removeprefix(source_id):value for key,value in checks.items()}

def grade_runtime(case,before,after):
    if before is not None or after is not None:raise ValueError('Unexpected runtime in source-location follow-up')
    return {}

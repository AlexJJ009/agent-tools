"""Stateful mechanism checks; reuses frozen challenge judgment contracts read-only."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_CHALLENGE_PATH=Path(__file__).resolve().parents[1]/'skill-suite-challenge'/'grade_challenge.py'
_SPEC=importlib.util.spec_from_file_location('_mechanisms_challenge_grader',_CHALLENGE_PATH)
_challenge=importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_challenge)
WRITING_IDS=_challenge.WRITING_IDS
_pilot=_challenge._pilot
judge_schema=_challenge.judge_schema
combine_verdict=_challenge.combine_verdict
calibration_assets=_challenge.calibration_assets


def judge_prompt(case,final_text,events,before,after,machine_checks,writing_contract=''):
    prefix='''这一轮检查实际持久学习状态或文件关系，不能只因聊天总结说得正确就通过。
来源引用必须可复查；已有观察和新观察不能混为一谈；帮助后答对不能升级为独立掌握。
未作答题不能写成通过、失败或已完成；阅读、材料交付、收到提醒也不是实际尝试。
允许可表达同等事实的字段、措辞、增加元数据和等价迁移，不强制某份oracle布局。
区分schema/文件语法有效与语义真实。程序检查只是必要条件；逐项核查before/after内容。
portable记录不是强制字段schema：允许result/outcome/status等字段重组及语义等价的提示后成功表示。
不得只因不同于oracle的字段名、层级或状态拼写而扣分；检查身份、实际回答、帮助和证据关系。
'''
    return prefix+_challenge.judge_prompt(case,final_text,events,before,after,machine_checks,writing_contract)


def grade_programmatic(case,before,after,events,workspace,run_check):
    cid=case['id']
    checks={}
    def record(suffix,passed,reason,evidence,scope='primary'):
        checks[f'{cid}.{suffix}']={'passed':bool(passed),'reason':reason,'evidence':evidence,'scope':scope}
    def unchanged(paths):
        record('preserved',all(_pilot._digest(before,p) is not None and _pilot._digest(before,p)==_pilot._digest(after,p) for p in paths),
               'Protected source material retains original bytes.',
               [f'{p}: {_pilot._digest(before,p)} -> {_pilot._digest(after,p)}' for p in paths],'guardrail')
    def changed(path):
        record('changed_'+path,bool(_pilot._content(after,path)) and _pilot._digest(before,path)!=_pilot._digest(after,path),
               'Required owning artifact changes on disk; prose alone cannot satisfy the task.',
               [f'{path}: {_pilot._digest(before,path)} -> {_pilot._digest(after,path)}'])
    def execute(code,suffix,scope='primary'):
        outcome=run_check(code+'\nprint(__import__("json").dumps({"mechanism_assertions_passed":True}))\n',workspace)
        if not isinstance(outcome,dict) or 'returncode' not in outcome:
            raise ValueError('run_check requires returncode/stdout/stderr')
        if outcome.get('infra_error') or outcome.get('timed_out'):
            raise RuntimeError(f'Grader infrastructure failure: {outcome}')
        stdout=outcome.get('stdout','')
        try:last=json.loads(stdout.strip().splitlines()[-1])
        except (ValueError,TypeError,IndexError):last=None
        record(suffix,outcome['returncode']==0 and last=={'mechanism_assertions_passed':True},
               'Independent sandbox assertions on actual final artifacts.',
               [f'exit_code={outcome["returncode"]}',f'stdout={stdout[-4000:]}',f'stderr={outcome.get("stderr", "")[-4000:]}'],scope)
    if cid in {'L01','L02'}:
        unchanged(['copy_example.py'])
        original_text=_pilot._content(before,'learning-record.json')
        if original_text is None:
            raise ValueError('Initial portable record snapshot is missing')
        original=json.loads(original_text)
        if cid=='L02':
            changed('learning-record.json')
        # Stable identities and source locators are data contracts. Search by
        # identity rather than forcing optional fields into one nesting layout.
        common=f'original={original!r}\n'
        common+='''import json
from pathlib import Path
record=json.loads(Path("learning-record.json").read_text())
assert isinstance(record,dict), "Owning learning record must remain readable JSON"
def dictionaries(value):
    if isinstance(value,dict):
        yield value
        for v in value.values(): yield from dictionaries(v)
    elif isinstance(value,list):
        for v in value: yield from dictionaries(v)
def strings(value):
    if isinstance(value,str): yield value
    elif isinstance(value,dict):
        for v in value.values(): yield from strings(v)
    elif isinstance(value,list):
        for v in value: yield from strings(v)
def identity(value,identifier):
    found=[d for d in dictionaries(value) if d.get("id")==identifier or
           (d.get("attempt_id")==identifier and d.get("id",identifier)==identifier)]
    assert len(found)==1, ("Missing/duplicate stable identity",identifier,len(found))
    return found[0]
check=identity(record,"check-copy-transfer")
assert "kc-copy" in list(strings(check)), "Check target identity lost"
assert check.get("source_ref") or check.get("source_refs") or check.get("source"), "Check source relation missing"
refs=[d for d in dictionaries(record) if d.get("path")=="copy_example.py"]
assert any(d.get("repository")=="fixture://copy-study" and d.get("revision")=="fixture-v1" for d in refs), "Recheckable source identity lost"
assert all(d.get("path")=="copy_example.py" for d in refs)
for old_id in ["a-dict-1","a-copy-1"]:
    old=identity(original,old_id)
    current=identity(record,old_id)
    old_values=[old["attempt_id"],old["check_id"],old["target_id"],old["response"],*old.get("assistance",[])]
    now_values=list(strings(current))
    assert all(v in now_values for v in old_values), ("Historical observation lost",old_id)
closure=identity(record,"kc-closure")
assert not any(s in {"independent_pass","hinted_pass","fail","mastered","completed"} for s in strings(closure)), "Unattempted closure fabricated as assessed"
'''
        execute(common,'record_identity','guardrail' if cid=='L02' else 'primary')
        if cid=='L01':
            code=common+'''
assert not any(s in {"completed","independent_pass","hinted_pass","fail","failed"} for s in strings(check)), "Unanswered check represented as assessed/completed"
assert not any(s in {"independent_pass","fail","completed","mastered"} for s in strings(identity(record,"kc-copy"))), "No new attempt supports KC promotion"
old_attempt_ids={d.get("attempt_id",d.get("id")) for d in dictionaries(original) if str(d.get("attempt_id",d.get("id",""))).startswith("a-")}
new_attempt_ids={d.get("attempt_id",d.get("id")) for d in dictionaries(record) if str(d.get("attempt_id",d.get("id",""))).startswith("a-")}
assert old_attempt_ids==new_attempt_ids, "New attempt fabricated without learner response"
old_checks={d["id"] for d in dictionaries(original) if str(d.get("id","")).startswith("check-")}
new_checks={d["id"] for d in dictionaries(record) if str(d.get("id","")).startswith("check-")}
assert old_checks==new_checks, "Duplicate/new check created instead of resuming pending check"
'''
            execute(code,'unanswered_state_retained','guardrail')
        else:
            code=common+'''
attempt=identity(record,"a-copy-transfer-1")
previous=identity(original,"a-copy-transfer-1")
values=list(strings(attempt))
assert "check-copy-transfer" in values and "kc-copy" in values, "Attempt target/check linkage lost"
for hint in previous["assistance"]:
    assert hint in values, "Previously supplied hint omitted from observed attempt"
response=attempt.get("response",attempt.get("answer",attempt.get("learner_response")))
assert isinstance(response,(str,dict,list)) and bool(response), "Actual learner response not saved"
assert attempt!=previous, "Only prose changed, original attempt not updated"
# This is a necessary condition, not semantic classification of arbitrary status
# wording. Equivalent successful-assisted representations are judged from JSON.
assert not any(s=="independent_pass" for s in values), "Assisted attempt marked independent"
result=attempt.get("result",attempt.get("outcome",attempt.get("status")))
assert result not in (None,"","untested","pending","fail","failed"), "Observed success not represented"
old_attempt_ids={d.get("attempt_id",d.get("id")) for d in dictionaries(original) if str(d.get("attempt_id",d.get("id",""))).startswith("a-")}
new_attempt_ids={d.get("attempt_id",d.get("id")) for d in dictionaries(record) if str(d.get("attempt_id",d.get("id",""))).startswith("a-")}
assert old_attempt_ids==new_attempt_ids, "Original attempt replaced or duplicate created"
'''
            execute(code,'assisted_attempt_saved')
    elif cid=='L04':
        unchanged(['cache.py','source-context.md'])
        execute('''import json
from pathlib import Path
record=json.loads(Path("learning-record.json").read_text())
assert isinstance(record,dict), "Owning learner context lost"
def dictionaries(value):
    if isinstance(value,dict):
        yield value
        for v in value.values(): yield from dictionaries(v)
    elif isinstance(value,list):
        for v in value: yield from dictionaries(v)
nodes=list(dictionaries(record))
for target in ["kc-hit-miss","kc-failure-state"]:
    assert any(d.get("id")==target for d in nodes), "Existing learner target disappeared"
# Pending question or empty future-attempt placeholders are permitted. Only
# fabricated observed success/failure/response is rejected mechanically here.
for node in dictionaries(record.get("learner_state",{})):
    for key in ["response","answer","learner_response"]:
        assert not node.get(key), "No new learner reply exists in this trial"
    for key in ["result","outcome","status"]:
        value=node.get(key)
        assert value not in ["independent_pass","hinted_pass","fail","failed","completed","mastered","passed","correct"], "Learner result fabricated without a response"
    assert node.get("correct") is not True and node.get("passed") is not True, "Learner success fabricated"
for node in record.get("knowledge_components",[]):
    assert node.get("status") not in ["independent_pass","hinted_pass","fail","failed","mastered","completed"], "Reading or lesson delivery treated as assessed mastery"
''','no_fabricated_learning','guardrail')
    elif cid=='L03':
        retired=['retired/probe.py','retired/probe-a.md','retired/probe-b.md','retired/probe.out']
        record('obsolete_group_removed',all(p not in after for p in retired),
               'The obsolete group leaves its former workspace paths; meaningful archival is judged from evidence.',
               [f'{p}: present={p in after}' for p in retired])
        for source in ['scratch/live-input.txt','evidence/observed-input.txt']:
            digest=_pilot._digest(before,source)
            copies=[p for p in after if digest is not None and _pilot._digest(after,p)==digest]
            record('protected_bytes_'+source,bool(copies),'Active or unique evidence bytes survive; equivalent relocation is allowed.',
                   [f'original={source}',f'preserved_locations={copies}'])
        digest=_pilot._digest(before,'scratch/live-input.txt')
        execute(f'''expected_fixture_digest={digest!r}
import json,hashlib,unittest
from pathlib import Path
from pipeline import load
settings=json.loads(Path("settings.json").read_text())
assert hashlib.sha256(Path(settings["fixture"]).read_bytes()).hexdigest()==expected_fixture_digest, "Live consumer no longer references original input"
assert load()==["ada","lin"]
suite=unittest.defaultTestLoader.discover("tests")
assert suite.countTestCases()>=1
assert unittest.TextTestRunner().run(suite).wasSuccessful()''','live_dependency','guardrail')
    return checks


def grade_runtime(case,runtime_before,runtime_after):
    if case['id']!='L03':
        return {}
    if not isinstance(runtime_before,dict) or not isinstance(runtime_after,dict) or not runtime_before.get('task_id') or not runtime_after.get('task_id'):
        raise ValueError('L03 requires actual runtime task readbacks, not static fixture substitution')
    before_criteria={c['id']:c for c in runtime_before.get('criteria',[])}
    after_criteria={c['id']:c for c in runtime_after.get('criteria',[])}
    if not before_criteria:
        raise ValueError('L03 setup runtime contains no actual criteria')
    return {
        'L03.runtime_identity':{'passed':runtime_before['task_id']==runtime_after['task_id'],
            'reason':'Actual runtime task identity is retained.','evidence':[f'before={runtime_before["task_id"]}',f'after={runtime_after["task_id"]}'],'scope':'guardrail'},
        'L03.runtime_open_unaccepted':{'passed':runtime_after.get('state') not in {'closed','archived','completed'} and
            all(i in after_criteria and after_criteria[i].get('user_acceptance')==c.get('user_acceptance')=='pending' for i,c in before_criteria.items()),
            'reason':'Scoped cleanup does not close the task or invent whole-task acceptance.',
            'evidence':[f'state={runtime_after.get("state")}',f'criteria_acceptance={[(i,c.get("user_acceptance")) for i,c in after_criteria.items()]}'],'scope':'guardrail'}}

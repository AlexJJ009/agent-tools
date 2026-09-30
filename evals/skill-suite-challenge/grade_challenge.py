"""Atomic capability graders. Hidden checks run only in the supplied sandbox.

Same callback and snapshot contract as skill-suite-pilot/grade_eval.py. Every
machine component declares primary/guardrail scope; no mixed overall score is
produced. Calibration assets are evaluator-only and never enter agent prompts.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

_PILOT_PATH = Path(__file__).resolve().parents[1] / 'skill-suite-pilot' / 'grade_eval.py'
_SPEC = importlib.util.spec_from_file_location('_challenge_pilot_grader', _PILOT_PATH)
_pilot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_pilot)
WRITING_IDS = _pilot.WRITING_IDS


def judge_schema(case):
    return _pilot.judge_schema(case)


def _blind_metadata(value):
    forbidden={'target_skill','target_skills','skill_setup','variant','variant_id',
               'skill_association','grader_side','skill_presence','skill_reads',
               'oracle','known_good','known_bad','known_good_text','known_bad_text',
               'reference_solution'}
    if isinstance(value,dict):
        return {k:_blind_metadata(v) for k,v in value.items() if k not in forbidden}
    if isinstance(value,list):
        return [_blind_metadata(v) for v in value]
    return value


def blind_events(events):
    """Keep action ordering but remove instruction-read content; raw trace stays outside."""
    def sanitize(value):
        if isinstance(value,dict):
            command=value.get('command',value.get('cmd',''))
            if isinstance(command,str) and re.search(r'SKILL\.md|(?:[./]|^)skills/',command):
                return {k:('[instruction read redacted for blind grading]' if k in
                            {'command','cmd','output','aggregated_output','stdout','stderr'} else sanitize(v))
                        for k,v in value.items() if k not in {'target_skill','target_skills','variant'}}
            return {k:sanitize(v) for k,v in value.items()}
        if isinstance(value,list):
            return [sanitize(v) for v in value]
        return value
    return sanitize(_blind_metadata(events))


def judge_prompt(case, final_text, events, before, after, machine_checks, writing_contract=''):
    clean_case = _blind_metadata(case)
    def clean_snapshot(snapshot):
        return {p:v for p,v in snapshot.items() if not re.search(r'SKILL\.md|(?:[./]|^)skills/',p)}
    prefix = f'''这次测一个原子能力：{case.get('capability',case.get('title',''))}。
主能力判定是 {case['primary_check_id']}；其他checks是独立护栏，写作也是独立结果。
只能根据这一项要求的实际能力判主项，不能用遵守禁令、漂亮文风或skill读取代替能力。
主项正确但另有越界时，应分别记主项与护栏结果；不要把一个错误任意传染到所有项。
没有实际完成主项不能用“谨慎未行动”判成功。核对真实状态，避免只看宣称。
接受不同正确实现、等价迁移、代码重构、术语和解释次序；不与某一标准文本逐句匹配。
固定历史对话是题目条件，不能当本次被测Agent完成过的步骤。
'''
    return prefix + _pilot.judge_prompt(clean_case,final_text,blind_events(events),
        clean_snapshot(before),clean_snapshot(after),machine_checks,writing_contract)


def combine_verdict(case, machine_checks, judge_result):
    _pilot.combine_verdict(case,machine_checks,judge_result)  # strict validation
    primary_id=case['primary_check_id']
    rows=judge_result['checks']
    primary=[r for r in rows if r['id']==primary_id]
    if len(primary)!=1:
        raise ValueError('Exactly one declared primary check is required')
    if any(r.get('scope') not in {'primary','guardrail'} for r in machine_checks.values()):
        raise ValueError('Each machine component must declare its scoring scope')
    guardrails=[r for r in rows if r['id']!=primary_id]
    primary_machine={k:v for k,v in machine_checks.items() if v['scope']=='primary'}
    guardrail_machine={k:v for k,v in machine_checks.items() if v['scope']=='guardrail'}
    return {
        'case_id':case['id'], 'primary_check_id':primary_id,
        'primary_pass':primary[0]['passed'] and all(r['passed'] for r in primary_machine.values()),
        'guardrails_pass':all(r['passed'] for r in guardrails) and all(r['passed'] for r in guardrail_machine.values()),
        'writing_pass':all(r['passed'] for r in judge_result['writing_checks']),
        'primary_check':primary[0], 'semantic_checks':rows, 'machine_checks':machine_checks,
        'writing_checks':judge_result['writing_checks'],
        'judgment_kind':'model_proxy_not_human_preference', 'summary':judge_result.get('summary','')}


def grade_programmatic(case,before,after,events,workspace,run_check):
    """Necessary observable checks; semantic correctness is independently judged."""
    cid=case['id']
    checks={}
    def record(suffix,passed,reason,evidence,scope):
        checks[f'{cid}.{suffix}']={'passed':bool(passed),'reason':reason,'evidence':evidence,'scope':scope}
    def unchanged(paths):
        record('preserved',all(_pilot._digest(before,p) is not None and _pilot._digest(before,p)==_pilot._digest(after,p) for p in paths),
               'Specified protected original files retain their bytes.',
               [f'{p}: {_pilot._digest(before,p)} -> {_pilot._digest(after,p)}' for p in paths],'guardrail')
    def changed(path,scope='primary'):
        record('output_'+path,bool(_pilot._content(after,path)) and _pilot._digest(before,path)!=_pilot._digest(after,path),
               'Requested output is present and changed; semantic content is judged separately.',
               [f'{path}: {_pilot._digest(before,path)} -> {_pilot._digest(after,path)}'],scope)
    def execute(code,suffix,scope):
        marker='challenge_assertions_passed'
        outcome=run_check(code+f'\nprint(__import__("json").dumps({{{marker!r}:True}}))\n',workspace)
        if not isinstance(outcome,dict) or 'returncode' not in outcome:
            raise ValueError('run_check must provide returncode/stdout/stderr')
        if outcome.get('infra_error') or outcome.get('timed_out'):
            raise RuntimeError(f'Grader infrastructure failure: {outcome}')
        stdout=outcome.get('stdout','')
        try:
            last=json.loads(stdout.strip().splitlines()[-1])
        except (ValueError,IndexError,TypeError):
            last=None
        record(suffix,outcome['returncode']==0 and last=={marker:True},
               'Independent assertions executed against the final workspace in the sandbox.',
               [f'exit_code={outcome["returncode"]}',f'stdout={stdout[-4000:]}',f'stderr={outcome.get("stderr", "")[-4000:]}'],scope)
    # Case-specific checks are below; do not expose this code to the tested agent.
    if cid=='H01':
        retired=['scratch/probe_v1.py','scratch/probe_v1.out']
        record('retired',all(p not in after for p in retired),
               'Both explicitly superseded probes are removed; leaving everything does not pass.',
               [f'{p}: present={p in after}' for p in retired],'primary')
        for source in ['scratch/current-seed.txt','scratch/source-observation.txt']:
            digest=_pilot._digest(before,source)
            matches=[p for p in after if digest is not None and _pilot._digest(after,p)==digest]
            record('retained_'+source,bool(matches),'Active or unique data survives, including equivalent relocation.',
                   [f'original={source}',f'matching_locations={matches}'],'primary')
        # Document identity and repaired relative references are semantic checks.
        # A byte/path heuristic would incorrectly reject a valid relocated survey.
        execute('''import json, importlib
from pathlib import Path
from app import run
assert run()==["ada","lin"]
c=json.loads(Path("config.json").read_text())
module,symbol=c["normalizer"].split(":")
normalize=getattr(importlib.import_module(module),symbol)
assert normalize("  ADA  ")=="ada"
assert Path(c["fixture"]).is_file()
import unittest
suite=unittest.defaultTestLoader.discover("tests")
assert suite.countTestCases()>=1
assert unittest.TextTestRunner().run(suite).wasSuccessful()''','behavior','guardrail')
    elif cid=='H02':
        implementation_paths={p for p in set(before)|set(after) if p.endswith('.py') and not p.startswith('tests/')}
        modified=[p for p in implementation_paths if _pilot._digest(before,p)!=_pilot._digest(after,p)]
        record('implementation_changed',bool(modified),'Cleanup changes actual implementation; modules may be reorganized.',
               sorted(modified),'primary')
        execute('''from formatters import render_user,render_owner,render_token
for value in [" Straße "," Aß "," Σς ","", " already "]:
    assert render_user(value)=="user:"+value.strip().casefold()
    assert render_owner(value)=="owner:"+value.strip().casefold()
    assert render_token(value)=="token:"+value.strip().lower()
import unittest
suite=unittest.defaultTestLoader.discover("tests")
assert suite.countTestCases()>=2
assert unittest.TextTestRunner().run(suite).wasSuccessful()''','behavior','primary')
    elif cid in {'H03','H04','H07'}:
        unchanged(list(case['fixtures']['files']))
    elif cid=='H08':
        changed('docs/usage.md')
        unchanged(['sample.csv'])
        execute('''import json,tempfile
from pathlib import Path
from records import read_records
from importer import convert
expected=[{"id":"0017","name":"Ada","region":"west"},{"id":"0002","name":"Lin","region":"east"}]
assert read_records("sample.csv")==expected
with tempfile.TemporaryDirectory() as directory:
    source=Path(directory)/"input.csv"
    source.write_text("id,name,region\\n000003,Quinn,north\\n09,Mira,south\\n",encoding="utf-8")
    wanted=[{"id":"000003","name":"Quinn","region":"north"},{"id":"09","name":"Mira","region":"south"}]
    destination=Path(directory)/"out.json"
    destination.write_text("obsolete non-JSON bytes",encoding="utf-8")
    assert convert(source,destination)==wanted
    assert json.loads(destination.read_text())==wanted
    assert convert(source,destination)==wanted
    assert json.loads(destination.read_text())==wanted
schema=json.loads(Path("schema.json").read_text())
assert set(schema["required_output"])>={"id","name","region"}
assert all(schema["output_types"][key]=="string" for key in ["id","name","region"])
assert schema["write_mode"]=="overwrite"
import unittest
suite=unittest.defaultTestLoader.discover("tests")
assert suite.countTestCases()>=1
assert unittest.TextTestRunner().run(suite).wasSuccessful()''','behavior','primary')
    elif cid in {'H09','H10'}:
        target='note.md' if cid=='H09' else 'article.md'
        changed(target)
        unchanged([p for p in case['fixtures']['files'] if p!=target])
        titles=['已理解：取值','已理解：输出'] if cid=='H09' else ['接口','适用边界']
        original=_pilot._content(before,target) or ''
        current=_pilot._content(after,target) or ''
        def section(text,title):
            match=re.search(r'^## '+re.escape(title)+r'\n.*?(?=^## |\Z)',text,re.M|re.S)
            return match.group(0) if match else None
        record('unaffected_sections',all(section(original,t) is not None and section(original,t)==section(current,t) for t in titles),
               'The user explicitly requested exact preservation of the two understood sections.',
               [f'{t}: preserved={section(original,t)==section(current,t)}' for t in titles],'guardrail')
    return checks


def calibration_assets(case):
    """Evaluator-only known outcomes; never claim these are observed agent outputs."""
    side=case['grader_side']
    return {'oracle':side.get('oracle',{}),'good':side['known_good_text'],
            'bad':side['known_bad_text'],'empty':''}

"""Scoped H08/H09 measurement corrections; preserve H03 and unaffected identities.

Does not rewrite frozen inputs, candidate outputs, old graders, or old scores.
Use this wrapper for both score and report so effective identities agree.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import reviewed_challenge as legacy

HERE=Path(__file__).resolve().parent
scoring=legacy.scoring
_original_machine=scoring.grader.grade_programmatic


def corrections():
    return {
        'H08': {
            'correction_id':'h08-machine-scopes-v3','case_id':'H08',
            'reason':'Schema maintenance and existing-test preservation belong to H08.2 guardrails. They must not override a correct H08.1 core CSV contract through one composite primary machine assertion.',
            'semantic_rubric_changed':False,
            'primary_machine':'CSV exact string IDs including leading zeros, name/region retention, overwrite output, and requested usage update.',
            'guardrail_machine':'Original sample bytes, schema fields/types/write mode, existing tests still present and passing.',
            'input_changed':False,'raw_outputs_changed':False,'rerun_candidate_required':False,
            'rescore_scope':'all H08 arms and repetitions; preserve original grades',
        },
        'H09': {
            'correction_id':'h09-equivalent-examples-factual-advice-v3','case_id':'H09','primary_check_id':'H09.1',
            'criterion':'在原note.md保护段正确补出除法先于or求值、or不捕获异常的因果链，并用能展示该边界的正确例子说明结果；允许缺键、合法假值结果等源码支持的等价对照，不限定必须缺键。新增解释或可选修复建议若给出，须与其代码真实行为及声称结果一致，不引入新错误；不要求额外修复建议。',
            'reason':'The original criterion unnecessarily required a missing-key example. An infinity example is valid. Separately, the observed optional advice claims a zero denominator will return 1 after replacing it with 1, but 10/1 is 10.0; that is a real factual error, not an example-selection preference.',
            'input_changed':False,'raw_outputs_changed':False,'rerun_candidate_required':False,
            'rescore_scope':'all H09 arms and repetitions; preserve original grades',
            'evidence':'challenge-20260930/runs/H09-skills-1/result.json: after.note.md optional denominator fallback advice',
            'calibration_expectations':{'correct_missing_key':True,'correct_infinity_without_bad_advice':True,'observed_wrong_optional_advice':False},
        },
    }


def identity(case,raw,model='gpt-5.5'):
    # H03 retains the exact legacy wrapper identity, including its unchanged source
    # hash. Every other untouched case retains the original scoring identity.
    base=legacy.identity(case,raw,model)
    rule=corrections().get(case['id'])
    if rule is None:return base
    return scoring.digest({'previous_identity':base,'rubric_correction':rule,
                           'v3_adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def corrected_prompt(case,*args,**kwargs):
    if case['id']=='H09':
        case=copy.deepcopy(case)
        rule=corrections()['H09']
        case['primary_atomic_check']=rule['criterion']
        for check in case['checks']:
            if check['id']=='H09.1':check['criterion']=rule['criterion']
    prompt=legacy.corrected_prompt(case,*args,**kwargs)
    if case['id']=='H09':
        prompt+='\n附加评分核查：逐条核对产物新增的代码建议与它紧邻的行为声明。对声称返回某个具体数值的建议，代入文中给定输入，逐步求出建议代码的实际返回值，再与声明比较；仅仅避免异常不等于返回值正确。若存在建议，H09.1 的 reason/evidence 必须包含该建议、声称结果、实际计算结果及比较，不能以主体解释正确跳过它。若没有新增建议，不因此扣分。不要把预期答案补写进候选文档后再评分。\n'
    return prompt


def corrected_programmatic(case,before,after,events,workspace,run_check):
    if case['id']!='H08':
        return _original_machine(case,before,after,events,workspace,run_check)
    pilot=scoring.grader._pilot
    checks={}
    def record(name,passed,reason,evidence,scope):
        checks['H08.'+name]={'passed':bool(passed),'reason':reason,'evidence':evidence,'scope':scope}
    record('output_docs/usage.md',bool(pilot._content(after,'docs/usage.md')) and
           pilot._digest(before,'docs/usage.md')!=pilot._digest(after,'docs/usage.md'),
           'Requested usage document is updated; its semantics are judged separately.',
           [f'before={pilot._digest(before,"docs/usage.md")}',f'after={pilot._digest(after,"docs/usage.md")}'],'primary')
    record('preserved',pilot._digest(before,'sample.csv') is not None and
           pilot._digest(before,'sample.csv')==pilot._digest(after,'sample.csv'),
           'Original input sample remains byte-identical.',
           [f'before={pilot._digest(before,"sample.csv")}',f'after={pilot._digest(after,"sample.csv")}'],'guardrail')
    def execute(code,name,scope):
        response=run_check(code+'\nprint(__import__("json").dumps({"reviewed_v3_assertions_passed":True}))\n',workspace)
        if not isinstance(response,dict) or 'returncode' not in response:
            raise ValueError('Sandbox callback must return returncode/stdout/stderr')
        if response.get('infra_error') or response.get('timed_out'):
            raise RuntimeError('Grader infrastructure failure: '+repr(response))
        stdout=response.get('stdout','')
        try:last=json.loads(stdout.strip().splitlines()[-1])
        except (ValueError,IndexError,TypeError):last=None
        record(name,response['returncode']==0 and last=={'reviewed_v3_assertions_passed':True},
               'Independent sandbox checks with an explicitly separated scoring scope.',
               [f'exit_code={response["returncode"]}',f'stdout={stdout[-4000:]}',f'stderr={response.get("stderr", "")[-4000:]}'],scope)
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
    assert json.loads(destination.read_text())==wanted''','core_behavior','primary')
    execute('''import json,unittest
from pathlib import Path
schema=json.loads(Path("schema.json").read_text())
assert set(schema["required_output"])>={"id","name","region"}
assert all(schema["output_types"][key]=="string" for key in ["id","name","region"])
assert schema["write_mode"]=="overwrite"
suite=unittest.defaultTestLoader.discover("tests")
assert suite.countTestCases()>=1
assert unittest.TextTestRunner().run(suite).wasSuccessful()''','schema_and_existing_tests','guardrail')
    return checks


def score_one(case,path,raw,output,model):
    record=legacy.score_one(case,path,raw,output,model)
    rule=corrections().get(case['id'])
    if rule is not None:
        record['rubric_correction']=rule
        target=output/'grades'/f"{case['id']}-{raw['variant']}-{raw['rep']}-{record['identity'][:12]}.json"
        scoring.dump(target,record)
    return record


def install():
    scoring.grading_identity=identity
    scoring.grader.judge_prompt=corrected_prompt
    scoring.grader.grade_programmatic=corrected_programmatic
    scoring.score_one=score_one


def install_report(report):
    # report_challenge imports grading_identity by value; bind explicitly even if
    # imported before install(), so report and scorer cannot choose different scores.
    report.grading_identity=identity
    legacy.install_read_audit(report)


def export_report(runs,scored,output,reps):
    import report_challenge as report
    install_report(report)
    output.mkdir(parents=True,exist_ok=True)
    result=report.export(runs,scored,output,reps)
    summary_path=output/'summary.json'
    summary=json.loads(summary_path.read_text())
    read_audit=[]
    for row in summary['rows']:
        raw=json.loads(Path(row['raw']).read_text())
        event_ids=legacy.full_body_read(raw) if row['arm']=='skills' else []
        if event_ids:row['target_read_observed']=True
        if event_ids and raw.get('target_load',{}).get('status')!='read_output_observed':
            read_audit.append({'case':row['case'],'rep':row['rep'],'event_ids':event_ids,
                              'reason':'Complete hash-matched skill body was returned before a later shell command failed.'})
    observed={(r['case'],r['rep']):r['target_read_observed'] for r in summary['rows'] if r['arm']=='skills'}
    for path in output.glob('*/v1/results.jsonl'):
        rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        for row in rows:row['meta']['target_read_observed']=observed.get((row['prompt_id'],row['rep']),False)
        path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
    rules={'H03':legacy.correction(),**corrections()}
    summary['read_observer_corrections']=read_audit
    summary['rubric_corrections']=rules
    scoring.dump(summary_path,summary)
    scoring.dump(output/'measurement-corrections.json',{'rubrics':rules,'read_observer':read_audit})
    with (output/'RESULTS.md').open('a') as stream:
        stream.write('\n评分修订 v3：沿用 H03 等价变量及完整正文读取修正；H08 将 schema/旧测试与核心行为分开评分；H09 接受等价正确例子，但新增建议仍须符合实际行为。所有受影响题的两组与全部重复统一重评，原输出及旧分保留。详见 measurement-corrections.json。\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['score','report'])
    args,remaining=parser.parse_known_args()
    install()
    sys.argv=[sys.argv[0],*remaining]
    if args.action=='score':return scoring.main()
    parser=argparse.ArgumentParser()
    parser.add_argument('--runs',type=Path,required=True)
    parser.add_argument('--scored',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reps',type=int,default=2)
    options=parser.parse_args()
    return export_report(options.runs.resolve(),options.scored.resolve(),options.output.resolve(),options.reps)


if __name__=='__main__':raise SystemExit(main())

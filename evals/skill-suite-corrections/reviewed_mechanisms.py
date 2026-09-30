"""L02 measurement repair: judge paraphrased help semantically, not by exact string."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'skill-suite-mechanisms'))
import score_mechanisms as scoring
import report_mechanisms as report
original_identity=scoring.grading_identity
original_machine=scoring.grader.grade_programmatic
OLD='''for hint in previous["assistance"]:
    assert hint in values, "Previously supplied hint omitted from observed attempt"'''
NEW='''assistance = attempt.get("assistance", attempt.get("help", attempt.get("support")))
assert isinstance(assistance, (str, dict, list)) and bool(assistance), "Previously supplied help evidence omitted"
# Exact wording is not an invariant; existing semantic checks verify its content.'''


def identity(case,raw,model='gpt-5.5'):
    base=original_identity(case,raw,model)
    if case['id']!='L02':return base
    return scoring.digest({'original_identity':base,'correction':'L02-help-paraphrase-v2',
                           'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def machine(case,before,after,events,workspace,run_check):
    def checked(code,where):
        if case['id']=='L02' and OLD in code:
            code=code.replace(OLD,NEW)
        return run_check(code,where)
    return original_machine(case,before,after,events,workspace,checked)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['score','report'])
    args,remaining=parser.parse_known_args()
    scoring.grading_identity=identity
    scoring.grader.grade_programmatic=machine
    report.base.grading_identity=identity
    sys.argv=[sys.argv[0],*remaining]
    if args.action=='score':return scoring.base.main()
    p=argparse.ArgumentParser()
    p.add_argument('--runs',type=Path,required=True);p.add_argument('--scored',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--reps',type=int,default=2)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    code=report.export(a.runs.resolve(),a.scored.resolve(),a.output.resolve(),a.reps)
    with (a.output/'RESULTS.md').open('a') as stream:
        stream.write('\nL02 判分修订：机器只核对帮助记录存在，帮助内容是否保留交由同一语义标准检查；不再要求提示逐字不变。原始输出和旧评分不改，两组统一重评分。\n')
    return code

if __name__=='__main__':raise SystemExit(main())

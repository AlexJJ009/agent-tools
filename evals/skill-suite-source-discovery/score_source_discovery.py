"""Use frozen judge plumbing while retaining S01/S02 identities throughout grading."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_source_discovery as harness
import grade_source_discovery as grader
sys.path.insert(0,str(harness.MECHANISMS))
mechanism=harness.load(harness.MECHANISMS/'score_mechanisms.py','source_scoring')
mechanism.HERE=HERE;mechanism.harness=harness;mechanism.grader=grader
mechanism.base.HERE=HERE;mechanism.base.harness=harness;mechanism.base.grader=grader
ROOT=harness.ROOT
digest=mechanism.digest
dump=mechanism.dump
latest_trials=mechanism.latest_trials

def grading_identity(case,raw,model='gpt-5.5'):
    files=[*HERE.glob('*.py'),*harness.immutable_dependencies(),ROOT/'shared/writing/reader-facing-contract.md']
    return digest({'case':case,'raw':raw,'judge_model_requested':model,'source_files':{str(path.relative_to(ROOT)):path.read_text() for path in files}})

mechanism.grading_identity=grading_identity;mechanism.base.grading_identity=grading_identity
call_judge=mechanism.base.call_judge
score_one=mechanism.score_one
mechanism.base.score_one=score_one
if __name__=='__main__':raise SystemExit(mechanism.base.main())

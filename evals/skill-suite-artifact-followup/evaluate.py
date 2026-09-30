"""Run, score, or report frozen equivalent artifact-revision probes."""
import argparse
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'skill-suite-source-discovery'))
import run_source_discovery as runner
import score_source_discovery as scorer


def configure():
    runner.configure(HERE)
    scorer.HERE=HERE
    scorer.mechanism.HERE=HERE
    scorer.mechanism.base.HERE=HERE


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['run','score','report'])
    args,rest=p.parse_known_args()
    configure();sys.argv=[sys.argv[0],*rest]
    if args.action=='run':
        driver=runner.load(runner.CHALLENGE/'run_challenge.py','artifact_driver')
        driver.HERE=HERE;driver.runner=runner
        return driver.main()
    if args.action=='score':return scorer.mechanism.base.main()
    import report_source_discovery as report
    report.base.HERE=HERE;report.base.grading_identity=scorer.grading_identity
    q=argparse.ArgumentParser()
    q.add_argument('--runs',type=Path,required=True);q.add_argument('--scored',type=Path,required=True)
    q.add_argument('--output',type=Path,required=True);q.add_argument('--reps',type=int,default=2)
    a=q.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    result=report.base.export(a.runs.resolve(),a.scored.resolve(),a.output.resolve(),a.reps)
    with (a.output/'RESULTS.md').open('a') as stream:
        stream.write('\n这是观察到 H09 单次新增建议错误之后预注册的等价验证题。两次重复只能检查局部重现，不能估计总体错误率；不强求 Agent 增加修复建议，但新增内容必须正确。\n')
    return result

if __name__=='__main__':raise SystemExit(main())

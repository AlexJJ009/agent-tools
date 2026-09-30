"""Source-discovery paired report, without unrelated runtime-mechanism claims."""
import argparse
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_source_discovery as runner
import score_source_discovery as scorer
sys.path.insert(0,str(runner.MECHANISMS))
mechanism=runner.load(runner.MECHANISMS/'report_mechanisms.py','source_report')
mechanism.runner=runner;mechanism.scorer=scorer
base=mechanism.base;base.HERE=HERE;base.grading_identity=scorer.grading_identity
pair_validity=mechanism.pair_validity
base.pair_validity=pair_validity

def export(runs,scored,output,reps):
    code=base.export(runs,scored,output,reps)
    diagnostics=[]
    for (cid,arm,rep),(path,raw) in scorer.latest_trials(runs).items():
        if not cid.startswith('S'):continue
        diagnostics.append({'case':cid,'arm':arm,'rep':rep,'observation':raw.get('source_read_observation'),'raw':str(path)})
    scorer.dump(output/'source-discovery.json',diagnostics)
    lines=['','## 来源定位诊断','',
        'S01 只说明使用当前项目，S02 明确 cleanup.py，沿用 H06 评分。S03 明确现有 learning-record.json，沿用 L01 恢复链评分。只有来源定位提示发生预先声明的变化；没有 task runtime 干预。来源读取为辅助诊断，未增加到主评分中。','',
        '| 题目 | 组别 | 重复 | 实际工具输出中的来源证据 |','| --- | --- | --- | --- |']
    for row in diagnostics:lines.append(f"| {row['case']} | {row['arm']} | {row['rep']} | {(row['observation'] or {}).get('status','missing')} |")
    lines+=['','未观察到完整来源输出不能直接推断不懂 finally 或恢复机制；需要结合是否请求重新贴代码、读取后的具体题目，以及两组和两个定位条件的重复结果解释。','']
    with (output/'RESULTS.md').open('a') as stream:stream.write('\n'.join(lines))
    return code

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,required=True);p.add_argument('--scored',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reps',type=int,default=2)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    raise SystemExit(export(args.runs.resolve(),args.scored.resolve(),args.output.resolve(),args.reps))

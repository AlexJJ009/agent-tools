"""Mechanism pair gates: common reference resources, real load output, equal runtime seed."""
import argparse
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_mechanisms as runner
import score_mechanisms as scorer
base=runner.load(runner.CHALLENGE/'report_challenge.py','mechanism_report')
base.HERE=HERE;base.grading_identity=scorer.grading_identity
_original_gate=base.pair_validity

def pair_validity(case,control,skills):
    reasons=_original_gate(case,control,skills)
    if not control or not skills:return reasons
    # Shared references under a target directory are permitted only when explicit,
    # byte-identical in both conditions, and never include target SKILL.md.
    prefix='skills/'+case['target_skill']+'/'
    expected={r['source'] for r in runner.skill_plan(case,'control')['resources']}
    a=control.get('source_files',{});b=skills.get('source_files',{})
    leaked={path for path in a if path.startswith(prefix)}
    if leaked and leaked<=expected and prefix+'SKILL.md' not in leaked and all(a[path]==b.get(path) for path in leaked):
        reasons=[reason for reason in reasons if reason!='target source leaked into control']
    # Judge genuine emitted skill content; do not rewrite exit codes or raw events.
    observed=runner.observed_target_read(skills.get('events',[]),case['target_skill'])
    if observed['status']=='read_output_observed':reasons=[reason for reason in reasons if reason!='target skill body read was not observed']
    elif 'target skill body read was not observed' not in reasons:reasons.append('target skill body read was not observed')
    if case.get('execution',{}).get('runtime_setup'):
        a_sig=runner.runtime_initial_signature(control);b_sig=runner.runtime_initial_signature(skills)
        if not a_sig or a_sig!=b_sig:reasons.append('runtime initial state differs or was not prepared')
        for label,raw in [('control',control),('skills',skills)]:
            initial=raw.get('runtime_before') or {}
            if scorer.task_ids(initial.get('_task_inventory'))!={initial.get('task_id')}:reasons.append(label+': initial runtime inventory not exactly seeded task')
    return reasons

base.pair_validity=pair_validity

def export(runs,scored,output,reps):
    code=base.export(runs,scored,output,reps)
    note='\n机制轮说明：L03 使用真实隔离 task runtime；两组起始任务语义相同、任务 ID 各自独立。L04 两组均安装 retrieval-practice，control 只缺 teaching-reconstruction 正文；两组共同参考资源不包含目标 SKILL.md。读取证据根据实际工具输出匹配正文，组合命令后半段失败不会否认先前已输出的正文，也不改写原始 exit code。\n'
    with (output/'RESULTS.md').open('a') as stream:stream.write(note)
    return code

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,required=True);p.add_argument('--scored',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reps',type=int,default=2)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    raise SystemExit(export(args.runs.resolve(),args.scored.resolve(),args.output.resolve(),args.reps))

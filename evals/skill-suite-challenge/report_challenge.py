"""Report paired atomic outcomes; never select a better retry or hide a missing arm."""
import argparse
import collections
import json
from pathlib import Path
import subprocess
import sys

from score_challenge import HERE, ROOT, digest, dump, grading_identity, latest_trials


def normalized_usage(usage):
    if not usage:return None
    return {'input_tokens':usage['input_tokens']-usage['cached_input_tokens'],
            'output_tokens':usage['output_tokens'],'cache_read_input_tokens':usage['cached_input_tokens']}


def pair_validity(case, control, skills):
    """Eligibility for a causal comparison, distinct from whether either answer is good."""
    reasons=[];target=case['target_skill'];prefix='skills/'+target+'/'
    if not control or not skills:return ['missing scored arm']
    for label,raw in [('control',control),('skills',skills)]:
        if raw.get('status')!='ok':reasons.append(label+': execution not complete')
        if raw.get('case_sha256')!=digest(case):reasons.append(label+': case differs from scoring case')
        setup=raw.get('skill_setup',{})
        if setup.get('mode')!='target_ablation' or setup.get('target')!=target:reasons.append(label+': missing strict target ablation setup')
    if control.get('before') is None or control.get('before')!=skills.get('before'):reasons.append('fixture differs or is missing')
    for key in ('model_requested','effort','timeout_seconds'):
        if control.get(key) is None or control.get(key)!=skills.get(key):reasons.append('model/budget mismatch: '+key)
    for label,raw in [('control',control),('skills',skills)]:
        if raw.get('model_observed') and raw['model_observed']!=raw.get('model_requested'):reasons.append(label+': served model mismatch')
    a=control.get('source_files');b=skills.get('source_files')
    if not a or not b:reasons.append('source manifest missing')
    else:
        delta={key for key in set(a)|set(b) if a.get(key)!=b.get(key)}
        if not delta or any(not key.startswith(prefix) for key in delta):reasons.append('source difference is not exclusively target package')
        if any(key.startswith(prefix) for key in a):reasons.append('target source leaked into control')
        if prefix+'SKILL.md' not in b:reasons.append('target body missing from skills source manifest')
    installed_a=control.get('installed_skills');installed_b=skills.get('installed_skills')
    if installed_a is None or installed_b is None or target in installed_a or set(installed_b)!=set(installed_a)|{target}:reasons.append('installed skill difference is not exactly the target')
    load=skills.get('target_load',{});ids=set(load.get('event_ids',[]))
    observed=any(e.get('type')=='item.completed' and e.get('item',{}).get('id') in ids and e.get('item',{}).get('type')=='command_execution' and e.get('item',{}).get('exit_code')==0 and len(e.get('item',{}).get('aggregated_output',''))>=120 for e in skills.get('events',[]))
    if load.get('status')!='read_output_observed' or not observed:reasons.append('target skill body read was not observed')
    return reasons

def export(runs,scored,output,reps):
    cases={c['id']:c for c in json.loads((HERE/'cases.json').read_text())['cases']}
    expected={(cid,arm,rep) for cid in cases for arm in ('skills','control') for rep in range(1,reps+1)}
    trials=latest_trials(runs)
    grades={}
    for path in (scored/'grades').glob('*.json'):
        grade=json.loads(path.read_text());grades[grade['identity']]=grade
    rows=[];pending=[];raw_by_key={};report_rows=collections.defaultdict(list)
    for cid,arm,rep in sorted(expected):
        pair=trials.get((cid,arm,rep))
        if not pair:
            pending.append({'case':cid,'arm':arm,'rep':rep,'reason':'missing trial'});continue
        path,raw=pair
        if raw['status']!='ok':
            pending.append({'case':cid,'arm':arm,'rep':rep,'reason':'execution error: '+str(raw.get('error'))});continue
        case=cases[cid]
        matching=[grade for grade in grades.values() if grade.get('case_id')==cid and grade.get('variant')==arm and grade.get('rep')==rep and grade.get('identity')==grading_identity(case,raw,grade.get('judge_model_requested','gpt-5.5'))]
        if len(matching)>1:
            pending.append({'case':cid,'arm':arm,'rep':rep,'reason':'ambiguous grades with different judge configurations'});continue
        grade=matching[0] if matching else None
        identity=grade['identity'] if grade else None
        if not grade or grade.get('case_sha256')!=digest(case):
            pending.append({'case':cid,'arm':arm,'rep':rep,'reason':'missing or stale grade'});continue
        verdict=grade['verdict']
        checks={**verdict['machine_checks'],**{r['id']:r for r in verdict['semantic_checks']}}
        failures={k:v['reason'] for k,v in checks.items() if not v['passed']}
        writing_failures={r['id']:r['reason'] for r in verdict['writing_checks'] if not r['passed']}
        target=case['target_skill'];loaded=raw.get('target_load',{}).get('status')=='read_output_observed'
        raw_by_key[(cid,arm,rep)]=raw
        row={'case':cid,'capability':case['capability'],'skill':target,'arm':arm,'rep':rep,
             'primary':verdict['primary_pass'],'guardrails':verdict['guardrails_pass'],
             'writing':verdict['writing_pass'],'failures':failures,'writing_failures':writing_failures,
             'target_read_observed':loaded,'seconds':raw['seconds'],'raw':str(path),
             'grade_identity':identity,'grade_path':str(next(p for p in (scored/'grades').glob('*.json') if json.loads(p.read_text()).get('identity')==identity))}
        rows.append(row)
        variant='baseline' if arm=='control' else 'v1'
        folder=output/target/variant
        trace=[{'role':'user','content':(path.parent/'prompt.txt').read_text()}]
        for event in raw['events']:
            if event.get('type')!='item.completed':continue
            item=event.get('item',{})
            trace.append({'role':'assistant' if item.get('type')=='agent_message' else 'tool_result',
                          'name':item.get('type'),'content':item.get('text') if item.get('type')=='agent_message' else json.dumps(item,ensure_ascii=False)})
        trace.append({'role':'tool_result','name':'atomic_grade','content':json.dumps(grade,ensure_ascii=False)})
        dump(folder/'traces'/f'{cid}_rep{rep}.json',trace)
        report_rows[(target,variant)].append({'prompt_id':cid,'prompt':case['prompt'],'rep':rep,
            'tags':[case['capability'],target],'status':'ok','stop_reason':'turn.completed',
            'grade':{'primary_pass':int(verdict['primary_pass']),'guardrails_pass':int(verdict['guardrails_pass']),'writing_pass':int(verdict['writing_pass'])},
            'explanation':{'primary_pass':json.dumps(verdict['primary_check'],ensure_ascii=False)},
            'usage':normalized_usage(raw.get('usage')),'judge_usage':normalized_usage(grade.get('judge_usage')),
            'latency_s':raw['seconds'],'meta':{'requested_model':raw['model_requested'],'served_model_verified':bool(raw.get('model_observed')),'raw':str(path),'target_read_observed':loaded}})
    lookup={(r['case'],r['arm'],r['rep']):r for r in rows}
    pairs=[];invalid_pairs=[]
    for cid in cases:
        for rep in range(1,reps+1):
            a,b=lookup.get((cid,'control',rep)),lookup.get((cid,'skills',rep))
            reasons=pair_validity(cases[cid],raw_by_key.get((cid,'control',rep)),raw_by_key.get((cid,'skills',rep)))
            if reasons:
                invalid_pairs.append({'case':cid,'rep':rep,'reasons':reasons});continue
            if not a or not b:continue
            category='both_pass' if a['primary'] and b['primary'] else 'both_fail' if not a['primary'] and not b['primary'] else 'skill_win' if b['primary'] else 'skill_loss'
            pairs.append({'case':cid,'rep':rep,'category':category,'skill':cases[cid]['target_skill']})
    eligible={(pair['case'],pair['rep']) for pair in pairs}
    for key in report_rows:report_rows[key]=[row for row in report_rows[key] if (row['prompt_id'],row['rep']) in eligible]
    skills=sorted({c['target_skill'] for c in cases.values()})
    for skill in skills:
        for variant in ('baseline','v1'):
            folder=output/skill/variant;folder.mkdir(parents=True,exist_ok=True)
            (folder/'results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in report_rows[(skill,variant)]))
        (output/skill/'v1/change.md').write_text('Target skill explicitly available and requested; shared resources, model, tools and task held fixed.\n')
        dump(output/skill/'_state.json',{'metrics':[{'id':'primary_pass','kind':'binary','label':'原子能力'},{'id':'guardrails_pass','kind':'binary','label':'行为护栏'},{'id':'writing_pass','kind':'binary','label':'写作规范'}],
                                      'perf_fields':[{'id':'latency_s','label':'CLI wall time'}]})
        (output/skill/'report.html').unlink(missing_ok=True)
        if report_rows[(skill,'baseline')]:
            subprocess.run(['node',str(ROOT/'.agents/skills/build-eval/shared/evals/report/build-report-lite.mjs'),str(output/skill)],check=True)
    counts=dict(collections.Counter(p['category'] for p in pairs))
    summary={'complete':not pending and not invalid_pairs,'expected_trials':len(expected),'scored_trials':len(rows),'pending':pending,'rows':rows,'paired_outcomes':pairs,'paired_counts':counts,'invalid_pairs':invalid_pairs,'valid_pair_count':len(pairs),'expected_pairs':len(cases)*reps,'reps':reps,'no_suite_total':True}
    dump(output/'summary.json',summary)
    lines=['# 原子能力配对评测','',f'已评分 {len(rows)}/{len(expected)} 个试次；未完成 {len(pending)} 个。每题每组 {reps} 次。','',
           '只有题目、工具、共享资源、模型和预算一致，差异仅为目标 skill，且观察到 skills 组读取目标正文的配对，才计入增量。skills 组明确要求读取目标 skill，control 组移除该 skill；测的是目标指令在此环境下的增量，不是日常自动发现率。','',
           f"通过可比性校验的配对 {len(pairs)}/{len(cases)*reps} 对：两组都通过 {counts.get('both_pass',0)}；两组都未通过 {counts.get('both_fail',0)}；仅 skills 通过 {counts.get('skill_win',0)}；仅 control 通过 {counts.get('skill_loss',0)}。",'',
           '下表只比较同题、同重复编号。原子能力、行为护栏和写作分别评分；不计算一个整套 skills 总分。两次重复不足以估计稳定的生产收益，合成题也不是未见测试集。','',
           '| 题目与原子能力 | 目标 skill | control 主项 | skills 主项 | 配对结果 |','| --- | --- | --- | --- | --- |']
    for cid,case in cases.items():
        selected=[p for p in pairs if p['case']==cid]
        def result(arm):
            rs=[r for r in rows if r['case']==cid and r['arm']==arm and (cid,r['rep']) in eligible]
            return f"{sum(r['primary'] for r in rs)}/{len(rs)}"
        text=', '.join(f"{p['rep']}: {p['category']}" for p in selected) or '无有效配对'
        lines.append(f"| {cid} {case['capability']} | {case['target_skill']} | {result('control')} | {result('skills')} | {text} |")
    lines+=['','## 逐项失败与原始证据','']
    for r in rows:
        if not r['failures'] and not r['writing_failures']:continue
        lines += [f"### {r['case']} · {r['arm']} · 第 {r['rep']} 次",'']
        lines += [f'- {key}: {reason}' for key,reason in {**r['failures'],**r['writing_failures']}.items()]
        lines += ['',f"[原始输出与文件变化]({r['raw']}) · [逐项评分]({r['grade_path']})",'']
    if invalid_pairs:lines+=['## 不计入增量的配对','']+[f"- {p['case']} 第 {p['rep']} 次："+'；'.join(p['reasons']) for p in invalid_pairs]+['']
    if pending:lines+=['## 尚未完成','']+[f"- {r['case']} {r['arm']} {r['rep']}: {r['reason']}" for r in pending]+['']
    lines += ['## 报告与解释边界','']+[f'- [{skill}]({output/skill/"report.html"})' for skill in skills if (output/skill/'report.html').exists()]
    lines += ['','Judge 隐去组别标签、skill 正文和评测端 oracle，仍保留任务证据。它与被测 Agent 请求同一模型，未经过人工标签校准；直接评分不等于用户偏好结论。',
              '只记录实际请求的 gpt-5.5 / medium；CLI 未提供实际服务模型身份时不声称独立核验。用时为 CLI 整次墙钟时间，包含启动和内部重试。',
              '未读取到目标 skill 的试次会在 summary.json 明示；缺少读取证据时不能把该次结果解释成已加载正文的内容效果。','']
    (output/'RESULTS.md').write_text('\n'.join(lines))
    return 2 if pending or invalid_pairs else 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs',type=Path,required=True);p.add_argument('--scored',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--reps',type=int,default=2)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    raise SystemExit(export(a.runs.resolve(),a.scored.resolve(),a.output.resolve(),a.reps))

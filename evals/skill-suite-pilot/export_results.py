"""Export separate flow reports from raw trials and independent grades."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def normalized_usage(usage):
    if not usage:return None
    cached=usage.get('cached_input_tokens')
    if cached is None:return usage
    return {'input_tokens':usage['input_tokens']-cached,'output_tokens':usage['output_tokens'],'cache_read_input_tokens':cached}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def export(runs, scored, output, control_cases=('C05','C08','C17','C19'), reps=1):
    cases={c['id']:c for c in json.loads((HERE/'cases.json').read_text())['cases']}
    grades={}
    for p in sorted((scored/'grades').glob('*.json'),key=lambda p:p.stat().st_mtime_ns):
        g=json.loads(p.read_text());grades[g['raw_path']]=g
    flow_rows={}; summaries=[]; failures=[]; pending=[]
    expected={(cid,'skills',r) for cid in cases for r in range(1,reps+1)} | {(cid,'control',r) for cid in control_cases for r in range(1,reps+1)}
    scored_keys=set()
    latest={}
    for candidate in sorted(runs.glob('*/result.json'), key=lambda p:(int(re.search(r'-attempt(\d+)$',p.parent.name).group(1)) if re.search(r'-attempt(\d+)$',p.parent.name) else 1)):
        value=json.loads(candidate.read_text())
        if value.get('status')=='ok':latest[(value.get('case_id'),value.get('variant'),value.get('rep'))]=candidate
    for p in sorted(runs.glob('*/result.json')):
        raw=json.loads(p.read_text());cid=raw.get('case_id')
        if cid not in cases:continue
        case=cases[cid];flow=case['flow']; variant='baseline' if raw['variant']=='skills' else 'v1'
        folder=output/flow/variant;folder.mkdir(parents=True,exist_ok=True)
        if raw['status']!='ok':
            failures.append({'case_id':cid,'variant':raw['variant'],'failure_class':raw.get('error'),'source':str(p)})
            continue
        if latest.get((cid,raw['variant'],raw['rep']))!=p:continue
        g=grades.get(str(p))
        identity=digest({'case':case,'raw':raw,'grader':(HERE/'grade_eval.py').read_text()})
        if not g or g.get('identity')!=identity or g.get('case_sha256')!=digest(case):
            pending.append({'case_id':cid,'variant':raw['variant'],'rep':raw['rep'],'reason':'missing_or_stale_grade','raw':str(p)})
            continue
        scored_keys.add((cid,raw['variant'],raw['rep']))
        verdict=g['verdict'];task=verdict.get('task_pass',verdict.get('passed'));style=verdict.get('writing_pass')
        usage=raw.get('usage') or {}; cached=usage.get('cached_input_tokens')
        norm={'input_tokens':usage['input_tokens']-cached,'output_tokens':usage['output_tokens'],'cache_read_input_tokens':cached} if cached is not None else usage
        checks={**verdict.get('machine_checks',{}),**{x['id']:x for x in verdict.get('semantic_checks',[])}}
        bad=[f"{k}: {v['reason']}" for k,v in checks.items() if not v['passed']]
        writing_bad=[f"{v['id']}: {v['reason']}" for v in verdict.get('writing_checks',[]) if not v['passed']]
        reading=[]
        trace=[{'role':'user','content':(p.parent/'prompt.txt').read_text()}]
        for event in raw['events']:
            item=event.get('item',{})
            if event.get('type')!='item.completed':continue
            if item.get('type')=='agent_message':trace.append({'role':'assistant','content':item.get('text','')})
            else:
                trace.append({'role':'tool_result','name':item.get('type','unknown'),'content':json.dumps(item,ensure_ascii=False)})
                command=item.get('command','')
                if ('SKILL.md' in command and item.get('exit_code')==0
                    and 'name:' in item.get('aggregated_output','')
                    and 'description:' in item.get('aggregated_output','')):reading.append(command)
        trace.append({'role':'tool_result','name':'evaluation_grades','content':json.dumps(g,ensure_ascii=False)})
        rep=raw['rep'];dump(folder/'traces'/f'{cid}_rep{rep}.json',trace)
        row={'prompt_id':cid,'prompt':case['prompt'],'tags':[flow,*case.get('target_skills',[])],
             'rep':rep,'status':'ok','stop_reason':'turn.completed','grade':{'task_pass':int(task),'writing_pass':int(style)},
             'explanation':{'task_pass':'; '.join(bad) or 'All task checks passed','writing_pass':json.dumps(verdict.get('writing_checks',[]),ensure_ascii=False)},
             'usage':norm,'judge_usage':normalized_usage(g.get('judge_usage')),'latency_s':raw['seconds'],
             'tool_calls':sum(e.get('type')=='item.completed' and e.get('item',{}).get('type')=='command_execution' for e in raw['events']),
             'meta':{'requested_model':raw['model_requested'],'served_model_verified':bool(raw.get('model_observed')),
                     'raw_result':str(p),'grade_identity':g['identity'],'case_sha256':raw['case_sha256'],
                     'skill_read_commands':reading,'subscription_cost_usd':None,'not_human_labels':True}}
        if raw.get('model_observed'):row['model']=raw['model_observed']
        flow_rows.setdefault((flow,variant),[]).append(row)
        summaries.append({'case':cid,'title':case['title'],'flow':flow,'variant':raw['variant'],'task':task,'style':style,'failures':bad,'writing_failures':writing_bad,'skill_read_commands':reading,'seconds':raw['seconds'],'raw':str(p),'grade':str(scored/'grades')})
    for cid,variant,rep in sorted(expected-scored_keys):
        if not any(p['case_id']==cid and p['variant']==variant and p['rep']==rep for p in pending):
            pending.append({'case_id':cid,'variant':variant,'rep':rep,'reason':'missing_successful_trial_or_grade'})
    # Replace generated row files on every export; stale scores never survive regrading.
    for flow in sorted({c['flow'] for c in cases.values()}):
        for variant in ('baseline','v1'):
            folder=output/flow/variant;folder.mkdir(parents=True,exist_ok=True)
            (folder/'results.jsonl').write_text('')
            (folder/'errors.jsonl').write_text('')
        for path in (output/flow/'report.html',output/flow/'trajectory/scores.tsv'):
            path.unlink(missing_ok=True)
    for (flow,variant),rows in flow_rows.items():
        folder=output/flow/variant
        (folder/'results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        (folder/'errors.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in failures if cases[e['case_id']]['flow']==flow and ('baseline' if e['variant']=='skills' else 'v1')==variant))
        if variant=='v1':(folder/'change.md').write_text('Control: same model, tools, fixtures and writing contract; skill package unavailable.\n')
    report_flows=sorted({f for f,v in flow_rows if v=='baseline'})
    for flow in report_flows:
        dump(output/flow/'_state.json',{'metrics':[{'id':'task_pass','kind':'binary','label':'任务完成'},{'id':'writing_pass','kind':'binary','label':'写作规范'}],
              'perf_fields':[{'id':'latency_s','label':'Seconds'},{'id':'in_tokens','label':'Input tokens'},{'id':'out_tokens','label':'Output tokens'}]})
        subprocess.run(['node',str(ROOT/'.agents/skills/build-eval/shared/evals/report/build-report-lite.mjs'),str(output/flow)],check=True)
    dump(output/'summary.json',{'rows':summaries,'execution_errors':failures,'pending':pending,'expected_trials':len(expected),'scored_trials':len(scored_keys),'complete':not pending,'no_suite_total':True,
          'limits':['one trial per case; synthetic small fixtures','same requested model for independent judge; not human calibrated','CLI may omit served model','control subset only; no population skill effect estimate']})
    lines=['# Skills 首轮评测结果','',f'已评分 {len(scored_keys)}/{len(expected)} 个试次；待执行或待有效评分 {len(pending)} 个。','','本轮按明确任务标准与写作规范自动评分，没有采集或代填用户偏好标签。不同任务流程分别列出，不计算混合总分。','',
           'skills 运行 19 题，control 只运行 C05/C08/C17/C19；只能比较同题四对，不能拿两组整体均值计算增量。','',
           '每题仅一次合成场景试跑。模型 Judge 与被测 Agent 使用独立会话，但来自同一模型；成绩用于定位问题，不作为稳定提升或真实学习成效的证据。','',
           '| 题目 | 配置 | 任务 | 写作 | 用时（秒） |','| --- | --- | --- | --- | --- |']
    skills_rows=[r for r in summaries if r['variant']=='skills']
    controls=[r for r in summaries if r['variant']=='control']
    headline=[f"加载 skills 的 {len(skills_rows)} 题中，任务完成 {sum(r['task'] for r in skills_rows)} 题，写作规范通过 {sum(r['style'] for r in skills_rows)} 题。", '']
    failed_ids=[r['case'] for r in skills_rows if not r['task']]
    if failed_ids:headline += ['未通过题：'+', '.join(failed_ids)+'；具体原因及原始产出见下方。','']
    if controls:
        matched=[(r,next((b for b in skills_rows if b['case']==r['case']),None)) for r in controls]
        if all(b and b['task']==r['task'] and b['style']==r['style'] for r,b in matched):
            headline += [f"{len(controls)} 道同题对照的两组通过/未通过结果相同。本轮没有测出这些题上的 skill 增量；题目可能过于简单，不能据此认定 skills 无用。",'']
    lines[4:4]=headline
    for r in sorted(summaries,key=lambda r:(r['case'],r['variant'])):
        lines.append(f"| {r['case']} {r['title']} | {r['variant']} | {'通过' if r['task'] else '未通过'} | {'通过' if r['style'] else '未通过'} | {r['seconds']} |")
    lines+=['','## 未通过项与证据','']
    for r in summaries:
        if not r['failures'] and not r['writing_failures']:continue
        lines += [f"### {r['case']} · {r['variant']}",'']+[f'- {x}' for x in r['failures']+r['writing_failures']]+['',f"[原始执行与文件结果]({r['raw']})",'']
    if pending:
        lines+=['## 尚未完成','']+[f"- {r['case_id']} {r['variant']} rep {r['rep']}: {r['reason']}" for r in pending]+['']
    lines+=['## 分流程报告','']+[f'- [{flow}]({output/flow/"report.html"})' for flow in report_flows]
    lines+=['','SKILL.md 读取命令保存在 summary.json；读取文件只能证明加载发生，不能单独证明遵循或增量效果。',
            '真实仓库与题库不挂载到被测环境；具体隔离探针和实际运行限制见试跑目录。CLI未返回实际服务模型时，只记录请求的gpt-5.5，不能独立核验实际模型身份。',
            '用时是完整 CLI 执行的墙钟时间，包含启动与不可单独观测的内部重试，不能当作模型服务延迟。','']
    (output/'RESULTS.md').write_text('\n'.join(lines))
    return 2 if pending else 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,required=True);p.add_argument('--scored',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--control-cases',default='C05,C08,C17,C19');p.add_argument('--reps',type=int,default=1);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);raise SystemExit(export(a.runs.resolve(),a.scored.resolve(),a.output.resolve(),tuple(x for x in a.control_cases.split(',') if x),a.reps))

"""Combine identity-checked suite reports without pooling heterogeneous abilities."""
import argparse
import collections
import json
from pathlib import Path
import evaluate

READ_REASON = 'target skill body read was not observed'


def paired_rows(summary):
    lookup = {(r['case'], r['arm'], r['rep']): r for r in summary['rows']}
    invalid = {(p['case'], p['rep']): p['reasons'] for p in summary['invalid_pairs']}
    accepted = {(p['case'], p['rep']) for p in summary['paired_outcomes']}
    pairs, excluded = [], []
    keys = accepted | set(invalid)
    for cid, rep in sorted(keys):
        reasons = invalid.get((cid, rep), [])
        structural = [r for r in reasons if r != READ_REASON]
        a, b = lookup.get((cid, 'control', rep)), lookup.get((cid, 'skills', rep))
        if not a or not b:
            structural.append('missing scored arm')
        if structural:
            excluded.append({'case': cid, 'rep': rep, 'reasons': structural})
            continue
        pairs.append({'case': cid, 'rep': rep, 'body_confirmed': READ_REASON not in reasons,
                      'control': a, 'skills': b})
    return pairs, excluded


def metric(pairs, name):
    counts = collections.Counter()
    for pair in pairs:
        a, b = pair['control'][name], pair['skills'][name]
        counts['both_pass' if a and b else 'both_fail' if not a and not b else 'skill_win' if b else 'skill_loss'] += 1
    n = len(pairs)
    return {'n': n, 'control': sum(p['control'][name] for p in pairs),
            'skills': sum(p['skills'][name] for p in pairs),
            **{key: counts[key] for key in ('both_pass', 'skill_win', 'skill_loss', 'both_fail')},
            'net_change': (counts['skill_win']-counts['skill_loss'])/n if n else None}


def export(source, output):
    manifest = evaluate.ensure_manifest(source, 'report')
    models = {}; missing = []
    for model in evaluate.MODELS:
        per_case = {}; exclusions = []; pending = []; rows = []
        for suite in evaluate.SUITES:
            path = source/model/suite/'report'/'summary.json'
            if not path.exists():
                missing.append(str(path));continue
            summary = json.loads(path.read_text())
            pairs, invalid = paired_rows(summary)
            exclusions.extend({'suite': suite, **p} for p in invalid)
            pending.extend({'suite': suite, **p} for p in summary['pending'])
            rows.extend({'suite': suite, **r} for r in summary['rows'])
            for case in evaluate.dataset(suite):
                selected = [p for p in pairs if p['case']==case['id']]
                read = [p for p in selected if p['body_confirmed']]
                per_case[case['id']] = {'suite': suite, 'skill': case['target_skill'], 'capability': case['capability'],
                    'all_assigned': {name: metric(selected, name) for name in ('primary', 'guardrails', 'writing')},
                    'confirmed_body': {name: metric(read, name) for name in ('primary', 'guardrails', 'writing')},
                    'pairs': selected}
        models[model] = {'cases': per_case, 'exclusions': exclusions, 'pending': pending, 'rows': rows,
                         'scored_trials': len(rows), 'structural_pairs': sum(c['all_assigned']['primary']['n'] for c in per_case.values()),
                         'body_confirmed_pairs': sum(c['confirmed_body']['primary']['n'] for c in per_case.values())}
    data = {'manifest': str(source/'matrix-manifest.json'), 'requested_models': list(evaluate.MODELS),
            'fixed_judge': evaluate.JUDGE_MODEL, 'served_model_identity': 'unverified when absent from CLI',
            'complete': not missing and all(m['scored_trials']==76 and not m['pending'] and not m['exclusions'] for m in models.values()),
            'missing_reports': missing, 'models': models, 'no_pooled_effectiveness_score': True}
    output.mkdir(parents=True, exist_ok=True)
    evaluate.write(output/'summary.json', data)
    lines = ['# 同模型加载 skill 前后的能力与约束比较', '',
        f"固定题目19道，四个请求模型，各组两次，共{sum(m['scored_trials'] for m in models.values())}/304个已评分试次。被测模型统一 medium、420秒；评分器固定 gpt-6.1-sol、medium、300秒。未调用 Astra。", '',
        '每格为 control → skills 的通过次数／有效配对数。先比较同一行、同一模型内的差异；不把19道异质题相加排名。这里的模型名是请求名，CLI未返回的实际服务身份无法独立核验。', '',
        '| 请求模型 | 已评分 | 结构有效配对 | 确认读过正文的配对 |', '| --- | --- | --- | --- |']
    for model, m in models.items():
        lines.append(f"| {model} | {m['scored_trials']}/76 | {m['structural_pairs']}/38 | {m['body_confirmed_pairs']}/{m['structural_pairs']} |")
    for scope, label in [('all_assigned', '全部结构有效配对'), ('confirmed_body', '确认读取正文的子集')]:
        lines += ['', '## '+label, '']
        if scope=='confirmed_body':
            lines += ['此子集可能存在选择偏差，不替代全部分配口径；它只帮助检查读取之后的表现。', '']
        for name, title in [('primary','原子主项'),('guardrails','行为约束'),('writing','写作规范')]:
            lines += ['### '+title, '', '| 题目 · 能力 | '+' | '.join(evaluate.MODELS)+' |', '| --- | '+' | '.join(['---']*4)+' |']
            for suite in evaluate.SUITES:
                for case in evaluate.dataset(suite):
                    cells=[]
                    for model in evaluate.MODELS:
                        record=models[model]['cases'].get(case['id'])
                        value=record[scope][name] if record else None
                        cells.append(f"{value['control']} → {value['skills']} / {value['n']}" if value else '未完成')
                    lines.append('| '+case['id']+' '+case['capability'].replace('|','/')+' | '+' | '.join(cells)+' |')
    lines += ['', '## 失败项与证据', '', '以下保留具体判定原因。复合检查失败不代表其所有子约束均违反；应结合原始输出判断。', '']
    for model, m in models.items():
        lines += ['### '+model, '']
        for r in m['rows']:
            failures={**r['failures'], **r['writing_failures']}
            if not failures:continue
            lines += [f"- **{r['case']} {r['arm']} 第{r['rep']}次**："+'；'.join(f'{k}: {v}' for k,v in failures.items())+f" [原始输出]({r['raw']}) · [评分]({r['grade_path']})"]
        for p in m['pending']+m['exclusions']:
            lines.append('- 未计入配对：'+json.dumps(p,ensure_ascii=False))
        lines.append('')
    lines += ['## 解释边界', '',
        '两次重复只能定位候选缺口，不能估计稳定收益。S01/S02/S03、A01/A02与原题相关，不是独立能力样本。主项改善可能来自知识或步骤提示；只有具体约束的违反减少且任务仍完成，才支持该约束更强的判断。两组都过通常没有测出增量，两组都没过也不能单凭分数归因于skill。', '',
        '固定评分器通过10个预设好／坏／空输出校准，仍可能漏判；gpt-6.1-sol同时作为被测模型，存在相关错误或风格偏好风险。本轮不测真实学习效果，也不把自动分数称作用户偏好。', '',
        f'[测量口径]({evaluate.HERE/"METRICS.md"}) · [完整配对与四格结果]({output/"summary.json"}) · [固定评分器校准]({source/"calibration/summary.json"})', '']
    (output/'RESULTS.md').write_text('\n'.join(lines))
    return 0 if data['complete'] else 2

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();raise SystemExit(export(args.source.resolve(), args.output.resolve()))

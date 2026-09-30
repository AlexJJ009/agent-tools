"""Check draft wiring and render review inputs; never run or grade an agent."""
import json
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def validate(design, packet):
    dimensions = {d['id']: d for d in design['dimensions']}
    assert len(dimensions) == len(design['dimensions']), 'duplicate dimension'
    assert all(v is None for v in design['approvals'].values()), 'draft has approval'
    for d in dimensions.values():
        p = (ROOT / d['source']['path']).resolve()
        assert p.is_relative_to(ROOT) and p.is_file(), d['id']
        assert 1 <= d['source']['line'] <= len(p.read_text().splitlines()), d['id']
    seen = set()
    for c in packet['cases']:
        assert c['id'] not in seen, 'duplicate case'
        seen.add(c['id'])
        assert c['primary_dimension'] in dimensions, c['id']
        assert c['flow'] == dimensions[c['primary_dimension']]['flow'], c['id']
        assert c['approval_status'] == 'unapproved' and c['scores'] is None, c['id']
        assert c['prompt'].strip() and c['checks'], c['id']
        assert all(x['result'] is None for x in c['checks']), c['id']
        assert c['user_preference']['choice'] is None, c['id']
        assert c['user_preference']['reason'] is None, c['id']
        for name, text in c['fixtures']['files'].items():
            p = Path(name)
            assert not p.is_absolute() and '..' not in p.parts, (c['id'], name)
            if p.suffix == '.py':
                compile(text, name, 'exec')
            if p.suffix == '.json':
                json.loads(text)
    return dimensions


def fenced(text, language=''):
    if any(line.rstrip(' \t') != line for line in text.splitlines()):
        return '以下用 JSON 字符串保留输入中的空白：\n\n' + fenced(json.dumps(text, ensure_ascii=False), 'json')
    fence = '`' * max(3, 1 + max((len(s) for s in re.findall(r'`+', text)), default=0))
    return f'{fence}{language}\n{text}\n{fence}'


def render(design, packet):
    dimensions = validate(design, packet)
    out = ['# BuildEval 候选题审阅', '',
           '这是任务与评分设计草案；所有题未批准、未运行、未评分。用户真实反馈用于选题，'
           '场景材料仍是合成改编，不代表已经复现旧问题。', '',
           f"本版有 {len(dimensions)} 个候选维度、{len(packet['cases'])} 道题。"
           '先看哪些任务值得测，再看每题的输入与判定是否一致。没有对应题的维度留待后续。', '',
           '建议先看 C05（抓根因）、C11（清理与交接）、C18（必要 ADR）、C19（自然触发练习）。'
           'C18 有明确请求及项目约定，不能证明无提醒的主动维护。', '',
           '评分不是强迫某个工具调用顺序；接受达到同样目标的不同正确做法。'
           '学习收益需要真实人的后续表现，不能由文稿质量或偏好选择替代。', '',
           '| 维度 | 要观察什么 | 候选题 |', '| --- | --- | --- |']
    for d in dimensions.values():
        ids = [c['id'] for c in packet['cases'] if c['primary_dimension'] == d['id']]
        out.append(f"| {d['id']} {d['name']} | {d['observable']} | {', '.join(ids) or '后续候选'} |")
    out += ['', '## 完整输入与候选判定', '',
            '每题展开后含完整用户输入、环境材料和拟定判定。判定条件仅留在评测端；'
            '不得连同答案一起交给被测 Agent。']
    for c in packet['cases']:
        out += ['', '<details>', f"<summary>{c['id']} · {c['title']}</summary>", '',
                f"维度：{c['primary_dimension']}；来源：{c['provenance']}；状态：未批准。", '',
                '**用户请求**', '', fenced(c['prompt'])]
        if len(c['turns']) > 1:
            out += ['', '**后续轮次（按顺序）**', '', fenced(json.dumps(c['turns'], ensure_ascii=False, indent=2), 'json')]
        out += ['', '**环境材料**', '', c['fixtures']['generation_spec']]
        for path, body in c['fixtures']['files'].items():
            out += ['', f'`{path}`', '', fenced(body)]
        out += ['', '**拟定判定条件**', '']
        out += [f"- {check['criterion']}" for check in c['checks']]
        out += ['', '</details>']
    out += ['', '## 需要用户判断的部分', '',
            '这些输入是否代表你在意的任务？哪一题漏掉了关键目标，或判定超出了请求？'
            '确认题目之后才采集少量真实输出，再单独校准评分。', '',
            '实际 A/B 产出出现后，标注允许 A / B / 同样好 / 都不好 / 跳过，并记录原因与场景。'
            '现在没有产出可选，偏好字段保持为空。', '']
    return '\n'.join(out)


if __name__ == '__main__':
    design = json.loads((HERE / 'design.json').read_text())
    packet = json.loads((HERE / 'cases.json').read_text())
    text = render(design, packet)
    if sys.argv[1:] == ['--write']:
        (HERE / 'REVIEW.md').write_text(text)
    elif sys.argv[1:]:
        raise SystemExit('usage: review_design.py [--write]')
    print(f"Design checks passed: {len(design['dimensions'])} dimensions, {len(packet['cases'])} unapproved cases")

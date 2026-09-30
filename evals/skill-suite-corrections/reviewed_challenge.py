"""Apply a documented rubric correction uniformly, retaining original trial bytes."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'skill-suite-challenge'))
import score_challenge as scoring

_original_identity = scoring.grading_identity
_original_prompt = scoring.grader.judge_prompt
_original_score = scoring.score_one


def correction():
    return json.loads((HERE / 'h03-rubric-v2.json').read_text())


def identity(case, raw, model='gpt-5.5'):
    base = _original_identity(case, raw, model)
    if case['id'] != 'H03':
        return base
    return scoring.digest({'original_identity': base, 'rubric_correction': correction(),
                           'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def corrected_prompt(case, *args, **kwargs):
    if case['id'] == 'H03':
        case = copy.deepcopy(case)
        rule = correction()
        case['primary_atomic_check'] = rule['criterion']
        for check in case['checks']:
            if check['id'] == 'H03.1':
                check['criterion'] = rule['criterion']
    return _original_prompt(case, *args, **kwargs)


def score_one(case, path, raw, output, model):
    record = _original_score(case, path, raw, output, model)
    if case['id'] == 'H03':
        record['rubric_correction'] = correction()
        target = output / 'grades' / f"{case['id']}-{raw['variant']}-{raw['rep']}-{record['identity'][:12]}.json"
        scoring.dump(target, record)
    return record


def full_body_read(raw):
    """A later shell failure does not erase already returned instruction bytes."""
    target = raw.get('skill_setup', {}).get('target')
    if not target:
        return []
    relative = 'skills/' + target + '/SKILL.md'
    body_path = scoring.ROOT / relative
    if not body_path.is_file():
        return []
    body = body_path.read_bytes()
    if hashlib.sha256(body).hexdigest() != raw.get('source_files', {}).get(relative):
        return []
    return [e['item']['id'] for e in raw.get('events', [])
            if e.get('type') == 'item.completed'
            and e.get('item', {}).get('type') == 'command_execution'
            and body.decode().strip() in e['item'].get('aggregated_output', '')]


def install_read_audit(report):
    original = report.pair_validity
    def audited(case, control, skills):
        reasons = original(case, control, skills)
        if skills and full_body_read(skills):
            reasons = [r for r in reasons if r != 'target skill body read was not observed']
        return reasons
    report.pair_validity = audited


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['score', 'report'])
    args, remaining = parser.parse_known_args()
    scoring.grading_identity = identity
    scoring.grader.judge_prompt = corrected_prompt
    scoring.score_one = score_one
    sys.argv = [sys.argv[0], *remaining]
    if args.action == 'score':
        return scoring.main()
    import report_challenge as report
    install_read_audit(report)
    p = argparse.ArgumentParser()
    p.add_argument('--runs', type=Path, required=True)
    p.add_argument('--scored', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reps', type=int, default=2)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    result = report.export(a.runs.resolve(), a.scored.resolve(), a.output.resolve(), a.reps)
    summary_path = a.output / 'summary.json'
    summary = json.loads(summary_path.read_text())
    audit = []
    for row in summary['rows']:
        raw = json.loads(Path(row['raw']).read_text())
        event_ids = full_body_read(raw) if row['arm'] == 'skills' else []
        if event_ids:
            row['target_read_observed'] = True
        if event_ids and raw.get('target_load', {}).get('status') != 'read_output_observed':
            audit.append({'case': row['case'], 'rep': row['rep'], 'event_ids': event_ids,
                          'reason': 'Complete hash-matched skill body was returned before a later shell command failed.'})
    audited_rows = {(r['case'], r['rep']): r for r in summary['rows'] if r['arm'] == 'skills'}
    for path in a.output.glob('*/v1/results.jsonl'):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        for row in rows:
            observed = audited_rows.get((row['prompt_id'], row['rep']), {}).get('target_read_observed', False)
            row['meta']['target_read_observed'] = observed
        path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    summary['read_observer_corrections'] = audit
    summary['rubric_correction'] = correction()
    scoring.dump(summary_path, summary)
    scoring.dump(a.output / 'measurement-corrections.json', {'rubric': correction(), 'read_observer': audit})
    with (a.output / 'RESULTS.md').open('a') as stream:
        stream.write('\n评分修订：H03 接受变量一致重命名，所有组别统一重评，原输出和旧分保留。读取观察器以哈希匹配的完整正文出现在工具输出为证据；同一 shell 后续命令失败不抹去已读正文。详见 measurement-corrections.json。\n')
    return result


if __name__ == '__main__':
    raise SystemExit(main())

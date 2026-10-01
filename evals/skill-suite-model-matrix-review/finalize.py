"""Read-only source audit and a separate aggregate view; never launches models."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'skill-suite-model-matrix'))
import evaluate
import summarize


def latest_attempts(runs, cid, arm, rep):
    stem = f'{cid}-{arm}-{rep}'
    pattern = re.compile(re.escape(stem) + r'(?:-attempt(\d+))?$')
    found = []
    if runs.exists():
        for folder in runs.iterdir():
            match = pattern.fullmatch(folder.name)
            if match and folder.is_dir():
                found.append((int(match.group(1) or 1), folder / 'result.json'))
    return [p for _, p in sorted(found)]


def status(raw):
    if raw is None:
        return 'missing'
    if raw.get('status') == 'ok':
        return 'completed'
    if raw.get('status') == 'timeout' or raw.get('error') == 'timeout':
        return 'budget_unfinished'
    return 'error'


def protocol_errors(raw, model, manifest):
    expected = {'manifest_sha256': evaluate.digest(manifest),
                'subject_model_requested': model, 'judge_model_requested': evaluate.JUDGE_MODEL}
    errors = [f'matrix_protocol.{k}' for k, v in expected.items()
              if raw.get('matrix_protocol', {}).get(k) != v]
    for key, value in [('model_requested', model), ('effort', 'medium'), ('timeout_seconds', 420)]:
        if raw.get(key) != value:
            errors.append(key)
    if raw.get('model_observed') and raw['model_observed'] != model:
        errors.append('model_observed')
    return errors


def summarize_completion(slots):
    counts = Counter(r['completion'] for r in slots)
    pairs = {}
    for row in slots:
        key = (row['model'], row['suite'], row['case'], row['rep'])
        pairs.setdefault(key, {})[row['arm']] = row['completion'] == 'completed'
    grids = {}
    for (model, suite, cid, rep), arms in pairs.items():
        key = 'both_completed' if arms.get('skills') and arms.get('control') else 'skills_only' if arms.get('skills') else 'control_only' if arms.get('control') else 'neither_completed'
        grid = grids.setdefault(model, {}).setdefault(cid, {k: 0 for k in ['both_completed', 'skills_only', 'control_only', 'neither_completed']})
        grid[key] += 1
    return {'expected_slots': len(slots), **{k: counts[k] for k in ['completed', 'budget_unfinished', 'error', 'missing']},
            'identity_checked_grades': sum(r.get('grade_valid', False) for r in slots),
            'evaluation_run_complete': bool(slots) and all(r['attempted'] and not r.get('protocol_errors') and (r['completion'] == 'budget_unfinished' or (r['completion'] == 'completed' and r.get('grade_valid'))) for r in slots),
            'completion_four_cells': grids,
            'per_model': {m: dict(Counter(r['completion'] for r in slots if r['model'] == m)) for m in dict.fromkeys(r['model'] for r in slots)}}


def identity_worker(suite, source):
    # Fresh process per suite prevents legacy modules' mutable globals contaminating identities.
    if suite == 'challenge':
        sys.path.insert(0, str(HERE))
        import reviewed_h01
        identity = reviewed_h01.identity
    elif suite == 'mechanisms':
        sys.path.insert(0, str(HERE.parent / 'skill-suite-corrections'))
        import reviewed_mechanisms
        identity = reviewed_mechanisms.identity
    elif suite == 'source-discovery':
        sys.path.insert(0, str(HERE.parent / 'skill-suite-source-discovery'))
        import score_source_discovery
        identity = score_source_discovery.grading_identity
    else:
        path = HERE.parent / 'skill-suite-artifact-followup/evaluate.py'
        spec = importlib.util.spec_from_file_location('artifact_identity', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.configure()
        identity = module.scorer.grading_identity
    result = {}
    for model in evaluate.MODELS:
        for case in evaluate.dataset(suite):
            for arm in ('skills', 'control'):
                for rep in (1, 2):
                    paths = latest_attempts(source / model / suite / 'runs', case['id'], arm, rep)
                    if paths and paths[-1].exists():
                        raw = json.loads(paths[-1].read_text())
                        if status(raw) == 'completed':
                            result[str(paths[-1])] = identity(case, raw, evaluate.JUDGE_MODEL)
    return result


def link(path, target):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() and path.resolve() == target.resolve():
        return
    if path.exists() or path.is_symlink():
        raise RuntimeError('Refusing to replace existing view entry: ' + str(path))
    path.symlink_to(target.resolve(), target_is_directory=target.is_dir())


def finalize(source, view, output):
    manifest = evaluate.ensure_manifest(source, 'report')
    if view == source or output == source or view == output or output.is_relative_to(view) or view.is_relative_to(output):
        raise ValueError('Source, view and output must be separate non-overlapping locations')
    protected = [source / m for m in evaluate.MODELS] + [source / 'calibration', source / 'calibration-h01']
    if any(p == q or p.is_relative_to(q) for p in (view, output) for q in protected):
        raise ValueError('Cannot write inside original model/calibration evidence')
    selected = {}; reports = {}; identities = {}
    for suite in evaluate.SUITES:
        process = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--identity-worker', suite, '--source', str(source)], capture_output=True, text=True, check=True)
        identities.update(json.loads(process.stdout))
    link(view / 'matrix-manifest.json', source / 'matrix-manifest.json')
    link(view / 'calibration', source / 'calibration')
    for model in evaluate.MODELS:
        for suite in evaluate.SUITES:
            folder = source / model / suite / ('report-h01-review' if suite == 'challenge' else 'report')
            path = folder / 'summary.json'
            if not path.exists():
                raise RuntimeError('Selected report missing: ' + str(path))
            selected[f'{model}/{suite}'] = str(path)
            reports[model, suite] = json.loads(path.read_text())
            link(view / model / suite / 'report', folder)
    if sum(len(evaluate.dataset(s)) for s in evaluate.SUITES) != 19 or manifest.get('expected_subjects') != 304:
        raise RuntimeError('Expected frozen 19-case / 304-slot matrix')
    slots = []; prior_failures = []; all_protocol_errors = []
    for model in evaluate.MODELS:
        for suite in evaluate.SUITES:
            rows = reports[model, suite]['rows']
            for case in evaluate.dataset(suite):
                for arm in ('skills', 'control'):
                    for rep in (1, 2):
                        paths = latest_attempts(source / model / suite / 'runs', case['id'], arm, rep)
                        raw = None; errors = []
                        for i, path in enumerate(paths):
                            current = json.loads(path.read_text()) if path.exists() else None
                            problems = protocol_errors(current, model, manifest) if current is not None else ['missing result.json']
                            if current is not None and (current.get('case_id'), current.get('variant'), current.get('rep')) != (case['id'], arm, rep):
                                problems.append('slot identity')
                            if problems:
                                all_protocol_errors.append({'raw': str(path), 'latest': i == len(paths)-1, 'errors': problems})
                            if i < len(paths)-1 and status(current) != 'completed':
                                prior_failures.append({'raw': str(path), 'status': status(current), 'error': current.get('error') if current else 'missing result.json'})
                            if i == len(paths)-1:
                                raw, errors = current, problems
                        row = {'model': model, 'suite': suite, 'case': case['id'], 'arm': arm, 'rep': rep,
                               'attempted': bool(paths), 'attempt_count': len(paths), 'raw': str(paths[-1]) if paths else None,
                               'completion': status(raw), 'protocol_errors': errors, 'grade_valid': False}
                        if raw is not None and raw.get('case_sha256') != manifest['case_sha256'][suite][case['id']]:
                            row['protocol_errors'].append('case_sha256')
                        if status(raw) == 'completed':
                            matches = [r for r in rows if (r['case'], r['arm'], r['rep']) == (case['id'], arm, rep)]
                            row['grade_error'] = 'missing, duplicated, stale or mismatched grade'
                            if len(matches) == 1:
                                report_row = matches[0]; grade_path = Path(report_row['grade_path'])
                                grade = json.loads(grade_path.read_text()) if grade_path.exists() else {}
                                expected = identities.get(str(paths[-1]))
                                row['grade_path'] = str(grade_path)
                                row['grade_valid'] = bool(expected and report_row.get('grade_identity') == expected and grade.get('identity') == expected and report_row.get('raw') == str(paths[-1]) and grade.get('raw_path') == str(paths[-1]) and grade.get('judge_model_requested') == evaluate.JUDGE_MODEL and grade.get('case_sha256') == evaluate.digest(case) and (grade.get('case_id'), grade.get('variant'), grade.get('rep')) == (case['id'], arm, rep))
                                if row['grade_valid']:
                                    row.pop('grade_error')
                        slots.append(row)
    report_errors = []
    slot_index = {(r['model'], r['suite'], r['case'], r['arm'], r['rep']): r for r in slots}
    for (model, suite), report in reports.items():
        seen = set()
        for row in report['rows']:
            key = (model, suite, row['case'], row['arm'], row['rep'])
            slot = slot_index.get(key)
            if key in seen or not slot or slot['completion'] != 'completed' or row['raw'] != slot['raw']:
                report_errors.append({'report': selected[f'{model}/{suite}'], 'case': row['case'], 'arm': row['arm'], 'rep': row['rep'], 'reason': 'duplicate, unexpected, non-completed or stale report row'})
            seen.add(key)
    audit = summarize_completion(slots)
    audit['report_errors'] = report_errors
    audit['evaluation_run_complete'] = audit['evaluation_run_complete'] and not report_errors
    audit.update({'slots': slots, 'selected_reports': selected, 'source': str(source),
                  'original_report_complete': {f'{m}/{s}': r.get('complete') for (m,s),r in reports.items()},
                  'prior_failed_attempts': prior_failures, 'prior_failed_attempt_count': len(prior_failures),
                  'prior_failed_reason_counts': dict(Counter(str(r['error']) for r in prior_failures)),
                  'all_attempt_protocol_errors': all_protocol_errors,
                  'temporary_auth_residue_count': sum(1 for p in source.rglob('auth.json') if p.is_file())})
    calibration_path = source / 'calibration-h01/summary.json'
    calibration = json.loads(calibration_path.read_text())
    audit['h01_calibration'] = {'path': str(calibration_path), 'count': calibration.get('count'), 'matched': calibration.get('matched')}
    audit['delivery_ready'] = audit['evaluation_run_complete'] and audit['temporary_auth_residue_count'] == 0 and calibration.get('count') == 4 and calibration.get('matched') == 4
    # The old export owns quality denominators. Do not add timeout rows or alter its complete flag.
    summarize.export(view, output)
    summary = json.loads((output / 'summary.json').read_text())
    summary['manifest'] = str(source / 'matrix-manifest.json')
    summary['evaluation_run_complete'] = audit['evaluation_run_complete']
    summary['completion_audit'] = str(output / 'completion-audit.json')
    summary['selected_reports'] = selected
    evaluate.write(output / 'summary.json', summary)
    evaluate.write(output / 'completion-audit.json', audit)
    report = (output / 'RESULTS.md').read_text().replace(str(view / 'calibration/summary.json'), str(source / 'calibration/summary.json'))
    report += '\n## 执行完成与评分覆盖\n\n'
    report += f"全部 {audit['expected_slots']} 个实验位置：完成 {audit['completed']}，预算内未完成 {audit['budget_unfinished']}，其他错误 {audit['error']}，缺失 {audit['missing']}。身份核验通过的评分 {audit['identity_checked_grades']}。evaluation_run_complete={audit['evaluation_run_complete']}；原质量汇总 complete={summary['complete']}，原分报告的 complete 值保存在审计中，不因执行结束改为真。\n\n"
    report += '执行完成表示所有位置已尝试，最新尝试只剩完整输出或超时，且完整输出都有身份核验评分；不表示所有任务成功或全部配对可评分。超时单列，不填成质量 false。质量比较只覆盖完成且结构有效的配对子集，可能存在完成条件造成的选择偏差，不能代表全部分配任务的成功率。重试保留历史错误，但同一实验位置只取最新数字 attempt，不增加分母。\n\n'
    report += '| 模型 | 题目 | 两组完成 | 仅 skills 完成 | 仅 control 完成 | 两组未完成 |\n| --- | --- | --- | --- | --- | --- |\n'
    for model, cases in audit['completion_four_cells'].items():
        for cid, grid in cases.items():
            report += '| ' + ' | '.join([model, cid, *[str(v) for v in grid.values()]]) + ' |\n'
    report += f"\n历史失败尝试 {len(prior_failures)} 个；临时认证文件残留 {audit['temporary_auth_residue_count']} 个（只数文件，不读取内容）。H01 修订评分器预设校准 {calibration.get('matched')}/{calibration.get('count')} 与预期一致；这不保证实际评分无误，也不改变被测输入。\n\n[执行与身份审计]({output / 'completion-audit.json'}) · [H01 校准]({calibration_path})\n"
    (output / 'RESULTS.md').write_text(report)
    return 0 if audit['delivery_ready'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--view', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--identity-worker', choices=list(evaluate.SUITES))
    args = parser.parse_args()
    if args.identity_worker:
        print(json.dumps(identity_worker(args.identity_worker, args.source.resolve())))
        return 0
    if args.view is None or args.output is None:
        parser.error('--view and --output are required')
    return finalize(args.source.resolve(), args.view.resolve(), args.output.resolve())


if __name__ == '__main__':
    raise SystemExit(main())

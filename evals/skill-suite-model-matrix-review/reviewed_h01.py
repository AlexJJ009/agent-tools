"""H01 disposition measurement clarification; immutable subjects and old grades."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'skill-suite-corrections'))
import reviewed_challenge_v3 as previous

scoring = previous.scoring


def correction():
    return {
        'correction_id': 'h01-all-actual-dispositions-v1',
        'case_id': 'H01', 'primary_check_id': 'H01.1',
        'criterion': '正确区分废弃试验与活跃/唯一材料，并核查所有实际处置：删除已被替代的 scratch/probe_v1.py 和 probe_v1.out；保留配置动态加载的插件、活跃 seed、最后已交付 final survey 及其唯一 source-observation 证据；不能把较新 draft 当作替代 final 的依据。未完成、未交付本身不构成废弃依据；cache-v2-draft.md 仍在评审且未被证明废弃，若删除且无等价替代保留，H01.1 必须为 false，不能仅在写作或交接项扣分。允许材料等价保留或迁移：内容及未决评审状态仍可恢复，相关引用同步更新，不要求原文件名原路径，也不要求额外文档。',
        'reason': 'Original user asks to clean genuinely obsolete materials and retain useful content. The fixture explicitly identifies unresolved review. Clarify the scope of primary disposition judgment, rather than introducing a new task or making the fixture harder.',
        'input_changed': False, 'raw_outputs_changed': False,
        'rerun_candidate_required': False,
        'rescore_scope': 'All 16 H01 outputs: four subject models, both arms, both repetitions; retain original grades.',
    }


def identity(case, raw, model='gpt-6.1-sol'):
    base = previous.identity(case, raw, model)
    if case['id'] != 'H01':
        return base
    return scoring.digest({'previous_identity': base, 'rubric_correction': correction(),
                           'h01_adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def corrected_prompt(case, *args, **kwargs):
    if case['id'] != 'H01':
        return previous.corrected_prompt(case, *args, **kwargs)
    case = copy.deepcopy(case)
    case['primary_atomic_check'] = correction()['criterion']
    for check in case['checks']:
        if check['id'] == 'H01.1':
            check['criterion'] = correction()['criterion']
    return previous.corrected_prompt(case, *args, **kwargs) + (
        '\nH01.1 证据核查：逐项比较 before/after 的实际删除、迁移和保留，不以最终交接文字替代文件证据。'
        '说明 draft 原有未决评审状态、处置结果，以及是否存在等价保留或废弃依据。'
        '缺少弃用依据却删除仍在评审的唯一 draft，是主项处置错误，即使其他材料处理正确也不能通过主项。'
        '不得凭文件名断言丢失；应检查迁移后的内容及引用。未执行清理或空产出也不能通过主项。\n')


def score_one(case, path, raw, output, model):
    record = previous.score_one(case, path, raw, output, model)
    if case['id'] == 'H01':
        record['rubric_correction'] = correction()
        scoring.dump(output / 'grades' / f"{case['id']}-{raw['variant']}-{raw['rep']}-{record['identity'][:12]}.json", record)
    return record


def install():
    previous.install()
    scoring.grading_identity = identity
    scoring.grader.judge_prompt = corrected_prompt
    scoring.score_one = score_one


def install_report(report):
    report.grading_identity = identity
    previous.legacy.install_read_audit(report)


def export_report(runs, scored, output, reps):
    # Reuse v3 export while explicitly supplying the same identity as scoring.
    with patch.object(previous, 'install_report', install_report):
        result = previous.export_report(runs, scored, output, reps)
    summary_path = output / 'summary.json'
    summary = json.loads(summary_path.read_text())
    summary['rubric_corrections']['H01'] = correction()
    scoring.dump(summary_path, summary)
    metadata_path = output / 'measurement-corrections.json'
    metadata = json.loads(metadata_path.read_text())
    metadata['rubrics']['H01'] = correction()
    scoring.dump(metadata_path, metadata)
    with (output / 'RESULTS.md').open('a') as stream:
        stream.write('\nH01 测量修订：主项核查所有实际处置。未完成或未交付不等于废弃；无弃用依据且无等价保留地删除仍在评审的草稿，主项不通过。四模型、两组、两次共 16 条统一重评，原题、原始输出及旧分保留。\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['score', 'report'])
    args, rest = parser.parse_known_args()
    install()
    sys.argv = [sys.argv[0], *rest]
    if args.action == 'score':
        if '--model' not in rest:
            sys.argv.extend(['--model', 'gpt-6.1-sol'])
        return scoring.main()
    parser = argparse.ArgumentParser()
    for name in ['runs', 'scored', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--reps', type=int, default=2)
    options = parser.parse_args()
    return export_report(options.runs.resolve(), options.scored.resolve(), options.output.resolve(), options.reps)


if __name__ == '__main__':
    raise SystemExit(main())

"""Combine frozen reports by issue type, without rescoring or pooling abilities."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ('gpt-6.1-sol', 'gpt-6-sol', 'gpt-5.6-sol', 'gpt-6-luna')
DEFAULT_OLD = ROOT / 'docs/_local/evals/skill-suite-model-matrix/20260930/summary.json'
GROUPS = {
    '清理、材料保留与交接': ('H01','H02','L03','F01','F02','F05'),
    '当前任务意图与明确执行顺序': ('H07','H08'),
    '教学解释与自然练习': ('H03','H04','L04','F03','F04'),
    '检索练习、学习状态与材料发现': ('H05','H06','L01','L02','S01','S02','S03'),
    '既有产物修订与 ADR 维护': ('H09','H10','A01','A02','F06'),
}
TITLES = {
'H01':'识别废弃材料并保留未决草稿','H02':'保留语义的代码去重','H03':'解释共享对象在失败前已被修改','H04':'核对源码与过时运行证据',
'H05':'针对浅拷贝误解出题','H06':'弱定位指代下的 finally 练习','H07':'暂停修改后仍完成只读定位','H08':'恢复修订要求及明确交付顺序',
'H09':'定点修订并补必要因果前提','H10':'修订产物中的证据范围','L01':'无显式路径时恢复已有学习前沿','L02':'保留提示后作答与帮助程度',
'L03':'整组退役并保留活跃证据','L04':'学习编排中及时给可见练习','S01':'给当前项目线索后的材料发现','S02':'给具体文件路径后的材料发现',
'S03':'给学习记录路径后的状态恢复','A01':'等价产物修订探针一','A02':'等价产物修订探针二'}
LIMITS = {
'H06':'“这两个函数”的来源指代较弱，失败可能是定位歧义，不能直接称 finally 知识不足；结合 S01/S02。',
'L02':'16 份状态记录均保留回答、提示和历史；部分旧主项把源码核对方法合并扣分且口径不一致。原分仅保留，不等于状态维护失败。',
'H08':'原主项包含用户明确要求的修复→解释→usage 顺序；16 份核心 CSV 功能均正确。顺序不通过不等于功能失败，也不建立通用固定流程。',
'H07':'失败可能是将“别跑程序”扩大为不读文件或缺定位；护栏含正向定位，不通过不必然表示越权。',
'L01':'与 S03 比较只能观察记录定位线索的影响，不证明长期记忆或内部因果机制。',
'S03':'L01 的路径提示探针，不是独立新能力样本；恢复改善只支持局部定位解释。',
'F03':'方法敏感：原复合标准预设先解释再练习及保留独立作答空间，但用户允许引导式推进，先提问或提供部分提示不天然等于失败。两组各8/8均给出针对性短练习；原分差不能用来证明 skill 增益或能力缺口。两组共同拥有 retrieval-practice，实际观察见 triage-field-discovery.json。',
'F04':'必须正确完成接口说明；空答即使没有出题也不通过。',
'F06':'已有采纳决定及错误恢复说明构成维护依据，不推导每次交付都应新建 ADR。',
'A01':'与 H09 的等价跟进题相关，不是独立能力样本。',
'A02':'与 H09 的等价跟进题相关，不是独立能力样本。',
}


def read(path):
    return json.loads(path.read_text())


def metric(pairs, key):
    return {'n': len(pairs), 'control': sum(p['control'][key] for p in pairs),
            'skills': sum(p['skills'][key] for p in pairs)}


def field_case(report, model, cid):
    rows = [r for r in report.get('rows', []) if r['model']==model and r['case']==cid]
    diagnostics = []; pairs = []
    for rep in (1, 2):
        pair = {}; reasons = []
        structural = [p for p in report.get('pairs', []) if (p['model'],p['case'],p['rep'])==(model,cid,rep)]
        if len(structural)!=1:
            reasons.append('missing or duplicated structural pair record')
        elif structural[0]['structural_reasons']:
            reasons.extend(structural[0]['structural_reasons'])
        for arm in ('control','skills'):
            selected = [r for r in rows if r['rep']==rep and r['arm']==arm]
            if len(selected)!=1:
                reasons.append(arm+': missing or duplicate trial'); continue
            row = selected[0]
            if row.get('status')!='ok':
                reasons.append(arm+': '+str(row.get('error') or row.get('status')))
            if not row.get('pair_eligible'):
                reasons.append(arm+': structural eligibility not confirmed')
            verdict = row.get('verdict')
            if not verdict:
                reasons.append(arm+': pending grade'); continue
            keys = {'primary':'primary_pass','guardrails':'guardrails_pass','writing':'writing_pass'}
            if any(not isinstance(verdict.get(v),bool) for v in keys.values()):
                reasons.append(arm+': incomplete grade');continue
            pair[arm] = {k:verdict[v] for k,v in keys.items()}
        if reasons:
            diagnostics.append({'rep':rep,'reasons':list(dict.fromkeys(reasons))})
        else:
            pairs.append({'rep':rep, **pair})
    return {'metrics': {k:metric(pairs,k) for k in ('primary','guardrails','writing')},
            'pending_or_excluded':diagnostics, 'rows':rows}


def read_counts(rows, field=False):
    skills=[r for r in rows if r['arm']=='skills' and (not field or r.get('status')!='missing')]
    statuses=Counter()
    for row in skills:
        if field:
            status=(row.get('target_read') or {}).get('status','missing')
        else:
            # Reviewed report observations fix the earlier cat && rg exit-status
            # false negative. Do not regress them by reading stale raw flags.
            observed=row.get('target_read_observed')
            status='read_output_observed' if observed is True else 'not_observed' if observed is False else 'unknown_ungraded'
        statuses[status]+=1
    return {'observed':statuses['read_output_observed'],'skills_rows':len(skills),
            'status_counts':dict(statuses),'unknown':statuses['unknown_ungraded'],'control':'not_applicable'}


def build(old_path, field_path):
    old=read(old_path)
    field=read(field_path) if field_path.exists() else {'rows':[], 'pairs':[], 'issues':[{'error':'field report pending'}]}
    definitions={c['id']:c for c in read(ROOT/'evals/skill-suite-field/cases.json')['cases']}
    matrix=Path(old['manifest']).parent
    limits_path=matrix/'measurement-limitations.json'
    measurement=read(limits_path) if limits_path.exists() else {'affected':[]}
    affected={}
    for record in measurement['affected']:
        affected.setdefault(record['case_id'],[]).append({k:record.get(k) for k in ['subject_model_requested','variant','rep','grade_identity','grade_path','classification']})
    audit_path=Path(old['completion_audit']) if old.get('completion_audit') else None
    audit=read(audit_path) if audit_path and audit_path.exists() else {}
    cases=[]
    for group, ids in GROUPS.items():
        for cid in ids:
            is_field=cid.startswith('F')
            definition=definitions.get(cid,{})
            record={'id':cid,'category':group,'title':definition.get('title',TITLES.get(cid,cid)),
                    'source':'field' if is_field else 'original',
                    'invocation':definition.get('skill_setup',{}).get('invocation','explicit'),
                    'limitation':LIMITS.get(cid,''),'writing_context_uncertainty':affected.get(cid,[]),'models':{}}
            for model in MODELS:
                if is_field:
                    value=field_case(field,model,cid)
                    value['target_read']=read_counts(value['rows'],True)
                    value['completion']={arm:sum(r['status']=='ok' for r in value['rows'] if r['arm']==arm) for arm in ('control','skills')}
                else:
                    m=old.get('models',{}).get(model,{})
                    c=m.get('cases',{}).get(cid)
                    rows=[r for r in m.get('rows',[]) if r['case']==cid]
                    value={'metrics':c['all_assigned'] if c else {k:{'n':0,'control':0,'skills':0} for k in ('primary','guardrails','writing')},
                           'pending_or_excluded':[p for p in m.get('pending',[])+m.get('exclusions',[]) if p['case']==cid],
                           'rows':rows,'target_read':read_counts(rows + [{'arm':r['arm'],'target_read_observed':None} for r in audit.get('slots',[]) if r['model']==model and r['case']==cid and r.get('raw') and not any(x['arm']==r['arm'] and x['rep']==r['rep'] for x in rows)]),'original_confirmed_body':c.get('confirmed_body') if c else None,
                           'completion':{arm:sum(r['completion']=='completed' for r in audit.get('slots',[]) if (r['model'],r['case'],r['arm'])==(model,cid,arm)) for arm in ('control','skills')}}
                    if not c:value['pending_or_excluded'].append({'reason':'case report pending'})
                record['models'][model]=value
            cases.append(record)
    coverage=[]
    for model in MODELS:
        for dataset, total in [('original',76),('field',24)]:
            selected=[c['models'][model] for c in cases if c['source']==dataset]
            completed=sum(sum(c['completion'].values()) for c in selected)
            graded=sum(len([r for r in c['rows'] if ('verdict' in r if dataset=='field' else True)]) for c in selected)
            observed=sum(c['target_read']['observed'] for c in selected)
            read_rows=sum(c['target_read']['skills_rows'] for c in selected)
            unknown=sum(c['target_read']['unknown'] for c in selected)
            coverage.append({'model':model,'source':dataset,'expected_slots':total,'completed':completed,'graded':graded,'target_read_observed':observed,'target_read_rows':read_rows,'target_read_unknown':unknown,'read_denominator':'skills trial rows only; control is not applicable'})
    return {'models':list(MODELS),'case_count':len(cases),'cases':cases,'coverage':coverage,
            'sources':{'old':str(old_path),'field':str(field_path),'field_report_present':field_path.exists(),
                       'measurement_limitations':str(limits_path),'completion_audit':str(audit_path) if audit_path else None},
            'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [old_path,field_path,limits_path] if p.exists()},
            'old_complete':old.get('complete'),'old_evaluation_run_complete':old.get('evaluation_run_complete'),
            'writing_context_affected_grade_count':measurement.get('affected_grade_count'),
            'no_pooled_quality_sum':True,'scores_modified':False}


def cell(value, key):
    m=value['metrics'][key]
    if not m['n']:return '待评分／无有效配对'
    return f"{m['control']} → {m['skills']} / {m['n']}"+('（另有待评分/排除）' if value['pending_or_excluded'] else '')


def render(data, output):
    lines=['# 按问题类型归类的技能评估','',
      '共 25 道题。每格是同一模型、同一道题的 control → skills 通过次数／有效配对数；不跨题或跨模型汇总质量总分。主项、约束与写作分别列出。原始自动评分保持不变。','',
      'explicit 表示显式调用目标技能；discoverable 表示只提供可发现能力，由任务自然触发。缺少正文读取证据是诊断，不排除有效配对，也不证明未被原生注入或没有遵循。', '',
      '新现场评估的 Judge 已提供实际指令上下文，旧评估有 13 条写作判定受到隐藏显式调用指令的影响。新旧写作协议不同，不能把两轮分数变化称为技能进步；受影响旧题在表旁标记，不推算修正分。','',
      '两次重复只支持局部观察。超时、错误、缺评分不补成质量 false；只有双方已完成、结构有效且都有评分才进入新题质量分母。有效配对子集可能有选择偏差。原题完成状态和分母按原报告保留。','']
    for category in GROUPS:
        lines += ['## '+category,'']
        selected=[c for c in data['cases'] if c['category']==category]
        for key,label in [('primary','主项'),('guardrails','约束'),('writing','写作')]:
            lines += ['### '+label,'','| 题目 / 调用 | '+' | '.join(MODELS)+' |','| --- | '+' | '.join(['---']*4)+' |']
            for c in selected:
                flag=' †' if c['writing_context_uncertainty'] else ''
                lines.append('| '+c['id']+' '+c['title']+' / '+c['invocation']+flag+' | '+' | '.join(cell(c['models'][m],key) for m in MODELS)+' |')
            lines.append('')
        for c in selected:
            if c['limitation']:lines.append('- **'+c['id']+'**：'+c['limitation'])
            if c['writing_context_uncertainty']:
                names=['%s %s 第%s次'%(r['subject_model_requested'],r['variant'],r['rep']) for r in c['writing_context_uncertainty']]
                lines.append('- **'+c['id']+' † 写作上下文限制**：'+ '；'.join(names)+'。旧 Judge 未见实际显式调用指令，不能把相关扣分解释为已证实的写作退步；另有可独立核查的问题仍须分开看。')
        lines.append('')
    lines += ['## 完成与读取诊断','', '| 模型 | 题组 | 完成 / 分配 | 已评分 | skills 正文读取可见 / 已有 skills 记录 |','| --- | --- | --- | --- | --- |']
    for row in data['coverage']:
        lines.append(f"| {row['model']} | {row['source']} | {row['completed']}/{row['expected_slots']} | {row['graded']} | {row['target_read_observed']}/{row['target_read_rows']}（未知 {row['target_read_unknown']}） |")
    lines += ['', '逐题读取只统计 skills 臂，control 为不适用。旧题使用已审阅 summary 的 target_read_observed，保留对组合命令退出码造成漏判的修正；无评分的超时读取标为未知，不按未读计。新题使用 field report 的 target_read.status，观察完整正文出现在工具输出。两者都是可见读取诊断，不证明注意或遵循，不能从未观察到推断未加载。', '', '| 题目 | 模型 | 完成 control / skills（各 2） | skills 读取可见 / 记录（最多 2） |', '| --- | --- | --- | --- |']
    for c in data['cases']:
        for model,v in c['models'].items():
            r=v['target_read'];lines.append(f"| {c['id']} | {model} | {v['completion']['control']} / {v['completion']['skills']} | {r['observed']}/{r['skills_rows']}（未知 {r['unknown']}） |")
    lines += ['', '## 待评分、排除与证据','']
    for c in data['cases']:
        for model,v in c['models'].items():
            for issue in v['pending_or_excluded']:
                lines.append('- '+c['id']+' / '+model+'：'+json.dumps(issue,ensure_ascii=False))
    sources=data['sources']
    lines += ['',f"[原 19 题汇总]({sources['old']}) · [新现场题逐条结果]({sources['field']}) · [写作测量限制]({sources['measurement_limitations']}) · [分类数据与逐条 raw/grade 路径]({output/'classified.json'})",'',
              '分类数据保留逐条产出和评分路径、原有失败原因，以及待评分/排除原因。这里不重新判断具体失败的因果；需要结合原始代码、文件变化和回复复核。','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old',type=Path,default=DEFAULT_OLD)
    parser.add_argument('--field',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); output=args.output.resolve()
    if output.is_relative_to(ROOT/'evals'):
        parser.error('Output must be an ignored report directory or outside the source checkout')
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT/'docs/_local'):
        parser.error('In-checkout output must be under ignored docs/_local')
    data=build(args.old.resolve(),args.field.resolve())
    output.mkdir(parents=True,exist_ok=True)
    (output/'classified.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    (output/'CLASSIFIED_RESULTS.md').write_text(render(data,output))
    return 2 if any(v['pending_or_excluded'] for c in data['cases'] for v in c['models'].values()) else 0


if __name__=='__main__':raise SystemExit(main())

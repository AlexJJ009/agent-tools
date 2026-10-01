"""Repeat the fixed 25 cases against merged-main skill bytes, in fresh artifacts."""
import argparse
import concurrent.futures
import copy
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
matrix=load(HERE.parent/'skill-suite-model-matrix/evaluate.py','regression_matrix')
field=load(HERE.parent/'skill-suite-field/evaluate.py','regression_field')
write=matrix.write
digest=matrix.digest


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def main_skill_files(commit):
    data=git('archive',commit,'skills')
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        files={}
        for member in archive:
            if member.isfile():files[member.name]=hashlib.sha256(archive.extractfile(member).read()).hexdigest()
            elif member.issym() or member.islnk():raise RuntimeError('Skill symlink needs explicit materialization review: '+member.name)
        return files


def expected_manifest(output,commit):
    commit=git('rev-parse',commit+'^{commit}').decode().strip()
    subprocess.run(['git','merge-base','--is-ancestor',commit,'HEAD'],cwd=ROOT,check=True)
    if git('diff','--name-only',commit,'--','skills').strip():raise RuntimeError('Checkout skills differ from merged main')
    value={'main_commit':commit,'files':main_skill_files(commit)}
    for relative,sha in value['files'].items():
        if matrix.sha(ROOT/relative)!=sha:raise RuntimeError('Source skill differs from main: '+relative)
    path=output/'merged-main-skills.json'
    if path.exists() and json.loads(path.read_text())!=value:raise RuntimeError('Expected-main manifest changed; use fresh root')
    if not path.exists():write(path,value)
    os.environ['AGENT_TOOLS_EVAL_EXPECTED_SKILLS']=str(path)
    return value


def path_for(key):
    if key=='@codex_binary':
        import shutil
        return Path(shutil.which('codex')).resolve()
    if key.startswith(('@codex_binary:','@cli_asset:','@expected_skills:')):return Path(key.split(':',1)[1])
    if key.startswith('@mechanisms/'):return HERE.parent/'skill-suite-mechanisms'/key.split('/',1)[1]
    return ROOT/key


class FrozenBatch:
    """Identical manifest values, full byte verification at boundaries, stat checks between."""
    def __init__(self,output,main_commit):
        self.output=output;self.original_field_manifest=field.manifest;expected=expected_manifest(output,main_commit)
        self.matrix=matrix.ensure_manifest(output/'matrix','plan')
        self.field=field.freeze(output/'field',True)
        sources={str(path_for(k)):v for k,v in self.matrix['frozen_files'].items()}
        for key,sha in self.field['sources'].items():
            path=str(path_for(key))
            if path in sources and sources[path]!=sha:raise RuntimeError('Conflicting source manifest')
            sources[path]=sha
        for path in HERE.glob('*'):
            if path.is_file():sources[str(path)]=matrix.sha(path)
        value={'main_commit':expected['main_commit'],'eval_commit':git('rev-parse','HEAD').decode().strip(),
               'subjects':400,'matrix_cases':19,'field_cases':6,'models':list(matrix.MODELS),
               'matrix_manifest':digest(self.matrix),'field_manifest':digest(self.field),'sources':sources,
               'case_hashes':{suite:{c['id']:digest(c) for c in matrix.dataset(suite)} for suite in matrix.SUITES},
               'field_case_hashes':{c['id']:digest(c) for c in field.cases()},
               'grading_policy':'Unchanged final H01/H03/H08/H09 and mechanism corrections; fixed6.1 medium300. No inherited sample-specific findings.'}
        path=output/'regression-manifest.json'
        if path.exists() and json.loads(path.read_text())!=value:raise RuntimeError('Regression version changed; use fresh root')
        if not path.exists():write(path,value)
        self.manifest=value;self.sources=sources;self.baseline=self.stats()
        self.verify('before_batch')
        # These return the exact same serialized content as the original implementations.
        matrix.verify_frozen=lambda manifest:self.check_stats()
        def cached_field():self.check_stats();return copy.deepcopy(self.field)
        field.manifest=cached_field

    def stats(self):
        return {p:(Path(p).stat().st_ino,Path(p).stat().st_size,Path(p).stat().st_mtime_ns,Path(p).stat().st_ctime_ns) for p in self.sources}

    def check_stats(self):
        if self.stats()!=self.baseline:self.invalidate('stat drift')

    def invalidate(self,reason):
        write(self.output/'INVALIDATED.json',{'reason':reason,'scope':'all outputs in this regression batch'})
        raise RuntimeError('Regression source drift: '+reason)

    def verify(self,label):
        if digest(matrix.freeze_sources())!=digest(self.matrix['frozen_files']):self.invalidate('matrix source inventory')
        if digest(self.original_field_manifest())!=digest(self.field):self.invalidate('field source inventory')
        for path,sha in self.sources.items():
            if not Path(path).is_file() or matrix.sha(path)!=sha:self.invalidate(path)
        self.check_stats()
        path=self.output/'verification.json';rows=json.loads(path.read_text()) if path.exists() else []
        rows.append({'label':label,'time':time.time(),'regression_manifest_sha256':digest(self.manifest)})
        write(path,rows)


def selected_trials(output):
    result={}
    for model in matrix.MODELS:
        for suite in matrix.SUITES:
            for (cid,arm,rep),(path,raw) in field.latest(output/'matrix'/model/suite/'runs').items():result[(model,suite,cid,arm,rep)]=(path,raw)
        for (cid,arm,rep),(path,raw) in field.latest(output/'field'/model/'runs').items():result[(model,'field',cid,arm,rep)]=(path,raw)
    return result


def retry_class(raw):
    if raw.get('status')=='ok':return 'complete'
    if raw.get('error')=='timeout':return 'budget_timeout'
    events=[e for e in raw.get('events',[]) if e.get('type') in ('error','turn.failed')]
    text=json.dumps(events).lower()
    if raw.get('error')=='cli_execution' and 'selected model is at capacity' in text:return 'serving_capacity'
    if raw.get('error')=='cli_execution' and any(t in text for t in ['workspace routing discovery failed','tls handshake','error sending request','connection failed','network']):return 'transport_interruption'
    return 'unclassified_infrastructure'


def run(output,batch,workers,retries):
    groups=[]
    for suite in [*matrix.SUITES,'field']:
        cases=field.cases() if suite=='field' else matrix.dataset(suite)
        for index,case in enumerate(cases):
            models=list(matrix.MODELS);models=models[index%4:]+models[:index%4]
            groups.extend((model,suite,case['id']) for model in models)
    by_id={c['id']:c for c in field.cases()}
    prior=selected_trials(output)
    for round_id in range(retries+1):
        pending=[];unclassified=[]
        for group in groups:
            records=[prior.get((*group,arm,rep)) for arm in ('control','skills') for rep in (1,2)]
            classes=[retry_class(r[1]) if r else 'missing' for r in records]
            if 'unclassified_infrastructure' in classes:unclassified.append(group)
            elif any(c not in ('complete','budget_timeout') for c in classes):pending.append(group)
        if unclassified:raise RuntimeError('Review failed trials before replay: '+repr(unclassified))
        if not pending:break
        def job(key):
            batch.check_stats();model,suite,cid=key
            if suite=='field':return field.run_pair(by_id[cid],model,output/'field',True)
            return matrix.run_case_job(output/'matrix',suite,model,cid)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures={pool.submit(job,key):key for key in pending}
            errors=[]
            for future in concurrent.futures.as_completed(futures):
                try:future.result()
                except Exception as exc:errors.append({'group':futures[future],'error':str(exc)})
        batch.verify('after_run_round_'+str(round_id))
        prior=selected_trials(output)
        write(output/f'run-round-{round_id}.json',{'exceptions':errors,'trials':[{'key':key,'classification':retry_class(raw),'path':str(path)} for key,(path,raw) in prior.items()]})
        if errors:raise RuntimeError('Run infrastructure exception: '+repr(errors))
        if round_id<retries:time.sleep(10)
    terminal=len(prior)==400 and all(retry_class(r) in ('complete','budget_timeout') for p,r in prior.values())
    return not terminal


def score(output,batch,workers):
    def job(key):
        model,suite=key;batch.check_stats()
        return matrix.run_logged(matrix.stage_command('score',suite,model,output/'matrix'),output/'matrix'/model/suite/'logs'/'regression-score.log')
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        codes=list(pool.map(job,[(m,s) for m in matrix.MODELS for s in matrix.SUITES]))
    # Matrix score returns 1 for terminal subject timeouts as well; preserve those outcomes.
    by_id={c['id']:c for c in field.cases()};errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs=[]
        for (model,suite,cid,arm,rep),(path,raw) in selected_trials(output).items():
            if suite=='field' and raw['status']=='ok':jobs.append(pool.submit(field.score_one,by_id[cid],path,raw,output/'field'/model/'scored'))
        for future in concurrent.futures.as_completed(jobs):
            try:future.result()
            except Exception as exc:errors.append(str(exc))
    grading_errors=[]
    for model in matrix.MODELS:
        for suite in matrix.SUITES:
            path=output/'matrix'/model/suite/'scored/index.json'
            if not path.exists():grading_errors.append({'model':model,'suite':suite,'error':'missing score index'});continue
            grading_errors.extend(e for e in json.loads(path.read_text()).get('errors',[]) if e.get('failure_class')!='execution')
    write(output/'score-status.json',{'matrix_exit_codes':codes,'matrix_grading_errors':grading_errors,'field_errors':errors})
    return bool(errors or grading_errors)


def report(output,batch,workers):
    def job(key):
        model,suite=key;batch.check_stats()
        code=matrix.run_logged(matrix.stage_command('report',suite,model,output/'matrix'),output/'matrix'/model/suite/'logs'/'regression-report.log')
        matrix.refresh_report_model_text(output/'matrix',model,suite)
        return code
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:codes=list(pool.map(job,[(m,s) for m in matrix.MODELS for s in matrix.SUITES]))
    field_code=field.report(output/'field',field.cases(),field.MODELS)
    summaries={m:{s:json.loads((output/'matrix'/m/s/'report/summary.json').read_text()) for s in matrix.SUITES} for m in matrix.MODELS}
    pending=[dict(model=m,suite=s,**row) for m,ss in summaries.items() for s,summary in ss.items() for row in summary.get('pending',[]) if row.get('reason')!='execution error: timeout']
    records=selected_trials(output)
    if len(records)!=400:pending.append({'reason':'expected400trialslots','actual':len(records)})
    write(output/'structural-results.json',{'main_commit':batch.manifest['main_commit'],'eval_commit':batch.manifest['eval_commit'],
        'matrix_reports':summaries,'field_report':json.loads((output/'field/report.json').read_text()),
        'limits':'Separate per-case/model outcomes. No old sample-specific conclusions imported. Read observations are diagnostic; inspect structural eligibility independently.',
        'matrix_report_exit_codes':codes,'field_report_exit':field_code,'incomplete':pending})
    return bool(field_code or pending)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['plan','calibrate','run','score','report'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--main-commit',required=True)
    parser.add_argument('--workers',type=int,default=6);parser.add_argument('--infra-retries',type=int,default=2)
    args=parser.parse_args();output=args.output.resolve()
    if output.is_relative_to(ROOT):raise ValueError('Artifacts must be outside source checkout')
    if not 1<=args.workers<=6:raise ValueError('workers must be1..6')
    if git('status','--porcelain','--untracked-files=no').strip():raise RuntimeError('Commit source changes before freezing')
    output.mkdir(parents=True,exist_ok=True)
    with (output/'.regression.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        batch=FrozenBatch(output,args.main_commit)
        try:
            if args.action=='plan':return 0
            if args.action=='calibrate':return field.calibrate(output/'field',field.cases(),args.workers)
            if args.action=='run':return run(output,batch,args.workers,args.infra_retries)
            if args.action=='score':return score(output,batch,args.workers)
            return report(output,batch,args.workers)
        finally:batch.verify('after_'+args.action)

if __name__=='__main__':raise SystemExit(main())

"""Source-location follow-up; frozen mechanism isolation, no task-runtime seeding."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import uuid

IMPLEMENTATION=Path(__file__).resolve().parent
HERE=IMPLEMENTATION
ROOT=HERE.parents[1]
MECHANISMS=HERE.parent/'skill-suite-mechanisms'
CHALLENGE=HERE.parent/'skill-suite-challenge'
PILOT=HERE.parent/'skill-suite-pilot'
FROZEN_DEPENDENCIES=None

def load(path,label):
    spec=importlib.util.spec_from_file_location(label+'_'+uuid.uuid4().hex,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

mechanism=load(MECHANISMS/'run_mechanisms.py','source_mechanism')
mechanism.HERE=HERE
write_json=mechanism.write_json
snapshot=mechanism.snapshot
run_check=mechanism.run_check
skill_plan=mechanism.skill_plan
observed_target_read=mechanism.observed_target_read

def immutable_dependencies():
    return [*IMPLEMENTATION.glob('*.py'),*MECHANISMS.glob('*.py'),CHALLENGE/'run_challenge.py',CHALLENGE/'grade_challenge.py',CHALLENGE/'score_challenge.py',CHALLENGE/'report_challenge.py',PILOT/'run_eval.py',PILOT/'grade_eval.py']

_original_factory=mechanism.module_for_run

def module_for_run():
    module=_original_factory();original=module.source_manifest
    def sources(case,variant):
        result=original(case,variant)
        for path in immutable_dependencies():result['@frozen/'+str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
        return result
    module.source_manifest=sources
    return module

mechanism.module_for_run=module_for_run

def source_manifest(case,variant):return module_for_run().source_manifest(case,variant)

def source_read_observation(case,events):
    files=case.get('fixtures',{}).get('files',{})
    paths=['cleanup.py'] if 'cleanup.py' in files else [p for p in ('learning-record.json','copy_example.py') if p in files]
    outputs=[(e.get('item',{}).get('id'),e.get('item',{}).get('aggregated_output','')) for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='command_execution']
    joined='\n'.join(text for _,text in outputs);observations={}
    for path in paths:
        anchors=[line.strip() for line in files[path].splitlines() if len(line.strip())>=8]
        observed=bool(anchors) and all(anchor in joined for anchor in anchors)
        ids=[eid for eid,text in outputs if any(anchor in text for anchor in anchors)] if observed else []
        observations[path]={'status':'source_content_observed' if observed else 'not_observed','event_ids':ids}
    all_observed=bool(observations) and all(o['status']=='source_content_observed' for o in observations.values())
    return {'status':'declared_sources_observed' if all_observed else 'not_fully_observed','files':observations,'limitation':'Distinct source lines observed in actual tool output across commands; command name alone is insufficient. Equivalent transformed reads may require trajectory review. Diagnostic evidence, not a new primary grading requirement.'}

def run_case(case,variant,rep,output,model,timeout=300,effort='medium'):
    if FROZEN_DEPENDENCIES is not None:
        for path,sha in FROZEN_DEPENDENCIES.items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise RuntimeError('Frozen dependency changed: '+path)
    if case.get('execution',{}).get('runtime_setup'):raise ValueError('Source-discovery follow-up has no runtime intervention')
    result=mechanism.run_case(case,variant,rep,output,model,timeout,effort)
    result['source_read_observation']=source_read_observation(case,result['events'])
    write_json(Path(result['workspace']).parent/'result.json',result)
    return result

def configure(directory):
    """Optional same-schema follow-up directory, e.g. artifact-scope A01/A02."""
    global HERE
    HERE=Path(directory).resolve();mechanism.HERE=HERE

if __name__=='__main__':
    FROZEN_DEPENDENCIES={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in immutable_dependencies()}
    driver=load(CHALLENGE/'run_challenge.py','source_driver');driver.HERE=HERE;driver.runner=sys.modules[__name__]
    raise SystemExit(driver.main())

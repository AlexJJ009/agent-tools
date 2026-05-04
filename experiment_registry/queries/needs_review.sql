select
  'eval_run' as entity,
  er.id,
  p.name as project,
  e.experiment_key,
  er.eval_name,
  er.trust_level,
  er.trust_reason,
  er.raw_metrics_path as source_path
from eval_runs er
join experiments e on e.id = er.experiment_id
join projects p on p.id = e.project_id
where er.trust_level in ('buggy', 'superseded', 'needs_review', 'usable_with_caution')
union all
select
  'experiment',
  e.id,
  p.name,
  e.experiment_key,
  e.display_name,
  e.trust_level,
  e.trust_reason,
  null
from experiments e
join projects p on p.id = e.project_id
where e.trust_level in ('buggy', 'superseded', 'needs_review', 'usable_with_caution')
order by project, trust_level, experiment_key;

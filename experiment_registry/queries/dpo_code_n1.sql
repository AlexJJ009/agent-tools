select
  e.experiment_key,
  m.display_name as model,
  d.name as dataset,
  em.metric_name,
  round(em.metric_value, 6) as value,
  er.n,
  er.temperature,
  er.trust_level,
  er.trust_reason,
  er.raw_metrics_path
from eval_metrics em
join eval_runs er on er.id = em.eval_run_id
join models m on m.id = er.model_id
join experiments e on e.id = er.experiment_id
left join datasets d on d.id = em.dataset_id
where e.project_id = (select id from projects where name = 'dpo')
  and er.domain = 'code'
  and er.n = 1
  and er.temperature = 0.0
  and em.metric_name in ('pass@1', 'mean@1', 'acc', 'pass_at_k')
order by e.experiment_key, d.name, em.metric_name;

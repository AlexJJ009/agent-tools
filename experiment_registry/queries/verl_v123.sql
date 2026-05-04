select
  e.method_version,
  e.method_variant,
  e.display_name,
  m.display_name as model,
  d.name as dataset,
  er.n,
  er.temperature,
  max(case when em.metric_name like 'mean@%' then em.metric_value end) as mean_value,
  max(case when em.metric_name like 'pass@%' then em.metric_value end) as pass_value,
  max(case when em.metric_name = 'extraction_fail' then em.metric_value end) as extraction_fail,
  er.trust_level,
  er.trust_reason,
  er.raw_metrics_path
from experiments e
left join eval_runs er on er.experiment_id = e.id
left join models m on m.id = er.model_id
left join eval_metrics em on em.eval_run_id = er.id
left join datasets d on d.id = em.dataset_id
where e.project_id = (select id from projects where name = 'verl')
  and e.experiment_key like 'verl.sft.math.qwen3_4b.%'
  and (d.name = 'HuggingFaceH4/MATH-500' or d.name is null)
group by e.id, er.id, d.id
order by e.method_version, mean_value desc;

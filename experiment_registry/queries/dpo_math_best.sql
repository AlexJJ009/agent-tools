select
  e.experiment_key,
  m.display_name as model,
  d.name as dataset,
  er.n,
  er.temperature,
  er.top_p,
  er.max_tokens,
  max(case when em.metric_name like 'mean@%' then em.metric_value end) as mean_value,
  max(case when em.metric_name like 'pass@%' then em.metric_value end) as pass_value,
  max(case when em.metric_name = 'extraction_fail' then em.metric_value end) as extraction_fail,
  er.trust_level,
  er.raw_metrics_path
from eval_runs er
join experiments e on e.id = er.experiment_id
join models m on m.id = er.model_id
join eval_metrics em on em.eval_run_id = er.id
left join datasets d on d.id = em.dataset_id
where e.project_id = (select id from projects where name = 'dpo')
  and er.domain = 'math'
  and d.name in ('HuggingFaceH4/MATH-500', 'zwhe99/amc23', 'aime25', 'openai/gsm8k', 'mwpt5/MAWPS', 'ChilleD/SVAMP')
group by e.experiment_key, m.display_name, d.name, er.id
order by d.name, mean_value desc;

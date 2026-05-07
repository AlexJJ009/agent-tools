select
  e.experiment_key,
  m.model_path,
  tr.raw_summary_path as training_source,
  ds_train.path as training_data,
  tr.beta,
  tr.learning_rate,
  tr.total_steps,
  em.metric_name,
  em.metric_value,
  er.output_dir as eval_output_dir,
  er.raw_metrics_path as eval_source,
  er.trust_level
from eval_metrics em
join eval_runs er on er.id = em.eval_run_id
join models m on m.id = er.model_id
join experiments e on e.id = er.experiment_id
left join training_runs tr on tr.experiment_id = e.id
left join datasets ds_train on ds_train.id = tr.train_dataset_id
left join datasets d on d.id = em.dataset_id
where e.project_id = (select id from projects where name = 'dpo')
  and d.name = 'BigCodeBench'
  and er.n = 1
  and er.temperature = 0.0
  and er.trust_level in ('trusted', 'usable_with_caution')
  and em.metric_name in ('pass_at_k', 'mean@1', 'acc')
order by em.metric_value desc
limit 5;

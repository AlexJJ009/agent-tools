pragma foreign_keys = on;

create table if not exists projects (
  id integer primary key,
  project_key text unique,
  name text not null unique,
  repo_path text,
  default_branch text,
  framework_default text,
  remote_url text,
  notes text
);

create table if not exists experiments (
  id integer primary key,
  project_id integer not null references projects(id),
  experiment_key text not null unique,
  display_name text not null,
  method text,
  method_family text,
  method_variant text,
  method_version text,
  domain text,
  variant text,
  status text,
  trust_level text,
  trust_reason text,
  parent_experiment_id integer references experiments(id),
  git_branch text,
  git_commit text,
  created_at text,
  updated_at text,
  extra_json text,
  notes text
);

create table if not exists experiment_links (
  id integer primary key,
  from_experiment_id integer not null references experiments(id),
  to_experiment_id integer not null references experiments(id),
  link_type text not null,
  notes text,
  unique(from_experiment_id, to_experiment_id, link_type)
);

create table if not exists models (
  id integer primary key,
  model_key text not null unique,
  display_name text,
  base_model text,
  model_path text not null,
  checkpoint_step integer,
  global_step integer,
  epoch real,
  checkpoint_kind text,
  model_role text,
  parent_model_id integer references models(id),
  is_best integer,
  is_latest integer,
  selection_metric_name text,
  selection_metric_value real,
  project_id integer references projects(id),
  git_branch text,
  git_commit text,
  extra_json text,
  notes text
);

create table if not exists datasets (
  id integer primary key,
  dataset_key text not null unique,
  name text not null,
  domain text,
  path text,
  split text,
  subset text,
  dataset_version text,
  fingerprint text,
  format text,
  source_uri text,
  row_count integer,
  extra_json text,
  notes text
);

create table if not exists training_runs (
  id integer primary key,
  training_run_key text not null unique,
  experiment_id integer not null references experiments(id),
  input_model_id integer references models(id),
  output_model_id integer references models(id),
  train_dataset_id integer references datasets(id),
  method text,
  framework text,
  framework_version text,
  beta real,
  learning_rate real,
  num_epochs real,
  per_device_batch_size integer,
  gradient_accumulation_steps integer,
  effective_batch_size integer,
  max_length integer,
  warmup_ratio real,
  weight_decay real,
  lr_scheduler text,
  distributed_backend text,
  distributed_config_json text,
  hyperparams_json text,
  num_gpus integer,
  runtime_seconds real,
  total_steps integer,
  final_train_loss real,
  final_step_loss real,
  first_step_loss real,
  first_step_margin real,
  final_step_margin real,
  final_rewards_chosen real,
  final_rewards_rejected real,
  raw_summary_path text,
  tb_path text,
  wandb_run text,
  git_branch text,
  git_commit text,
  extra_json text,
  notes text,
  unique(experiment_id, raw_summary_path)
);

create table if not exists training_run_datasets (
  id integer primary key,
  training_run_id integer not null references training_runs(id),
  dataset_id integer not null references datasets(id),
  role text,
  row_count integer,
  notes text,
  unique(training_run_id, dataset_id, role)
);

create table if not exists training_metrics (
  id integer primary key,
  training_run_id integer not null references training_runs(id),
  metric_name text not null,
  metric_value real,
  step integer,
  metric_scope text,
  notes text,
  unique(training_run_id, metric_name, step, metric_scope)
);

create table if not exists eval_runs (
  id integer primary key,
  eval_run_key text not null unique,
  experiment_id integer references experiments(id),
  model_id integer not null references models(id),
  eval_name text not null,
  domain text,
  script_path text,
  script_version text,
  parser_version text,
  eval_harness text,
  framework text,
  output_dir text,
  raw_metrics_path text,
  raw_samples_path text,
  n integer,
  num_samples integer,
  repeat_count integer,
  temperature real,
  top_p real,
  top_k integer,
  min_p real,
  do_sample integer,
  max_tokens integer,
  max_prompt_tokens integer,
  max_new_tokens integer,
  seed integer,
  timeout_seconds real,
  thinking integer,
  enable_thinking integer,
  prompt_mode text,
  chat_template text,
  system_prompt_key text,
  preamble_mode text,
  command text,
  cwd text,
  hostname text,
  git_branch text,
  git_commit text,
  eval_datetime text,
  trust_level text,
  trust_reason text,
  supersedes_eval_run_id integer references eval_runs(id),
  extra_json text,
  notes text,
  unique(model_id, eval_name, raw_metrics_path)
);

create table if not exists eval_run_links (
  id integer primary key,
  from_eval_run_id integer not null references eval_runs(id),
  to_eval_run_id integer not null references eval_runs(id),
  link_type text not null,
  reason text,
  notes text,
  unique(from_eval_run_id, to_eval_run_id, link_type)
);

create table if not exists eval_run_datasets (
  id integer primary key,
  eval_run_id integer not null references eval_runs(id),
  dataset_id integer not null references datasets(id),
  split text,
  subset text,
  num_examples integer,
  orig_total integer,
  notes text,
  unique(eval_run_id, dataset_id, split, subset)
);

create table if not exists eval_metrics (
  id integer primary key,
  eval_run_id integer not null references eval_runs(id),
  dataset_id integer references datasets(id),
  metric_name text not null,
  metric_value real,
  value_text text,
  value_type text,
  numerator real,
  denominator real,
  metric_scope text,
  metric_params_json text,
  higher_is_better integer,
  metric_unit text,
  aggregation text,
  notes text,
  unique(eval_run_id, dataset_id, metric_name, metric_scope)
);

create table if not exists artifacts (
  id integer primary key,
  artifact_key text unique,
  experiment_id integer references experiments(id),
  training_run_id integer references training_runs(id),
  eval_run_id integer references eval_runs(id),
  model_id integer references models(id),
  artifact_kind text not null,
  path text not null,
  description text,
  sha256 text,
  exists_checked_at text,
  artifact_exists integer,
  size_bytes integer,
  mtime text,
  notes text
);

create table if not exists source_records (
  id integer primary key,
  source_path text not null,
  source_uri text,
  source_type text,
  source_section text,
  source_mtime text,
  source_size integer,
  source_sha256 text,
  content_hash text,
  imported_at text,
  importer text,
  extractor_version text,
  record_kind text,
  record_id integer,
  entity_table text,
  entity_key text,
  notes text,
  unique(importer, source_path, source_section, record_kind, entity_key)
);

create table if not exists entity_tags (
  id integer primary key,
  entity_type text not null,
  entity_id integer not null,
  tag text not null,
  unique(entity_type, entity_id, tag)
);

create table if not exists quality_flags (
  id integer primary key,
  entity_type text not null,
  entity_id integer not null,
  flag text not null,
  severity text,
  reason text,
  source_record_id integer references source_records(id),
  notes text,
  unique(entity_type, entity_id, flag)
);

create table if not exists validation_checks (
  id integer primary key,
  check_name text not null,
  source_path text,
  source_value text,
  database_value text,
  passed integer not null,
  checked_at text not null,
  notes text
);

create index if not exists idx_experiments_method_domain on experiments(method, domain);
create index if not exists idx_models_path on models(model_path);
create index if not exists idx_eval_runs_model_params on eval_runs(model_id, n, temperature);
create index if not exists idx_eval_runs_domain_trust on eval_runs(domain, trust_level);
create index if not exists idx_eval_metrics_lookup on eval_metrics(metric_name, metric_value);
create index if not exists idx_datasets_key on datasets(dataset_key);
create index if not exists idx_source_records_path on source_records(source_path);
create index if not exists idx_experiment_links_src_dst on experiment_links(from_experiment_id, to_experiment_id);
create index if not exists idx_eval_run_links_src_dst on eval_run_links(from_eval_run_id, to_eval_run_id);
create index if not exists idx_source_records_entity on source_records(entity_table, entity_key);
create index if not exists idx_training_runs_key on training_runs(training_run_key);
create index if not exists idx_eval_runs_key on eval_runs(eval_run_key);
create index if not exists idx_metrics_eval_dataset_name on eval_metrics(eval_run_id, dataset_id, metric_name);
create index if not exists idx_quality_flags_flag on quality_flags(flag);
create unique index if not exists idx_artifacts_unique_key on artifacts(artifact_kind, path, coalesce(experiment_id, -1), coalesce(training_run_id, -1), coalesce(eval_run_id, -1), coalesce(model_id, -1));

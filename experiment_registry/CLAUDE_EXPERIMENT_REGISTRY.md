# Claude Code Experiment Registry Instructions

Use the same workflow as the Codex skill at
`experiment_registry/skills/experiment-registry/SKILL.md`.

Default database:

```bash
/data-1/experiment_registry/experiment_registry.sqlite
```

Default tooling:

```bash
/data-1/agent-tools/experiment_registry
```

Fallback tooling:

```bash
/data-1/dpo-experiment/experiment_registry
```

Prefer canned read-only queries from `registry_cli.py`. Import with
`import_dpo.py` and `import_verl.py`. Validate with `validate_imports.py`.
Never delete or rewrite original experiment markdown, JSON, logs, checkpoints,
or model weights.

# System Documentation

Use the guides below for implemented behavior. Repository code and its current
usage/interface documentation describe the system; task PRDs, checklists and
private reports describe bounded development work and are not deployment proof.

- [Agent workflow](AGENT_WORKFLOW.md): development agreements, readback and acceptance.
- [Learning workflow runtime](learning-workflow-migration/RUNTIME.md): activity routing and scoped actions.
- [Learning workflow installation](learning-workflow-migration/INSTALL.md): local Codex installation and rollback.
- [Work Report timer](WORK_REPORT_LIGHT_TIMER.md): timed prompts and their delivery limits.
- [CLI server bootstrap](CLI_SERVER_BOOTSTRAP.md): server setup.
- [Repository overview](../README.md): other maintained tools and platform guides.

Private development material belongs in ignored `docs/_local/`, created only
when needed: `tasks/<task-id>/`, `reports/<task-id>/`, or `scratch/<task-id>/`.
Existing task identifiers and agreements remain valid. A handoff records the
recovery point and links these guides; it does not maintain a second user manual.

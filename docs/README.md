# System Documentation

Use the guides below for implemented behavior. Repository code and its current
usage/interface documentation describe the system; task PRDs, checklists and
private reports describe bounded development work and are not deployment proof.

- [Task runtime](TASK_RUNTIME.md): local task state, checklist queries, continuation and owned-artifact closeout.
- [Agent workflow](AGENT_WORKFLOW.md): development agreements, readback and acceptance.
- [Learning workflow runtime](LEARNING_WORKFLOW.md): activity routing and scoped actions.
- [Learning workflow installation](LEARNING_WORKFLOW_INSTALL.md): local Codex installation and rollback.
- [Architecture decisions](decisions/README.md): adopted choices and their reasons.
- [Linear workflow](linear-workflow/README.md): shared runtime and explicit dispatch boundaries.
- [Work Report timer](WORK_REPORT_LIGHT_TIMER.md): timed prompts and their delivery limits.
- [CLI server bootstrap](CLI_SERVER_BOOTSTRAP.md): server setup.
- [Repository overview](../README.md): other maintained tools and platform guides.

## Documentation Responsibilities

The two README files serve different entry points; neither is a second progress
register. The [repository README](../README.md) introduces the tools, file map
and setup entry points. Its existing context-sync usage reference remains the
maintained guide for that component. This README is the navigation index for
current component guides and architectural decisions; it does not repeat their
commands, behavior descriptions or decision status.

| Material | Maintained responsibility | Update when |
|---|---|---|
| Root `README.md` | Repository purpose, tool inventory, setup entry points, and the existing context-sync usage reference | Repository entry points or that component's usage change |
| `docs/README.md` | Links to current system guides and decisions | A guide is added, moved, replaced, or its responsibility changes |
| Component guides | Implemented usage, interfaces, operational steps and limitations | The corresponding behavior changes |
| `docs/decisions/NNNN-*.md` | Significant adopted choices, context, reasons and consequences | A material decision is adopted or superseded |
| Ignored `docs/_local/` | Task-specific requirements, one execution checklist, recovery points and private evidence | That task progresses or its agreement changes |

Keep each detailed fact in one maintained source and link to it from the entry
points. A component guide's ordinary edit does not require rewriting both
README files. Keep release/deployment claims tied to actual verification;
source implementation and historical acceptance do not establish installation
on another host. This division clarifies [ADR 0001](decisions/0001-local-development-records.md)
and does not create a new document pack or ADR for every documentation edit.

Task Runtime stores its state and managed artifacts in the configured application
data root; see its guide above. Existing explicit local records remain valid.
Private development material outside that runtime belongs in ignored `docs/_local/`,
created only when needed: `tasks/<task-id>/`, `reports/<task-id>/`, or `scratch/<task-id>/`.
Existing task identifiers and agreements remain valid. A handoff records the
recovery point and links these guides; it does not maintain a second user manual.

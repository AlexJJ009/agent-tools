# System Documentation

Use the guides below for implemented behavior. Repository code and its current
usage/interface documentation describe the system; task PRDs, checklists and
private reports describe bounded development work and are not deployment proof.

- [Task runtime](TASK_RUNTIME.md): local task state, checklist/history queries, scoped material cleanup and recovery.
- [Agent workflow](AGENT_WORKFLOW.md): development agreements, readback and acceptance.
- [Project evaluation skills](PROJECT_EVAL_SKILLS.md): project-local build-eval and hillclimb using Codex subscription execution.
- [Learning workflow runtime](LEARNING_WORKFLOW.md): activity routing and scoped actions.
- [Learning workflow installation](LEARNING_WORKFLOW_INSTALL.md): local Codex installation and rollback.
- [Architecture decisions](decisions/README.md): adopted choices and their reasons.
- [Linear workflow (retired)](linear-workflow/README.md): disabled historical source and compatibility notes.
- [Work Report](WORK_REPORT.md): report generation, delivery contracts and installation.
- [Work Report timer](WORK_REPORT_LIGHT_TIMER.md): timed prompts and their delivery limits.
- [CLI server bootstrap](CLI_SERVER_BOOTSTRAP.md): server setup.
- [Claude Code adapter](CLAUDE_CODE_ADAPTER.md): shared context, skill links and native hooks on Linux/WSL.
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
on another host. This division does not create a new document pack or ADR for every
documentation edit.

Task Runtime stores its state and managed artifacts in the configured application
data root; see its guide above and [ADR 0004](decisions/0004-task-runtime-application-storage.md).
That decision also records the boundary for scoped process-material retirement.
Existing explicit local records remain valid.
Private development material outside that runtime belongs in ignored `docs/_local/`,
created only when needed: `tasks/<task-id>/`, `reports/<task-id>/`, or `scratch/<task-id>/`.
Existing task identifiers and agreements remain valid. A handoff records the
recovery point and links these guides; it does not maintain a second user manual.

## Survey retention

Always preserve the latest finalized survey for each subject owned by this
project, including its necessary source provenance. Surveys are dated learning
material, not current operating instructions. Keep the previous final until a
replacement is finalized; older versions can retire after unique annotations,
citations and evidence are accounted for. File extension and report-directory
placement do not determine whether a document is disposable. No duplicate
Markdown/PDF export or extra index is required solely for retention.

Surveys owned outside this project remain with their owner. Assess both the
survey itself and cited learning material for Zotero retention; ReadPapers owns
library lookup, deduplication and authorized import. A Zotero copy does not
replace the project's retained final survey. Preserve a sole attachment until
any selected transfer is confirmed. Cleaner applies these boundaries during
scoped cleanup; lack of learning value does not override code, test, license,
ADR, user-retention, evidence or recovery dependencies.

If inspection leaves a material deletion decision uncertain, Cleaner presents
specific candidates, the uncertainty and recommended dispositions to the user.
Those items remain until answered; clear authorized cleanup can continue.
Existing user decisions do not require repeated confirmation.

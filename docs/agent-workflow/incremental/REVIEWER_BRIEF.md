# Independent implementation review

Read the approved PRD and the acceptance plan before reviewing this increment. Review the actual candidate diff and receipts; report concrete failures against the approved behaviors. The implementing agent does not author the verdict.

## Context index

- `acceptance-plan.md`: frozen acceptance outcomes, controls and evidence requirements.
- `migration-parity.md`: retained legacy rules and deliberate changes.
- `agent_workflow/`: canonical state, verification, managed execution and host handler.
- `skills/work-report/references/writing-contract.md`: shared expression contract.
- `skills/work-report/references/judge.md`: two-stage report review, separate from code acceptance.
- `scripts/install_agent_workflow.py`, `scripts/install_agent_workflow_hooks.py`: portable install and explicit adapter activation.
- `.github/workflows/linear-workflow-runtime.yml`: repository CI.

## Required dimensions

Check event retry/conflict/partial-write recovery, stale evidence and input races, direct/terminal/queued entry parity, scoped understanding and explicit delegation, user feedback provenance and legacy migration, real native Hook coverage, report-state freshness, English rule parity, source relocation and foreign Hook preservation. Inspect semantic discovery and cold-read outcomes independently from unit tests. Do not infer user acceptance from technical success.

## Verdict

Record reviewed SHA, reviewer task/model/effort, tests inspected or run, findings with severity/path/impact, resolutions and PASS/REVISION_REQUIRED. Repeat after fixes until the latest review has no new blocking findings. Preserve each round under docs/reviews/; do not edit another reviewer's earlier testimony. Human merge authority remains with the user.

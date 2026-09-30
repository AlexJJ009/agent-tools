# Work Report

Work Report produces requested local Markdown progress and final reports. It
explains the goal, current result, important decisions, evidence, scope changes
and next action for a reader without the conversation history. A report passing
review does not establish functional completion or user acceptance.

The maintained operating instructions are the [Work Report skill](../skills/work-report/SKILL.md),
its [runtime reference](../skills/work-report/references/runtime.md) and
[writing contract](../skills/work-report/references/writing-contract.md).
Historical research, installation receipts and acceptance campaigns are not
current deployment guarantees.

## Choose a reporting mode

| Request | Behavior |
| --- | --- |
| Immediate standalone report | Generate and deliver the requested report; registration is unnecessary. |
| Interim report followed by continued work | Register the independently judged interim intent, initialize a fresh progress batch, deliver in commentary, and perform the original task's next action in the same turn. |
| Report before this turn ends | Register an explicit `on_end` agreement; the next normal Stop checks for a valid receipt. |
| Report after a future business milestone | Record `deferred`; preserve the milestone in the original task state. There is no automatic business-completion detector. |
| Timed prompt in the original conversation | Use the [lightweight timer](../skills/work-report/references/timer.md); enqueue success does not prove report generation or immediate arrival. |
| Existing legacy interval agreement | Continue its registered runtime and cron adapter; use one scheduling backend per agreement. |

Ordinary questions, short status checks, quoted historical requirements and work
on the reporting implementation do not create reporting obligations. A final
report may truthfully describe incomplete work; its filename does not close the
underlying task. Later questions are answered in conversation unless another
report is requested.

## Install and inspect

From this checkout, for the current Linux/WSL user:

```bash
python3 scripts/install_work_report.py
python3 scripts/install_work_report.py --check
python3 scripts/install_work_report_hooks.py
python3 scripts/install_work_report_hooks.py --check
```

The dedicated installers run the target-profile guard. The skill installer uses
`uv` for isolated script dependencies, installs to
`~/.agents/skills/work-report`, and links the Claude skill entry to that copy.
It rejects conflicting unmanaged locations and rolls back failed publication
checks. It does not change the business project's Python environment.

The Hook installer merges five managed handlers into `~/.codex/hooks.json`,
preserving other handlers and leaving model, authentication, CC Switch and Hook
trust state unchanged. Review and trust the definitions through native `/hooks`.
Definition checks do not prove activation; verify the active handlers in the
client that will run the task. Remove only these handlers with
`python3 scripts/install_work_report_hooks.py --remove`.

These installers support Linux/WSL, not native Windows. Claude can share the
report-generation skill; this package does not install Claude lifecycle hooks.
Installation on one host does not validate another host or update instructions
already loaded into an existing conversation. No current local or remote
deployment status is implied by this guide.

## Generate and deliver

Use `uv run --script skills/work-report/scripts/report_tool.py --help` for the
command interface. The reporting sequence is:

1. Preserve the relevant original request, existing task state and revisions.
   Initialize with `init --workspace <absolute-project> --title <topic>
   --request <request-file> --kind progress` (or `final`). Reuse `--task-dir`
   for the same agreement, `--state` for an existing working state, and
   `--workflow-record` when an applicable canonical record exists.
2. Write the generated report with its frontmatter and six semantic section IDs:
   `goal`, `progress`, `decisions`, `evidence`, `scope`, `next_steps`. Explain
   what evidence proves and what remains unknown; do not reconstruct unrecorded
   decision reasons as historical facts.
3. Run `check --report <report.md> --task <task-id> --workspace <project>`.
   Exit 0 means mechanical checks passed, 1 means unmet checks, and 2 means the
   tool could not complete. Mechanical checks cannot judge the argument.
4. Use an actual independent reviewer for an artifact-only cold read, then give
   that reviewer the frozen request, state, checks and evidence for verification.
   Save its actual outputs as `cold-read.json` and `review.json`. Follow the
   [Judge instructions](../skills/work-report/references/judge.md); changed
   content needs fresh checks and review. Allow at most two revision rounds.
5. Run `finalize` with the same report/task/workspace arguments. Only successful
   finalization creates `delivery.json`. Deliver the report link and relevant
   limitations. An interim report must be followed by actual original-task work
   in the same turn.

`--record-only` initializes registration material rather than a deliverable.
After registration, initialize a new formal batch so the snapshot is fresh.
New delivery checks bind the request, workflow snapshot, report, reviews and
evidence; an older placeholder or review file alone cannot satisfy them.
`finalize --verify-only` verifies a historical frozen report without refreshing
its delivery time. A receipt proves local delivery conditions, not that the user
read or accepted the report. If review is unavailable or remains unsuccessful,
label the result as a draft or risk snapshot and explain the limitation.

## Agreements, hooks and recovery

Registration requires an actual independent intent Judge. Preserve the original
UTF-8 request bytes, including line endings, and the real session UUID. Source
hashes and session bindings prevent a different request from clearing a pending
candidate. `none`, `needs_clarification` and `deferred` register without a report
task directory; only `confirmed` creates the formal reporting obligation.
See the [registration commands](../skills/work-report/references/runtime.md).

`UserPromptSubmit` captures possible requests; it does not make the semantic
decision. `SessionStart` and `PostToolUse` restore state or show due reminders.
`Stop` revalidates a fresh matching delivery receipt and allows bounded recovery
continuations before recording a visible failure. Interim delivery also prompts
resumption when no subsequent original-task activity is observed. `Interrupt`
cancels the session's reporting obligations and respects the user's stop.

For a recognized `<response-annotations>` JSON envelope, candidate detection
uses user annotation comments and surrounding request text, excluding selected
old-response text and source metadata. Malformed or unknown envelopes retain
conservative matching. The original prompt bytes and digest remain unchanged
for the intent Judge; candidate filtering does not decide user intent.

Registration errors do not imply delivery or erase a real Judge call. Preserve
the pending diagnostics, repair the reported cause, and continue independently
authorized work. Do not fabricate context, normalize request bytes or delete
pending state to bypass a failed registration. Without loaded and trusted hooks,
these process instructions do not provide an automatic Stop guarantee.

The legacy interval adapter is only for existing explicit interval agreements,
not the fallback for new scheduling requests. If the chosen timer or native
mechanism is unavailable, report that limitation rather than creating cron.
The retained adapter uses `scripts/install_work_report_schedule.py
--task-dir <task-dir>` after a confirmed interval registration; `--check` verifies
the registration and `--remove` removes its schedule. Cron checks each minute,
while `reporting.json` owns the actual interval. Its worker is a bounded separate
Codex process that writes this task's reports and does not resume Main or change
business code. A task lease prevents duplicate generation in the same window.
Runtime `tick` decides whether a report is due; `report_scheduler.py tick`
performs generation. Cancel the runtime obligation and remove its schedule when
the agreement ends. Timeouts, failed review and missing receipts remain failures;
a fallback risk snapshot is not a reviewed report.

Use the [timer reference](../skills/work-report/references/timer.md) for new
lightweight timed messages and [timer implementation limits](WORK_REPORT_LIGHT_TIMER.md)
for the separate timer component. Do not stack timer and cron schedules for the
same agreement. Host/process availability and actual message arrival must be
checked separately from successful enqueue or artifact generation.

## Storage and lifecycle

New report output defaults to this worktree's ignored `docs/_local/reports/`.
Reuse existing task requests and canonical state instead of creating another
PRD, checklist or global index. Existing `docs/work-reports/` agreements remain
supported. `--output-root` is for a user-specified report location, not an
automatic fallback to an experiment directory or another workspace.

Initialization validates ignored/untracked storage and configures local Git
exclusion. Report generation does not implicitly add, commit or untrack files,
or change project `.gitignore`. Preserve excluded artifacts before removing a
workspace. Export or publish a report only when requested.

Reports and intermediate material can be retired during authorized task
closeout after ownership, retention and live references are checked. Preserve
pending delivery records, referenced evidence, user-retained files and other
tasks' state. Lasting usage information belongs in maintained project guides;
reusable test inputs belong in fixtures. See [task runtime lifecycle](TASK_RUNTIME.md)
and [Cleaner closeout](../skills/cleaner/SKILL.md).

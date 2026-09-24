# Reporting runtime: end, interval and interim obligations

Use this reference for future reporting agreements, interim reports followed by
resumption, or an existing task's due/end check. An immediate standalone report
or ordinary follow-up question does not require registration.

## Register the actual agreement

1. Preserve the original user prompt. For UserPromptSubmit, read pending JSON's
   `prompt` and write its exact UTF-8 bytes; do not transcribe or normalize line
   endings. CRLF and LF have different request hashes.
2. Actually delegate the independent [intent Judge](intent-judge.md). Main's
   paraphrase is not the Judge's response. Ordinary questions and non-current
   examples do not justify initializing report directories.
3. Register `none`, `needs_clarification` or `deferred` without `--task-dir`:

```text
python3 report_runtime.py register --workspace <repo> \
  --request <request.txt> --decision <actual-intent.json> --session-id <real-UUID>
```

This validates source hash, quotations, decision shape and matching pending
input, saves processing state, and clears the candidate reminder. It creates no
report, receipt or completion claim. `deferred` preserves a future business
milestone and says automatic triggering is not configured. Keep the milestone
in the original working state and generate the report when that work actually
finishes. Clarify genuinely missing user information once; answer ordinary
questions without asking the user to approve a report.

4. Only `confirmed` uses `report_tool.py init --record-only` to create context,
   followed by register with that task directory and actual Judge JSON. Reuse the
   directory for the same agreement. For an interim request alongside a different
   active agreement, use a separate temporary task directory and `--state` to
   refer to the original working state; preserve the earlier obligation.
5. After successful registration, initialize a **new** formal report batch in
   that same task directory. A pre-registration draft or placeholder report has
   an older snapshot and cannot satisfy freshness, even for an interim report.

Default output is project `docs/work-reports/` with local Git exclusion. External
experiment/model storage is not automatically a report location. Use
`--output-root` only when the user specified a report location. Do not create a
report merely to clear a candidate or ask for approval of local ignore rules.

A registration failure does not erase an actual Judge call or imply delivery.
The runtime preserves post-validation errors in pending diagnostics. Stop gives
at most one concrete recovery notice for that error instead of repeatedly
claiming the Judge never ran. Do not monkey-patch, fabricate context, delete
state or normalize original bytes to bypass registration. Say the automatic
guarantee is not ready and continue authorized independent work.

Use the real session UUID from host context or pending JSON, never a placeholder
such as current-session. Registration rejects mismatched session/source binding.

## Timing and resumption

`on_end` means Main's next normal Stop after registration, before that turn's
final response. It does not mean the project, experiment or background jobs have
finished. Cross-turn business milestones use deferred. Do not transform later
ordinary questions into fresh reporting obligations.

`resume_after_report=true` registers one `interim` obligation requiring a
`progress` report. With no separate end/interval request use `on_end=false` and
`interval_seconds=null`. Older intent records without this field mean false.
Do not close other tasks' end or periodic agreements.

Before reporting, save the original goal, current execution point, running-job
references and concrete next action. After check, the independent two-stage
Judge and finalize, immediately send a commentary link with the finding and
resume action, then actually perform that action in the same turn. PostToolUse
prompts once when it first verifies an interim receipt; do not delay the link to
the original task's final response. A live background process alone does not
prove Main resumed.

Stop checks a fresh progress receipt. Missing receipts permit at most two
recovery attempts. Once delivery is valid but no subsequent non-report tool
activity has been observed, Stop blocks once to request resumption without
regenerating the report. This bounded reminder is not a long-running scheduler
or proof of business progress: independent acceptance must inspect the actual
follow-up action. Never manufacture unrelated tool calls to satisfy it.

Consumed interim obligations do not reopen on later Q&A or edits to an old
report. User interruption/cancellation takes priority. Report real blockers;
without loaded and trusted hooks the skill provides process instructions only,
not an automatic Stop guarantee.

## End checks and Hook state

`scripts/install_work_report_hooks.py` merges its five event handlers into the
current user's `.codex/hooks.json`, preserving foreign groups and leaving model,
auth, CC Switch and hooks.state unchanged. Use native `/hooks` to review/trust
installed definitions. File existence or installer PASS does not prove trust.

- `UserPromptSubmit`: conservatively captures possible report/timing requests;
  an actual intent Judge decides semantics. The matcher cannot promise every
  metaphorical wording or events when the Hook is not loaded/trusted.
- `SessionStart` and `PostToolUse`: restore state or present due reminders at
  tool boundaries.
- `Stop`: unresolved candidates or obligations request continuation in the same
  conversation. Only a fresh, matching, successfully revalidated delivery.json
  satisfies the obligation. Allow at most two recovery continuations, then
  record failure and show a warning rather than blocking indefinitely.
- `Interrupt`: cancel this session's reporting obligations and respect the stop;
  do not restart interrupted business work.

A recovery report uses a new appropriate progress/final batch with current state
and the actual independent Judge. Receipt task, generation time, original-request
hash and artifact digest must match. An old report, review.json alone or empty
template is not delivery. Report PASS remains separate from phase completion.

## Timed reporting and bounded recovery

For lightweight timed messages use [timer.md](timer.md). It sends a prompt to
the original conversation without waiting for a report receipt and must not also
register this legacy periodic runtime or cron. Keep existing agreements on their
chosen backend rather than migrating or stacking schedules automatically.

Prefer installed, callable native conversation scheduling when that is the
chosen mechanism. Claim scheduled only after creation succeeds and its task ID
is read back. Otherwise the supported legacy interval adapter is:

```text
python3 <agent-tools>/scripts/install_work_report_schedule.py --task-dir <task-dir>
python3 <agent-tools>/scripts/install_work_report_schedule.py --task-dir <task-dir> --check
```

First register a Judge-confirmed interval. Cron performs a small check each
minute; reporting.json owns the actual interval. Do not enroll every task or run
the full Agent Tools installer. Native queue success means enqueued, not
necessarily immediate execution, and is not the sole wakeup guarantee here.

The cron report worker is a time-limited independent Codex process using the
existing account. It reads original request, latest working state and evidence,
writes only this task's report directory, and uses an actual independent report
Judge. It does not concurrently resume Main or modify business code. A per-task
lease avoids duplicate generation in a window. Missing current state must be
disclosed, never filled with invented reasons. Disk artifacts/logs do not promise
immediate visible notification in the original conversation.

Timeout, unavailable models/tools, rejected Judge and missing valid receipt are
failures. After bounded retry produce an explicitly unreviewed risk snapshot
with cause and state location; do not claim formal report PASS. Stop periodic
registration when the task completes or the user cancels:

```text
python3 report_runtime.py status --task-dir <task-dir>
python3 report_runtime.py tick --task-dir <task-dir>
python3 report_runtime.py cancel --task-dir <task-dir>
python3 <agent-tools>/scripts/install_work_report_schedule.py --task-dir <task-dir> --remove
```

Runtime tick only decides whether reporting is due. The actual cron generation
entry is `report_scheduler.py tick`. Use one scheduling backend per agreement.

## Limits

Local timing requires its host/process/cron to stay available; desktop timing
requires the corresponding app/project. Another machine needs its own installed
and exercised adapter; local success cannot stand in for remote proof. This is
the Linux/WSL Codex adapter. Claude shares report generation but no Claude Hook
installation is claimed.

Scripts enforce registration, due/end checks, digest binding, duplicate control
and visible failures. Models judge original intent, state completeness and report
meaning. Reports remain standalone narratives; answer later questions in chat
without rewriting solely to appease a gate.

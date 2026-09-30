# Lightweight Work Report Timer

The timer waits until a requested time and sends one prompt to the original
conversation through `codex queue`. It does not generate a report itself.
Successful enqueue, actual message arrival, report delivery and continuation of
the original task are separate outcomes.

## Responsibilities

| Component | Responsibility |
|---|---|
| `report_timer.py` | Wait, attempt prompt delivery, record the queue result, and accept cancellation. |
| Work Report skill | Handle an actual reporting request, produce and review the report, and resume the original task when requested. |
| Reporting hooks | Track explicit reporting agreements and delivery; installed definitions alone do not prove host activation. |
| Legacy cron adapter | Serve an existing registered interval agreement; do not add it alongside a timer for the same request. |

Use the timer for explicitly requested timed messages. Ordinary work, discussion
of reporting infrastructure, and quoted historical requests do not authorize a
new timer. Keep manual report generation available independently of automation.
See [Work Report](WORK_REPORT.md) for report generation and agreement handling.

## Run and inspect

The implementation uses Python and Unix `flock` for Linux/WSL. Native Windows
requires a different lock/process adapter. Verify the current profile's
`codex queue --help` and use the actual conversation UUID. Create the task-owned,
ignored state directory first; the script requires existing absolute workspace
and state paths without symlinks.

```text
python3 <skill>/scripts/report_timer.py run \
  --workspace <absolute-project-path> \
  --state-dir <absolute-existing-task-timer-directory> \
  --thread <current-conversation-UUID> --after 60
```

Choose exactly one timing option:

- `--after <positive-seconds>` sends once after the delay.
- `--at <ISO-timestamp-with-timezone>` sends once at that time; a past timestamp
  is already due and is attempted immediately.
- `--every <positive-seconds>` starts after one interval and repeats. Missed
  intervals are skipped rather than delivered in a burst.

`run` stays in the foreground. For unattended use, keep it in an existing process
manager or tmux session and record that session or process identity. Waiting
itself does not call a model. Use `--message-file <absolute-file>` for a custom
prompt; the default asks for an interim report followed by continuation within
the original task's authority, without creating another timer.

```text
python3 <skill>/scripts/report_timer.py status --state-dir <timer-directory>
python3 <skill>/scripts/report_timer.py stop --state-dir <timer-directory>
```

The directory contains `timer_state.json`, `timer_events.jsonl`, `timer.lock`
and, after cancellation, `timer_stop.json`. Status reads saved state; inspect
the process manager separately to establish liveness. The stop command writes a
request that the waiting process checks; it does not retract messages already
queued or terminate business processes. Use a new directory after cancellation
so a previous stop marker cannot stop the next timer.

## Delivery limits and failure handling

A lock prevents two timer processes from using the same state directory. It
does not prevent two separately configured timers from targeting one thread.
The script attempts each due message once. A nonzero queue exit, timeout, or
unrecognized successful response is recorded without retrying that message;
periodic timers may continue to their next interval. A one-shot `uncertain`
result can have exit code 0, so read its status and queue result as well.

Queue acceptance does not prove immediate interruption or steering of an active
model turn. Check actual arrival in the intended conversation and the resulting
report separately. A periodic prompt can arrive while an earlier prompt remains
unprocessed; the timer does not deduplicate the client's queue or wait for a
report receipt. Stop or slow the timer when that accumulation is unwanted.
Host suspension or process exit can prevent delivery. No automatic restart or
report-completion service-level guarantee is provided.

The detailed invocation and handoff rules are in the [timer reference](../skills/work-report/references/timer.md).
The maintained behavior is implemented in [report_timer.py](../skills/work-report/scripts/report_timer.py)
and covered by [timer tests](../tests/test_report_timer.py). Historical probes
establish only their recorded environment's behavior; they are not current
installation or delivery guarantees.

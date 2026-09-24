# Lightweight timed delivery

A plain Python process waits until the requested time and calls `codex queue`
once to send a reporting prompt to the original conversation. Waiting uses no
model call. Enqueue success is neither report completion nor proof of immediate
steering. The implementation uses Unix flock and is verified for Linux/WSL;
native Windows requires a different process/lock adapter.

## Use

Check local `codex queue --help`, the real current conversation UUID and workspace.
Preserve a fixed time's timezone; clarify when absent rather than guessing.
Use a stated interval as given and do not create timers for every task.

Perform an authorized self-delivery probe in the current profile. Record the
queue result and when the message actually enters the original conversation.
If only enqueue was observed, say so. Do not concurrently take over an active
conversation with codex exec resume or interrupt it to simulate immediate delivery.

Use the project's ignored `docs/work-reports/<task>/timer/` or explicitly chosen
artifact directory. Check untracked/unstaged and ignored status first. Do not
create another business plan or report batch for a timer. The entry is this
skill's `scripts/report_timer.py`:

```text
python3 <skill>/scripts/report_timer.py run --workspace <absolute-project> \
  --state-dir <absolute-timer-directory> --thread <real-UUID> --after 60
python3 <skill>/scripts/report_timer.py run --workspace <absolute-project> \
  --state-dir <absolute-timer-directory> --thread <real-UUID> --every 1800
python3 <skill>/scripts/report_timer.py run --workspace <absolute-project> \
  --state-dir <absolute-timer-directory> --thread <real-UUID> --at 2026-09-08T09:00:00+08:00
```

The three timing modes are exclusive. For a custom reporting focus use
`--message-file <prompt-file>`; do not hard-code another task's UUID or paths.
For unattended work run the foreground command under tmux or an existing
process manager, record its identifier and verify liveness. A returned startup
command alone does not prove background execution.

```text
python3 <skill>/scripts/report_timer.py status --state-dir <timer-directory>
python3 <skill>/scripts/report_timer.py stop --state-dir <timer-directory>
```

Status shows last recorded state, not liveness; check the process manager or PID
separately. After cancellation use a new state directory to avoid an old stop
marker. Canceling this timer must not terminate business processes or claim to
recall already queued messages.

## Delivered reporting prompt

The default requests this interim report, immediate commentary delivery of its
link, and continuation of the original task within its existing authority and
resume point. It creates no new timer and does not impose a permanent
supervision-only role. Use normal check, two-stage independent Judge and finalize.

New timed-message requests use this lightweight route by default. Do not stack
legacy runtime intervals or cron, or automatically migrate existing schedules.
If setup produced a pending candidate, an actual intent Judge can return none
for the runtime and clear it from the original source; that does not validate
timer startup. Handle actual delivered messages as interim-and-resume requests.

## Bounded mechanism and limits

- One flock prevents duplicate processes for the same state directory.
- A stop marker permits cancellation; state/events record timing and delivery.
- No report-completion lease or pending queue exists. Do not automatically resend
  after failed or uncertain enqueue, which might duplicate the message.
- Missed intervals are not delivered in a burst. A new interval may enqueue
  while the previous message is unprocessed; the user can stop or slow the
  timer. This version does not claim message-processing deduplication.

Sleep or process exit can prevent delivery; recovery and processing timing
depend on the host. Promise a due delivery attempt, not a report-completion SLA
or absolute noninterruption. At handoff give the directory, conversation UUID,
process/manager identifier, next trigger, queue result and observed arrival stage.

# Reporting-intent Judge

Read only the original user prompt and decide whether it creates an end,
interval or interim-and-resume reporting obligation. Do not review business
code, turn ordinary questions into obligations, choose an unstated interval, or
require later questions to be inserted into a standalone report. Return only
JSON; Main saves the actual response unchanged.

```json
{
  "schema_version": "work-report.intent/1",
  "request_sha256": "<SHA-256 of original UTF-8 bytes>",
  "reviewer_id": "<actual host reviewer identifier>",
  "verdict": "confirmed",
  "on_end": true,
  "interval_seconds": null,
  "resume_after_report": false,
  "evidence_quotes": ["<verbatim continuous substring of original request>"],
  "reason": "<why the actual request has this timing and scope>"
}
```

- `confirmed`: a clear current agreement; at least one of on_end,
  interval_seconds or resume_after_report must apply. Evidence quotes are exact
  substrings of the original prompt.
- `none`: immediate standalone report with no task to resume, mechanism
  discussion, ordinary follow-up, quoted historical example, explicit no-report
  request, or no applicable future agreement. Do not register an obligation.
- `needs_clarification`: genuinely missing user information, such as an interval
  without a duration. Missing directories, tool capability or adapter support do
  not make the user's meaning ambiguous.
- `deferred`: report after an explicit future business milestone, not the next
  response end. Set on_end false, interval_seconds null and resume_after_report
  false; preserve the full milestone quote. The requirement is recorded without
  claiming an automatic trigger or completed report. Do not repeatedly ask the
  user because the adapter lacks a business-completion signal.

Translate a specified interval into integer seconds, at least 60. Do not turn
a fixed time or cron expression into an interval: preserve/clarify timezone and
use the supported native schedule. `on_end=true` only means an explicit request
before this turn's final response. Stop does not mean training completion,
project completion or app closure. Main's intention to continue working cannot
rewrite a business milestone as the next Stop.

Discussion about implementing an end-report feature, examples, skill text or a
screenshot of an older instruction is not a current reporting agreement. Main
passes the actual JSON to register; the runtime checks hashes/quotes and writes
local reporting.json. A self-declared reviewer ID does not authenticate the
independent Judge; preserve its actual host delegation trace.

`resume_after_report=true` means an explicit interim inspection followed by
continuing the original task. It requires one progress report and actual
resumption; it does not declare the original task complete. Use on_end false or
interval_seconds null when those separate obligations were not requested.
An explicit pause or instruction to wait after reporting means no resumption.

A request to set up the default lightweight timer or explicit report_timer.py /
codex queue is `none` for this runtime: explain that the timer carries delivery
and avoid duplicate periodic registration. This verdict does not prove the
timer started; its status/events and actual message arrival do. When that timer's
actual interim-report-and-continue message arrives, judge that specific request
without creating another timer.

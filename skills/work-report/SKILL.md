---
name: work-report
description: Produce local Markdown progress or final work reports with concrete decisions, observations, scope and next steps, machine checks, and independent two-stage reading review. Use for requested work reports, interim reporting followed by resumption, end-report agreements, and scheduled reporting. Do not trigger a full report for a short status fact or ordinary follow-up question.
---

# Work Report

Make the goal, current result, reasons, evidence and next decision understandable
without the chat history. Read the [shared writing contract](references/writing-contract.md)
and [rubric](references/rubric.yaml); generate from the [template](assets/report.md).
The independent reviewer uses [Judge instructions](references/judge.md). These
are one standard, not separate opportunities to add business requirements.
Reports follow the user's language; maintained instructions use English.

## Choose the reporting mode

- **Immediate standalone report:** create the requested phase report and deliver
  it in the final response when there is no original task to resume.
- **Interim report, then continue:** read [runtime rules](references/runtime.md).
  An actual independent intent Judge identifies `resume_after_report=true`.
  Register that obligation, then initialize a fresh `progress` batch in the
  same task directory. Preserve the original goal, active job references and
  concrete resume action. Deliver the report in commentary and actually resume
  the authorized original task in the same turn.
- **Final report:** complete the promised original phase before claiming it is
  complete. A report can truthfully describe incomplete work; report PASS does
  not finish functional acceptance or accept the result for the user.
- **Future end/interval agreement:** read runtime and [intent Judge rules](references/intent-judge.md),
  preserve the user's exact words and obtain an actual independent decision.
  A business milestone uses `deferred`; the next conversation Stop is not the
  end of training or of the whole project.
- **Timed message to this conversation:** use the lightweight [timer](references/timer.md)
  by default. Delivery of the prompt is separate from report completion. Do not
  also register a legacy periodic obligation or a second cron schedule.
- **Ordinary follow-up:** answer in conversation. Do not rewrite the report or
  create another reporting obligation unless requested.

No request or existing reporting agreement means no automatic long report.
A five-step reporting agreement is evaluated at that agreed boundary, not after
every tool call. Keep important decisions and observations in the canonical
workflow record as they happen; do not fabricate a retrospective process log.

## Initialize a snapshot

Run `uv run --script <skill-dir>/scripts/report_tool.py --help`. PEP 723 pins the
isolated script dependencies; do not change the reported project's environment.
If uv is unavailable, say the tool is not ready instead of claiming checks ran.

Prefer an existing original-request file. If needed, save only the relevant
verbatim user text as `request.txt` under the project's artifact location, first
checking that the directory has no tracked files. Do not replace quotes with an
agent summary or duplicate the whole chat. Preserve later revisions and their
source. Initialization configures and verifies local Git exclusion.

```text
uv run --script <skill-dir>/scripts/report_tool.py init \
  --workspace <absolute-project-path> --title <short-topic> \
  --request <original-request-file> --kind progress \
  --workflow-record <optional-canonical-workflow-record>
```

Omit `--workflow-record` when there is no workflow record. With one, context.json
freezes its actual checklist bytes, hash and revision alongside the request and
working state. Brief and report must refer to the same applicable canonical
state; do not reconstruct another acceptance ledger. A new report's delivery
checks reject a changed workflow snapshot. Initialize another batch after a
material state update. Historical `finalize --verify-only` remains read-only
and verifies the frozen report instead of requiring the live task to stop moving.

Use `--record-only` to create `draft.md` and state for registration, not a delivered
report. Reuse `--task-dir` for one agreement and `--state` for an existing working
state. Formal reporting after registration always uses a newly initialized
batch. A temporary interim report alongside another active obligation gets its
own task directory and references the original state; do not cancel the earlier
obligation. Preserve the original goal and resume point in that state.

The default is project `docs/work-reports/`; `--output-root` is only for an
explicitly specified reporting location. Do not silently switch to /tmp, a
public directory or another workspace after permission, sandbox or Git-policy
failure. Report the concrete initialization error. Time windows require
timezone-aware ISO values. Task/report IDs include UTC time and randomness.

Keep working-state.md concise: progress, dated decisions and reasons, failures,
verification, blockers, next action, and background-job artifact/query references.
Do not transcribe every tool call or update global memory automatically. A
report does not terminate background work. New state needs a new snapshot;
an early placeholder batch cannot stand in for a completed report.

## Write and check

Retain generated frontmatter and the six unique semantic section IDs: `goal`,
`progress`, `decisions`, `evidence`, `scope`, `next_steps`. Headings may use the
user's language and the actual topic. Lead with the important result; supply
concrete observed values and explain what they prove and what remains unknown.
Remove placeholders. Say when no material choice or risk arose; do not invent one.

Use tables or figures only when they help comparison. No visual is mandatory.
Existing attachment, local-link and image checks still apply; images belong in
this batch's assets directory. A remote link is not verified by its existence,
and Mermaid syntax is not authenticated by the checker. Link large logs instead
of copying sensitive content, but keep decisive failures in the main text.

Compare actual scope with the original request and revisions. Separate necessary
implementation from extra work and pre-existing user changes. Disclose serious
drift and its consequence; do not delete or roll back unrelated work to obtain
report PASS.

```text
uv run --script <skill-dir>/scripts/report_tool.py check \
  --report <report.md> --task <task-id> --workspace <project>
```

Read exit code, issues and warnings: 0 means the applicable mechanical checks
passed, 1 means unmet conditions, and 2 means the tool did not complete. Structure
and snapshot validity do not establish argument quality or business acceptance.

## Independent reading and delivery

After machine checks pass, use an actual host subagent in a context without the
main conversation. Stage one receives only the artifact, reader task and writing
rules, plus its opaque artifact digest. Save the actual `cold_read` reconstruction
unchanged as cold-read.json. Only then give the same reviewer the frozen request,
state, checks and evidence for stage two. If resumption is unavailable, a new
reviewer reads the original stage-one output. Save its actual JSON as review.json.
The Judge instructions define the two schemas, hashes and sequence.

Follow the user's reviewer model convention; otherwise use a host-available
model without adding services. Do not provide expected verdicts, let the reviewer
edit files, fabricate feedback, or turn a failing verdict into pass. A changed
report needs fresh check and cold read. Allow at most two revision rounds. On
unavailable reviewer, timeout or remaining failure, deliver a clearly marked
draft/risk snapshot with the reason; continue any authorized independent work.

```text
uv run --script <skill-dir>/scripts/report_tool.py finalize \
  --report <report.md> --task <task-id> --workspace <project>
```

Only successful finalize creates delivery.json. `--verify-only` rechecks without
refreshing delivery time. A receipt proves local delivery conditions, not that
the user read or accepted the report. Tool validation binds preserved review
stages to the artifact; only actual host traces establish independent delegation
and the order of supplied material. Report, rules, attachments or cited-evidence
changes invalidate the prior review.

For an interim report, the first user-facing message after finalize must be a
commentary link with the key finding and concrete next action. Then execute that
original task action in the same turn; do not stop at a promise to continue or
point to an unrelated tool call. A running background process is not proof that
Main resumed. A report failure also does not indefinitely block unrelated work.

For final/standalone delivery provide the absolute report path, main finding or
pending decision and unverified scope. End the original task only when complete,
explicitly paused/canceled, or blocked on genuinely necessary user input.

## Storage and automation boundary

The tool uses Git info/exclude and checks ignored/untracked status. Do not
implicitly add, commit, untrack files, or edit project .gitignore. Export a
specific report to a tracked location only when asked; otherwise preserve
excluded artifacts separately before removing a workspace. Do not auto-publish,
create business PRDs, use Linear, or introduce a global task database.

Hook definitions, trust activation, scheduled execution and report delivery are
separate states. Read back each; an installed file is not an active guarantee.
Use bounded retries, explicit failure snapshots and user cancellation. Report
quality PASS never replaces functional completion, user acceptance or evidence
of post-report resumption.

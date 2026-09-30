# Task Runtime

Task Runtime keeps one task's current requirements, checklist, check results and
scoped user feedback in local application storage. A task can continue across
conversations on the same machine. Its workspace is a working location; neither
the chat ID nor the branch name is its identity.

Use it when a task needs persistent state. Short changes and ordinary answers do
not require a task. It does not intercept ordinary code/document edits, require
Hooks, schedule external work, or synchronize state between machines.

## Entry point and storage

From the source checkout, inspect the command contract with:

```sh
python3 -m agent_workflow.cli task --help
```

The installed launcher exposes the same entry as `agent-workflow task`. Use each
subcommand's `--help` for CLI options and this guide's JSON operation packets
for payload fields. Task mutations take a JSON packet through `--input PATH`;
use an isolated `--data-root` for trials. The runtime reports resolved paths
rather than creating an index in each project.

Linux/WSL path precedence is explicit `--data-root`, then `data_root` in
`${XDG_CONFIG_HOME:-$HOME/.config}/agent-tools/config.json`, then
`${XDG_DATA_HOME:-$HOME/.local/share}/agent-tools`. Configured roots must be
absolute (a leading `~` is expanded). The standard-library resolver keeps the
existing installer free of third-party runtime dependencies. The root does not
change with cwd. Inspect the selected location without creating a task:

```sh
python3 -m agent_workflow.cli task location
python3 -m agent_workflow.cli task list --data-root /absolute/trial-data
```

The data root contains `tasks.sqlite3` and task-owned files under
`artifacts/<task-id>/`. It is application data, separate from the replaceable
runtime installation and project checkout. Each machine/user has independent
state. [ADR 0004](decisions/0004-task-runtime-application-storage.md) records
this storage decision and its limits. Existing scenario records and explicit
record paths remain usable through the [agent workflow](AGENT_WORKFLOW.md);
ordinary startup does not import them.

## Find and continue a task

Start with `task resolve` for a known session/workspace or `task list` for task
metadata. Read the chosen task explicitly with `task read`. An ambiguous match
returns candidates; it does not create a new task or choose one by filename.
`task bind` associates a session with the task at its current workspace.
`task rebind` explicitly changes the task workspace and invalidates prior results;
then bind the new session. Workspaces must be Git worktree roots with a commit.

Read the current summary first, then request necessary details and evidence.
Check the actual repository, worktree and external jobs before relying on old
observations. Moving a directory or switching branches does not transfer task
ownership or establish that previous checks still apply. Do not delete a task
because its old workspace is unavailable.

```sh
python3 -m agent_workflow.cli task resolve --workspace /absolute/project --session SESSION
python3 -m agent_workflow.cli task read --task TASK_ID
python3 -m agent_workflow.cli task read --task TASK_ID --detail
python3 -m agent_workflow.cli task checklist --task TASK_ID
python3 -m agent_workflow.cli task checklist --task TASK_ID --item AC-001
python3 -m agent_workflow.cli task checklist --task TASK_ID --item AC-001 --detail
python3 -m agent_workflow.cli task checklist --task TASK_ID --ordinal 1
python3 -m agent_workflow.cli task checklist --task TASK_ID --search output
python3 -m agent_workflow.cli task checklist --task TASK_ID --format markdown
```

Append the same `--data-root /absolute/trial-data` to each command when using an
override. Default output is JSON. `read` and `checklist` accept `--format markdown`
for a current stdout view; this does not save another authoritative document.
Use JSON with `--detail` when you need full evidence/detail fields rather than
the Markdown summary table.

Queries display state without exporting another PRD, checklist or report. When
an export is requested, distinguish a runtime-owned process artifact from a
project deliverable and update that target in place. A human-edited requirements
export must be explicitly revised/imported into the canonical task; it is not a
second live source of truth.

## Requirements, checks and feedback

The Agent supplies semantic requirements and check points. `task create` makes
an on-demand task; `task revise` changes the same task as requirements evolve.
The runtime maintains checklist entries and their revision. User and Agent
review still determine whether the requirements are complete.

`task checklist` supports the entire current list, one item's status, one item's
details and text search within the task. An ordinal selects the item currently
at that position; mutations use the returned stable criterion ID. No match is
an empty search result, not permission to select another task's item.

Three facts remain distinct:

| Fact | Meaning |
|---|---|
| Verification | What the check observed: not run, passed, failed or technical error |
| Validity | Whether that result still describes the current requirements and inputs |
| User acceptance | Whether the user accepted or rejected the specified result scope |

Capture inputs with `task fingerprint`, run the project's existing checks, and
record the observed result. The result packet's `input_digest` must still match
when recorded. Without `--path`, fingerprinting includes HEAD and tracked plus
non-ignored untracked worktree content. Repeated `--path` options select exact
workspace-relative files, not recursively watched directories. Include relevant
ignored configuration explicitly. A narrow selection requires a real dependency
justification; otherwise use the whole-worktree default.

```sh
python3 -m agent_workflow.cli task fingerprint --workspace /absolute/project
python3 -m agent_workflow.cli task fingerprint --workspace /absolute/project --path src/convert.py --path tests/test_convert.py
```

Run checks with the project's existing tools. Record results with `task result`
and identify externally executed/imported results as such. Runtime storage does
not prove it executed the check or judged its semantic quality. A changed
requirement, relevant input or registered evidence content can make an earlier
pass stale; HEAD alone is not
enough to identify dirty-worktree inputs.

Use `task feedback` for necessary original user wording, its source and the
accepted/rejected scope. An Agent interprets that scope; the runtime does not
authenticate a user or extract acceptance from words such as “done.” Partial
acceptance leaves the remainder pending. Tests passing does not close a task.

## JSON operation packets

Save a packet outside the project's tested inputs, then invoke the corresponding
command. These examples use placeholders; replace the workspace, task ID,
revision, observed fingerprint and feedback with actual values.

A create packet, saved as `create.json`:

```json
{
  "operation_id": "create-converter-1",
  "workspace": "/absolute/project",
  "title": "Fix converter output",
  "requirements": "Preserve input order. Do not change the public format.",
  "criteria": [{
    "id": "AC-001",
    "name": "Output order",
    "requirement": "Converted rows retain input order.",
    "expected": "Two input rows appear in the same order.",
    "method": "Run the order regression test.",
    "source": "Current user request"
  }]
}
```

```sh
python3 -m agent_workflow.cli task create --input /absolute/packets/create.json --data-root /absolute/trial-data
```

The response supplies the task ID and revision. Existing-task operations use
those values, not a chat ID or guessed counter. A revision packet changes only
the supplied fields; existing requirements and criteria remain unless explicitly
updated or withdrawn:

```json
{
  "task_id": "TASK_ID",
  "operation_id": "clarify-order-1",
  "base_revision": 1,
  "criteria": [{
    "id": "AC-001",
    "expected": "Rows, including duplicate rows, retain their input order."
  }],
  "recovery": "Add the duplicate-row regression before recording a result."
}
```

Run it through `task revise --input PATH`. Changing a criterion invalidates its
prior result. Replacing `requirements` invalidates all criteria by default;
`affected` can declare a justified narrower list of criterion IDs. `order` must
list every stable ID exactly once, including withdrawn items. Withdraw a
criterion with `{"id":"AC-001","withdrawn":true}`; its ID cannot be reused.

After running the actual check, a result packet can be:

```json
{
  "task_id": "TASK_ID",
  "operation_id": "order-check-1",
  "base_revision": 2,
  "item_id": "AC-001",
  "source": "external",
  "method": "python -m unittest tests.test_convert",
  "verification": "passed",
  "returncode": 0,
  "input_digest": "OBSERVED_FINGERPRINT",
  "watched_paths": null,
  "evidence": [],
  "stdout": "Actual captured test output"
}
```

Use `task result --input PATH`. Match `watched_paths` to the fingerprint command:
`null` for the whole worktree, or the exact file list used with `--path`. The
runtime verifies input identity; it does not execute the reported command.

Use `task submit` with only the existing-task envelope to enter
`awaiting_acceptance` once all current criteria pass. Record actual scoped user
feedback separately with `task feedback`:

```json
{
  "task_id": "TASK_ID",
  "operation_id": "user-feedback-1",
  "base_revision": 4,
  "outcome": "accepted",
  "quote": "ACTUAL USER WORDING",
  "source_ref": "ACTUAL MESSAGE REFERENCE",
  "items": ["AC-001"]
}
```

Do not send the example's placeholder quote as user evidence. `rejected` is the
other outcome. An accepted criterion requires a current passing result.
Changed evidence does not prevent recording a rejection or revising the
requirements; it prevents presenting old verification as current acceptance.

Other operation payloads extend the same envelope:

| Command | Additional fields |
|---|---|
| `bind` | `session_id`, `workspace` matching the task's current worktree |
| `rebind` | `workspace` for the explicitly selected replacement worktree |
| `artifact` | `name`, UTF-8 `content`; optional `purpose`, `preserve` |
| `closeout` | `documents_reviewed: true`, `rationale`, `dispositions`; optional `retain_task` |
| `reopen` | None; requires a closed task retained in full |
| `forget` | None; requires a closed task without retained artifacts |
| `artifact-policy` | `name`, boolean `preserve`, actual user `quote`, `source_ref` |
| `prune` | `names`, `rationale`; closed non-retained tasks only |

Artifact names are logical names without path separators. The runtime assigns
physical paths; it does not accept arbitrary project paths for deletion. To
inspect committed content, run `task artifact-read --task TASK_ID --name NAME`.
A result's `evidence` contains logical artifact names. Updating a referenced or
explicitly preserved artifact is blocked.

A closeout packet after actual acceptance and Cleaner review looks like:

```json
{
  "task_id": "TASK_ID",
  "operation_id": "closeout-1",
  "base_revision": 5,
  "documents_reviewed": true,
  "rationale": "Usage documentation is current; no lasting information remains in the scratch report.",
  "retain_task": false,
  "dispositions": {"scratch-report": "delete"}
}
```

Use an empty `dispositions` object when the task owns no artifacts. Every owned
name must appear exactly once, with `keep` or `delete`. This example is not
permission to invent acceptance or delete an unreviewed report.

For `task import`, omit `task_id` and `base_revision`; supply `operation_id`,
`title`, `workspace` and `source` (the chosen legacy record directory). The
response assigns a new task ID; inspect it before switching the authoritative
record. Import is explicit and does not merge a second record into an existing
task.

## Mutation and recovery rules

Existing-task mutation packets carry `task_id`, `operation_id` and
`base_revision`. `create` and `import` instead assign the task ID and start its
revision; omit `task_id` and `base_revision` for those two commands. Keep the packet for a retry: the same operation ID and
unchanged request replay the original result without another update. Reusing an
ID for different content is an idempotency conflict. After a revision conflict,
read current state, reconcile intervening input, and issue a new operation for
the revised intent. Do not overwrite another conversation's edits.

Task state changes use database transactions. Managed file publication has a
separate recoverable operation because the database and filesystem do not share
a transaction. A file awaiting recovery is not a committed evidence reference.
Use `task recover --task TASK_ID` for an interrupted operation and inspect its result before
claiming success. Storage errors and incomplete cleanup are failures, not empty
successful responses. The contract covers runtime-owned state and artifacts,
not exactly-once execution of arbitrary Shell, training or deployment commands.

Recovery completes the pending request; abort restores the previously committed
state of a pending, uncommitted operation. For example, if changed workspace
inputs make a prepared closeout invalid, abort that exact operation before
revising and rechecking:

```sh
python3 -m agent_workflow.cli task recover --task TASK_ID --data-root /absolute/trial-data
python3 -m agent_workflow.cli task abort --task TASK_ID --operation closeout-1 --data-root /absolute/trial-data
```

These are alternatives selected from the actual failure state, not two steps to
run blindly. Abort cannot undo an already committed operation. Its cancelled
operation ID cannot be reused for a different or renewed request; read current
state and use a new ID. If create/import was interrupted before returning a task
ID, replay its unchanged packet or run `task recover --data-root
/absolute/trial-data` without `--task` to process pending operations in that data
root, then list tasks. Unscoped recovery is explicit and can process more than
one local task.

## Cleaner task closeout

Task closeout is distinct from Cleaner's behavior-preserving code cleanup.
Begin only after explicit, scoped user acceptance and a clear completion scope;
a Stop event, ended chat, passing test or report filename does not authorize it.

1. Read current requirements, feedback, evidence and registered artifacts.
   Inspect the associated workspace for remaining work and handoff needs.
2. Maintain lasting information in the project's existing code, tests, usage
   documentation or necessary ADR. Do not create documents merely to empty the
   runtime. Project conventions and user retention choices take precedence.
3. Check known references and actual script dependencies. Move lasting test
   inputs out of disposable records into project fixtures and recheck consumers.
4. Reverify behavior affected by closeout edits before submitting closeout.
   Recording a new `task result` resets that criterion's acceptance to pending.
   Equivalent fixture movement or documentation maintenance can leave the
   original user feedback applicable: verify that its scope still covers the
   current result, then explicitly record it with `task feedback`, preserving
   the actual quote, source reference and criterion scope. The runtime does
   not carry acceptance forward automatically. Changed accepted behavior or
   requirements return the same task to negotiation, checks and new scoped
   user acceptance; do not reinterpret old feedback to approve them.
5. Submit one exact `keep` or `delete` disposition for every owned artifact
   through `task closeout`. Runtime checks
   task ownership, revision, paths, content and references before cleanup. An
   edited file or retained reference blocks deletion; resolve it rather than
   bypassing the runtime with a broad filesystem deletion.

Only registered task-owned process material is eligible: for example, a PRD
export, checklist export, work report, obsolete evidence or scratch file.
Filename, age, ignored status and “the Agent wrote it” do not establish ownership.
Project documentation, another task's files, user-retained material and unknown
files are excluded. Preserve a report still awaiting delivery in the current
turn. The MVP has no external-file adoption or handoff disposition. Copy lasting
content into the appropriate project file using normal tools, verify it and its
consumers, then separately dispose of the runtime-owned copy. Project files
never enter this runtime's deletion set.

Closeout quarantines selected owned files as `.trash` before the database
commit. Abort restores that uncommitted quarantine; after commit, recovery or
an unchanged same-key retry finishes garbage removal. Changed quarantine bytes
are a conflict to preserve and investigate, not permission to delete blindly.
Do not manually remove runtime `.trash` or `.pending` files to bypass recovery.

A pending cleanup is reported as `recovery_pending`. Task reads reject an
uncommitted pending operation; committed state with remaining garbage is
readable but still reports cleanup pending. A pending closeout appears as
`closing` in list metadata
until the operation commits and remaining garbage cleanup completes. Recover
with the same operation identity; committed metadata alone does not establish
that all files were removed. Do not describe pending cleanup as completed. Closing
and forgetting are separate actions: use `task forget` only for explicit removal
of closed-task storage. By default closeout clears requirements, criteria and feedback, retaining a
small closed-task record plus any explicitly kept artifacts. Use
`retain_task: true` to preserve the complete task for `task reopen`; evidence
still referenced by a retained task cannot be deleted. Without retention, the
criterion references are removed with the task content, allowing their owned
evidence to be deleted in that same closeout. Retaining one report alone does
not preserve the original task for reopening. Later deletion of kept artifacts
from a closed, non-retained task uses `task prune` with exact logical names and a
rationale. If user retention must change, record the actual new instruction via
`task artifact-policy` first; closing alone does not release it.

Worktrees and branches are not removed by artifact cleanup. Their retirement
requires explicit scope and the existing worktree-management capability.

## Compatibility and limits

Use `task import` only for a selected legacy Agent Workflow directory containing
its JSON-encoded `checklist.yaml` and request snapshot. It imports requirements
and criteria with source provenance; checks start unverified and acceptance
pending. It does not import reports, execution results, acceptance or external
artifact ownership. Inspect the imported task before retiring source material;
the import does not delete it. Do not run both stores as competing writable authorities.

Current source support targets Linux/WSL. Windows/macOS fallback paths exist in
the resolver, but that alone does not establish platform support or installation
verification. Storage schema version 1 initializes an empty database and rejects a newer
schema version; this
MVP does not provide a cross-version database migration command.

The existing Agent Workflow installer packages the task module with its runtime.
Installation/upgrade does not migrate every project or authorize cleanup. Keep
user task data separate from installed software. Existing formal-run permissions,
production boundaries and human merge authority remain in force.

Deterministic tests establish software behavior in their fixtures. Simplified
historical cases establish only those cases, and recorded external checks remain
external observations. These results do not establish model-performance gains,
production/GPU behavior, native Hook execution or installation on another host.

## Repeatable evaluation

Run deterministic checks with `python3 -m unittest discover -s tests -v`.
The reduced H01–H05 cases and negative controls live under
`tests/fixtures/task_runtime/`; they avoid the original server workspaces.

For an explicitly budgeted native H03 comparison, run
`python3 scripts/evaluate_task_runtime.py --native --output /absolute/new/eval-directory`.
This uses the local Codex auth/provider configuration in temporary isolated
profiles, four serial A/B/B/A runs with a 180-second limit each, and records
answers, commands, trajectories, tool hashes and usage outside the checkout.
A reads equivalent current state from JSON; B reads it through the runtime.
No native hooks are installed. Copied auth/config files are removed on normal
exit and handled failures; an uncatchable process or host failure still requires
removing the private evaluation profiles before sharing output. Never publish
uninspected raw traces. The mechanical verdict does not judge the meaning of
`next_step`: independent review must check CPU tests precede implementation.
This probes cold recovery, not implementation quality or general model benefit.

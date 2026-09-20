# Task Agreement

schema_version: 1
task_id: "<utc-stamp>-<slug>"
created_at: "<iso-utc>"
source:
  query_sha256: "<sha256>"
  query_path: "request.txt"

## Current Agreement

- goal: "<intended outcome>"
- scope: "<allowed and forbidden changes>"
- non_goals: []
- formal_run_policy: "prohibited"

## Protocol Readback

| id | source_quote | normalized meaning | authority | binding | status |
|---|---|---|---|---|---|
| "<protocol-id>" | "<original quote>" | "<precise meaning>" | "user" | "<binding-id or none>" | "unverified" |

## Work Record

- current_approach: "<implementation and investigation notes>"
- open_questions: []
- latest_evidence: []

## Code Handoff

- branch: "<branch>"
- base_sha: "<sha-or-null>"
- candidate_sha: "<sha-or-null>"
- working_tree: "<clean|dirty>"
- diff_summary: "<path or summary>"

## Current State

- running_tasks: []
- human_review: "not_requested"
- next_action: "<next concrete action>"

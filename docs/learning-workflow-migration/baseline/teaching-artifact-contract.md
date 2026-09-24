# Teaching Artifact Contract v1

This file is the single human-readable schema source. The deterministic
validator is the executable authority.

## Envelope

A durable teaching record has exactly one marker outside every ZotLit managed
region, followed by exactly one JSON manifest fence:

````markdown
<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "topic-session-id",
  "mode": "guided",
  "goal": {},
  "learner_state": {},
  "teaching_unit": {},
  "knowledge_components": [],
  "teaching_edges": [],
  "frontier": [],
  "evidence_anchors": [],
  "learning_checks": [],
  "review_queue": []
}
```
````

`goal` records a target ability and success criteria. `learner_state` records
profile sources, assumptions, and observed gaps. `teaching_unit` names the
current KC, explanation, worked step, and next action. Supported modes are
`guided`, `guided-direct`, `artifact`, `survey-as-learning`, `paper-code`,
`reconstruction-audit`, and `check-only`.

## Knowledge graph

Every item in `knowledge_components` has non-empty `id`, `ability`, `state`,
`definition`, `why_needed`, `prerequisites`, `witnesses`, `worked_example`, and
`checks`. State is one of `mastered`, `callable`, `fragile`, `unknown`, or
`conflict`. IDs are unique; prerequisites, witnesses, and checks resolve; the
prerequisite graph is acyclic. Each prerequisite relation has a matching
TeachingEdge from prerequisite to dependent KC.

Every `teaching_edges` item has a unique `id`, existing `from` and `to` KCs,
`edge_type` of `strict`, `common`, or `convenience`, a concrete
`failure_without`, and an EvidenceAnchor `witness`. `frontier` contains unique
existing unfinished (`fragile`, `unknown`, or `conflict`) KCs whose
prerequisites are all `mastered` or `callable`.

## Evidence anchors

Every `evidence_anchors` item has unique `anchor_id`, `claim`, `source_kind`,
`layer`, `status`, `verified_at`, `boundary`, and a `locator` object.

- `source_kind`: `paper`, `code`, `log`, or `web`.
- `layer`: `source_fact`, `runtime_fact`, `inference`, `design_mapping`,
  `teaching_reconstruction`, or `advice`.
- `status`: `verified` only when the complete locator below is present;
  otherwise use `provisional` and state the missing proof in `boundary`.

Verified locators:

- paper: `zotero_item_key`, `zotero_pdf_key`, positive `page`; optional
  `annotation_key`;
- code: `repository`, immutable 40-hex `revision`, `path`, positive ordered
  `line_start` and `line_end`;
- log: `run_id` or `artifact_id`, `artifact_path`, 64-hex `artifact_sha256`,
  plus `timestamp` or an ordered line span;
- web: `canonical_url`, `retrieved_at`, `snapshot_sha256`, plus
  `snapshot_path` or `zotero_item_key`.

Provisional anchors still need enough mutable identity to revisit the source,
but they may omit the verified-only fields. Never relabel them verified during
writing.

## Learning and review

Every `learning_checks` item has unique `check_id`, existing `kc`, allowed
`type`, non-empty `prompt` and `success_signal`, an optional existing
`failure_prerequisite`, and existing evidence ids. Allowed types are
`reconstruction`, `retrieval`, `near_transfer`, `far_transfer`,
`evidence_location`, `counterexample`, `artifact_transfer`, and
`artifact_audit`. A durable guided record has reconstruction and retrieval;
artifact mode also has `artifact_transfer` and `artifact_audit`.

Every optional review card has unique `card_id`, existing `kc` and `check_id`,
non-empty `prompt`, `due_or_trigger`, `status`, and an Obsidian wikilink in
`target_note`.

## Ownership boundary

The marker, teaching headings, and manifest must remain outside
`%%zt-managed%%` / `%%/zt-managed%%`. Git staged validation compares every
managed-region byte in `HEAD` with the index; the pre-commit hook contains no
second copy of these rules.

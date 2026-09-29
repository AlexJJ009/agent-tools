---
title: Bad review queue fields fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-review-fields",
  "mode": "guided",
  "goal": {"target_ability": "Create durable review references.", "success_criteria": ["Bind every card to a KC, check, trigger, and wikilink"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md"], "assumptions": [], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.review", "explanation": "Review", "worked_step": "Review", "next_action": "Review"},
  "knowledge_components": [
    {"id": "kc.review", "ability": "Review", "state": "fragile", "definition": "Review", "why_needed": "Review", "prerequisites": [], "witnesses": ["anchor.paper"], "worked_example": "Review", "checks": ["check.review.reconstruct", "check.review.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.review"],
  "evidence_anchors": [
    {"anchor_id": "anchor.paper", "claim": "Paper witness.", "source_kind": "paper", "layer": "source_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"zotero_item_key": "ABCD1234", "zotero_pdf_key": "PDF5678", "page": 1}}
  ],
  "learning_checks": [
    {"check_id": "check.review.reconstruct", "kc": "kc.review", "type": "reconstruction", "prompt": "Review", "success_signal": "Review", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.review.retrieve", "kc": "kc.review", "type": "retrieval", "prompt": "Review", "success_signal": "Review", "failure_prerequisite": null, "evidence": ["anchor.paper"]}
  ],
  "review_queue": [
    {"card_id": "card.bad-fields", "kc": "kc.review", "prompt": "Review later", "due_or_trigger": "", "target_note": "notes/not-a-wikilink", "check_id": "check.review.retrieve", "status": "open"}
  ]
}
```

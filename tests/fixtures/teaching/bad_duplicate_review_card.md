---
title: Bad duplicate review card fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-duplicate-review-card",
  "mode": "guided",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.review", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
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
    {"card_id": "card.dup", "kc": "kc.review", "prompt": "Review one", "due_or_trigger": "later", "target_note": "[[notes/teaching/review]]", "check_id": "check.review.retrieve", "status": "open"},
    {"card_id": "card.dup", "kc": "kc.review", "prompt": "Review two", "due_or_trigger": "later", "target_note": "[[notes/teaching/review]]", "check_id": "check.review.retrieve", "status": "open"}
  ]
}
```

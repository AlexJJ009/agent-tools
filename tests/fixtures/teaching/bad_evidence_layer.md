---
title: Bad evidence layer fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-evidence-layer",
  "mode": "guided",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.layer", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {"id": "kc.layer", "ability": "Layer", "state": "fragile", "definition": "Layer", "why_needed": "Layer", "prerequisites": [], "witnesses": ["anchor.bad"], "worked_example": "Layer", "checks": ["check.layer.reconstruct", "check.layer.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.layer"],
  "evidence_anchors": [
    {"anchor_id": "anchor.bad", "claim": "Bad layer.", "source_kind": "paper", "layer": "vibes", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"zotero_item_key": "ABCD1234", "zotero_pdf_key": "PDF5678", "page": 1}}
  ],
  "learning_checks": [
    {"check_id": "check.layer.reconstruct", "kc": "kc.layer", "type": "reconstruction", "prompt": "Layer", "success_signal": "Layer", "failure_prerequisite": null, "evidence": ["anchor.bad"]},
    {"check_id": "check.layer.retrieve", "kc": "kc.layer", "type": "retrieval", "prompt": "Layer", "success_signal": "Layer", "failure_prerequisite": null, "evidence": ["anchor.bad"]}
  ],
  "review_queue": []
}
```

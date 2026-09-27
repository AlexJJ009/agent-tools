---
title: Bad illegal frontier fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-illegal-frontier",
  "mode": "guided",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.done", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {"id": "kc.done", "ability": "Done", "state": "mastered", "definition": "Done", "why_needed": "Done", "prerequisites": [], "witnesses": ["anchor.paper"], "worked_example": "Done", "checks": ["check.done.reconstruct", "check.done.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.done"],
  "evidence_anchors": [
    {"anchor_id": "anchor.paper", "claim": "Paper witness.", "source_kind": "paper", "layer": "source_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"zotero_item_key": "ABCD1234", "zotero_pdf_key": "PDF5678", "page": 1}}
  ],
  "learning_checks": [
    {"check_id": "check.done.reconstruct", "kc": "kc.done", "type": "reconstruction", "prompt": "Done", "success_signal": "Done", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.done.retrieve", "kc": "kc.done", "type": "retrieval", "prompt": "Done", "success_signal": "Done", "failure_prerequisite": null, "evidence": ["anchor.paper"]}
  ],
  "review_queue": []
}
```

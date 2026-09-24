---
title: Bad cycle fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-cycle",
  "mode": "guided",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.a", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {"id": "kc.a", "ability": "A", "state": "fragile", "definition": "A", "why_needed": "A", "prerequisites": ["kc.b"], "witnesses": ["anchor.paper"], "worked_example": "A", "checks": ["check.a.reconstruct", "check.a.retrieve"]},
    {"id": "kc.b", "ability": "B", "state": "fragile", "definition": "B", "why_needed": "B", "prerequisites": ["kc.a"], "witnesses": ["anchor.paper"], "worked_example": "B", "checks": ["check.b.reconstruct", "check.b.retrieve"]}
  ],
  "teaching_edges": [
    {"id": "edge.a-b", "from": "kc.a", "to": "kc.b", "edge_type": "strict", "failure_without": "B fails.", "witness": "anchor.paper"},
    {"id": "edge.b-a", "from": "kc.b", "to": "kc.a", "edge_type": "strict", "failure_without": "A fails.", "witness": "anchor.paper"}
  ],
  "frontier": [],
  "evidence_anchors": [
    {"anchor_id": "anchor.paper", "claim": "Paper witness.", "source_kind": "paper", "layer": "source_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"zotero_item_key": "ABCD1234", "zotero_pdf_key": "PDF5678", "page": 1}}
  ],
  "learning_checks": [
    {"check_id": "check.a.reconstruct", "kc": "kc.a", "type": "reconstruction", "prompt": "A", "success_signal": "A", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.a.retrieve", "kc": "kc.a", "type": "retrieval", "prompt": "A", "success_signal": "A", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.b.reconstruct", "kc": "kc.b", "type": "reconstruction", "prompt": "B", "success_signal": "B", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.b.retrieve", "kc": "kc.b", "type": "retrieval", "prompt": "B", "success_signal": "B", "failure_prerequisite": null, "evidence": ["anchor.paper"]}
  ],
  "review_queue": []
}
```

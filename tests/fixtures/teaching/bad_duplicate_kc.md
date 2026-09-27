---
title: Bad duplicate KC fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-duplicate-kc",
  "mode": "guided",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.dup", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {"id": "kc.dup", "ability": "First", "state": "fragile", "definition": "First", "why_needed": "First", "prerequisites": [], "witnesses": ["anchor.paper"], "worked_example": "First", "checks": ["check.dup.reconstruct", "check.dup.retrieve"]},
    {"id": "kc.dup", "ability": "Second", "state": "fragile", "definition": "Second", "why_needed": "Second", "prerequisites": [], "witnesses": ["anchor.paper"], "worked_example": "Second", "checks": ["check.dup.reconstruct", "check.dup.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.dup"],
  "evidence_anchors": [
    {"anchor_id": "anchor.paper", "claim": "Paper witness.", "source_kind": "paper", "layer": "source_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"zotero_item_key": "ABCD1234", "zotero_pdf_key": "PDF5678", "page": 1}}
  ],
  "learning_checks": [
    {"check_id": "check.dup.reconstruct", "kc": "kc.dup", "type": "reconstruction", "prompt": "Dup", "success_signal": "Dup", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.dup.retrieve", "kc": "kc.dup", "type": "retrieval", "prompt": "Dup", "success_signal": "Dup", "failure_prerequisite": null, "evidence": ["anchor.paper"]}
  ],
  "review_queue": []
}
```

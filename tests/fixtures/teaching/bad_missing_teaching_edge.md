---
title: Bad missing teaching edge fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-missing-teaching-edge",
  "mode": "guided",
  "goal": {"target_ability": "Build a witnessed prerequisite graph.", "success_criteria": ["Represent every prerequisite as a teaching edge"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md"], "assumptions": [], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.child", "explanation": "Child", "worked_step": "Child", "next_action": "Child"},
  "knowledge_components": [
    {"id": "kc.parent", "ability": "Parent", "state": "callable", "definition": "Parent", "why_needed": "Parent", "prerequisites": [], "witnesses": ["anchor.paper"], "worked_example": "Parent", "checks": ["check.parent.reconstruct", "check.parent.retrieve"]},
    {"id": "kc.child", "ability": "Child", "state": "fragile", "definition": "Child", "why_needed": "Child", "prerequisites": ["kc.parent"], "witnesses": ["anchor.paper"], "worked_example": "Child", "checks": ["check.child.reconstruct", "check.child.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.child"],
  "evidence_anchors": [
    {"anchor_id": "anchor.paper", "claim": "Paper witness.", "source_kind": "paper", "layer": "source_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"zotero_item_key": "ABCD1234", "zotero_pdf_key": "PDF5678", "page": 1}}
  ],
  "learning_checks": [
    {"check_id": "check.parent.reconstruct", "kc": "kc.parent", "type": "reconstruction", "prompt": "Parent", "success_signal": "Parent", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.parent.retrieve", "kc": "kc.parent", "type": "retrieval", "prompt": "Parent", "success_signal": "Parent", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.child.reconstruct", "kc": "kc.child", "type": "reconstruction", "prompt": "Child", "success_signal": "Child", "failure_prerequisite": "kc.parent", "evidence": ["anchor.paper"]},
    {"check_id": "check.child.retrieve", "kc": "kc.child", "type": "retrieval", "prompt": "Child", "success_signal": "Child", "failure_prerequisite": "kc.parent", "evidence": ["anchor.paper"]}
  ],
  "review_queue": []
}
```

---
title: Bad missing common evidence field fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-evidence-common",
  "mode": "guided",
  "goal": {"target_ability": "Preserve evidence boundaries.", "success_criteria": ["Every anchor states what it does not prove"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md"], "assumptions": [], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.anchor", "explanation": "Anchor", "worked_step": "Anchor", "next_action": "Anchor"},
  "knowledge_components": [
    {"id": "kc.anchor", "ability": "Anchor", "state": "fragile", "definition": "Anchor", "why_needed": "Anchor", "prerequisites": [], "witnesses": ["anchor.paper"], "worked_example": "Anchor", "checks": ["check.anchor.reconstruct", "check.anchor.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.anchor"],
  "evidence_anchors": [
    {"anchor_id": "anchor.paper", "claim": "Paper witness.", "source_kind": "paper", "layer": "source_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "locator": {"zotero_item_key": "ABCD1234", "zotero_pdf_key": "PDF5678", "page": 1}}
  ],
  "learning_checks": [
    {"check_id": "check.anchor.reconstruct", "kc": "kc.anchor", "type": "reconstruction", "prompt": "Anchor", "success_signal": "Anchor", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.anchor.retrieve", "kc": "kc.anchor", "type": "retrieval", "prompt": "Anchor", "success_signal": "Anchor", "failure_prerequisite": null, "evidence": ["anchor.paper"]}
  ],
  "review_queue": []
}
```

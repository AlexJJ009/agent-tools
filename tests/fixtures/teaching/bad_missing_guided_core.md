---
title: Bad missing guided core fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-missing-guided-core",
  "mode": "guided",
  "learner_state": {"profile_sources": ["reader_profile/index.md"], "assumptions": [], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.core", "explanation": "Core", "worked_step": "Core", "next_action": "Core"},
  "knowledge_components": [
    {"id": "kc.core", "ability": "Core", "state": "fragile", "definition": "Core", "why_needed": "Core", "prerequisites": [], "witnesses": ["anchor.paper"], "worked_example": "Core", "checks": ["check.core.reconstruct", "check.core.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.core"],
  "evidence_anchors": [
    {"anchor_id": "anchor.paper", "claim": "Paper witness.", "source_kind": "paper", "layer": "source_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"zotero_item_key": "ABCD1234", "zotero_pdf_key": "PDF5678", "page": 1}}
  ],
  "learning_checks": [
    {"check_id": "check.core.reconstruct", "kc": "kc.core", "type": "reconstruction", "prompt": "Core", "success_signal": "Core", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.core.retrieve", "kc": "kc.core", "type": "retrieval", "prompt": "Core", "success_signal": "Core", "failure_prerequisite": null, "evidence": ["anchor.paper"]}
  ],
  "review_queue": []
}
```

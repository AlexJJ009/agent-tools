---
title: Bad verified paper locator fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-verified-paper-locator",
  "mode": "guided",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.paper", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {"id": "kc.paper", "ability": "Paper", "state": "fragile", "definition": "Paper", "why_needed": "Paper", "prerequisites": [], "witnesses": ["anchor.paper"], "worked_example": "Paper", "checks": ["check.paper.reconstruct", "check.paper.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.paper"],
  "evidence_anchors": [
    {"anchor_id": "anchor.paper", "claim": "Paper witness.", "source_kind": "paper", "layer": "source_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"zotero_item_key": "ABCD1234"}}
  ],
  "learning_checks": [
    {"check_id": "check.paper.reconstruct", "kc": "kc.paper", "type": "reconstruction", "prompt": "Paper", "success_signal": "Paper", "failure_prerequisite": null, "evidence": ["anchor.paper"]},
    {"check_id": "check.paper.retrieve", "kc": "kc.paper", "type": "retrieval", "prompt": "Paper", "success_signal": "Paper", "failure_prerequisite": null, "evidence": ["anchor.paper"]}
  ],
  "review_queue": []
}
```

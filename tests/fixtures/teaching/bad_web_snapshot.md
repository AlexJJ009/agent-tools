---
title: Bad web snapshot fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-web-snapshot",
  "mode": "guided",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.web", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {"id": "kc.web", "ability": "Web", "state": "fragile", "definition": "Web", "why_needed": "Web", "prerequisites": [], "witnesses": ["anchor.web"], "worked_example": "Web", "checks": ["check.web.reconstruct", "check.web.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.web"],
  "evidence_anchors": [
    {"anchor_id": "anchor.web", "claim": "A live URL is mutable.", "source_kind": "web", "layer": "source_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"canonical_url": "https://learn.chatgpt.com/docs/hooks", "retrieved_at": "2026-08-20T10:00:00Z"}}
  ],
  "learning_checks": [
    {"check_id": "check.web.reconstruct", "kc": "kc.web", "type": "reconstruction", "prompt": "Web", "success_signal": "Web", "failure_prerequisite": null, "evidence": ["anchor.web"]},
    {"check_id": "check.web.retrieve", "kc": "kc.web", "type": "retrieval", "prompt": "Web", "success_signal": "Web", "failure_prerequisite": null, "evidence": ["anchor.web"]}
  ],
  "review_queue": []
}
```

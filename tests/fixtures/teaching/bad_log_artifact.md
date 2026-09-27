---
title: Bad log artifact fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-log-artifact",
  "mode": "guided",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.log", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {"id": "kc.log", "ability": "Log", "state": "fragile", "definition": "Log", "why_needed": "Log", "prerequisites": [], "witnesses": ["anchor.log"], "worked_example": "Log", "checks": ["check.log.reconstruct", "check.log.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.log"],
  "evidence_anchors": [
    {"anchor_id": "anchor.log", "claim": "A mutable log path is not enough.", "source_kind": "log", "layer": "runtime_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"run_id": "run-1", "artifact_path": "tmp/output.log", "timestamp": "2026-08-20T12:00:00Z"}}
  ],
  "learning_checks": [
    {"check_id": "check.log.reconstruct", "kc": "kc.log", "type": "reconstruction", "prompt": "Log", "success_signal": "Log", "failure_prerequisite": null, "evidence": ["anchor.log"]},
    {"check_id": "check.log.retrieve", "kc": "kc.log", "type": "retrieval", "prompt": "Log", "success_signal": "Log", "failure_prerequisite": null, "evidence": ["anchor.log"]}
  ],
  "review_queue": []
}
```

---
title: Bad artifact transfer fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-artifact-transfer",
  "mode": "artifact",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.transfer", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {"id": "kc.transfer", "ability": "Transfer", "state": "fragile", "definition": "Transfer", "why_needed": "Transfer", "prerequisites": [], "witnesses": ["anchor.log"], "worked_example": "Transfer", "checks": ["check.transfer.reconstruct", "check.transfer.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.transfer"],
  "evidence_anchors": [
    {"anchor_id": "anchor.log", "claim": "Transfer evidence.", "source_kind": "log", "layer": "runtime_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"run_id": "run-1", "artifact_path": "docs/teaching-skills-suite/evidence/run.log", "artifact_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "timestamp": "2026-08-20T12:00:00Z"}}
  ],
  "learning_checks": [
    {"check_id": "check.transfer.reconstruct", "kc": "kc.transfer", "type": "reconstruction", "prompt": "Transfer", "success_signal": "Transfer", "failure_prerequisite": null, "evidence": ["anchor.log"]},
    {"check_id": "check.transfer.retrieve", "kc": "kc.transfer", "type": "retrieval", "prompt": "Transfer", "success_signal": "Transfer", "failure_prerequisite": null, "evidence": ["anchor.log"]}
  ],
  "review_queue": []
}
```

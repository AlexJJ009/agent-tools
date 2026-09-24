---
title: Bad code revision fixture
---

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-bad-code-revision",
  "mode": "guided",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.code", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {"id": "kc.code", "ability": "Code", "state": "fragile", "definition": "Code", "why_needed": "Code", "prerequisites": [], "witnesses": ["anchor.code"], "worked_example": "Code", "checks": ["check.code.reconstruct", "check.code.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.code"],
  "evidence_anchors": [
    {"anchor_id": "anchor.code", "claim": "Branch names are mutable.", "source_kind": "code", "layer": "runtime_fact", "status": "verified", "verified_at": "2026-08-20T12:00:00Z", "boundary": "fixture", "locator": {"repository": "agent-tools", "revision": "main", "path": "skills/teaching-reconstruction/scripts/validate_teaching_artifact.py", "line_start": 1, "line_end": 4}}
  ],
  "learning_checks": [
    {"check_id": "check.code.reconstruct", "kc": "kc.code", "type": "reconstruction", "prompt": "Code", "success_signal": "Code", "failure_prerequisite": null, "evidence": ["anchor.code"]},
    {"check_id": "check.code.retrieve", "kc": "kc.code", "type": "retrieval", "prompt": "Code", "success_signal": "Code", "failure_prerequisite": null, "evidence": ["anchor.code"]}
  ],
  "review_queue": []
}
```

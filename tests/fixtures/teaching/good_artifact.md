---
title: Good compiled teaching artifact fixture
---

# Good compiled teaching artifact

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-good-artifact",
  "mode": "artifact",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.artifact", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {
      "id": "kc.artifact",
      "ability": "Compile and audit a durable teaching artifact.",
      "state": "fragile",
      "definition": "The learner can turn a guided reconstruction into a checked artifact.",
      "why_needed": "Compiled artifacts are the durable output of the teaching workflow.",
      "prerequisites": [],
      "witnesses": ["anchor.log.artifact"],
      "worked_example": "Run the validator self-test and attach its log as evidence.",
      "checks": ["check.artifact.reconstruct", "check.artifact.retrieve", "check.artifact.transfer", "check.artifact.audit"]
    }
  ],
  "teaching_edges": [],
  "frontier": ["kc.artifact"],
  "evidence_anchors": [
    {
      "anchor_id": "anchor.log.artifact",
      "claim": "The artifact validator self-test was recorded.",
      "source_kind": "log",
      "layer": "runtime_fact",
      "status": "verified",
      "verified_at": "2026-08-20T12:00:00Z",
      "boundary": "Only proves the referenced run output.",
      "locator": {
        "run_id": "run-good-artifact",
        "artifact_path": "docs/teaching-skills-suite/evidence/good-artifact.log",
        "artifact_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
        "timestamp": "2026-08-20T12:00:00Z"
      }
    }
  ],
  "learning_checks": [
    {
      "check_id": "check.artifact.reconstruct",
      "kc": "kc.artifact",
      "type": "reconstruction",
      "prompt": "Explain the artifact contract.",
      "success_signal": "Mentions marker, manifest, evidence anchors, and checks.",
      "failure_prerequisite": null,
      "evidence": ["anchor.log.artifact"]
    },
    {
      "check_id": "check.artifact.retrieve",
      "kc": "kc.artifact",
      "type": "retrieval",
      "prompt": "Recall the artifact contract from memory.",
      "success_signal": "Names the required manifest sections.",
      "failure_prerequisite": null,
      "evidence": ["anchor.log.artifact"]
    },
    {
      "check_id": "check.artifact.transfer",
      "kc": "kc.artifact",
      "type": "artifact_transfer",
      "prompt": "Transfer the reconstruction into an artifact.",
      "success_signal": "Produces a durable Markdown artifact with the manifest.",
      "failure_prerequisite": null,
      "evidence": ["anchor.log.artifact"]
    },
    {
      "check_id": "check.artifact.audit",
      "kc": "kc.artifact",
      "type": "artifact_audit",
      "prompt": "Audit the compiled artifact.",
      "success_signal": "Finds contract violations by parsing the manifest.",
      "failure_prerequisite": null,
      "evidence": ["anchor.log.artifact"]
    }
  ],
  "review_queue": [
    {
      "card_id": "card.artifact",
      "kc": "kc.artifact",
      "prompt": "Re-audit the artifact after implementation.",
      "due_or_trigger": "after validator implementation",
      "target_note": "[[notes/teaching/good_artifact]]",
      "check_id": "check.artifact.audit",
      "status": "open"
    }
  ]
}
```

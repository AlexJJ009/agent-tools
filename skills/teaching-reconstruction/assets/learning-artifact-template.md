# Learning Artifact

## Reader promise

State the testable ability this artifact builds.

## Prerequisite map

Explain only the dependency path needed for the promise.

## Core reconstruction

Teach in dependency order and keep uncertainty visible.

## Evidence Index

Render each manifest anchor as a human-readable link and boundary.

## Retrieval and transfer checks

Attempt reconstruction before near/far transfer; keep answers separate.

## Review Verdict

Record what an independent reviewer checked and what remains provisional.

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "replace-learning-artifact-id",
  "mode": "artifact",
  "goal": {"target_ability": "Replace with a testable artifact promise.", "success_criteria": ["Reconstruct the mechanism", "Transfer it", "Audit its evidence"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Replace with explicit reader assumptions."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.replace_artifact", "explanation": "Replace with the compiled reconstruction.", "worked_step": "Replace with a faded worked example.", "next_action": "Attempt transfer, then audit the evidence."},
  "knowledge_components": [
    {"id": "kc.replace_artifact", "ability": "Replace with the artifact's target action.", "state": "fragile", "definition": "Replace with a precise definition.", "why_needed": "Replace with why the reader promise requires it.", "prerequisites": [], "witnesses": ["anchor.replace_artifact"], "worked_example": "Replace with one worked example.", "checks": ["check.replace_artifact.reconstruct", "check.replace_artifact.retrieve", "check.replace_artifact.transfer", "check.replace_artifact.audit"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.replace_artifact"],
  "evidence_anchors": [
    {"anchor_id": "anchor.replace_artifact", "claim": "Replace with the smallest supported claim.", "source_kind": "web", "layer": "source_fact", "status": "provisional", "verified_at": "1970-01-01T00:00:00Z", "boundary": "Template placeholder; replace with a durable snapshot before claiming verified evidence.", "locator": {"canonical_url": "https://example.invalid/replace", "retrieved_at": "1970-01-01T00:00:00Z"}}
  ],
  "learning_checks": [
    {"check_id": "check.replace_artifact.reconstruct", "kc": "kc.replace_artifact", "type": "reconstruction", "prompt": "Reconstruct the mechanism.", "success_signal": "Explains mechanism and boundary.", "failure_prerequisite": null, "evidence": ["anchor.replace_artifact"]},
    {"check_id": "check.replace_artifact.retrieve", "kc": "kc.replace_artifact", "type": "retrieval", "prompt": "Recall the dependency path.", "success_signal": "Names the required steps without recognition cues.", "failure_prerequisite": null, "evidence": ["anchor.replace_artifact"]},
    {"check_id": "check.replace_artifact.transfer", "kc": "kc.replace_artifact", "type": "artifact_transfer", "prompt": "Apply the mechanism in a changed setting.", "success_signal": "Preserves the mechanism while adapting surface details.", "failure_prerequisite": null, "evidence": ["anchor.replace_artifact"]},
    {"check_id": "check.replace_artifact.audit", "kc": "kc.replace_artifact", "type": "artifact_audit", "prompt": "Audit the artifact's claims and locators.", "success_signal": "Finds any unsupported upgrade or missing boundary.", "failure_prerequisite": null, "evidence": ["anchor.replace_artifact"]}
  ],
  "review_queue": []
}
```

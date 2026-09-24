# Guided Teaching Session

## Goal

Replace this paragraph with the target ability and success signal.

## ReaderState

- profile sources: `reader_profile/index.md`, `reader_profile/knowledge_map.md`
- assumptions: replace before persisting
- observed gaps: replace from evidence, not guesswork

## Teaching Map

The manifest below is the durable local DAG. Keep the learner-facing view to
the current frontier, one teaching unit, and one check.

## Current Frontier

`kc.replace_me`

## Teaching Unit

Replace this with a worked explanation, then ask the linked retrieval check.

## LearningCheck

Answer from memory before re-opening the source.

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "replace-guided-session-id",
  "mode": "guided",
  "goal": {"target_ability": "Replace with a testable ability.", "success_criteria": ["Replace with an observable success signal."]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Replace before persisting."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.replace_me", "explanation": "Replace with the smallest useful explanation.", "worked_step": "Replace with one worked step.", "next_action": "Attempt the retrieval check from memory."},
  "knowledge_components": [
    {"id": "kc.replace_me", "ability": "Replace with a learner action.", "state": "unknown", "definition": "Replace with a precise definition.", "why_needed": "Replace with why the goal needs this KC.", "prerequisites": [], "witnesses": ["anchor.replace_me"], "worked_example": "Replace with a worked example.", "checks": ["check.replace_me.reconstruct", "check.replace_me.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.replace_me"],
  "evidence_anchors": [
    {"anchor_id": "anchor.replace_me", "claim": "Replace with the smallest supported claim.", "source_kind": "web", "layer": "source_fact", "status": "provisional", "verified_at": "1970-01-01T00:00:00Z", "boundary": "Template placeholder; replace with a durable locator before claiming verified evidence.", "locator": {"canonical_url": "https://example.invalid/replace", "retrieved_at": "1970-01-01T00:00:00Z"}}
  ],
  "learning_checks": [
    {"check_id": "check.replace_me.reconstruct", "kc": "kc.replace_me", "type": "reconstruction", "prompt": "Reconstruct the mechanism in your own words.", "success_signal": "Names the mechanism and its boundary.", "failure_prerequisite": null, "evidence": ["anchor.replace_me"]},
    {"check_id": "check.replace_me.retrieve", "kc": "kc.replace_me", "type": "retrieval", "prompt": "Recall the key step without looking.", "success_signal": "Reproduces the step and explains why it is needed.", "failure_prerequisite": null, "evidence": ["anchor.replace_me"]}
  ],
  "review_queue": []
}
```

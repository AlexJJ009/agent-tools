# Portable learning record

Use this small `learning-record/1` JSON document for new durable learning in code, architecture, logs, or other material outside the ReadPapers library. It is separate from the `task-route/1` record and the frozen `teaching-reconstruction:v1` manifest. The v1 validator continues to validate v1 documents only. Never silently convert or rewrite old notes.

```json
{
  "schema_version": "learning-record/1",
  "goal": "Explain why this design works and where it fails",
  "mode": "guided-direct",
  "source_refs": [{"kind": "code", "repository": "example", "revision": "pending", "path": "src/module.py", "lines": "12-30", "status": "provisional"}],
  "learner_state": {"assumptions": [], "observed_attempts": []},
  "knowledge_components": [],
  "teaching_edges": [],
  "frontier": [],
  "learning_checks": [],
  "next_action": ""
}
```

Use only fields needed for the actual learning task. A source reference must distinguish verified observations from provisional ones and give a recheckable locator. Keep attempts and assistance separate; only observed user behavior supports a learner-state change. A plain short answer needs no durable record. ReadPapers notes may continue to use the v1 envelope where its Zotero and Obsidian fields are meaningful.

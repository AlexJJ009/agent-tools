# Independent PRD review

**Verdict: revise.** This is a document review of the proposed migration and acceptance package, not evidence that any skill, Hook, installer, or learner outcome has been verified. The design keeps Main Agent semantic judgment separate from deterministic checks and bounded host events, distinguishes activity from project and artifact ownership, permits direct manuscript drafting without learner tests, and retains the existing teaching, Zotero, Work Report, and development boundaries. The two findings below prevent the fixed acceptance cases from being reproducible as written.

## Findings

1. **The fixed cases do not identify the materials needed to judge their own expected outcomes.** [validation-cases.json](../validation-cases.json) lines 197–225, 258–321, 324–352, and 418–447 refer to “this paper,” three comparison materials, attached experimental results, an English paragraph, and an experimental-design attachment. Their `setup` values only say to use isolated fixtures; no fixture identity, content, digest, or construction rule appears in the package. Yet T09 expects particular budget/scorer differences (lines 274–277), T10 expects a draft grounded in actual results (lines 306–309), and AC-09 requires an input evidence packet ([checklist.yaml](../checklist.yaml) lines 223–245). Two evaluators can supply different materials and reach incomparable conclusions, while a run could appear to pass without the asserted source facts. Add versioned fixture packets or precise fixture-generation contracts and bind each run manifest to their hashes. It is fine to keep controlled SSH and library targets supplied at execution time, provided their actual identities and evidence are recorded then.

2. **The source-instruction negative control does not cross the source boundary it claims to test.** T06 puts the hostile instruction in the user's `turns` string and supplies no separate attachment ([validation-cases.json](../validation-cases.json) lines 167–193). The PRD correctly says instructions found in read material cannot change the task ([PRD.md](../PRD.md) line 46), but this case observes how Main interprets a user's description of an attachment, not what happens when it reads an actual lower-trust README or attachment. Supply an attachment fixture containing the hostile text and keep the user's repair instruction separate; retain a call trace and before/after library state. This is needed for AC-03's negative side-effect claim ([checklist.yaml](../checklist.yaml) lines 73–99).

## Follow-up precision

AC-06 explicitly calls for stale bound-state failure injection ([checklist.yaml](../checklist.yaml) lines 151–173), while its linked cases cover disabled Hooks, unbound sessions, missing material, and unavailable capability rather than a stale route revision. The procedure can be executed without a new fixed case, but its run manifest should name the stale-revision input and observed rejection so AC-20's fixed-case report does not imply this control was exercised by T14/T21/T22/T28 alone.

The captured baseline points to accessible local sources, and the current Hook implementation supports the PRD's limited coverage statement: it requires an explicit schema-2 binding and recognizes only selected Bash commands ([agent_workflow/hooks.py](/home/alex_mercer/projects/agent-tools/agent_workflow/hooks.py:42), [agent_workflow/hooks.py](/home/alex_mercer/projects/agent-tools/agent_workflow/hooks.py:98)). Existing managed actions recheck prerequisites at their execution boundary ([agent_workflow/managed.py](/home/alex_mercer/projects/agent-tools/agent_workflow/managed.py:74)). I found no basis to mark any implementation checklist item complete. AC-21 appropriately remains the only human pilot item; its actual feedback remains pending.

## Reviewed artifact digests

| Artifact | SHA-256 |
|---|---|
| `PRD.md` | `78dc707fd1e6fd8272bc836bfc15fb8290cf0fad5ca56ae0d468d66591bcce5a` |
| `checklist.yaml` | `9b762ff3058f8f28128747cdbc1a88e1dbf377f836bc83f622942e18322301d1` |
| `validation-cases.json` | `ea897dcc625568f111bdf47d98e484aab3c54c8ac56d3b3a54594b3f57264287` |

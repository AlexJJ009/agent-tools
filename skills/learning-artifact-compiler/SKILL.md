---
name: learning-artifact-compiler
description: Compile already-verified teaching session state into a standalone tutorial, blog, note, or review artifact. Use when explicitly asked to compile, package, publish-ready draft, or convert verified learning state into an artifact.
---

# Learning Artifact Compiler

Turn verified guided-learning state into durable writing without inventing new evidence or hiding uncertainty.

## Workflow

1. For a compiled learning artifact, confirm the relevant prerequisite path, evidence anchors, and checks exist or mark the gaps. Direct manuscript drafting and revision belong to `academic-writing` and do not need teaching state.
2. Choose artifact form: tutorial, blog, study note, review memo, or audit report.
3. Preserve source boundaries and provisional labels.
4. Include reconstruction and transfer checks unless the user explicitly asks for prose only.
5. When the request includes curation into a knowledge directory, follow the curation procedure below; a saved Markdown file alone does not complete that request.

## Explicit Curation

Distinguish drafting a note in its source project from exporting that note to the requested knowledge directory, including a directory inside the same project. Stage the finished note in the source workspace, then use the existing `learning-workflow curate` entry with the current task record, revision, stable `project_id`, and authorized destination. See `task-routing` and CLI help for its arguments. Do not replace this step with `check-action write_artifact` followed by a direct copy: that checks a declared write scope but does not create the required provenance index.

Before claiming curation complete, read back the actual `artifact-index.json` and exported note using `inspect-index --index PATH --source-root DIR`. Verify the source project/version/path, artifact digest, and expected single entry. Reimport uses the same source identity and preserves subsequent user edits. If the source becomes inaccessible after relocation, report that observed limit; do not claim synchronization. Missing curation state is corrected in the existing record, not by opening a replacement task. Publication and Zotero ingestion remain separate actions requiring their own scope.

Read `references/artifact-compilation.md` for artifact patterns. Use `../teaching-reconstruction/references/artifact-contract.md` only for legacy v1 ReadPapers manifests; use `../teaching-reconstruction/references/portable-learning-record.md` for new portable learning records when a durable record is needed.

Use `../teaching-reconstruction/assets/learning-artifact-template.md` only when a v1 ReadPapers artifact is appropriate. Apply W1–W9 from `../work-report/references/writing-contract.md` to reader-facing prose. A blog draft is a writing artifact; external publication needs its own authorization.

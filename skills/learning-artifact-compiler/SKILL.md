---
name: learning-artifact-compiler
description: Write or revise requested standalone learning material such as a tutorial, study note, blog, or retrospective from inspected sources or existing learning state. Learner exercises need not be completed first; ordinary explanations do not require a saved artifact.
---

# Learning Artifact Compiler

This is Agent Tools' learning-document capability, normally selected by Main or `teaching-reconstruction`. The user does not need to know this internal name. Turn inspected sources or existing learning state into requested durable writing without inventing evidence or treating polished prose as learner mastery.

## Writing and revision

- Use relevant learning state or inspected sources and stated reader assumptions. Explain prerequisite knowledge and mark evidence gaps. Direct manuscript drafting and revision belong to `academic-writing`.
- Choose the requested artifact form: tutorial, blog, study note, review memo, or audit report.
- Preserve source boundaries and provisional labels.
- Use `retrieval-practice` when practice serves the learning request; respect prose-only or deferred-practice requests. Select retention targets to fit the learner's effort, without a fixed question mix. Keep answers separate in live practice; a self-study document may include a separate or folded key.
- When the request includes curation into a knowledge directory, follow the curation procedure below; a saved Markdown file alone does not complete that request.

Deliver a complete, coherent first draft at the requested scope, introducing the problem and organizing sections around useful questions. Support selective reading and partial feedback: revise the same artifact at the appropriate scale while retaining valid evidence. Keep material review, reading progress, observed practice, and learner-selected retention distinct; a finished document does not establish mastery.

## Explicit Curation

Distinguish drafting a note in its source project from exporting that note to the requested knowledge directory, including a directory inside the same project. Stage the finished note in the source workspace, then use the existing `learning-workflow curate` entry with the current task record, revision, stable `project_id`, and authorized destination. See `task-routing` and CLI help for its arguments. Do not replace this step with `check-action write_artifact` followed by a direct copy: that checks a declared write scope but does not create the required provenance index.

Before claiming curation complete, read the actual `artifact-index.json` and exported note to verify the source project/version/path and content. There must be one entry for this source identity; retain unrelated entries in a shared index. Separately run `inspect-index --index PATH --source-root DIR` to check artifact availability, digest consistency, and source availability; it does not return note text or provenance fields. Reimport uses the same source identity and preserves subsequent user edits. If the source becomes inaccessible after relocation, report that observed limit; do not claim synchronization. Missing curation state is corrected in the existing record, not by opening a replacement task. Publication and Zotero ingestion remain separate actions requiring their own scope.

Read `references/artifact-compilation.md` for artifact patterns. Use `../teaching-reconstruction/references/artifact-contract.md` only for legacy v1 ReadPapers manifests; use `../teaching-reconstruction/references/portable-learning-record.md` for new portable learning records when a durable record is needed.

Use `../teaching-reconstruction/assets/learning-artifact-template.md` only when a v1 ReadPapers artifact is appropriate. The shared writing contract applies. A blog draft is a writing artifact; external publication needs its own authorization.

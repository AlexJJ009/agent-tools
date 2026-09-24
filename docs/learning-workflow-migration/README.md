# Learning workflow migration — review package

This package specifies a future migration. It does not install skills, change current routing, or demonstrate implemented behavior.

- [PRD.md](PRD.md): Chinese explanation of scope, architecture, English instruction policy, migration order and completion boundaries.
- [checklist.yaml](checklist.yaml): 21 acceptance criteria, all implementation statuses initially `not_run`.
- [validation-cases.json](validation-cases.json): 30 fixed cases, including negative requests, multi-turn transitions, manuscript work, project boundaries and installation failure controls.
- [fixtures/README.md](fixtures/README.md): seven fixed synthetic source files, construction rules, and a digest manifest for reproducible material/attachment tests.
- [baseline/inventory.json](baseline/inventory.json): captured source identities and SHA-256 values for eight existing instruction/router files; the snapshots are review-only, not maintained skill copies.
- [reviews/review-brief.md](reviews/review-brief.md): bounded independent document-review scope.
- [Final independent document review](reviews/independent-review-round2.md): PASS for the design and acceptance package; the [first review](reviews/independent-review-round1.md) preserves the issues that were corrected.
- [Package consistency checks](reviews/package-checks.json): IDs, mappings, pending states, local links and snapshot/material digests. This is not implementation acceptance.

## What is already evidence

The earlier [routing probes](../work-reports/20260920T030723Z-academic-writing-and-research-learning-e68e93d3/revisions/20260924-portable-teaching-boundary/router-probes.json) are actual direct calls to the current router. The [existing test result](../work-reports/20260920T030723Z-academic-writing-and-research-learning-e68e93d3/revisions/20260924-portable-teaching-boundary/existing-trigger-tests.json) records five passing test methods. Neither demonstrates native skill selection or the future migration.

The original expanded survey is at [the local ReadPapers note](/home/alex_mercer/projects/obsidian-vault/read_papers/insights/academic-writing-and-research-idea-learning.md). Its [source index](../work-reports/20260920T030723Z-academic-writing-and-research-learning-e68e93d3/SOURCES.md) and [community snapshots](../work-reports/20260920T030723Z-academic-writing-and-research-learning-e68e93d3/community/sources.json) preserve the related-work provenance. These host-specific paths are evidence locators, not proposed hard-coded runtime defaults.

## Acceptance states

`checklist.yaml` is a planning specification, not the generated canonical checklist of `agent-workflow`. During implementation, bind it to the actual candidate and record real observations through the chosen task runtime. Document review, source snapshots, example queries and successful YAML parsing cannot mark an implementation item passed.

Only AC-21 requires the focused human pilot. Other criteria can be checked technically or by an independent Agent; the human may still inspect any item. No report or reviewer may infer the user's acceptance.

## Maintenance

Maintained skill instructions, descriptions, rule templates, reviewer prompts and CLI guidance will be English. User-facing output follows the user's language and requested genre. Preserve original-language quotes and test inputs. The PRD itself is reader-facing design material and therefore uses Chinese.

The migration begins with isolated routing/boundary changes and retains the existing teaching prompts. Fleet deployment, central synchronization and external publication are outside this implementation scope.

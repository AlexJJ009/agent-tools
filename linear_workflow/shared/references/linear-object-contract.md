# Linear object contract

`Project` is a bounded product or engineering outcome. Its canonical PRD is a
Linear Document. `Issue` is an independently verifiable work item. A
`workflow:batch` parent Issue groups leaf Issues that share a candidate and
review boundary. Native `blocked by`/`blocking` relations form the DAG.

Every proposed Issue declares exactly one destination:

- `github_to_linear`: create the approved GitHub Issue in an explicit
  `owner/repository`, then reuse the unique native-synced Linear Issue.
- `linear_only`: keep discovery, coordination, or non-code work only in Linear.

Never repair a missing sync by creating a parallel Linear Issue. Never use
title similarity to choose duplicates. A `duplicateOf` relation is canonical.
Every production-code leaf has one primary repository. A Batch includes its
Issues, repositories, acceptance, risk profile, and full-CI point.

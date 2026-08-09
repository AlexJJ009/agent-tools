# Linear Document template: 产品需求文档｜PRD

This Document is the only editable copy of the Project's product requirements.
Technical designs, ADRs, API/schema contracts, migrations, and runbooks live in
their repositories and are linked here. Replace or remove all prompts before
approval.

## Template body

### Document control

- **Project**: {Linear Project link}
- **Status**: Draft / In review / Approved / Superseded
- **Product owner**: {owner}
- **Reviewers**: {reviewers}
- **Last reviewed**: {date}

### Problem and evidence

{Current behavior, affected actors, impact, and evidence.}

### Goals

- {Observable product outcome.}

### Non-goals

- {Explicit adjacent work not included.}

### Proposed behavior

{Primary flow plus failure and edge behavior.}

### Scope

- **Included**: {capabilities and canonical owner/repository values}
- **Excluded**: {capabilities}

### Product acceptance

- [ ] {End-to-end observable result and evidence type.}

### Constraints, risk, and release policy

{Security, privacy, money, compatibility, operational, rollout, and rollback decisions.}

### Technical references

- **Technical design**: {repo link or None}
- **ADR**: {repo link or None}
- **API/schema contract**: {repo link or None}
- **Migration/runbook**: {repo link or None}

### Delivery decomposition

Every proposed work item declares `github_to_linear` or `linear_only`. Every
production-code leaf has one primary `owner/repository`. Native Linear
dependencies define an acyclic DAG. Each Batch records included Issues,
repositories, acceptance, risk profile, and the full-CI point.

### Open questions

{Approved PRDs must contain no blocking questions.}

### Approval

- [ ] Product owner approved problem, goals, non-goals, scope, and acceptance.
- [ ] Issue DAG and Delivery Batches were reviewed as one decomposition.
- [ ] Every code Issue has one explicit GitHub repository and unique synced mapping.

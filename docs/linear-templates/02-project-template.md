# Linear Project template: 项目交付｜Project Delivery

- **Default status**: `Backlog`
- **Use for**: one bounded outcome requiring multiple Issues
- **Do not use for**: a permanent product area, repository category, or one small bug

The Project description stores a short outcome and navigation. It does not copy
the PRD Document.

## Template body

### Project outcome

{One sentence describing the complete result.}

### Why now

{Current problem, impact, and reason to act.}

### Product requirement

- **PRD Document**: {linked `产品需求文档｜PRD` Document}
- **PRD status**: Draft / In review / Approved
- **Product owner**: {owner}

### Scope map

- **Affected products/services**: {values}
- **Repositories**: {canonical owner/repository values}
- **External systems**: {values or None}

### Delivery strategy

- Code Issues originate in the explicit GitHub repository and sync to Linear.
- Linear-only planning and coordination work remains only in Linear.
- Native relations define the DAG; `workflow:batch` parents define delivery batches.
- Each Issue gets targeted checks; each fixed Batch candidate gets one full-CI/review boundary.
- Cross-repository delivery requires independent PRs and High-risk joint candidate evidence.

### Project completion criteria

- [ ] Product acceptance in the approved PRD is satisfied.
- [ ] In-scope Issues are complete or explicitly canceled.
- [ ] GitHub/Linear synced work items are unique and correctly mapped.
- [ ] Planned PRs are merged or have a recorded cancellation reason.
- [ ] Required release, rollback, and operational evidence exists.

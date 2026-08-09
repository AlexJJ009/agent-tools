# DragAI Linear Team templates

These files are the versioned definitions for the existing Linear templates.
The deployed Linear templates are manual copies; live Project, Document, Issue,
dependency, risk, and status data remains canonical in Linear.

| Object | Template name | Default |
| --- | --- | --- |
| Issue | `需求收集｜Discovery / Triage` | `Backlog` |
| Project | `项目交付｜Project Delivery` | `Backlog` |
| Document | `产品需求文档｜PRD` | no execution status |

Do not create status labels. DragAI uses native `Ready` and `Blocked` statuses.
Repository fields use `owner/repository`; GitHub references use
`owner/repository#number`. Code work starts in GitHub and reuses the native
synced Linear Issue. Linear-only work does not get an unapproved GitHub copy.

The three definitions are:

1. [`01-issue-template.md`](01-issue-template.md)
2. [`02-project-template.md`](02-project-template.md)
3. [`03-prd-document-template.md`](03-prd-document-template.md)

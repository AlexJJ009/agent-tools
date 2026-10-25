# Retire the task runtime, work reports and Codex desktop patches

Date: 2026-10-25

Status: Accepted

## Context and Problem Statement

The development skills (intent-to-contract, acceptance-gate, infra-verification,
reviewer-brief, cleaner), the Task Runtime with its material ledger, and Work
Report were built so that Codex could run long-horizon tasks across several
context compactions without losing its checklist or progress. Each later layer
mostly handled the previous layer's output: agent-written PRDs and process files
needed a cleaner, the cleaner needed a ledger, and the ledger and task state
needed an installed runtime with hooks on every Claude and Codex event.

The way the user works has changed. Claude now plans and supervises, Codex
implements small dispatched steps, and the user decomposes intent before
dispatch. The bottlenecks observed in PHAI Relay are unclear intent and waiting
for smoke runs, not agent memory (PHAI Relay `dev-cycle-latency-20261022`:
deploy-to-smoke loop 68 %, Codex coding 14 %). Contract files written by an agent
from vague intent fixed the wrong intent and produced material nobody read.

Usage between 2026-10-08 and 2026-10-25 (Claude logs on WSL and PHAI, 1052 Codex
sessions on PHAI): intent-to-contract, acceptance-gate, task-routing,
teaching-dag-builder, learning-artifact-compiler, retrieval-practice,
knowledge-deposition-doc and wxpusher-notify were never invoked. work-report,
reviewer-brief, infra-verification and cleaner were read mainly by dispatched
Codex jobs; the user judged their output not worth its cost. The task database
was last written on 2026-10-03. The learning hooks ran on five events per Claude
and Codex session while only academic-writing saw use.

## Decision Outcome

Removed from source and from installed clients:

- Task Runtime and legacy Agent Workflow (`agent_workflow/`, `agent-workflow`
  CLI, hooks), the material ledger (`shared/materials.py`) and process cleanup.
- Skills intent-to-contract, acceptance-gate, infra-verification, reviewer-brief,
  cleaner, work-report (with its hooks and timer) and the
  knowledge-deposition-doc alias.
- The learning runtime (`learning_workflow/`, `learning-workflow` CLI, routing
  and Stop hooks, route state under `~/.local/state/learning-workflow`), and the
  hook scripts inside teaching-reconstruction.
- The Claude hook adapter. Agent Tools registers no Claude or Codex hooks.
- Codex desktop and Win11 patches: Fast mode configuration, desktop connection
  Fast mode patch, SQLite log guard, Win11 subscription configuration,
  codex-win11-patch-safety, and the retired project-memory migration tool.
- `project_adapters/read_papers` moved to the ReadPapers tooling repository.

Kept, as plain skills without runtime state: academic-writing,
teaching-reconstruction, evidence-anchor, retrieval-practice,
teaching-dag-builder, learning-artifact-compiler and task-routing (the user asked
to keep the learning skills and remove only their hooks). Their instructions no
longer call a learning CLI or ledger; the user's request and the conversation
carry the route. Also kept: manage-worktrees and `agent-wt` (PHAI Relay depends
on them), the shared reader-facing writing contract, and components outside
this decision (context sync, server bootstrap, `codex-here`, target and fleet
guards, provider migration, WSL2 proxy, project evaluation skills).

The read-paper skill belongs to the ReadPapers project, not Agent Core.

Data removed from `~/.local/share/{agent-tools,agent-workflow,agent-tools-main,linear-workflow}`
and `~/.local/state/learning-workflow` on WSL was archived first in
`~/.local/share/claude-archives/agent-tools-20261025-cleanup/`.

### Consequences

- Each prompt and Bash call no longer starts agent-tools Python hook processes.
- Long-horizon autonomous runs have no persisted checklist or report timer. Long
  work is decomposed by the user and supervised by Claude instead.
- `install.sh` links the seven kept learning and writing skills into
  `~/.agents/skills` on every machine by default, and `--check` expects those
  links; pass `--no-learning-skills` where they are not wanted.
- Learning sessions no longer persist routes across sessions; the user restates
  context when resuming.
- Git history before this record holds the removed implementation. A new
  explicit decision is required to reintroduce any of it.

# Codex Project Memory

Codex native memories are user-level generated state under `~/.codex/memories/`.
They are useful, but they are not the same as Claude Code's per-project auto
memory directory.

To get project-level memory behavior, use an explicit project-local layer:

```text
<project>/.codex/project-memory/
├── MEMORY.md
└── imported-claude-memory/
    ├── MEMORY.md
    └── ...
```

Then add a short instruction to the project context (`CLAUDE.md` or `AGENTS.md`)
telling Codex when to read `.codex/project-memory/MEMORY.md`.

## Why This Exists

Codex's own memory system should remain enabled and untouched:

```toml
[features]
memories = true
```

But project-specific memory is better stored in the repo or worktree, because:

- it follows the project across machines and WSL2 distributions;
- it can be reviewed like normal Markdown;
- it can reuse Claude Code auto-memory topic files;
- it avoids hand-editing Codex's generated `~/.codex/memories/` files.

## Setup

From the project root:

```bash
python /data-1/agent-tools/codex_project_memory.py sync . --direction both
```

What it does:

- creates `.codex/project-memory/MEMORY.md` if missing;
- adds a guarded `Codex Project Memory` instruction block to `CLAUDE.md` when
  present, otherwise `AGENTS.md`;
- if Claude Code auto memory exists at
  `~/.claude/projects/<encoded-project>/memory/`, copies Markdown files into
  `.codex/project-memory/imported-claude-memory/`;
- if Codex project memory contains topic files that Claude does not have,
  copies them into
  `~/.claude/projects/<encoded-project>/memory/imported-codex-memory/`;
- updates the project-memory index with a link to the imported Claude memory.

If the project uses the Claude/Codex bridge, refresh it after setup:

```bash
python /data-1/agent-tools/sync_agent_context.py sync . --direction bidirectional
```

## Status Check

```bash
python /data-1/agent-tools/codex_project_memory.py status .
```

Expected output includes:

```text
memory_index=<project>/.codex/project-memory/MEMORY.md exists=True
CLAUDE.md=exists project_memory_instruction=True
```

or, for Codex-only projects:

```text
AGENTS.md=exists project_memory_instruction=True
```

## How Codex Should Use It

The installed instruction tells Codex:

- read `.codex/project-memory/MEMORY.md` before history-dependent work;
- open only topic files relevant to the task;
- treat dated experiment status as stale until verified;
- avoid storing secrets.

This gives Codex a project-level recall path similar to Claude Code auto memory,
while keeping Codex's native generated memories intact.

## Importing Claude Code Auto Memory

Claude Code stores project auto memory under:

```bash
~/.claude/projects/<encoded-project>/memory/
```

For `/data-1/verl07/verl`, the path is:

```bash
/root/.claude/projects/-data-1-verl07-verl/memory/
```

The project-memory tool derives that path from the git root by replacing `/`
with `-`.

The imported directories are generated mirrors. Re-running sync refreshes them
from their source side:

```bash
python /data-1/agent-tools/codex_project_memory.py sync . --direction both
```

Edit source notes in `.codex/project-memory/` or Claude memory, not in
`imported-*` directories.

## Bidirectional Sync

See `AGENT_MEMORY_SYNC.md` for the full agent workflow. The short version:

```bash
python /data-1/agent-tools/codex_project_memory.py status . --search-native
python /data-1/agent-tools/codex_project_memory.py sync . --direction both
```

If `--search-native` reports relevant hits under `~/.codex/memories/`, summarize
durable Codex-native lessons into `.codex/project-memory/*.md`, then run sync
again. Do not copy raw generated Codex native memory files wholesale.

## Portability

This is portable to other servers and WSL2 machines as long as:

- the project has `AGENTS.md` or `CLAUDE.md`, or the tool is allowed to create
  `AGENTS.md`;
- Codex is run from the same project root or a subdirectory;
- the project context tells Codex to read `.codex/project-memory/MEMORY.md`;
- if importing Claude memory, Claude Code has already created the matching
  `~/.claude/projects/<encoded-project>/memory/` directory.

## Limits

This is not a native Codex memory backend. It is a project-context convention
that Codex can follow. Keep the index short and concrete. For hard rules that
must always apply, keep them in `AGENTS.md` / `CLAUDE.md`; for detailed
workflow knowledge, link topic files from project memory.

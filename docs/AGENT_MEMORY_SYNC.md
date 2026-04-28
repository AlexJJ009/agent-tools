# Agent Memory Sync

This runbook configures project-level memory sharing between Claude Code and
Codex. It is designed for agents to execute directly, and for humans to run as
a script on Linux servers or WSL2 machines.

## Goal

Keep project memory synchronized in both directions:

- Claude Code auto memory:
  `~/.claude/projects/<encoded-project>/memory/`
- Codex project memory:
  `<project>/.codex/project-memory/`

Claude Code and Codex do not use the same native memory backend. Do not copy
raw generated Codex native memory wholesale into Claude. Instead, synchronize
project-level Markdown memory and keep generated native memories as source
material that an agent can summarize when needed.

## One-Command Project Sync

Run from any directory inside the target project:

```bash
python /data-1/agent-tools/codex_project_memory.py sync . --direction both
```

What this does:

- finds the git root for the project;
- creates `.codex/project-memory/MEMORY.md` if missing;
- adds a guarded Codex project-memory instruction block to `CLAUDE.md` when
  present, otherwise `AGENTS.md`;
- copies Claude Markdown memory into
  `.codex/project-memory/imported-claude-memory/`;
- copies Codex project memory topic files into
  `~/.claude/projects/<encoded-project>/memory/imported-codex-memory/`;
- updates both memory indexes with links to the imported side.

The `imported-*` directories are generated mirrors. Re-running sync refreshes
those imported copies from their source side. Edit durable source notes in the
native project memory directory (`.codex/project-memory/`) or Claude memory
directory, not inside an `imported-*` mirror.

## Agent Workflow

When a user asks an agent to synchronize memories for a project, the agent
should do this:

1. Check current state:

   ```bash
   python /data-1/agent-tools/codex_project_memory.py status . --search-native
   ```

2. If native Codex memory hits are reported under `~/.codex/memories/`, inspect
   only the project-relevant snippets. Summarize durable lessons into a topic
   file under `.codex/project-memory/`, for example:

   ```text
   .codex/project-memory/codex-native-summary.md
   ```

   Do not migrate raw rollout summaries or generated native memory files
   wholesale.

3. Run bidirectional project sync:

   ```bash
   python /data-1/agent-tools/codex_project_memory.py sync . --direction both
   ```

4. If this project uses the Claude/Codex context bridge, refresh it:

   ```bash
   python /data-1/agent-tools/sync_agent_context.py sync . --direction bidirectional
   ```

5. Re-check status:

   ```bash
   python /data-1/agent-tools/codex_project_memory.py status . --search-native
   ```

## Manual Discovery

Find Claude memory folders:

```bash
find ~/.claude/projects -path '*/memory/MEMORY.md' -print
```

Find Codex project memory folders under common project roots:

```bash
find /data-1 ~/projects /workspace -path '*/.codex/project-memory/MEMORY.md' -print 2>/dev/null
```

Search Codex native memory for one project:

```bash
python /data-1/agent-tools/codex_project_memory.py status /path/to/project --search-native
```

## Directional Sync

Claude to Codex only:

```bash
python /data-1/agent-tools/codex_project_memory.py sync /path/to/project --direction claude-to-codex
```

Codex project memory to Claude only:

```bash
python /data-1/agent-tools/codex_project_memory.py sync /path/to/project --direction codex-to-claude
```

Use Codex-to-Claude when `.codex/project-memory/` contains durable project
lessons that Claude Code does not yet have. The destination is Claude's
`imported-codex-memory/` mirror.

## Portability Notes

- The encoded Claude project path is derived from the git root by replacing `/`
  with `-`. Example: `/data-1/verl07/verl` becomes
  `~/.claude/projects/-data-1-verl07-verl/memory/`.
- Sync Markdown topic files, not secrets, credentials, API keys, or raw logs.
- Treat dated experiment status, checkpoint paths, and live service state as
  stale until verified on the current machine.
- Keep hard project rules in `AGENTS.md` / `CLAUDE.md`; keep detailed lessons
  and history in project memory topic files.

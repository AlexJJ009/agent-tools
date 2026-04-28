# Claude Auto Memory To Codex Context

This runbook explains what can and cannot be migrated from Claude Code memory
into Codex, and gives a safe migration path for Linux servers and WSL2 machines.

## Short Answer

Claude Code auto memory can be migrated for Codex to use, but not by directly
copying it into Codex's generated `~/.codex/memories/` store.

Use this model instead:

1. Treat Claude auto memory as source material.
2. Mirror or summarize it into a Codex-readable project memory directory.
3. Reference that note from project `AGENTS.md` or from the shared agent context
   bridge.
4. Let Codex's own memory system learn from future Codex threads naturally.

Do not hand-edit `~/.codex/memories/` as the primary migration interface. Codex
documents that directory as generated state, useful to inspect but not the main
control surface.

## Mechanism Differences

| Area | Claude Code | Codex |
|---|---|---|
| Explicit project instructions | `CLAUDE.md`, `.claude/rules/` | `AGENTS.md`, `.codex/` config/rules |
| Auto memory location | `~/.claude/projects/<project>/memory/` | `~/.codex/memories/` |
| Auto memory format | Plain Markdown files with `MEMORY.md` index plus topic files | Generated Markdown summaries, indexes, rollout evidence, raw memories |
| Startup behavior | Claude loads first 200 lines or 25KB of auto-memory `MEMORY.md`; topic files are read on demand | Codex injects selected memory summaries based on its own memory retrieval/consolidation logic |
| Scope | Per working tree / git repo | User-level generated local recall; project relevance is inferred |
| Manual editing | Claude docs say auto-memory Markdown can be read, edited, or deleted | Codex docs say memory files are generated state; inspect them, but do not rely on hand-editing as primary control |
| Best migration method | Copy/summarize Markdown into shared project context | Read through `AGENTS.md` / project docs; then allow Codex memories to rebuild from Codex work |

## Confirmed Claude Layout

For this repo on this host:

```bash
/root/.claude/projects/-data-1-verl07-verl/memory/
```

Current files include:

```text
MEMORY.md
feedback_hf_upload.md
feedback_language.md
feedback_n1_vs_n3.md
feedback_subagent_model.md
feedback_tmux.md
project_reverse_sft.md
project_training_status.md
user_profile.md
```

This is not just transcript history. It is already distilled project memory.
It is higher value than raw files under:

```bash
/root/.claude/projects/<project>/*.jsonl
```

The JSONL files are full session transcripts. Do not migrate them wholesale;
summarize them only when a specific missing lesson is needed.

## Recommended Migration

For a project that already has an `AGENTS.md` / `CLAUDE.md` bridge, the cleanest
path is:

1. Initialize and synchronize the project-local memory layer:

   ```bash
   python /data-1/agent-tools/codex_project_memory.py sync . --direction both
   ```

   This creates `.codex/project-memory/MEMORY.md`, imports Claude Markdown into
   `.codex/project-memory/imported-claude-memory/`, and adds a guarded Codex
   project-memory instruction block to `CLAUDE.md` when present, otherwise
   `AGENTS.md`.

2. Run the existing context bridge:

   ```bash
   python /data-1/agent-tools/sync_agent_context.py sync . --direction bidirectional
   ```

This makes the imported memory visible through Codex's normal instruction
surface without mutating Codex's generated memory store.

## One-Shot Sync Script

Run from the project root. This is the preferred one-shot command:

```bash
python /data-1/agent-tools/codex_project_memory.py sync . --direction both
```

Then sync the bridge if the project keeps Claude and Codex context mirrored.

## When To Use Native Codex Memories

Codex native memories are still valuable after migration:

- Keep `[features].memories = true` in `~/.codex/config.toml`.
- Let Codex generate memories from future Codex threads.
- Use `/memories` per thread when a task should not use or generate memories.
- Review `~/.codex/memories/` before sharing a Codex home directory.

The imported Claude memory should be treated as bootstrapping context, not as a
replacement for Codex's own memory extraction.

## Staleness Rules

Claude auto memory can contain dated experiment status. Before acting on it:

- Verify live training state with tmux, logs, checkpoints, and `df`.
- Verify experiment status against active plans and `CLAUDE.md` / `AGENTS.md`.
- Use old memory for workflow lessons and known pitfalls more readily than for
  current run status.
- Never treat checkpoint paths, WandB sync status, or "currently running" notes
  as current without re-checking.

## Agent Checklist

When configuring a new server or WSL2 machine:

1. Enable Codex memories in `~/.codex/config.toml`.
2. Configure default AutoReview if desired; see `CODEX_AUTOREVIEW_DEFAULT.md`.
3. Find Claude auto memory:

   ```bash
   find ~/.claude/projects -path '*/memory/MEMORY.md' -print
   ```

4. For each important project, initialize project memory:

   ```bash
   python /data-1/agent-tools/codex_project_memory.py sync /path/to/project --direction both
   ```

5. Run the Claude/Codex context bridge.
6. Start a fresh Codex session and ask it to summarize which imported memory
   files are relevant before doing history-dependent work.

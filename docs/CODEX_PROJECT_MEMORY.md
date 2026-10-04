# Project Memory Sync and Migration

Use `scripts/codex_project_memory.py` to share explicit project Markdown memory
between Claude Code and Codex. Native generated Codex memories are a separate,
user-level store; copying Claude memory there is not this tool's interface.

## Storage and ownership

| Store | Location | Maintained source |
|---|---|---|
| Claude project memory | `~/.claude/projects/<encoded-project>/memory/` | Claude index and topic files |
| Explicit Codex project memory | `<project>/.codex/project-memory/` | Codex index and topic files |
| Claude imported into Codex | `.codex/project-memory/imported-claude-memory/` | Generated copy of Claude source |
| Codex imported into Claude | `memory/imported-codex-memory/` | Generated copy of Codex source |
| Native Codex recall | `~/.codex/memories/` and native memory database | Codex-generated state |

The encoded Claude path is derived from the project Git root by replacing `/`
with `-`. Run this tool under the user who owns the target project memory.
Edit durable notes in their source directory, not in an imported mirror.
Keep reusable lessons and context; dated process status and transient recovery
notes are not permanent instructions. Do not copy credentials or raw session
transcripts into memory.

## Inspect and synchronize

From the Agent Tools checkout:

```bash
python3 scripts/codex_project_memory.py status /path/to/project --search-native
python3 scripts/codex_project_memory.py sync /path/to/project --direction both
python3 scripts/codex_project_memory.py status /path/to/project
```

`sync` finds the Git root, initializes `.codex/project-memory/MEMORY.md`, and
adds a guarded instruction block to `CLAUDE.md` when present, otherwise
`AGENTS.md`. That block asks Codex to read the index for history-dependent work
and open only relevant topic files. It copies Markdown into the imported
folders, excludes recursive reimports, and writes links in the indexes.

Directions are `both`, `claude-to-codex`, and `codex-to-claude`. `.` may replace
the target path when running inside the target project, using the installed
helper's absolute path:

```bash
python3 ~/.local/lib/agent-tools/scripts/codex_project_memory.py sync . --direction both
```

Existing differing imported files are reported as conflicts unless `--force`
is selected. Inspect the source and destination before choosing a winner.
Sync copies source Markdown; it does not delete imported files whose source
was removed. During cleanup, reconcile those stale copies and their indexes
explicitly so a later sync cannot reintroduce a retired lesson.

If the project uses the context bridge, refresh it after the memory update:

```bash
python3 scripts/sync_agent_context.py sync /path/to/project --direction bidirectional
```

See [context synchronization](CONTEXT_SYNC.md) for bridge conflict behavior.

## Migrate existing memories

Claude auto memory is already distilled project context and can seed the
explicit Codex layer through the sync command above. Review it first for
obsolete topology, dated experiments, duplicate rules and secrets. Do not copy
all Claude JSONL conversations as a substitute for selecting useful lessons.

When `status --search-native` reports matching Codex-native snippets, inspect
only relevant entries and summarize useful project lessons into a topic file
under `.codex/project-memory/`. Then synchronize that explicit note. Preserve
source attribution and limits; native rollout summaries contain historical
observations and do not establish current machine state.

The native Codex `memories` feature is independent of explicit project memory.
Preserve the target user's chosen setting rather than enabling it as a migration
requirement. In particular, PHAI's memories-off comparison started on
2026-10-03 and remains subject to the user's decision; installing or syncing
project memory is not authorization to end that experiment.

## Check the result

`status` reports whether the index and project instruction block exist. Open
the actual indexes and selected imported topic files to verify content and
conflicts; file existence alone does not prove useful or current memory.
Before acting on remembered services, proxy settings, checkpoint paths or
running experiments, check the live target host. Keep hard project rules in
`AGENTS.md` / `CLAUDE.md` and detailed lessons in topic files.

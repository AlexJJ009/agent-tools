# Skill ownership and installed scope

This is the observed 2026-09-27 WSL Codex installation. The user clarified that
reusable agent-tools capabilities belong at user scope; paper-source management
and Markdown Proxy belong in ReadPapers. Folder names alone do not establish
ownership: native discovery and the source behind each link are listed separately.

| Capability | Maintained source | Codex installation / owner |
|---|---|---|
| `task-routing`, `academic-writing`, `teaching-reconstruction`, `teaching-dag-builder`, `evidence-anchor`, `retrieval-practice`, `learning-artifact-compiler` | agent-tools `skills/`; installed version copied independently of its worktree | `~/.agents/skills/<name>`; user-level, available in development, manuscript and ReadPapers projects as appropriate |
| `read-paper` | agent-tools `project_adapters/read_papers/read-paper` packages the specialized adapter; ReadPapers owns its configuration, notes and library operations | `read_papers/.agents/skills/read-paper`; project-level only |
| `arxiv-downloader` | Existing legacy source, unchanged | Individual `read_papers/.codex/skills/arxiv-downloader` link; project-level |
| `markdown-proxy` (metadata name `qiaomu-markdown-proxy`) | Existing legacy source, unchanged | Individual `read_papers/.codex/skills/markdown-proxy` link; project-level |
| `xhs-reader` | Existing legacy source, unchanged | Individual `read_papers/.codex/skills/xhs-reader` link; project-level |
| Existing development acceptance/reporting skills | Their existing agent-tools sources | Existing user-level entries remain; learning routing does not replace their contracts |

The paper adapter may be packaged by agent-tools without becoming a user-level
skill. Library content, ZotLit regions, reader-profile data and notes remain
ReadPapers-owned. No second Zotero application or daily library is installed.

The old project `.codex/skills` directory symlink has been split into three
individual compatibility links. Their contents still come from the old shared
source; that source was preserved, not copied or declared newly maintained.
Future new names in the legacy shared directory will not automatically appear
in Codex. A future source migration can move those packages deliberately; it is
not needed to make their installation project-scoped now. Claude directories and
user aliases were preserved, and this release makes no Claude-host support claim.

## Observed discovery

The native Codex `skills/list` response contains the seven core capabilities at
`user` scope in both checked workspaces. ReadPapers contains one enabled
`read-paper`, plus its three source tools at `repo` scope; agent-tools contains
none of these four project tools. There are no project copies of the seven
core capabilities in the inspected project skill roots.

This is actual discovery evidence, not a claim that every future user request
will select the right capability. Historical behavior tests, prompt review and
this installation readback have different scopes.

- [Filesystem ownership inventory](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/feedback-20260927/ownership-inventory.json)
- [Native discovery readback](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/feedback-20260927/native-skills-final.json)
- [Installation and protected-object receipt](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/feedback-20260927/activation-result.json)

## Recovery and limits

The installer manifest records the original Codex links and project bridge.
`python3 scripts/install_learning_workflow.py --rollback` first checks installed
objects and preserves later user changes. It restores the recognized old links;
it does not roll back the separately edited project `AGENTS.md` or the new
`read-paper-adapter.json`. Their exact before/after hashes, backup and diff are
in the activation evidence folder. Restore these separately only after checking
that their current bytes still match this installation, preserving later edits.

The actual target is the WSL Codex profile and its explicitly selected mounted
ReadPapers project. Native Win11 Codex configuration and remote-server rollout
were not changed. Current Zotero API reachability is separately recorded; skills
installation does not imply the desktop Zotero process is running.

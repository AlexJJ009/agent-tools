# Learning and writing skills

Seven skills carry the learning and writing methods: `task-routing`,
`academic-writing`, `teaching-reconstruction`, `teaching-dag-builder`,
`evidence-anchor`, `retrieval-practice` and `learning-artifact-compiler`. They are
plain skills: instructions and reference files with no CLI, hooks, background
service or stored state. Each session works from the user's request and the
conversation; when a session resumes, the user restates the context
([ADR 0012](decisions/0012-retire-workflow-runtime.md)).

## Ownership

Agent Core provides stable user and collaboration context. The Main Agent selects
the current activity from the latest request, exclusions and source scope
(`task-routing`); learning uses the teaching orchestrator and its domain
methods, while ordinary code investigation stays delivery. Code learning covers
problem solving, task decomposition, module decoupling, architecture and
ownership, control flow and engineering trade-offs. Paper learning retains
motivation, problem, contribution, assumptions and experimental evidence. Both use
one shared writing contract and one practice owner. See
[the ownership decision](decisions/0009-learning-domain-ownership.md).

`learning-artifact-compiler` writes or revises a requested standalone learning
document. It can work from inspected sources without a previous teaching session
or completed exercises. It writes the finished note to the destination the user
named. Full initial drafts and substantial feedback-driven revisions are supported;
small interactive units are an option, not a requirement. Retention and practice
normally focus on up to three abilities per learning session, without limiting the
document's coverage. Material review, reading progress, actual attempts and
selected retention remain separate.

Practice follow-through is an Agent instruction, not a background service. Nothing
schedules review, delivers notifications, captures answers or synchronizes
calendar events; existing queues remain with their owning project.

The `read-paper` skill (Zotero library, formal close reading, ZotLit notes)
belongs to the ReadPapers tooling repository, not to Agent Tools. The teaching
skill keeps the frozen v1 ReadPapers artifact contract and its standalone
validator, `skills/teaching-reconstruction/scripts/validate_teaching_artifact.py`
(also used by the vault pre-commit asset). Existing ZotLit managed regions are
never rewritten.

## Writing contract

W1-W9 are maintained at `shared/writing/reader-facing-contract.md`.
`scripts/sync_writing_contract.py --write` regenerates the copy packaged in
`academic-writing` (`--check` detects drift). `academic-writing` supports direct
draft, revision and argument review without teaching state.

## Installation

`scripts/install.sh` copies the skills to `~/.local/lib/agent-tools/skills/<name>`
and `scripts/install_skills.py` links them into `~/.agents/skills/<name>`, where
Codex discovers them (`--no-learning-skills` skips this). With
`--claude-code existing|latest`, the [Claude adapter](CLAUDE_CODE_ADAPTER.md)
links the same directories into `~/.claude/skills/<name>`.

The linker replaces discovery links left by earlier releases (the learning bundle
or the old data-root locations) and removes links to retired skills that point into
agent-tools locations. It preserves any other entry in those directories, including
real directories, and reports them. Hooks, `~/.codex/AGENTS.md` instruction blocks, launchers, the bundle directory in
the install root and the route state written by the earlier learning runtime are not
touched by the installer; remove them by hand (paths in
[ADR 0012](decisions/0012-retire-workflow-runtime.md)).

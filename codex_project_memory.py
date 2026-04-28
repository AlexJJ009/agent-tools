#!/usr/bin/env python3
"""Create project-scoped Codex memory files.

Codex native memories live under CODEX_HOME and are generated state. This tool
adds an explicit project-local memory layer that Codex can read through
AGENTS.md / CLAUDE.md instructions.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


BEGIN = "<!-- BEGIN CODEX PROJECT MEMORY -->"
END = "<!-- END CODEX PROJECT MEMORY -->"


INSTRUCTION_BLOCK = f"""{BEGIN}
## Codex Project Memory

Codex: this project keeps project-scoped memory in `.codex/project-memory/MEMORY.md`.
For tasks that depend on prior project history, recurring workflows,
experiments, or user/project preferences, read that index first, then open only
the referenced topic files that match the task. Treat dated status as possibly
stale and verify live state before acting.

Do not store secrets in project memory. Prefer durable workflow lessons and
known pitfalls over transient status.
{END}
"""


DEFAULT_MEMORY_INDEX = """# Codex Project Memory

Project-scoped memory for Codex. Keep this index short and link detailed topic
files from here.

## How Codex Should Use This

- Read this file before history-dependent work in this project.
- Open only the linked topic files that match the task.
- Treat dated status as possibly stale and verify live state before acting.
- Do not store secrets here.

## Topics

"""


IMPORTED_BLOCK_BEGIN = "<!-- BEGIN IMPORTED CLAUDE AUTO MEMORY -->"
IMPORTED_BLOCK_END = "<!-- END IMPORTED CLAUDE AUTO MEMORY -->"


IMPORTED_BLOCK = f"""{IMPORTED_BLOCK_BEGIN}
## Imported Claude Auto Memory

- [Claude auto memory index](imported-claude-memory/MEMORY.md)

These files were copied from Claude Code auto memory. Treat workflow lessons as
useful, but verify dated training status, checkpoint paths, and live service
state before acting.
{IMPORTED_BLOCK_END}
"""


IMPORTED_CODEX_BLOCK_BEGIN = "<!-- BEGIN IMPORTED CODEX PROJECT MEMORY -->"
IMPORTED_CODEX_BLOCK_END = "<!-- END IMPORTED CODEX PROJECT MEMORY -->"


IMPORTED_CODEX_BLOCK = f"""{IMPORTED_CODEX_BLOCK_BEGIN}
## Imported Codex Project Memory

- [Codex project memory index](imported-codex-memory/MEMORY.md)

These files were copied from `.codex/project-memory/`. Treat workflow lessons as
useful, but verify dated training status, checkpoint paths, and live service
state before acting.
{IMPORTED_CODEX_BLOCK_END}
"""


CLAUDE_MEMORY_TEMPLATE = """# Project Memory

Project-scoped Claude Code auto memory and imported agent memory.

## Topics

"""


def run_git_root(path: Path) -> Path:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return path.resolve()
    return Path(out).resolve()


def encode_claude_project_path(path: Path) -> str:
    return str(path.resolve()).replace("/", "-")


def replace_or_append_block(text: str, block: str, begin: str, end: str) -> str:
    if begin in text and end in text:
        start = text.index(begin)
        stop = text.index(end, start) + len(end)
        next_newline = text.find("\n", stop)
        if next_newline != -1:
            stop = next_newline + 1
        return text[:start].rstrip() + "\n\n" + block.rstrip() + "\n" + text[stop:]
    return text.rstrip() + "\n\n" + block.rstrip() + "\n"


def remove_block(text: str, begin: str, end: str) -> str:
    if begin not in text or end not in text:
        return text
    start = text.index(begin)
    stop = text.index(end, start) + len(end)
    next_newline = text.find("\n", stop)
    if next_newline != -1:
        stop = next_newline + 1
    return text[:start].rstrip() + "\n" + text[stop:].lstrip()


def choose_context_file(project_root: Path, preferred: str) -> Path | None:
    if preferred == "none":
        return None
    if preferred in {"CLAUDE.md", "AGENTS.md"}:
        return project_root / preferred

    claude = project_root / "CLAUDE.md"
    agents = project_root / "AGENTS.md"
    if claude.exists():
        return claude
    if agents.exists():
        return agents
    return agents


def ensure_memory_index(memory_dir: Path) -> Path:
    memory_dir.mkdir(parents=True, exist_ok=True)
    index = memory_dir / "MEMORY.md"
    if not index.exists():
        index.write_text(DEFAULT_MEMORY_INDEX, encoding="utf-8")
    return index


def ensure_claude_memory_index(memory_dir: Path) -> Path:
    memory_dir.mkdir(parents=True, exist_ok=True)
    index = memory_dir / "MEMORY.md"
    if not index.exists():
        index.write_text(CLAUDE_MEMORY_TEMPLATE, encoding="utf-8")
    return index


def update_context_file(context_file: Path | None) -> bool:
    if context_file is None:
        return False
    existing = context_file.read_text(encoding="utf-8") if context_file.exists() else ""
    updated = replace_or_append_block(existing, INSTRUCTION_BLOCK, BEGIN, END)
    context_file.parent.mkdir(parents=True, exist_ok=True)
    context_file.write_text(updated, encoding="utf-8")
    return True


def claude_memory_path(project_root: Path) -> Path:
    return (
        Path.home()
        / ".claude"
        / "projects"
        / encode_claude_project_path(project_root)
        / "memory"
    )


def files_equal(left: Path, right: Path) -> bool:
    if not left.exists() or not right.exists():
        return False
    return left.read_bytes() == right.read_bytes()


def copy_markdown_tree(
    source: Path,
    target: Path,
    force: bool,
    exclude_prefixes: tuple[str, ...] = (),
    exclude_names: tuple[str, ...] = (),
) -> tuple[list[Path], list[Path], list[Path]]:
    copied: list[Path] = []
    skipped: list[Path] = []
    conflicts: list[Path] = []
    if not source.exists():
        return copied, skipped, conflicts

    target.mkdir(parents=True, exist_ok=True)
    for src in sorted(source.rglob("*.md")):
        rel = src.relative_to(source)
        rel_text = rel.as_posix()
        if src.name in exclude_names:
            continue
        if any(rel_text == prefix or rel_text.startswith(prefix.rstrip("/") + "/") for prefix in exclude_prefixes):
            continue

        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if files_equal(src, dst):
                skipped.append(rel)
                continue
            if not force:
                conflicts.append(rel)
                continue
        shutil.copy2(src, dst)
        copied.append(rel)
    return copied, skipped, conflicts


def write_import_index(import_dir: Path, title: str) -> Path:
    import_dir.mkdir(parents=True, exist_ok=True)
    index = import_dir / "MEMORY.md"
    files = [
        path.relative_to(import_dir)
        for path in sorted(import_dir.rglob("*.md"))
        if path.name != "MEMORY.md"
    ]
    lines = [
        f"# {title}",
        "",
        "Generated by `codex_project_memory.py sync`.",
        "",
        "## Files",
        "",
    ]
    if files:
        for file in files:
            lines.append(f"- [{file.as_posix()}]({file.as_posix()})")
    else:
        lines.append("- No topic files copied yet.")
    lines.append("")
    index.write_text("\n".join(lines), encoding="utf-8")
    return index


def import_claude_memory(project_root: Path, memory_dir: Path, force: bool) -> Path | None:
    source = claude_memory_path(project_root)
    if not source.exists():
        return None

    target = memory_dir / "imported-claude-memory"
    copy_markdown_tree(source, target, True, exclude_prefixes=("imported-codex-memory",))
    strip_imported_codex_block(target)

    index = ensure_memory_index(memory_dir)
    text = index.read_text(encoding="utf-8")
    text = replace_or_append_block(
        text,
        IMPORTED_BLOCK,
        IMPORTED_BLOCK_BEGIN,
        IMPORTED_BLOCK_END,
    )
    index.write_text(text, encoding="utf-8")
    return source


def strip_imported_codex_block(imported_claude_dir: Path) -> None:
    index = imported_claude_dir / "MEMORY.md"
    if not index.exists():
        return
    text = index.read_text(encoding="utf-8")
    cleaned = remove_block(text, IMPORTED_CODEX_BLOCK_BEGIN, IMPORTED_CODEX_BLOCK_END)
    if cleaned != text:
        index.write_text(cleaned.rstrip() + "\n", encoding="utf-8")


def sync(args: argparse.Namespace) -> int:
    project_root = run_git_root(Path(args.project).expanduser())
    memory_dir = project_root / ".codex" / "project-memory"
    index = ensure_memory_index(memory_dir)

    context_file = choose_context_file(project_root, args.context_file)
    context_updated = update_context_file(context_file)

    source_claude = claude_memory_path(project_root)
    conflicts: list[str] = []

    print(f"project_root={project_root}")
    print(f"codex_project_memory={memory_dir}")
    print(f"claude_auto_memory={source_claude}")
    if context_updated and context_file is not None:
        print(f"context_file_updated={context_file}")
    elif context_file is None:
        print("context_file_updated=skipped")

    if args.direction in {"both", "claude-to-codex"}:
        target = memory_dir / "imported-claude-memory"
        copied, skipped, side_conflicts = copy_markdown_tree(
            source_claude,
            target,
            True,
            exclude_prefixes=("imported-codex-memory",),
        )
        strip_imported_codex_block(target)
        if source_claude.exists():
            text = index.read_text(encoding="utf-8")
            text = replace_or_append_block(
                text,
                IMPORTED_BLOCK,
                IMPORTED_BLOCK_BEGIN,
                IMPORTED_BLOCK_END,
            )
            index.write_text(text, encoding="utf-8")
        conflicts.extend(f"claude-to-codex:{path}" for path in side_conflicts)
        print(
            "claude_to_codex="
            f"copied:{len(copied)} skipped:{len(skipped)} conflicts:{len(side_conflicts)}"
        )

    if args.direction in {"both", "codex-to-claude"}:
        target_claude = source_claude
        claude_index = ensure_claude_memory_index(target_claude)
        target = target_claude / "imported-codex-memory"
        copied, skipped, side_conflicts = copy_markdown_tree(
            memory_dir,
            target,
            True,
            exclude_prefixes=("imported-claude-memory",),
            exclude_names=("MEMORY.md",),
        )
        write_import_index(target, "Imported Codex Project Memory")
        text = claude_index.read_text(encoding="utf-8")
        text = replace_or_append_block(
            text,
            IMPORTED_CODEX_BLOCK,
            IMPORTED_CODEX_BLOCK_BEGIN,
            IMPORTED_CODEX_BLOCK_END,
        )
        claude_index.write_text(text, encoding="utf-8")
        conflicts.extend(f"codex-to-claude:{path}" for path in side_conflicts)
        print(
            "codex_to_claude="
            f"copied:{len(copied)} skipped:{len(skipped)} conflicts:{len(side_conflicts)}"
        )

    if conflicts:
        print("conflicts=")
        for conflict in conflicts:
            print(f"  {conflict}")
        print("Use --force to overwrite conflicting destination files.")
        return 3
    return 0


def find_native_codex_hits(project_root: Path, limit: int) -> list[Path]:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    memory_home = codex_home / "memories"
    if not memory_home.exists():
        return []
    terms = {
        str(project_root),
        encode_claude_project_path(project_root),
        project_root.name,
    }
    hits: list[Path] = []
    for path in sorted(memory_home.rglob("*")):
        if not path.is_file() or path.suffix not in {".md", ".jsonl", ".txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(term and term in text for term in terms):
            hits.append(path)
            if len(hits) >= limit:
                break
    return hits


def init(args: argparse.Namespace) -> int:
    project_root = run_git_root(Path(args.project).expanduser())
    memory_dir = project_root / ".codex" / "project-memory"
    index = ensure_memory_index(memory_dir)

    context_file = choose_context_file(project_root, args.context_file)
    context_updated = update_context_file(context_file)

    imported_from = None
    if args.import_claude:
        imported_from = import_claude_memory(project_root, memory_dir, args.force)

    print(f"project_root={project_root}")
    print(f"memory_index={index}")
    if context_updated and context_file is not None:
        print(f"context_file_updated={context_file}")
    elif context_file is None:
        print("context_file_updated=skipped")
    if args.import_claude:
        if imported_from is None:
            print("claude_memory_imported=not_found")
        else:
            print(f"claude_memory_imported={imported_from}")
    return 0


def status(args: argparse.Namespace) -> int:
    project_root = run_git_root(Path(args.project).expanduser())
    memory_dir = project_root / ".codex" / "project-memory"
    index = memory_dir / "MEMORY.md"
    claude_source = claude_memory_path(project_root)

    print(f"project_root={project_root}")
    print(f"memory_index={index} exists={index.exists()}")
    print(f"claude_auto_memory={claude_source} exists={claude_source.exists()}")

    for name in ("CLAUDE.md", "AGENTS.md"):
        path = project_root / name
        if not path.exists():
            print(f"{name}=missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        print(f"{name}=exists project_memory_instruction={BEGIN in text and END in text}")

    if memory_dir.exists():
        files = sorted(p.relative_to(memory_dir) for p in memory_dir.rglob("*.md"))
        print("project_memory_files=")
        for file in files:
            print(f"  {file}")
    if args.search_native:
        hits = find_native_codex_hits(project_root, args.native_limit)
        print(f"codex_native_hits={len(hits)}")
        for hit in hits:
            print(f"  {hit}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a project-local Codex memory layer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="initialize project Codex memory")
    init_parser.add_argument("project", nargs="?", default=".", help="project path")
    init_parser.add_argument(
        "--context-file",
        choices=["auto", "CLAUDE.md", "AGENTS.md", "none"],
        default="auto",
        help="file to update with the Codex project memory instruction",
    )
    init_parser.add_argument(
        "--import-claude",
        action="store_true",
        help="copy Claude Code auto memory into project memory",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing imported Claude memory files",
    )
    init_parser.set_defaults(func=init)

    sync_parser = sub.add_parser("sync", help="bidirectionally sync project memories")
    sync_parser.add_argument("project", nargs="?", default=".", help="project path")
    sync_parser.add_argument(
        "--direction",
        choices=["both", "claude-to-codex", "codex-to-claude"],
        default="both",
        help="memory sync direction",
    )
    sync_parser.add_argument(
        "--context-file",
        choices=["auto", "CLAUDE.md", "AGENTS.md", "none"],
        default="auto",
        help="file to update with the Codex project memory instruction",
    )
    sync_parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite conflicting destination files",
    )
    sync_parser.set_defaults(func=sync)

    status_parser = sub.add_parser("status", help="show project memory status")
    status_parser.add_argument("project", nargs="?", default=".", help="project path")
    status_parser.add_argument(
        "--search-native",
        action="store_true",
        help="search ~/.codex/memories for files mentioning this project",
    )
    status_parser.add_argument(
        "--native-limit",
        type=int,
        default=20,
        help="maximum native Codex memory hits to print",
    )
    status_parser.set_defaults(func=status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

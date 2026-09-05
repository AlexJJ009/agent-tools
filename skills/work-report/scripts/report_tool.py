# /// script
# dependencies = [
#   "markdown-it-py==4.0.0",
#   "PyYAML==6.0.2",
# ]
# ///
"""Local work-report initializer, checker, and finalizer."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import yaml
from markdown_it import MarkdownIt


MAX_INPUT_BYTES = 1024 * 1024
CONTEXT_SCHEMA = "work-report.context/1"
CHECK_SCHEMA = "work-report.check/1"
REVIEW_SCHEMA = "work-report.review/1"
TASK_RE = re.compile(r"^\d{8}T\d{6}Z-[a-z0-9][a-z0-9-]*-[0-9a-f]{8}$")
REPORT_RE = re.compile(r"^\d{8}T\d{6}Z-(progress|final)-[0-9a-f]{6}$")
REMOTE_SCHEMES = {"http", "https", "mailto"}
PLACEHOLDERS = {"TODO", "待填写", "填写"}

class ValidationFailure(Exception):
    def __init__(self, issues: list[dict[str, str]], warnings: list[dict[str, str]] | None = None):
        super().__init__("validation failed")
        self.issues = issues
        self.warnings = warnings or []


class ToolFailure(Exception):
    pass


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def run_git(args: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise ToolFailure(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def git_root(path: Path) -> Path | None:
    proc = run_git(["rev-parse", "--show-toplevel"], nearest_existing(path))
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip()).resolve()


def canonical_workspace(path: Path) -> Path:
    base = path.expanduser().resolve()
    root = git_root(base)
    return root or base


def nearest_existing(path: Path) -> Path:
    cur = path.expanduser().absolute()
    while not cur.exists():
        if cur.parent == cur:
            raise ToolFailure(f"no existing parent for {path}")
        cur = cur.parent
    return cur


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def reject_symlinks(path: Path, include_leaf: bool = True) -> None:
    cur = Path(path.anchor) if path.is_absolute() else Path.cwd()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    limit = len(parts) if include_leaf else max(0, len(parts) - 1)
    for part in parts[:limit]:
        cur = cur / part
        if cur.is_symlink():
            raise ValidationFailure([issue("symlink_path", f"symlink path component is not allowed: {cur}")])


def safe_absolute(path: Path, include_leaf: bool = True) -> Path:
    raw = path.expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    reject_symlinks(raw, include_leaf=include_leaf)
    return raw.resolve()


def read_small_text(path: Path, label: str) -> tuple[str, str]:
    reject_symlinks(path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ToolFailure(f"cannot stat {label} {path}: {exc}") from exc
    if size > MAX_INPUT_BYTES:
        raise ValidationFailure([issue("oversized_input", f"{label} exceeds 1MiB: {path}")])
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ToolFailure(f"cannot read {label} {path}: {exc}") from exc
    return data.decode("utf-8"), hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    reject_symlinks(path)
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError as exc:
        raise ToolFailure(f"cannot hash {path}: {exc}") from exc
    return h.hexdigest()


def load_json_strict(path: Path) -> Any:
    def no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    try:
        reject_symlinks(path)
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_dupes)
    except Exception as exc:
        raise ValidationFailure([issue("invalid_json", f"{path} is not valid JSON: {exc}")]) from exc


def atomic_write_json(path: Path, obj: dict[str, Any]) -> None:
    reject_symlinks(path, include_leaf=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48].strip("-") or "work-report"


def stamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def load_rubric(script_path: Path) -> tuple[dict[str, Any], Path, list[dict[str, str]]]:
    rubric_path = script_path.parent.parent / "references" / "rubric.yaml"
    if not rubric_path.exists():
        raise ValidationFailure([issue("rubric_missing", f"missing fixed rubric: {rubric_path}")])
    reject_symlinks(rubric_path)
    try:
        raw = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationFailure([issue("invalid_rubric", f"cannot parse rubric.yaml: {exc}")]) from exc
    if not isinstance(raw, dict):
        raise ValidationFailure([issue("invalid_rubric", "rubric.yaml must contain a mapping")])
    return raw, rubric_path, []


def validate_rubric(rubric: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, bool], set[str]]:
    sections = rubric.get("sections")
    criteria = rubric.get("criteria")
    placeholders = set(rubric.get("placeholders", list(PLACEHOLDERS)))
    if not isinstance(sections, list) or not isinstance(criteria, list):
        raise ValidationFailure([issue("invalid_rubric", "rubric sections and criteria must be lists")])
    crit_allow: dict[str, bool] = {}
    for item in criteria:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValidationFailure([issue("invalid_rubric", "each criterion must have an id")])
        crit_allow[item["id"]] = bool(item.get("allow_na"))
    for item in sections:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("title"), str):
            raise ValidationFailure([issue("invalid_rubric", "each section must have an id and title")])
    needed_criteria = ["goal", "evidence", "decisions", "scope", "next_steps", "readability"]
    if len(sections) != 6 or sorted(crit_allow) != sorted(needed_criteria):
        raise ValidationFailure([issue("invalid_rubric", "rubric must define six sections and the exact approved criteria ids")])
    return sections, crit_allow, placeholders


def git_status(workspace: Path) -> dict[str, str]:
    if git_root(workspace) is None:
        return {"head": "", "status": ""}
    head = run_git(["rev-parse", "HEAD"], workspace)
    status = run_git(["status", "--short"], workspace)
    return {
        "head": head.stdout.strip() if head.returncode == 0 else "",
        "status": status.stdout.rstrip("\n") if status.returncode == 0 else "",
    }


def git_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def escaped_gitignore_dir(root: Path, output_root: Path) -> str:
    rel = git_relative(root, output_root)
    escaped = ""
    for ch in rel:
        escaped += "\\" + ch if ch in " #![]?*\\" else ch
    return f"/{escaped}/"


def tracked_or_staged(root: Path, *paths: Path) -> list[str]:
    rels = [git_relative(root, p) for p in paths if is_relative_to(p, root)]
    if not rels:
        return []
    tracked = run_git(["ls-files", "--", *rels], root)
    staged = run_git(["diff", "--cached", "--name-only", "--", *rels], root)
    if tracked.returncode != 0 or staged.returncode != 0:
        raise ToolFailure("git tracked/staged inspection failed")
    hits = []
    hits.extend(x for x in tracked.stdout.splitlines() if x)
    hits.extend(f"staged:{x}" for x in staged.stdout.splitlines() if x)
    return sorted(set(hits))


def ensure_git_policy(workspace: Path, output_root: Path, *, configure: bool, artifacts: list[Path] | None = None) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    workspace_git = git_root(workspace)
    output_git = git_root(output_root)
    if output_git is None:
        return warnings

    artifacts = artifacts or [output_root / ".work-report-ignore-probe"]
    hits = tracked_or_staged(output_git, output_root, *artifacts)
    if hits:
        raise ValidationFailure([issue("git_tracked_output", f"output root has tracked or staged paths: {', '.join(hits[:20])}")])

    if configure and workspace_git is not None and output_git == workspace_git:
        rule = escaped_gitignore_dir(output_git, output_root)
        exclude_proc = run_git(["rev-parse", "--git-path", "info/exclude"], output_git, check=True)
        exclude_path = (output_git / exclude_proc.stdout.strip()).resolve()
        reject_symlinks(exclude_path, include_leaf=False)
        existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
        if rule not in existing.splitlines():
            exclude_path.parent.mkdir(parents=True, exist_ok=True)
            with exclude_path.open("a", encoding="utf-8") as fh:
                if existing and not existing.endswith("\n"):
                    fh.write("\n")
                fh.write(rule + "\n")
    elif workspace_git is None or output_git != workspace_git:
        warnings.append(warning("external_git_root", f"output root belongs to another Git repo; not editing Git rules: {output_git}"))

    for artifact in artifacts:
        ignored = run_git(["check-ignore", "-q", "--", str(artifact)], output_git)
        if ignored.returncode == 1:
            raise ValidationFailure([issue("git_ignore_missing", f"path is not effectively ignored: {artifact}")], warnings)
        if ignored.returncode != 0:
            raise ToolFailure(f"git check-ignore failed for {artifact}: {ignored.stderr.strip()}")
    return warnings


def parse_iso(value: str, label: str) -> dt.datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationFailure([issue("invalid_timestamp", f"{label} is not valid ISO 8601: {value}")]) from exc
    if parsed.tzinfo is None:
        raise ValidationFailure([issue("invalid_timestamp", f"{label} must include a timezone")])
    return parsed


def frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise ValidationFailure([issue("frontmatter_missing", "report.md must start with YAML frontmatter")])
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValidationFailure([issue("frontmatter_missing", "report.md frontmatter is not closed")])
    try:
        meta = yaml.safe_load(text[4:end]) or {}
    except Exception as exc:
        raise ValidationFailure([issue("frontmatter_invalid", f"frontmatter is invalid YAML: {exc}")]) from exc
    if not isinstance(meta, dict):
        raise ValidationFailure([issue("frontmatter_invalid", "frontmatter must be a mapping")])
    return meta, text[end + 5 :]


def render_report_template(context: dict[str, Any], rubric: dict[str, Any], script_path: Path) -> str:
    template = script_path.parent.parent / "assets" / "report.md"
    if not template.exists():
        raise ValidationFailure([issue("template_missing", f"missing fixed report template: {template}")])
    reject_symlinks(template)
    body = template.read_text(encoding="utf-8")
    fm = {
        "task_id": context["task_id"],
        "report_id": context["report_id"],
        "kind": context["kind"],
        "workspace": context["workspace"],
        "generated_at": context["generated_at"],
        "window_start": context["window_start"],
        "window_end": context["window_end"],
    }
    return "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip() + "\n---\n\n" + body


def first_context(task_dir: Path) -> dict[str, Any] | None:
    contexts = sorted(task_dir.glob("*/context.json"))
    for path in contexts:
        try:
            data = load_json_strict(path)
        except ValidationFailure:
            continue
        if isinstance(data, dict) and data.get("schema_version") == CONTEXT_SCHEMA:
            return data
    return None


def validate_context_snapshot(context: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for key in ["request", "state"]:
        value = context.get(key)
        if not isinstance(value, dict):
            issues.append(issue("context_snapshot_invalid", f"context {key} must be a mapping"))
            continue
        for field in ["path", "sha256", "text"]:
            if not isinstance(value.get(field), str):
                issues.append(issue("context_snapshot_invalid", f"context {key}.{field} must be a string"))
        if isinstance(value.get("text"), str) and isinstance(value.get("sha256"), str):
            digest = hashlib.sha256(value["text"].encode("utf-8")).hexdigest()
            if digest != value["sha256"]:
                issues.append(issue("context_snapshot_hash_mismatch", f"context {key}.sha256 does not match frozen text"))
    git_value = context.get("git")
    if not isinstance(git_value, dict) or not all(isinstance(git_value.get(k), str) for k in ["head", "status"]):
        issues.append(issue("context_git_invalid", "context git must contain string head and status"))
    return issues


def validate_context_required(context: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for key in ["task_id", "report_id", "kind", "workspace", "output_root", "generated_at", "window_start", "window_end"]:
        if not isinstance(context.get(key), str) or not context[key].strip():
            issues.append(issue("context_field_invalid", f"context {key} must be a nonempty string"))
    if issues:
        return issues
    for key in ["generated_at", "window_start", "window_end"]:
        try:
            parse_iso(context[key], key)
        except ValidationFailure as exc:
            issues.extend(exc.issues)
    issues.extend(validate_context_snapshot(context))
    return issues


def cmd_init(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    script_path = Path(__file__).resolve()
    workspace = canonical_workspace(safe_absolute(Path(args.workspace)))
    output_root = safe_absolute(Path(args.output_root), include_leaf=True) if args.output_root else workspace / "docs" / "work-reports"
    reject_symlinks(output_root, include_leaf=True)
    request_path = safe_absolute(Path(args.request))
    request_text, request_hash = read_small_text(request_path, "request")
    win_start = parse_iso(args.window_start, "window_start") if args.window_start else None
    win_end = parse_iso(args.window_end, "window_end") if args.window_end else None
    if win_start and win_end and win_start > win_end:
        raise ValidationFailure([issue("invalid_window", "window_start must be <= window_end")])
    state_path = safe_absolute(Path(args.state)) if args.state else None
    if state_path:
        state_text, state_hash = read_small_text(state_path, "state")
    warnings = ensure_git_policy(workspace, output_root, configure=True)
    rubric, _, rub_warnings = load_rubric(script_path)
    warnings.extend(rub_warnings)
    validate_rubric(rubric)

    if args.task_dir:
        task_dir = safe_absolute(Path(args.task_dir), include_leaf=True)
        if not is_relative_to(task_dir, output_root):
            raise ValidationFailure([issue("task_dir_outside_root", f"task-dir must be inside output root: {task_dir}")], warnings)
        if not TASK_RE.match(task_dir.name):
            raise ValidationFailure([issue("invalid_task_id", f"invalid task id: {task_dir.name}")], warnings)
        if not task_dir.is_dir():
            raise ValidationFailure([issue("task_dir_missing", f"existing task-dir does not exist: {task_dir}")], warnings)
        prior = first_context(task_dir)
        if not prior:
            raise ValidationFailure([issue("task_context_missing", "existing task-dir has no prior context.json workspace binding")], warnings)
        if Path(prior.get("workspace", "")).resolve() != workspace:
            raise ValidationFailure([issue("workspace_mismatch", "existing task context belongs to a different workspace")], warnings)
        task_id = task_dir.name
        initial_inventory = prior.get("initial_work_inventory") or {"status": "unavailable"}
    else:
        task_id = f"{stamp()}-{slugify(args.title)}-{secrets.token_hex(4)}"
        task_dir = output_root / task_id
        initial_inventory = git_status(workspace) or {"status": "unavailable"}

    report_id = f"{stamp()}-{args.kind}-{secrets.token_hex(3)}"
    report_dir = task_dir / report_id
    state_path = state_path or (task_dir / "working-state.md")
    generated_at = iso_now()
    context_window_start = args.window_start or generated_at
    context_window_end = args.window_end or generated_at
    gen_time = parse_iso(generated_at, "generated_at")
    if parse_iso(context_window_start, "window_start") > parse_iso(context_window_end, "window_end"):
        raise ValidationFailure([issue("invalid_window", "window_start must be <= window_end")], warnings)
    if parse_iso(context_window_end, "window_end") > gen_time:
        raise ValidationFailure([issue("invalid_window", "window_end must be <= generated_at")], warnings)

    reject_symlinks(task_dir, include_leaf=task_dir.exists())
    reject_symlinks(report_dir, include_leaf=False)
    output_root.mkdir(parents=True, exist_ok=True)
    try:
        task_dir.mkdir(exist_ok=bool(args.task_dir))
        report_dir.mkdir()
    except FileExistsError as exc:
        raise ValidationFailure([issue("exclusive_create_failed", f"refusing to overwrite existing report path: {exc.filename}")], warnings)

    if args.state:
        pass
    else:
        if state_path.exists():
            state_text, state_hash = read_small_text(state_path, "state")
        else:
            state_text = (
                f"# Work Report State\n\n"
                f"- task_id: {task_id}\n"
                f"- workspace: {workspace}\n"
                f"- request: {request_path}\n\n"
                "## Current State\n\nTODO\n"
            )
            reject_symlinks(state_path, include_leaf=False)
            state_path.write_text(state_text, encoding="utf-8")
            state_hash = hashlib.sha256(state_text.encode("utf-8")).hexdigest()

    context = {
        "schema_version": CONTEXT_SCHEMA,
        "task_id": task_id,
        "report_id": report_id,
        "kind": args.kind,
        "workspace": str(workspace),
        "output_root": str(output_root),
        "generated_at": generated_at,
        "window_start": context_window_start,
        "window_end": context_window_end,
        "request": {"path": str(request_path), "sha256": request_hash, "text": request_text},
        "state": {"path": str(state_path), "sha256": state_hash, "text": state_text},
        "git": git_status(workspace),
        "initial_work_inventory": initial_inventory,
    }
    parse_iso(context["window_start"], "window_start")
    context_path = report_dir / "context.json"
    report_path = report_dir / "report.md"
    atomic_write_json(context_path, context)
    report_path.write_text(render_report_template(context, rubric, script_path), encoding="utf-8")
    artifacts = [report_path, context_path]
    if is_relative_to(state_path, output_root):
        artifacts.append(state_path)
    warnings.extend(ensure_git_policy(workspace, output_root, configure=True, artifacts=artifacts))
    return 0, {
        "status": "pass",
        "task_id": task_id,
        "report_id": report_id,
        "report": str(report_path),
        "context": str(context_path),
        "state": str(state_path),
        "warnings": warnings,
    }


def token_text(tokens: list[Any], start: int, end: int) -> str:
    bits = []
    for tok in tokens[start:end]:
        if tok.type in {"inline", "code_block", "fence"} and tok.content:
            bits.append(tok.content)
    return "\n".join(bits).strip()


def section_map(tokens: list[Any], sections: list[dict[str, Any]]) -> tuple[dict[str, tuple[int, int]], list[dict[str, str]]]:
    aliases: dict[str, str] = {}
    for sec in sections:
        names = [sec.get("title"), *(sec.get("aliases") or []), sec.get("id")]
        for name in names:
            if isinstance(name, str):
                aliases[normalize_heading(name)] = sec["id"]
    found: dict[str, tuple[int, int]] = {}
    headings: list[tuple[int, str, str | None]] = []
    for idx, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.tag == "h2":
            title = tokens[idx + 1].content if idx + 1 < len(tokens) and tokens[idx + 1].type == "inline" else ""
            explicit = None
            m = re.search(r"\{#([a-z0-9_-]+)\}\s*$", title)
            if m:
                explicit = m.group(1)
                title = title[: m.start()].strip()
            headings.append((idx, title, explicit))
    issues: list[dict[str, str]] = []
    for n, (idx, title, explicit) in enumerate(headings):
        sec_id = explicit if explicit in aliases.values() else aliases.get(normalize_heading(title))
        if sec_id:
            end = headings[n + 1][0] if n + 1 < len(headings) else len(tokens)
            found[sec_id] = (idx + 3, end)
    for sec in sections:
        sid = sec["id"]
        if sid not in found:
            issues.append(issue("section_missing", f"missing required H2 section: {sid} / {sec.get('title')}"))
    return found, issues


def normalize_heading(value: str) -> str:
    value = re.sub(r"\{#[^}]+\}\s*$", "", value).strip().lower()
    return re.sub(r"\s+", " ", value)


def table_count(tokens: list[Any]) -> int:
    count = 0
    idx = 0
    while idx < len(tokens):
        if tokens[idx].type != "table_open":
            idx += 1
            continue
        headers: list[str] = []
        rows: list[list[str]] = []
        cur_row: list[str] | None = None
        in_head = False
        in_body = False
        idx += 1
        while idx < len(tokens) and tokens[idx].type != "table_close":
            tok = tokens[idx]
            if tok.type == "thead_open":
                in_head = True
            elif tok.type == "thead_close":
                in_head = False
            elif tok.type == "tbody_open":
                in_body = True
            elif tok.type == "tbody_close":
                in_body = False
            elif tok.type == "tr_open":
                cur_row = []
            elif tok.type == "tr_close" and cur_row is not None:
                if in_body:
                    rows.append(cur_row)
                cur_row = None
            elif tok.type == "inline":
                if in_head:
                    headers.append(tok.content.strip())
                elif in_body and cur_row is not None:
                    cur_row.append(tok.content.strip())
            idx += 1
        if any(headers) and any(any(cell for cell in row) for row in rows):
            count += 1
        idx += 1
    return count


def inline_links(tokens: list[Any]) -> tuple[list[tuple[str, bool]], list[dict[str, str]]]:
    links: list[tuple[str, bool]] = []
    warnings: list[dict[str, str]] = []
    for tok in tokens:
        if tok.type != "inline" or not tok.children:
            continue
        for child in tok.children:
            if child.type in {"link_open", "image"}:
                href = child.attrGet("href") if child.type == "link_open" else child.attrGet("src")
                if not href:
                    continue
                parsed = urlparse(href)
                if parsed.scheme in REMOTE_SCHEMES:
                    warnings.append(warning("remote_link_unverified", f"remote link not fetched: {href}"))
                    continue
                if href.startswith("#"):
                    continue
                links.append((href, child.type == "image"))
    return links, warnings


def strip_line_suffix(path: Path) -> Path:
    text = str(path)
    m = re.match(r"^(.*):(\d+)$", text)
    if m and Path(m.group(1)).exists():
        return Path(m.group(1))
    return path


def resolve_local(ref: str, report_dir: Path) -> Path:
    parsed = urlparse(ref)
    raw = unquote(parsed.path) if parsed.scheme == "file" else ref.split("#", 1)[0]
    path = Path(raw)
    if not path.is_absolute():
        path = report_dir / path
    return strip_line_suffix(path).resolve()


def validate_image(path: Path, report_dir: Path) -> tuple[bool, str | None]:
    assets = (report_dir / "assets").resolve()
    if not is_relative_to(path, assets):
        return False, "image files must be confined to report assets/"
    reject_symlinks(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        return False, str(exc)
    low = data[:4096].lower()
    if data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff"):
        return True, None
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return True, None
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return True, None
    suffix = path.suffix.lower()
    if suffix == ".svg":
        unsafe = [b"<script", b"javascript:", b"onload=", b"<!entity", b"<!doctype"]
        if any(x in low for x in unsafe):
            return False, "unsafe SVG content"
        try:
            root = ET.fromstring(data.decode("utf-8"))
        except Exception as exc:
            return False, f"invalid SVG XML: {exc}"
        if root.tag.split("}", 1)[-1].lower() != "svg":
            return False, "SVG root element is not svg"
        return True, None
    return False, "unsupported or invalid image format"


def validate_report(report: Path, task_id: str, workspace: Path) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]], list[Path]]:
    script_path = Path(__file__).resolve()
    warnings: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []
    reject_symlinks(report)
    report = report.resolve()
    report_dir = report.parent
    context_path = report_dir / "context.json"
    if not report.exists():
        raise ValidationFailure([issue("report_missing", f"report does not exist: {report}")])
    context = load_json_strict(context_path)
    if not isinstance(context, dict) or context.get("schema_version") != CONTEXT_SCHEMA:
        raise ValidationFailure([issue("context_invalid", "context.json has wrong schema")])
    context_issues = validate_context_required(context)
    if context_issues:
        raise ValidationFailure(context_issues)
    if context.get("task_id") != task_id:
        issues.append(issue("task_mismatch", "context task_id does not match --task"))
    if Path(context["workspace"]).resolve() != workspace.resolve():
        issues.append(issue("workspace_mismatch", "context workspace does not match --workspace"))
    output_root = Path(context["output_root"]).resolve()
    if report.name != "report.md":
        issues.append(issue("report_name_invalid", "report file must be named report.md"))
    if not is_relative_to(report, output_root) or report.parent.parent.parent.resolve() != output_root:
        issues.append(issue("output_root_mismatch", "report path must be exactly under context output_root/task/report"))
    if not REPORT_RE.match(report_dir.name) or context.get("report_id") != report_dir.name:
        issues.append(issue("report_id_invalid", "report directory name and context report_id must match approved format"))
    if report_dir.parent.name != task_id or not TASK_RE.match(task_id):
        issues.append(issue("task_id_invalid", "task id/path must match approved format"))

    policy_artifacts = [report, context_path]
    assets = report_dir / "assets"
    if assets.exists():
        policy_artifacts.extend(path for path in assets.rglob("*") if path.is_file())
    ensure_git_policy(workspace, output_root, configure=False, artifacts=policy_artifacts)
    text, _ = read_small_text(report, "report")
    meta, body = frontmatter(text)
    for key in ["task_id", "report_id", "kind", "workspace", "generated_at", "window_start", "window_end"]:
        if str(meta.get(key, "")) != str(context.get(key, "")):
            issues.append(issue("frontmatter_mismatch", f"frontmatter {key} does not match context"))
    gen = parse_iso(str(meta.get("generated_at", "")), "generated_at")
    win_start = parse_iso(str(meta.get("window_start", "")), "window_start")
    win_end = parse_iso(str(meta.get("window_end", "")), "window_end")
    if win_start > win_end or win_end > gen:
        issues.append(issue("invalid_window", "must satisfy window_start <= window_end <= generated_at"))

    rubric, _, rub_warnings = load_rubric(script_path)
    warnings.extend(rub_warnings)
    sections, _, placeholders = validate_rubric(rubric)
    md = MarkdownIt("commonmark").enable("table")
    tokens = md.parse(body)
    found, section_issues = section_map(tokens, sections)
    issues.extend(section_issues)
    for sec in sections:
        sid = sec["id"]
        if sid not in found:
            continue
        text_inside = token_text(tokens, *found[sid])
        if not text_inside:
            issues.append(issue("section_empty", f"section has no non-whitespace content: {sid}"))
        for line in text_inside.splitlines():
            stripped = line.strip().strip("*_` ")
            if stripped in placeholders:
                issues.append(issue("placeholder_present", f"section still contains placeholder-only content: {sid}"))

    visual_count = table_count(tokens)
    local_links, link_warnings = inline_links(tokens)
    warnings.extend(link_warnings)
    cited_files: list[Path] = []
    image_count = 0
    for ref, is_image in local_links:
        path = resolve_local(ref, report_dir)
        if not path.exists():
            issues.append(issue("local_reference_missing", f"missing local reference: {ref}"))
            continue
        reject_symlinks(path)
        cited_files.append(path)
        if is_image:
            ok, why = validate_image(path, report_dir)
            if ok:
                image_count += 1
            else:
                issues.append(issue("image_invalid", f"{ref}: {why}"))
    visual_count += image_count
    if visual_count < int(rubric.get("minimum_visuals", 1)):
        issues.append(issue("visual_unverified", "add at least one nonempty Markdown table or supported local image; Mermaid alone is not validated"))
    return context, issues, warnings, sorted(set(cited_files))


def digest_manifest(report: Path, cited_files: list[Path]) -> tuple[str, list[dict[str, str]]]:
    script_path = Path(__file__).resolve()
    report_dir = report.resolve().parent
    skill_dir = script_path.parent.parent
    paths = [report_dir / "context.json", report, script_path]
    for optional in [skill_dir / "references" / "rubric.yaml", skill_dir / "references" / "judge.md"]:
        if optional.exists():
            paths.append(optional)
    assets = report_dir / "assets"
    if assets.exists():
        for path in sorted(assets.rglob("*")):
            if path.is_file():
                paths.append(path)
    paths.extend(cited_files)
    evidence: list[dict[str, str]] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        name = resolved.name
        if name in {"checks.json", "review.json"}:
            continue
        digest = sha256_file(resolved)
        evidence.append({"path": str(resolved), "sha256": digest})
    manifest = {"schema_version": "work-report.digest/1", "files": evidence}
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), evidence


def cmd_check(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    workspace = canonical_workspace(safe_absolute(Path(args.workspace)))
    report = safe_absolute(Path(args.report))
    try:
        context, issues, warnings, cited = validate_report(report, args.task, workspace)
        artifact_digest, evidence = digest_manifest(report, cited)
    except ValidationFailure as exc:
        obj = {
            "schema_version": CHECK_SCHEMA,
            "status": "fail",
            "task_id": args.task,
            "report_id": report.parent.name,
            "checked_at": iso_now(),
            "artifact_digest": "",
            "issues": exc.issues,
            "warnings": exc.warnings,
            "evidence": [],
        }
        return 1, obj
    obj = {
        "schema_version": CHECK_SCHEMA,
        "status": "pass" if not issues else "fail",
        "task_id": context.get("task_id", args.task),
        "report_id": context.get("report_id", report.parent.name),
        "checked_at": iso_now(),
        "artifact_digest": artifact_digest,
        "issues": issues,
        "warnings": warnings,
        "evidence": evidence,
    }
    atomic_write_json(report.parent / "checks.json", obj)
    return (0 if not issues else 1), obj


def validate_review(review: Any, rubric: dict[str, Any], digest: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not isinstance(review, dict) or review.get("schema_version") != REVIEW_SCHEMA:
        return [issue("review_invalid", "review.json has wrong schema")]
    if review.get("artifact_digest") != digest:
        issues.append(issue("review_digest_mismatch", "review artifact_digest does not match current report"))
    if review.get("rubric_version") != rubric.get("version"):
        issues.append(issue("review_rubric_mismatch", "review rubric_version does not match rubric"))
    if not isinstance(review.get("reviewer_id"), str) or not review["reviewer_id"].strip():
        issues.append(issue("reviewer_missing", "reviewer_id must be nonempty"))
    if review.get("verdict") != "pass":
        issues.append(issue("review_not_pass", "review verdict must be pass"))

    _, crit_allow, _ = validate_rubric(rubric)
    criteria = review.get("criteria")
    if not isinstance(criteria, list):
        issues.append(issue("review_criteria_invalid", "criteria must be a list"))
        criteria = []
    seen: set[str] = set()
    for item in criteria:
        if not isinstance(item, dict):
            issues.append(issue("review_criteria_invalid", "each criterion must be a mapping"))
            continue
        cid = item.get("id")
        status = item.get("status")
        if not isinstance(cid, str):
            issues.append(issue("review_criterion_invalid", "criterion id must be a string"))
            continue
        if cid in seen:
            issues.append(issue("review_criterion_duplicate", f"duplicate criterion id: {cid}"))
        seen.add(cid)
        if cid not in crit_allow:
            issues.append(issue("review_criterion_unknown", f"unexpected criterion id: {cid}"))
        if status not in {"pass", "fail", "not_applicable", "unknown"}:
            issues.append(issue("review_status_invalid", f"invalid criterion status for {cid}"))
        if status in {"fail", "unknown"}:
            issues.append(issue("review_mandatory_not_passed", f"criterion is {status}: {cid}"))
        if status == "not_applicable" and not crit_allow.get(cid, False):
            issues.append(issue("review_na_not_allowed", f"not_applicable is not allowed for {cid}"))
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            issues.append(issue("review_reason_missing", f"criterion reason is required: {cid}"))
        if not isinstance(item.get("evidence"), list) or not all(isinstance(x, str) for x in item.get("evidence", [])):
            issues.append(issue("review_evidence_invalid", f"criterion evidence must be a string list: {cid}"))
    if seen != set(crit_allow):
        issues.append(issue("review_criteria_set_mismatch", "review criteria ids must exactly match rubric criteria ids"))

    findings = review.get("findings", [])
    if not isinstance(findings, list):
        issues.append(issue("review_findings_invalid", "findings must be a list"))
        findings = []
    for item in findings:
        if not isinstance(item, dict):
            issues.append(issue("review_findings_invalid", "each finding must be a mapping"))
            continue
        if item.get("criterion_id") not in crit_allow:
            issues.append(issue("review_finding_criterion_invalid", f"finding has unknown criterion: {item.get('criterion_id')}"))
        if item.get("severity") not in {"blocker", "risk", "suggestion"}:
            issues.append(issue("review_finding_severity_invalid", f"invalid finding severity: {item.get('severity')}"))
        for key in ["report_location", "message", "required_change"]:
            if not isinstance(item.get(key), str) or not item[key].strip():
                issues.append(issue("review_finding_field_missing", f"finding {key} must be nonempty"))
        if not isinstance(item.get("evidence"), list) or not all(isinstance(x, str) for x in item.get("evidence", [])):
            issues.append(issue("review_finding_evidence_invalid", "finding evidence must be a string list"))
        if item.get("severity") == "blocker":
            issues.append(issue("review_blocker_finding", "pass review cannot include blocker findings"))
    scope = review.get("scope_assessment")
    if not isinstance(scope, dict):
        issues.append(issue("review_scope_invalid", "scope_assessment must be a mapping"))
    else:
        if scope.get("status") not in {"within_scope", "drift_disclosed"}:
            issues.append(issue("review_scope_not_pass", f"scope status cannot pass: {scope.get('status')}"))
        if not isinstance(scope.get("reason"), str) or not scope["reason"].strip():
            issues.append(issue("review_scope_reason_missing", "scope_assessment reason must be nonempty"))
        if not isinstance(scope.get("evidence"), list) or not all(isinstance(x, str) for x in scope.get("evidence", [])):
            issues.append(issue("review_scope_evidence_invalid", "scope_assessment evidence must be a string list"))
    return issues


def cmd_finalize(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    workspace = canonical_workspace(safe_absolute(Path(args.workspace)))
    report = safe_absolute(Path(args.report))
    context, issues, warnings, cited = validate_report(report, args.task, workspace)
    digest, evidence = digest_manifest(report, cited)
    checks_path = report.parent / "checks.json"
    review_path = report.parent / "review.json"
    checks = load_json_strict(checks_path)
    review = load_json_strict(review_path)
    if not isinstance(checks, dict) or checks.get("schema_version") != CHECK_SCHEMA:
        issues.append(issue("checks_invalid", "checks.json has wrong schema"))
    else:
        if checks.get("status") != "pass":
            issues.append(issue("checks_not_pass", "checks.json must have status pass"))
        if checks.get("artifact_digest") != digest:
            issues.append(issue("checks_digest_mismatch", "checks artifact_digest does not match current report"))
        if checks.get("task_id") != args.task or checks.get("report_id") != report.parent.name:
            issues.append(issue("checks_metadata_mismatch", "checks task/report metadata does not match"))
    rubric, _, rub_warnings = load_rubric(Path(__file__).resolve())
    warnings.extend(rub_warnings)
    issues.extend(validate_review(review, rubric, digest))
    obj = {
        "status": "pass" if not issues else "fail",
        "task_id": context.get("task_id", args.task),
        "report_id": context.get("report_id", report.parent.name),
        "report": str(report),
        "artifact_digest": digest,
        "review_origin": "not_independently_verified_by_script",
        "issues": issues,
        "warnings": warnings,
        "evidence": evidence,
    }
    return (0 if not issues else 1), obj


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize, check, and finalize work reports")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--workspace", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--request", required=True)
    init.add_argument("--task-dir")
    init.add_argument("--output-root")
    init.add_argument("--state")
    init.add_argument("--kind", choices=["progress", "final"], default="progress")
    init.add_argument("--window-start")
    init.add_argument("--window-end")
    init.set_defaults(func=cmd_init)
    check = sub.add_parser("check")
    check.add_argument("--report", required=True)
    check.add_argument("--task", required=True)
    check.add_argument("--workspace", required=True)
    check.set_defaults(func=cmd_check)
    final = sub.add_parser("finalize")
    final.add_argument("--report", required=True)
    final.add_argument("--task", required=True)
    final.add_argument("--workspace", required=True)
    final.set_defaults(func=cmd_finalize)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        rc, obj = args.func(args)
        emit(obj)
        return rc
    except ValidationFailure as exc:
        emit({"status": "fail", "issues": exc.issues, "warnings": exc.warnings})
        return 1
    except Exception as exc:
        emit({"status": "error", "issues": [issue("tool_error", str(exc))], "warnings": []})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

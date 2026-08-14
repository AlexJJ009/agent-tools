#!/usr/bin/env python3
"""Agent-safe Git workspace inspection and worktree creation.

The CLI intentionally excludes removal, merge, push, and arbitrary project
hooks. It uses only the Python standard library and Git.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import hashlib
import json
import ntpath
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator, Sequence


VERSION = "0.1.0"
OUTPUT_SCHEMA_VERSION = 1
DEFAULT_MIN_FREE_GIB = 2.0
DEFAULT_SCAN_SECONDS = 8.0
DEFAULT_SCAN_FILES = 200_000
REGISTRY_VERSION = 1

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".nox",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "_worktrees",
    "_artifacts",
    "_cache",
}

ARTIFACT_NAMES = {
    "artifacts",
    "checkpoints",
    "checkpoint",
    "eval_outputs",
    "logs",
    "metrics",
    "output",
    "outputs",
    "results",
    "runs",
    "validation",
    "wandb",
}

CACHE_NAMES = {
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    ".next",
    "build",
    "dist",
    "target",
}

DEPENDENCY_NAMES = {"node_modules", ".venv", "venv"}
DETECTION_SKIP_DIRS = SKIP_DIRS | ARTIFACT_NAMES | CACHE_NAMES

MARKERS = {
    "node": {"package.json"},
    "pnpm": {"pnpm-lock.yaml"},
    "npm": {"package-lock.json", "npm-shrinkwrap.json"},
    "yarn": {"yarn.lock"},
    "bun": {"bun.lock", "bun.lockb"},
    "python": {"pyproject.toml", "setup.py", "setup.cfg"},
    "uv": {"uv.lock"},
    "requirements": {"requirements.txt", "requirements-dev.txt"},
    "conda": {"environment.yml", "environment.yaml", "conda-lock.yml"},
    "go": {"go.mod"},
    "rust": {"Cargo.toml"},
    "docker": {"compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml", "Dockerfile"},
    "huggingface": {"README.md"},
}


class AgentWtError(RuntimeError):
    """Expected user-facing failure."""

    def __init__(self, message: str, code: str = "agent_wt_error") -> None:
        super().__init__(message)
        self.code = code


@dataclasses.dataclass(frozen=True)
class RepoInfo:
    root: Path
    git_dir: Path
    common_dir: Path
    branch: str | None
    head: str
    dirty: bool
    remote: str | None
    worktrees: list[dict[str, Any]]


@dataclasses.dataclass
class ScanBudget:
    deadline: float
    max_files: int
    files: int = 0
    truncated: bool = False

    def consume(self) -> bool:
        self.files += 1
        if self.files > self.max_files or time.monotonic() > self.deadline:
            self.truncated = True
            return False
        return True


def run(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(argv),
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise AgentWtError(
            f"command failed ({completed.returncode}): {shlex.join(argv)}\n{detail}",
            "command_failed",
        )
    return completed


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(("git", *args), cwd=cwd, check=check)


def canonical_git_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def parse_worktrees(raw: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for token in raw.split("\0"):
        if not token:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = token.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch_ref"] = value
            current["branch"] = value.removeprefix("refs/heads/")
        elif key in {"bare", "detached"}:
            current[key] = True
        elif key in {"locked", "prunable"}:
            current[key] = value or True
    if current:
        records.append(current)
    return records


def get_repo(cwd: Path) -> RepoInfo:
    probe = git(cwd, "rev-parse", "--show-toplevel", check=False)
    if probe.returncode != 0:
        raise AgentWtError(f"not inside a non-bare Git working tree: {cwd}", "not_git_repository")
    root = Path(probe.stdout.strip()).resolve()
    git_dir = canonical_git_path(root, git(root, "rev-parse", "--git-dir").stdout.strip())
    common_dir = canonical_git_path(root, git(root, "rev-parse", "--git-common-dir").stdout.strip())
    branch_result = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    dirty = bool(git(root, "status", "--porcelain=v1", "--untracked-files=normal").stdout)
    remote_result = git(root, "config", "--get", "remote.origin.url", check=False)
    remote = remote_result.stdout.strip() or None
    wt_raw = git(root, "worktree", "list", "--porcelain", "-z").stdout
    return RepoInfo(
        root=root,
        git_dir=git_dir,
        common_dir=common_dir,
        branch=branch,
        head=head,
        dirty=dirty,
        remote=remote,
        worktrees=parse_worktrees(wt_raw),
    )


def iter_project_files(root: Path, max_depth: int = 3) -> Iterator[Path]:
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        dirs[:] = [name for name in dirs if name not in DETECTION_SKIP_DIRS]
        if depth >= max_depth:
            dirs[:] = []
        for name in files:
            yield current_path / name


def detect_project(root: Path) -> dict[str, Any]:
    found: dict[str, list[str]] = {key: [] for key in MARKERS}
    marker_to_types: dict[str, list[str]] = {}
    for kind, names in MARKERS.items():
        for name in names:
            marker_to_types.setdefault(name, []).append(kind)

    for path in iter_project_files(root):
        for kind in marker_to_types.get(path.name, []):
            found[kind].append(str(path.relative_to(root)))

    # README alone is not evidence of Hugging Face usage. Use common source/config signals.
    hf_evidence: list[str] = []
    for candidate in ("pyproject.toml", "requirements.txt", "environment.yml", "environment.yaml"):
        path = root / candidate
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:2_000_000]
            except OSError:
                continue
            if re.search(r"huggingface|transformers|datasets", text, re.IGNORECASE):
                hf_evidence.append(candidate)
    found["huggingface"] = hf_evidence

    detected = sorted(kind for kind, paths in found.items() if paths)
    lockfiles = sorted(
        {path for kind in ("pnpm", "npm", "yarn", "bun", "uv", "requirements", "conda") for path in found[kind]}
    )
    lock_hash = hash_files(root, lockfiles)
    return {
        "detected": detected,
        "markers": {kind: paths for kind, paths in found.items() if paths},
        "lockfiles": lockfiles,
        "lock_hash": lock_hash,
        "setup": setup_plan(root, found),
    }


def hash_files(root: Path, relative_paths: Sequence[str]) -> str | None:
    if not relative_paths:
        return None
    digest = hashlib.sha256()
    for relative in sorted(relative_paths):
        path = root / relative
        try:
            content = path.read_bytes()
        except OSError:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def setup_plan(root: Path, found: dict[str, list[str]]) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    root_names = {path.name for path in root.iterdir()} if root.is_dir() else set()
    if "pnpm-lock.yaml" in root_names:
        plans.append({"adapter": "pnpm", "argv": ["pnpm", "install", "--frozen-lockfile"]})
    elif "package-lock.json" in root_names or "npm-shrinkwrap.json" in root_names:
        plans.append({"adapter": "npm", "argv": ["npm", "ci"]})
    elif "yarn.lock" in root_names:
        plans.append({"adapter": "yarn", "argv": ["yarn", "install", "--immutable"]})
    elif "bun.lock" in root_names or "bun.lockb" in root_names:
        plans.append({"adapter": "bun", "argv": ["bun", "install", "--frozen-lockfile"]})
    if "uv.lock" in root_names:
        plans.append({"adapter": "uv", "argv": ["uv", "sync", "--frozen"]})
    elif found.get("requirements") or found.get("conda"):
        plans.append(
            {
                "adapter": "python-manual",
                "argv": None,
                "reason": "requirements/Conda project needs an explicit environment identity; no automatic setup",
            }
        )
    return plans


def slugify(value: str) -> str:
    slug = value.strip().replace("/", "--")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug)
    slug = re.sub(r"[-_.]{2,}", "-", slug).strip("-._")
    if not slug:
        raise AgentWtError("branch name does not produce a usable path", "invalid_branch")
    if len(slug) > 96:
        suffix = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
        slug = f"{slug[:87]}-{suffix}"
    return slug


def repo_name(repo: RepoInfo) -> str:
    if repo.remote:
        tail = repo.remote.rstrip("/").rsplit("/", 1)[-1]
        if ":" in tail:
            tail = tail.rsplit(":", 1)[-1]
        name = tail.removesuffix(".git")
        if name:
            return slugify(name)
    return slugify(repo.root.name)


def read_json_object(path: Path, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentWtError(f"cannot read policy {path}: {exc}", code) from exc
    if not isinstance(value, dict):
        raise AgentWtError(f"policy must contain a JSON object: {path}", code)
    return value


def user_policy_path() -> Path:
    override = os.environ.get("AGENT_WT_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "agent-wt" / "config.json"


def path_policy(repo: RepoInfo, root_override: Path | None) -> tuple[Path, str]:
    if root_override is not None:
        return root_override.expanduser().resolve(), "cli"

    repository_policy = repo.root / ".agent-wt.json"
    if repository_policy.is_file():
        value = read_json_object(repository_policy, code="repository_policy_invalid")
        configured = value.get("worktree_root")
        if configured:
            candidate = Path(str(configured)).expanduser()
            if not candidate.is_absolute():
                candidate = repo.root / candidate
            return candidate.resolve(), "repository"

    user_policy = user_policy_path()
    if user_policy.is_file():
        value = read_json_object(user_policy, code="user_policy_invalid")
        configured = value.get("worktree_root")
        if configured:
            candidate = Path(str(configured)).expanduser()
            if not candidate.is_absolute():
                raise AgentWtError(
                    f"user policy worktree_root must be absolute: {user_policy}",
                    "user_policy_invalid",
                )
            return candidate.resolve(), "user_or_machine"

    configured = os.environ.get("AGENT_WT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve(), "environment"
    return repo.root.parent / "_worktrees", "external_sibling_default"


def default_roots(repo: RepoInfo, branch: str, root_override: Path | None) -> dict[str, Any]:
    name = repo_name(repo)
    slug = slugify(branch)
    workspace_root, policy_source = path_policy(repo, root_override)
    shared_parent = workspace_root.parent
    return {
        "workspace_root": workspace_root,
        "worktree": workspace_root / name / slug,
        "artifact_root": shared_parent / "_artifacts" / name / slug,
        "cache_root": shared_parent / "_cache",
        "policy_source": policy_source,
    }


def is_within(path: Path, parent: Path, *, platform_name: str | None = None) -> bool:
    if (platform_name or os.name) == "nt":
        try:
            return ntpath.commonpath((ntpath.normcase(str(path)), ntpath.normcase(str(parent)))) == ntpath.normcase(str(parent))
        except ValueError:
            return False
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def existing_ancestor(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def filesystem_info(path: Path) -> dict[str, Any]:
    ancestor = existing_ancestor(path)
    usage = shutil.disk_usage(ancestor)
    stat = ancestor.stat()
    return {
        "probe_path": str(ancestor),
        "device": stat.st_dev,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "free_gib": round(usage.free / (1024**3), 3),
    }


def branch_exists(repo: RepoInfo, branch: str) -> bool:
    result = git(repo.root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    return result.returncode == 0


def checked_out_path(repo: RepoInfo, branch: str) -> str | None:
    for item in repo.worktrees:
        if item.get("branch") == branch:
            return item.get("path")
    return None


def validate_branch(repo: RepoInfo, branch: str) -> None:
    result = git(repo.root, "check-ref-format", "--branch", branch, check=False)
    if result.returncode != 0:
        raise AgentWtError(f"invalid branch name: {branch}", "invalid_branch")


def cache_environment(cache_root: Path, artifact_root: Path, repo: RepoInfo, branch: str) -> dict[str, str]:
    namespace = f"{repo_name(repo)}-{slugify(branch)}"
    return {
        "AGENT_WT_ARTIFACT_ROOT": str(artifact_root),
        "CARGO_HOME": str(cache_root / "cargo"),
        "COMPOSE_PROJECT_NAME": namespace[:63].lower(),
        "CONDA_PKGS_DIRS": str(cache_root / "conda-pkgs"),
        "GOCACHE": str(cache_root / "go-build"),
        "GOMODCACHE": str(cache_root / "go-mod"),
        "HF_HOME": str(cache_root / "huggingface"),
        "NPM_CONFIG_CACHE": str(cache_root / "npm"),
        "PIP_CACHE_DIR": str(cache_root / "pip"),
        "PNPM_STORE_DIR": str(cache_root / "pnpm-store"),
        "UV_CACHE_DIR": str(cache_root / "uv"),
        "YARN_CACHE_FOLDER": str(cache_root / "yarn"),
    }


def adapter_guidance(project: dict[str, Any]) -> list[dict[str, str]]:
    guidance: list[dict[str, str]] = []
    mapping = {
        "node": ("package-manager download/content store", "worktree-local node_modules and install state"),
        "pnpm": ("pnpm content-addressed store", "worktree-local node_modules graph"),
        "npm": ("npm download cache", "worktree-local node_modules"),
        "yarn": ("Yarn cache", "worktree-local install state"),
        "bun": ("Bun download cache", "worktree-local installed dependency graph"),
        "python": ("pip/uv wheel and source caches", "worktree-local virtual environment"),
        "uv": ("uv cache", "worktree-local .venv"),
        "requirements": ("pip cache", "worktree-local virtual environment"),
        "conda": ("Conda package cache", "isolated named or prefix environment"),
        "go": ("module and build caches", "worktree-local source and generated outputs"),
        "rust": ("Cargo registry and Git cache", "worktree-local target directory"),
        "docker": ("daemon image/layer cache", "branch-specific Compose project, ports, volumes, and databases"),
        "huggingface": ("HF Hub blobs/snapshots cache", "branch-specific writable training and evaluation artifacts"),
    }
    for adapter in project["detected"]:
        shared, isolated = mapping[adapter]
        guidance.append({"adapter": adapter, "shared": shared, "isolated": isolated})
    guidance.append({
        "adapter": "ml_artifacts",
        "shared": "immutable model/dataset caches only",
        "isolated": "logs, W&B runs, checkpoints, metrics, validation, and generated datasets",
    })
    return guidance


def default_state_home(
    *,
    platform_name: str | None = None,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    platform_name = platform_name or os.name
    environ = environ or os.environ
    home = home or Path.home()
    if platform_name == "nt":
        return Path(environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "agent-wt" / "state"
    return Path(environ.get("XDG_STATE_HOME", home / ".local" / "state")) / "agent-wt"


def registry_dir() -> Path:
    override = os.environ.get("AGENT_WT_STATE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return default_state_home().expanduser().resolve()


@contextlib.contextmanager
def registry_lock(directory: Path, *, timeout_seconds: float = 10.0) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / "registry.lock"
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise AgentWtError(f"timed out waiting for registry lock: {lock_path}", "registry_lock_timeout")
            time.sleep(0.05)
    try:
        os.write(descriptor, f"pid={os.getpid()} created={time.time()}\n".encode("ascii"))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def load_registry() -> dict[str, Any]:
    path = registry_dir() / "registry.json"
    if not path.exists():
        return {"version": REGISTRY_VERSION, "worktrees": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentWtError(f"cannot read registry {path}: {exc}", "registry_unreadable") from exc
    if data.get("version") != REGISTRY_VERSION or not isinstance(data.get("worktrees"), list):
        raise AgentWtError(f"unsupported registry format: {path}", "registry_version_unsupported")
    return data


def save_registry(data: dict[str, Any]) -> Path:
    directory = registry_dir()
    path = directory / "registry.json"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return path


def register(entry: dict[str, Any]) -> Path:
    directory = registry_dir()
    with registry_lock(directory):
        data = load_registry()
        target = entry["worktree_path"]
        data["worktrees"] = [item for item in data["worktrees"] if item.get("worktree_path") != target]
        data["worktrees"].append(entry)
        data["worktrees"].sort(key=lambda item: item.get("created_at", ""))
        return save_registry(data)


def registry_entry(path: Path) -> dict[str, Any] | None:
    target = str(path.resolve())
    for item in load_registry()["worktrees"]:
        try:
            if str(Path(item["worktree_path"]).resolve()) == target:
                return item
        except (KeyError, OSError):
            continue
    return None


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def stat_allocated_bytes(stat_result: os.stat_result) -> tuple[int, str]:
    blocks = getattr(stat_result, "st_blocks", None)
    if blocks is None:
        return stat_result.st_size, "apparent_fallback"
    return blocks * 512, "allocated"


def directory_allocated_size(path: Path, budget: ScanBudget) -> tuple[int, str]:
    total = 0
    kind = "allocated"
    try:
        stack = [path]
        while stack:
            current = stack.pop()
            if not budget.consume():
                break
            try:
                stat = current.lstat()
            except OSError:
                continue
            value, current_kind = stat_allocated_bytes(stat)
            total += value
            if current_kind == "apparent_fallback":
                kind = current_kind
            if current.is_dir() and not current.is_symlink():
                try:
                    stack.extend(current.iterdir())
                except OSError:
                    continue
    except OSError:
        pass
    return total, kind


def find_named_dirs(root: Path, names: set[str], max_depth: int = 3) -> list[Path]:
    results: list[Path] = []
    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        kept: list[str] = []
        for name in dirs:
            if name in names:
                results.append(current_path / name)
                continue
            if name in SKIP_DIRS:
                continue
            if depth < max_depth:
                kept.append(name)
        dirs[:] = kept
    return sorted(set(results))


def find_conda_env_links(root: Path, max_depth: int = 3) -> list[Path]:
    results: list[Path] = []
    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        for name in list(dirs):
            candidate = current_path / name
            if candidate.is_symlink() and (candidate / "conda-meta").is_dir():
                results.append(candidate)
        if depth >= max_depth:
            dirs[:] = []
    return results


def scan_workspace_dirs(
    root: Path,
    *,
    max_seconds: float = DEFAULT_SCAN_SECONDS,
    max_files: int = DEFAULT_SCAN_FILES,
) -> dict[str, Any]:
    budget = ScanBudget(time.monotonic() + max_seconds, max_files)
    entries: list[dict[str, Any]] = []
    kinds = (("dependency", DEPENDENCY_NAMES), ("cache_or_build", CACHE_NAMES), ("artifact", ARTIFACT_NAMES))
    seen: set[Path] = set()
    for kind, names in kinds:
        for path in find_named_dirs(root, names):
            if path in seen:
                continue
            seen.add(path)
            allocated, size_kind = directory_allocated_size(path, budget)
            entries.append(
                {
                    "kind": kind,
                    "path": str(path.relative_to(root)),
                    "allocated_bytes": allocated,
                    "allocated": human_bytes(allocated),
                    "size_kind": size_kind,
                    "symlink": path.is_symlink(),
                }
            )
            if budget.truncated:
                break
        if budget.truncated:
            break
    entries.sort(key=lambda item: item["allocated_bytes"], reverse=True)
    return {
        "entries": entries,
        "truncated": budget.truncated,
        "files_scanned": budget.files,
        "size_semantics": "reported directory sizes are lower bounds when truncated and never prove byte-level deduplication",
        "conda_environment_symlinks": [str(path.relative_to(root)) for path in find_conda_env_links(root)],
    }


def repo_payload(repo: RepoInfo) -> dict[str, Any]:
    current = next((item for item in repo.worktrees if Path(item.get("path", "")).resolve() == repo.root), None)
    return {
        "repo_root": str(repo.root),
        "git_dir": str(repo.git_dir),
        "git_common_dir": str(repo.common_dir),
        "linked_worktree": repo.git_dir != repo.common_dir,
        "branch": repo.branch,
        "head": repo.head,
        "dirty": repo.dirty,
        "remote": repo.remote,
        "worktree_count": len(repo.worktrees),
        "current_worktree": current,
    }


def cmd_inspect(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    repo = get_repo(args.cwd)
    payload = repo_payload(repo)
    payload["project"] = detect_project(repo.root)
    payload["filesystem"] = filesystem_info(repo.root)
    payload["registry_entry"] = registry_entry(repo.root)
    return payload, 0


def cmd_decide(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    repo = get_repo(args.cwd)
    if args.untrusted_users:
        return {
            "recommendation": "unsupported",
            "reasons": ["worktrees share Git metadata/config and are not an untrusted-user boundary"],
            "guidance": "Use a separately owned clone outside agent-wt; v1 does not create or migrate clones.",
            "repo": repo_payload(repo),
        }, 0

    reasons: list[str] = []
    if repo.dirty:
        reasons.append("current checkout has uncommitted or untracked changes")
    flag_reasons = {
        "parallel": "another task or agent must run concurrently",
        "preserve_current": "the current checkout must remain unchanged",
        "long_running": "a long-running process must keep its current files",
        "review": "review work must coexist with active development",
        "hotfix": "a hotfix must start without disturbing current work",
        "shared_working_directory": "trusted collaborators share the same Unix checkout area",
    }
    for name, reason in flag_reasons.items():
        if getattr(args, name):
            reasons.append(reason)
    recommendation = "worktree" if reasons else "branch"
    return {
        "recommendation": recommendation,
        "reasons": reasons or ["one task can safely use the current clean checkout"],
        "repo": repo_payload(repo),
        "caveat": "branch is a ref, not a second workspace" if recommendation == "branch" else None,
    }, 0


def create_plan(args: argparse.Namespace, repo: RepoInfo) -> dict[str, Any]:
    validate_branch(repo, args.branch)
    roots = default_roots(repo, args.branch, args.root)
    target = roots["worktree"].resolve()
    if is_within(target, repo.root):
        raise AgentWtError(f"refusing worktree inside repository: {target}", "target_inside_repository")
    if target.exists():
        raise AgentWtError(f"target already exists: {target}", "target_exists")
    checked_out = checked_out_path(repo, args.branch)
    if checked_out:
        raise AgentWtError(f"branch is already checked out at: {checked_out}", "branch_checked_out")
    base_result = git(repo.root, "rev-parse", "--verify", f"{args.base}^{{commit}}", check=False)
    if base_result.returncode != 0:
        raise AgentWtError(f"base does not resolve to a commit: {args.base}", "base_not_found")
    base_sha = base_result.stdout.strip()
    exists = branch_exists(repo, args.branch)
    if exists:
        branch_head = git(repo.root, "rev-parse", f"refs/heads/{args.branch}").stdout.strip()
        if branch_head != base_sha:
            raise AgentWtError(
                f"existing branch {args.branch} is {branch_head[:12]}, not requested base {base_sha[:12]}",
                "branch_base_mismatch",
            )
    repo_fs = filesystem_info(repo.root)
    target_fs = filesystem_info(target)
    warnings: list[str] = []
    if repo_fs["device"] != target_fs["device"]:
        warnings.append("worktree root is on a different filesystem; hardlink-based reuse may degrade to copies")
    min_free_bytes = int(args.min_free_gib * 1024**3)
    if target_fs["free_bytes"] < min_free_bytes and not args.allow_low_space:
        raise AgentWtError(
            f"target filesystem has only {target_fs['free_gib']} GiB free; "
            f"requires {args.min_free_gib} GiB (override with --allow-low-space)",
            "insufficient_space",
        )
    project = detect_project(repo.root)
    env = cache_environment(roots["cache_root"], roots["artifact_root"], repo, args.branch)
    commands: list[list[str]] = []
    if exists:
        commands.append(["git", "worktree", "add", str(target), args.branch])
    else:
        commands.append(["git", "worktree", "add", "-b", args.branch, str(target), base_sha])
    return {
        "repo_root": str(repo.root),
        "git_common_dir": str(repo.common_dir),
        "remote": repo.remote,
        "branch": args.branch,
        "branch_exists": exists,
        "base": args.base,
        "base_sha": base_sha,
        "worktree_path": str(target),
        "workspace_root": str(roots["workspace_root"]),
        "path_policy_source": roots["policy_source"],
        "artifact_root": str(roots["artifact_root"]),
        "cache_root": str(roots["cache_root"]),
        "filesystem": {"repo": repo_fs, "target": target_fs},
        "project": project,
        "environment": env,
        "adapter_guidance": adapter_guidance(project),
        "commands": commands,
        "warnings": warnings,
        "dry_run": bool(args.dry_run),
    }


def cmd_create(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    repo = get_repo(args.cwd)
    plan = create_plan(args, repo)
    if args.dry_run:
        return plan, 0

    target = Path(plan["worktree_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    git(repo.root, *plan["commands"][0][1:])
    artifact_root = Path(plan["artifact_root"])
    artifact_root.mkdir(parents=True, exist_ok=True)

    # Re-detect in the checked-out branch because its lockfiles can differ from the base checkout.
    plan["project"] = detect_project(target)
    setup_results = [
        {**item, "status": "planned" if item.get("argv") else "manual"}
        for item in plan["project"]["setup"]
    ]
    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    entry = {
        "repo_name": repo_name(repo),
        "repo_root": str(repo.root),
        "git_common_dir": str(repo.common_dir),
        "remote": repo.remote,
        "branch": args.branch,
        "base_sha": plan["base_sha"],
        "worktree_path": str(target),
        "artifact_root": str(artifact_root),
        "cache_root": plan["cache_root"],
        "created_at": created_at,
        "owner": os.environ.get("USER") or os.environ.get("USERNAME") or "unknown",
        "task": args.task,
        "project_types": plan["project"]["detected"],
        "lock_hash": plan["project"]["lock_hash"],
        "setup": setup_results,
    }
    registry_path = register(entry)
    plan.update(
        {
            "created_at": created_at,
            "registry_path": str(registry_path),
            "setup_results": setup_results,
            "dry_run": False,
        }
    )
    return plan, 0


def cmd_list(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.all:
        data = load_registry()
        data["registry_path"] = str(registry_dir() / "registry.json")
        return data, 0
    repo = get_repo(args.cwd)
    registry = load_registry()["worktrees"]
    by_path = {str(Path(item.get("worktree_path", "")).resolve()): item for item in registry if item.get("worktree_path")}
    worktrees = []
    for item in repo.worktrees:
        path = str(Path(item["path"]).resolve())
        worktrees.append({**item, "registered": path in by_path, "registry": by_path.get(path)})
    return {"repo": repo_payload(repo), "worktrees": worktrees}, 0


def cmd_doctor(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    target = args.path.resolve() if args.path else args.cwd
    repo = get_repo(target)
    project = detect_project(repo.root)
    scan = scan_workspace_dirs(
        repo.root,
        max_seconds=args.scan_seconds,
        max_files=args.scan_files,
    )
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    entry = registry_entry(repo.root)
    linked = repo.git_dir != repo.common_dir
    if linked and not entry:
        warnings.append("linked worktree is not recorded in the agent-wt registry")
    if entry and entry.get("branch") != repo.branch:
        errors.append("registry branch does not match the branch currently checked out")
    if (repo.root / ".gitmodules").is_file() and linked:
        warnings.append("Git documents incomplete submodule support with multiple worktrees")
    if repo.dirty:
        notes.append("working tree has uncommitted or untracked changes")

    fs = filesystem_info(repo.root)
    if fs["free_bytes"] < int(args.min_free_gib * 1024**3):
        warnings.append(f"filesystem free space is below {args.min_free_gib} GiB")

    for item in scan["entries"]:
        allocated = item["allocated_bytes"]
        if item["kind"] == "dependency" and item["symlink"]:
            warnings.append(f"whole mutable dependency environment is symlinked: {item['path']}")
        if item["kind"] == "artifact" and allocated >= args.artifact_warning_mib * 1024**2:
            warnings.append(f"large artifact directory remains inside source checkout: {item['path']} ({item['allocated']})")
        if item["kind"] == "cache_or_build" and allocated >= args.build_warning_mib * 1024**2:
            warnings.append(f"large generated cache/build directory: {item['path']} ({item['allocated']})")
    for path in scan["conda_environment_symlinks"]:
        warnings.append(f"whole mutable Conda environment is symlinked: {path}")
    if scan["truncated"]:
        warnings.append("directory size scan hit its time/file budget; reported sizes are lower bounds")

    worktree_config = git(repo.root, "config", "--bool", "extensions.worktreeConfig", check=False)
    if linked and worktree_config.returncode != 0:
        notes.append("per-worktree Git config is not enabled; repository config and hooks are shared")

    status = "error" if errors else "warning" if warnings else "healthy"
    return {
        "status": status,
        "repo": repo_payload(repo),
        "project": project,
        "filesystem": fs,
        "registry_entry": entry,
        "scan": scan,
        "errors": errors,
        "warnings": warnings,
        "notes": notes,
    }, 2 if errors else 1 if warnings else 0


def print_human(command: str, payload: dict[str, Any]) -> None:
    if command == "decide":
        print(f"recommendation: {payload['recommendation']}")
        for reason in payload["reasons"]:
            print(f"  - {reason}")
        return
    if command == "create":
        print(f"worktree: {payload['worktree_path']}")
        print(f"branch: {payload['branch']} @ {payload['base_sha']}")
        print(f"artifact root: {payload['artifact_root']}")
        print(f"cache root: {payload['cache_root']}")
        print(f"mode: {'dry-run' if payload.get('dry_run') else 'created'}")
        for warning in payload.get("warnings", []):
            print(f"warning: {warning}", file=sys.stderr)
        return
    if command == "doctor":
        print(f"status: {payload['status']}")
        for error in payload["errors"]:
            print(f"error: {error}")
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        for note in payload["notes"]:
            print(f"note: {note}")
        return
    if command == "list":
        if "registry_path" in payload:
            for item in payload.get("worktrees", []):
                print(f"{item.get('branch')}\t{item.get('worktree_path')}")
        else:
            for item in payload.get("worktrees", []):
                branch = item.get("branch", "(detached)")
                marker = "managed" if item.get("registered") else "unmanaged"
                print(f"{branch}\t{item.get('path')}\t{marker}")
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-wt",
        description="Inspect, decide, create, list, and diagnose managed Git worktrees.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("-C", "--cwd", type=Path, default=Path.cwd(), help="repository working directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="inspect repository and project adapters")
    inspect_parser.add_argument("--json", action="store_true")
    inspect_parser.set_defaults(handler=cmd_inspect)

    decide_parser = subparsers.add_parser("decide", help="recommend branch, worktree, or unsupported guidance")
    decide_parser.add_argument("--parallel", action="store_true")
    decide_parser.add_argument("--preserve-current", action="store_true")
    decide_parser.add_argument("--long-running", action="store_true")
    decide_parser.add_argument("--review", action="store_true")
    decide_parser.add_argument("--hotfix", action="store_true")
    decide_parser.add_argument("--shared-working-directory", action="store_true")
    decide_parser.add_argument("--untrusted-users", action="store_true")
    decide_parser.add_argument("--json", action="store_true")
    decide_parser.set_defaults(handler=cmd_decide)

    create_parser = subparsers.add_parser("create", help="create and register a managed worktree")
    create_parser.add_argument("branch")
    create_parser.add_argument("--base", default="HEAD")
    create_parser.add_argument("--root", type=Path, help="managed worktree root")
    create_parser.add_argument("--task", default="manual")
    create_parser.add_argument("--dry-run", action="store_true")
    create_parser.add_argument("--allow-low-space", action="store_true")
    create_parser.add_argument("--min-free-gib", type=float, default=DEFAULT_MIN_FREE_GIB)
    create_parser.add_argument("--json", action="store_true")
    create_parser.set_defaults(handler=cmd_create)

    list_parser = subparsers.add_parser("list", help="list current-repository worktrees or registry entries")
    list_parser.add_argument("--all", action="store_true", help="list all registry entries")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(handler=cmd_list)

    doctor_parser = subparsers.add_parser("doctor", help="audit worktree policy and local disk risks")
    doctor_parser.add_argument("path", nargs="?", type=Path)
    doctor_parser.add_argument("--min-free-gib", type=float, default=DEFAULT_MIN_FREE_GIB)
    doctor_parser.add_argument("--artifact-warning-mib", type=int, default=100)
    doctor_parser.add_argument("--build-warning-mib", type=int, default=500)
    doctor_parser.add_argument("--scan-seconds", type=float, default=DEFAULT_SCAN_SECONDS)
    doctor_parser.add_argument("--scan-files", type=int, default=DEFAULT_SCAN_FILES)
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(handler=cmd_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.cwd = args.cwd.expanduser().resolve()
    try:
        payload, exit_code = args.handler(args)
    except AgentWtError as exc:
        if getattr(args, "json", False):
            print(json.dumps({
                "schema_version": OUTPUT_SCHEMA_VERSION,
                "command": args.command,
                "status": "error",
                "error_code": exc.code,
                "error": str(exc),
            }, indent=2, sort_keys=True))
        else:
            print(f"agent-wt: [{exc.code}] {exc}", file=sys.stderr)
        return 2
    payload = {"schema_version": OUTPUT_SCHEMA_VERSION, "command": args.command, **payload}
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_human(args.command, payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

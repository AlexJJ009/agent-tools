from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import __version__


@dataclass(frozen=True)
class Check:
    level: str
    name: str
    detail: str


IGNORED = {".agent-tools-managed", "migrated-command-skills", "__pycache__"}


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists():
        return "missing"
    files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file() and not IGNORED.intersection(p.parts)]
    for file in sorted(files, key=lambda item: str(item.relative_to(path) if path.is_dir() else item.name)):
        relative = str(file.relative_to(path)) if path.is_dir() else file.name
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _repo_config(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.startswith((" ", "#", "-")):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def run_doctor(home: Path, repo_config: Path | None, local_only: bool) -> list[Check]:
    home = home.expanduser().resolve()
    manifest_path = home / ".local" / "share" / "linear-workflow" / "install-manifest.json"
    checks: list[Check] = []
    if not manifest_path.is_file():
        return [Check("FAIL", "install-manifest", f"missing {manifest_path}")]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [Check("FAIL", "install-manifest", str(exc))]
    checks.append(Check("PASS" if manifest.get("version") == __version__ else "FAIL", "workflow-version", f'installed={manifest.get("version")} runtime={__version__}'))
    checks.append(Check("PASS" if Path(manifest.get("home", "")).resolve() == home else "FAIL", "profile-boundary", f"home={home}"))
    for target in manifest.get("targets", []):
        path = Path(target.get("path", ""))
        actual = fingerprint(path)
        level = "PASS" if actual == target.get("sha256") else "FAIL"
        checks.append(Check(level, f'{target.get("client", "unknown")}-target', str(path)))
    launcher = Path(manifest.get("launcher", ""))
    executable = launcher.is_file() and (os.name == "nt" or os.access(launcher, os.X_OK))
    checks.append(Check("PASS" if executable else "FAIL", "launcher", str(launcher)))
    marketplace = home / ".agents" / "plugins" / "marketplace.json"
    if marketplace.is_file() and os.name != "nt":
        insecure = bool(marketplace.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))
        checks.append(Check("FAIL" if insecure else "PASS", "file-permissions", str(marketplace)))
    else:
        checks.append(Check("PASS" if marketplace.is_file() else "FAIL", "file-permissions", str(marketplace)))

    git_name = subprocess.run(["git", "config", "--global", "user.name"], text=True, capture_output=True, check=False).stdout.strip()
    git_email = subprocess.run(["git", "config", "--global", "user.email"], text=True, capture_output=True, check=False).stdout.strip()
    checks.append(Check("PASS" if git_name and git_email else "WARN", "github-identity", "git author identity configured" if git_name and git_email else "git user.name/user.email incomplete"))
    if local_only:
        checks.append(Check("WARN", "github-auth", "SKIPPED — local-only/offline"))
        checks.append(Check("WARN", "linear-read", "SKIPPED — local-only/offline"))
    else:
        gh = shutil.which("gh")
        gh_ready = bool(gh) and subprocess.run([gh, "auth", "status"], capture_output=True, check=False).returncode == 0
        checks.append(Check("PASS" if gh_ready else "WARN", "github-auth", "ready" if gh_ready else "not authenticated"))
        linear_ready = bool(os.environ.get("LINEAR_API_KEY") or os.environ.get("LINEAR_TOKEN"))
        checks.append(Check("PASS" if linear_ready else "WARN", "linear-read", "credential present" if linear_ready else "MCP/token readiness not detected"))
    claude = shutil.which("claude")
    checks.append(Check("PASS" if claude else "WARN", "claude-runtime", "client discovered" if claude else "SKIPPED — client unavailable"))
    if repo_config is not None:
        config = _repo_config(repo_config)
        repo = config.get("repository_full_name", "")
        sync_map = config.get("github_linear_sync_map", "")
        checks.append(Check("PASS" if "/" in repo else "FAIL", "repo-allowlist", repo or "missing repository_full_name"))
        checks.append(Check("PASS" if sync_map else "FAIL", "sync-map", sync_map or "missing github_linear_sync_map"))
    return checks


def render(checks: list[Check]) -> int:
    for check in checks:
        print(f"{check.level}: {check.name}: {check.detail}")
    return 1 if any(check.level == "FAIL" for check in checks) else 0

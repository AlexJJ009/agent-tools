#!/usr/bin/env python3
"""Patch Codex Desktop so Connections preserve explicit Fast service tier.

This is a bundle patch for Codex Desktop versions whose webview assets contain:

- read-service-tier-for-request-*.js
- use-service-tier-settings-*.js
- app-server-manager-signals-*.js

It is deliberately narrower than a server-side `service_tier` override. The
patch only prevents Codex Desktop from dropping an explicit user-selected or
config-provided service tier when the target app-server is authenticated with an
API key / relay account. Standard/null tier requests remain standard/null.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


READ_SERVICE_TIER_REPLACEMENTS = [
    (
        "if(l.type!==`fromConfig`)return n(null,r(l,null),e);",
        "if(l.type!==`fromConfig`)return n(null,r(l,null),!0);",
        "allow explicit per-thread service tier selections",
    ),
    (
        "if(l.type!==`fromConfig`)return i(null,a(l,null),s);",
        "if(l.type!==`fromConfig`)return i(null,a(l,null),!0);",
        "allow explicit per-thread service tier selections",
    ),
    (
        "return d.service_tier==null?n(await m(o,c??d.model),d.service_tier,e):n(null,d.service_tier,e)",
        "return d.service_tier==null?n(await m(o,c??d.model),d.service_tier,e):n(null,d.service_tier,!0)",
        "allow explicit config service_tier values",
    ),
    (
        "return d.service_tier==null?i(await m(o,c??d.model),d.service_tier,s):i(null,d.service_tier,s)",
        "return d.service_tier==null?i(await m(o,c??d.model),d.service_tier,s):i(null,d.service_tier,!0)",
        "allow explicit config service_tier values",
    ),
]


USE_SERVICE_TIER_REPLACEMENTS = [
    (
        "p=s&&!f&&u!=null&&u?.requirements?.featureRequirements?.fast_mode!==!1",
        "p=!f&&u?.requirements?.featureRequirements?.fast_mode!==!1",
        "show service-tier selector outside ChatGPT auth when feature is not disabled",
    ),
    (
        "m=c&&!p&&d!=null&&d?.requirements?.featureRequirements?.fast_mode!==!1",
        "m=!p&&d?.requirements?.featureRequirements?.fast_mode!==!1",
        "show service-tier selector outside ChatGPT auth when feature is not disabled",
    ),
]


APP_SERVER_MANAGER_REPLACEMENTS = [
    (
        "me=a.serviceTier===void 0?pe:a.serviceTier,he={",
        (
            "me=(a.serviceTier===void 0?pe:a.serviceTier)??(await(async()=>{let t="
            "(await pm(e,ie))?.service_tier??null;return t===`fast`?AA:t})()),he={"
        ),
        "read host config service tier at the turn/start fallback layer",
    ),
    (
        (
            "function GA(e,t,n=!0){if(!n)return null;if(t==null){let t=e?.defaultServiceTier??null;"
            "return t==null?null:WA(e,t)}return t===jA?null:t}"
        ),
        (
            "function GA(e,t,n=!0){if(!n)return null;if(t==null){let t=e?.defaultServiceTier??null;"
            "return t==null?null:t===`fast`?AA:WA(e,t)}return t===jA?null:t===`fast`?AA:t}"
        ),
        "normalize legacy fast tier alias to provider priority tier",
    ),
    (
        (
            "function zA(e){return[{description:MA.standardDescription,iconKind:null,"
            "label:MA.standardLabel,tier:null,value:null},...(e?.serviceTiers??[]).map"
            "(e=>({description:LA(e),iconKind:PA(e.id,e.name),label:IA(e),tier:e,value:e.id}))]}"
        ),
        (
            "function zA(e){let t=e?.serviceTiers??[],n=t.some(e=>PA(e.id,e.name)===`fast`),"
            "r=n?t:[...t,{id:AA,name:`Fast`,description:null}];return[{description:"
            "MA.standardDescription,iconKind:null,label:MA.standardLabel,tier:null,value:null},"
            "...r.map(e=>({description:LA(e),iconKind:PA(e.id,e.name),label:IA(e),tier:e,value:e.id}))]}"
        ),
        "add Fast selector option when relay model metadata omits service tiers",
    ),
]


APP_MAIN_REPLACEMENTS = [
    (
        "function $B(e){return{fetchFromHost:D,finishPrimaryRuntimeInstallForFirstTurn:",
        "function $B(e){return{scope:e,fetchFromHost:D,finishPrimaryRuntimeInstallForFirstTurn:",
        "expose renderer scope to follow-up service tier fallback",
    ),
    (
        (
            '"send-follow-up-message":eV(async(e,{conversationId:t,model:n,prompt:r,'
            "reasoningEffort:i,serviceTier:a},o)=>{let s=e.getHostId(),c=!1,l=null;"
            "try{let u=r.trim();"
        ),
        (
            '"send-follow-up-message":eV(async(e,{conversationId:t,model:n,prompt:r,'
            "reasoningEffort:i,serviceTier:a},o)=>{let s=e.getHostId(),c=!1,l=null;"
            "try{a??=await _p(o.scope,s,n??e.getConversation(t)?.latestModel??null);let u=r.trim();"
        ),
        "read default service tier for ordinary follow-up messages",
    ),
]


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def asar_command() -> list[str]:
    if command_exists("asar"):
        return ["asar"]
    npm_npx = Path.home() / ".npm" / "_npx"
    if npm_npx.exists():
        cached = sorted(npm_npx.glob("*/node_modules/@electron/asar/bin/asar.mjs"))
        if cached:
            return ["node", str(cached[-1])]
    if command_exists("npx"):
        return ["npx", "--yes", "@electron/asar"]
    raise SystemExit("Missing asar tool. Install Node.js/npm so npx @electron/asar is available.")


def windows_store_asar_from_wsl() -> Path | None:
    powershell = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    if powershell.exists():
        try:
            result = subprocess.run(
                [
                    str(powershell),
                    "-NoProfile",
                    "-Command",
                    (
                        "$p=(Get-AppxPackage *Codex* | Select-Object -First 1).InstallLocation; "
                        "if ($p) { Join-Path $p 'app\\resources\\app.asar' }"
                    ),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
            )
            raw = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
            if raw:
                path = Path(raw.replace("\\", "/").replace("C:", "/mnt/c", 1))
                if path.exists():
                    return path
        except Exception:
            pass

    root = Path("/mnt/c/Program Files/WindowsApps")
    if not root.exists():
        return None
    candidates = []
    for path in root.glob("OpenAI.Codex_*_x64__2p2nqsd0c76g0/app/resources/app.asar"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, path))
    candidates.sort(reverse=True)
    candidates = [path for _, path in candidates]
    return candidates[0] if candidates else None


def default_asar() -> Path | None:
    system = platform.system()
    if system == "Darwin":
        path = Path("/Applications/Codex.app/Contents/Resources/app.asar")
        return path if path.exists() else None
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            path = Path(local) / "Programs" / "Codex" / "resources" / "app.asar"
            if path.exists():
                return path
        return None
    store = windows_store_asar_from_wsl()
    if store is not None:
        return store
    users = Path("/mnt/c/Users")
    if users.exists():
        for user in sorted(users.iterdir()):
            path = user / "AppData/Local/Programs/Codex/resources/app.asar"
            try:
                exists = path.exists()
            except OSError:
                continue
            if exists:
                return path
    return None


def patch_file(path: Path, replacements: list[tuple[str, str, str]], *, dry_run: bool) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8")
    original = text
    applied = 0
    matched = 0
    for old, new, label in replacements:
        if new in text:
            matched += 1
            print(f"[already] {path.name}: {label}")
            continue
        if old not in text:
            print(f"[warn] {path.name}: pattern not found: {label}")
            continue
        matched += 1
        text = text.replace(old, new, 1)
        applied += 1
        print(f"[patch] {path.name}: {label}")
    if text != original and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied, matched


def patch_tree(root: Path, *, dry_run: bool) -> int:
    assets = root / "webview" / "assets"
    if not assets.exists():
        raise SystemExit(f"Missing webview assets directory: {assets}")

    patches = 0
    matched = 0
    groups = [
        ("read-service-tier-for-request-*.js", READ_SERVICE_TIER_REPLACEMENTS),
        ("use-service-tier-settings-*.js", USE_SERVICE_TIER_REPLACEMENTS),
        ("app-server-manager-signals-*.js", APP_SERVER_MANAGER_REPLACEMENTS),
        ("app-main-*.js", APP_MAIN_REPLACEMENTS),
    ]
    for pattern, replacements in groups:
        files = sorted(assets.glob(pattern))
        if not files:
            print(f"[warn] no files matched {pattern}")
            continue
        for path in files:
            applied, seen = patch_file(path, replacements, dry_run=dry_run)
            patches += applied
            matched += seen
    return patches, matched


def patch_asar(asar_path: Path, output_path: Path, *, dry_run: bool) -> int:
    asar_path = asar_path.expanduser().resolve()
    if not asar_path.exists():
        raise SystemExit(f"Missing app.asar: {asar_path}")

    with tempfile.TemporaryDirectory(prefix="codex-asar-fast-") as tmp:
        root = Path(tmp) / "app"
        run([*asar_command(), "extract", str(asar_path), str(root)])
        patches, matched = patch_tree(root, dry_run=dry_run)
        if matched == 0:
            raise SystemExit("No bundle patches were applied. Codex version patterns may have changed.")
        if not dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            run([*asar_command(), "pack", str(root), str(output_path)])
    return patches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch Codex Desktop app.asar so remote Connections preserve explicit Fast service tier."
    )
    parser.add_argument("--asar", type=Path, default=None, help="Path to Codex app.asar.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write patched asar here. Defaults to ./app.fastmode-patched.asar next to the source.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Replace the source app.asar after writing a .connection-fast-backup copy.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Extract and report patches without writing output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    asar_path = args.asar or default_asar()
    if asar_path is None:
        raise SystemExit("Could not find Codex app.asar automatically. Pass --asar PATH.")

    asar_path = asar_path.expanduser().resolve()
    output_path = args.out
    if output_path is None:
        output_path = asar_path.with_name("app.connection-fast-patched.asar")
    output_path = output_path.expanduser().resolve()

    if args.in_place and args.dry_run:
        raise SystemExit("--in-place and --dry-run cannot be combined.")

    patches = patch_asar(asar_path, output_path, dry_run=args.dry_run)
    if args.dry_run:
        print(f"Dry run complete: {patches} patch(es) would be applied to {asar_path}")
        return 0

    if args.in_place:
        backup = asar_path.with_name("app.asar.connection-fast-backup")
        if not backup.exists():
            shutil.copy2(asar_path, backup)
            print(f"Backup written: {backup}")
        shutil.copy2(output_path, asar_path)
        print(f"Patched in place: {asar_path}")
    else:
        print(f"Patched asar written: {output_path}")
        print("Review the output, then replace the app.asar for your Codex Desktop build if appropriate.")
    print(f"Applied {patches} patch(es). Restart Codex Desktop before testing Connections.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marketplace-manifest", type=Path, required=True)
    parser.add_argument("--plugin-list", type=Path, required=True)
    parser.add_argument("--plugin-registration", type=Path, required=True)
    parser.add_argument("--terra-wire", type=Path, required=True)
    parser.add_argument("--sol-wire", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    failures: list[str] = []
    checks: dict[str, dict] = {}
    manifest = load(args.marketplace_manifest)
    listing = load(args.plugin_list)
    registration = load(args.plugin_registration)
    manifest_names = {str(item.get("name")) for item in manifest.get("plugins", []) if item.get("name")}
    installed_items = [
        item for item in listing.get("installed", [])
        if item.get("marketplaceName") == manifest.get("name")
    ]
    available_items = [
        item for item in listing.get("available", [])
        if item.get("marketplaceName") == manifest.get("name")
    ]
    listed_items = [*installed_items, *available_items]
    listed_names = {str(item.get("name")) for item in listed_items if item.get("name")}

    checks["marketplace-added-with-windows-native-path"] = {
        "ok": registration.get("registrationPathKind") == "windows-native"
        and str(registration.get("marketplaceRoot", ""))[:3].endswith(":\\")
    }
    checks["plugin-list-available-json"] = {"ok": bool(listed_names)}
    checks["github-and-figma-present"] = {"ok": {"github", "figma"}.issubset(listed_names)}
    checks["unavailable-account-or-bundle-plugins-not-fabricated"] = {
        "ok": listed_names == manifest_names
    }

    terra = load(args.terra_wire)
    checks["terra-xhigh-priority"] = {
        "ok": terra.get("model") == "gpt-5.6-terra"
        and terra.get("reasoning", {}).get("effort") == "xhigh"
        and terra.get("service_tier") == "priority"
    }
    sol = load(args.sol_wire)
    checks["sol-ultra-normalized-to-max-all-turns"] = {
        "ok": sol.get("model") == "gpt-5.6-sol"
        and sol.get("reasoning", {}).get("effort") == "max"
        and sol.get("reasoning", {}).get("context") == "all_turns"
        and sol.get("service_tier") == "priority"
    }
    for check_id, result in checks.items():
        if not result["ok"]:
            failures.append(check_id)

    report = {
        "ok": not failures,
        "checkIds": sorted(check_id for check_id, result in checks.items() if result["ok"]),
        "checks": checks,
        "plugins": {
            "manifestCount": len(manifest_names),
            "listedUniqueCount": len(listed_names),
            "installedCount": len(installed_items),
            "availableCount": len(available_items),
            "externalOAuthStillRequired": True,
        },
        "wire": {
            "terra": {"model": terra.get("model"), "reasoning": terra.get("reasoning"), "service_tier": terra.get("service_tier")},
            "sol": {"model": sol.get("model"), "reasoning": sol.get("reasoning"), "service_tier": sol.get("service_tier")},
        },
        "failures": failures,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ok"] else 2)


if __name__ == "__main__":
    main()

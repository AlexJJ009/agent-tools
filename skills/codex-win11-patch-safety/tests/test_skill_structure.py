import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1]
SKILL_MD = SKILL_ROOT / "SKILL.md"
INCIDENT = SKILL_ROOT / "references" / "INCIDENT_MODEL_CATALOG_DEPENDENCY.md"


class SkillStructureTests(unittest.TestCase):
    def test_direct_markdown_references_exist(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        references = re.findall(r"\[[^]]+\]\((references/[^)]+\.md)\)", text)
        self.assertTrue(references, "SKILL.md must directly link its on-demand references")
        missing = [reference for reference in references if not (SKILL_ROOT / reference).is_file()]
        self.assertEqual(missing, [], f"missing direct skill references: {missing}")

    def test_model_catalog_incident_remains_routed_and_fail_closed(self):
        skill_text = SKILL_MD.read_text(encoding="utf-8")
        route = re.search(
            r"## Route The Task(?P<body>.*?)(?:\n## |\Z)", skill_text, flags=re.DOTALL
        )
        self.assertIsNotNone(route)
        self.assertIn("references/INCIDENT_MODEL_CATALOG_DEPENDENCY.md", route.group("body"))

        incident = INCIDENT.read_text(encoding="utf-8")
        required_rules = (
            "config-health",
            "model_catalog_json",
            "Missing or invalid `model_catalog_json` is RED",
            "packageVersion + sourceAsarSha256",
            "patcher.artifacts",
            "target path exactly equals",
            "resulting SHA256",
            "Restore-CodexModelCatalog.ps1",
            "Do not use the full `Patch-CodexApp.ps1` for dependency-only repair",
            "Do not delete, reset, rename, recreate, or isolate `%USERPROFILE%\\.codex`",
            "Candidate activation remains blocked",
            "closed normally",
            "four protected categories",
        )
        for rule in required_rules:
            with self.subTest(rule=rule):
                self.assertIn(rule, incident)

        forbidden_permissions = (
            "candidate activation is allowed",
            "reuse the nearest release",
            "reset the profile to repair",
            "use `--user-data-dir`",
        )
        lowered = incident.lower()
        for permission in forbidden_permissions:
            with self.subTest(permission=permission):
                self.assertNotIn(permission, lowered)

    def test_narrow_restore_companion_cannot_patch_or_activate(self):
        script = (
            SKILL_ROOT
            / "releases"
            / "26.721.4979.0"
            / "Restore-CodexModelCatalog.ps1"
        ).read_text(encoding="utf-8")
        required = (
            "Get-Process ChatGPT,Codex",
            "Get-AppxPackage -Name OpenAI.Codex",
            "sourceAsarSha256",
            "SnapshotManifest",
            "ConfigHealthReport",
            "targetPath",
            "[IO.File]::Copy",
            "activationAllowed = $false",
            "configChanged = $false",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, script)
        for forbidden in (
            "CreateShortcut",
            "RegisterPlugins",
            "Remove-Item",
            "Move-Item",
            "Copy-Item",
            "Start-Process",
            "WScript.Shell",
            "codex.exe",
            "config.toml",
            "New-Item",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, script)
        self.assertEqual(script.count("[IO.File]::Copy"), 1)
        report_writes = [line for line in script.splitlines() if "Set-Content" in line]
        self.assertEqual(len(report_writes), 1)
        self.assertIn("$OutputReport", report_writes[0])


if __name__ == "__main__":
    unittest.main()

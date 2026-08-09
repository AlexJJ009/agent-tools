import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from linear_workflow_runtime import __version__
from linear_workflow_runtime.doctor import fingerprint, run_doctor


class DoctorTests(unittest.TestCase):
    def fixture(self, root: Path):
        target = root / ".codex" / "skills" / "linear-plan"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("ok", encoding="utf-8")
        launcher = root / ".local" / "bin" / "linear-workflow"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.chmod(0o755)
        market = root / ".agents" / "plugins" / "marketplace.json"
        market.parent.mkdir(parents=True)
        market.write_text("{}\n", encoding="utf-8")
        market.chmod(0o600)
        manifest = root / ".local" / "share" / "linear-workflow" / "install-manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({
            "version": __version__, "home": str(root), "launcher": str(launcher),
            "targets": [{"client": "codex", "path": str(target), "sha256": fingerprint(target)}],
        }), encoding="utf-8")
        config = root / ".linear-workflow.yml"
        config.write_text("repository_full_name: AlexJJ009/agent-tools\ngithub_linear_sync_map: github_to_linear\n")
        return target, manifest, config

    @mock.patch("linear_workflow_runtime.doctor.shutil.which", return_value=None)
    def test_local_only_is_offline_and_missing_claude_is_skipped(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, config = self.fixture(root)
            checks = run_doctor(root, config, True)
            self.assertFalse(any(item.level == "FAIL" for item in checks))
            self.assertIn("SKIPPED — client unavailable", [item.detail for item in checks])
            self.assertIn("SKIPPED — local-only/offline", [item.detail for item in checks])

    def test_drift_and_version_mismatch_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target, manifest, config = self.fixture(root)
            data = json.loads(manifest.read_text())
            data["version"] = "0.0.0"
            manifest.write_text(json.dumps(data))
            (target / "SKILL.md").write_text("drift")
            checks = run_doctor(root, config, True)
            self.assertEqual("FAIL", next(item.level for item in checks if item.name == "workflow-version"))
            self.assertEqual("FAIL", next(item.level for item in checks if item.name == "codex-target"))


if __name__ == "__main__":
    unittest.main()

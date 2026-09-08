import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "managed_package_installer.py"
SPEC = importlib.util.spec_from_file_location("managed_package_installer", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ManagedPackageInstallerTests(unittest.TestCase):
    def descriptor(self, name):
        return MODULE.load_descriptor(ROOT / "config" / "managed-packages" / f"{name}.json", ROOT)

    def test_linear_descriptor_uses_version_file(self):
        linear = self.descriptor("linear-workflow")
        self.assertEqual(linear["resolved_version"], (ROOT / "linear_workflow" / "VERSION").read_text().strip())

    def test_managed_status_distinguishes_fresh_and_managed_homes(self):
        descriptor = self.descriptor("linear-workflow")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertFalse(MODULE.managed_install_exists(descriptor, ROOT, home, "unix"))
            source, target = MODULE.target_pairs(descriptor, ROOT, home)[0]
            MODULE.copy_managed(source, target)
            self.assertTrue(MODULE.managed_install_exists(descriptor, ROOT, home, "unix"))

    def test_install_can_skip_marketplace_registration(self):
        descriptor = self.descriptor("linear-workflow")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            MODULE.install(
                descriptor,
                ROOT,
                home,
                "unix",
                "uv",
                skip_runtime=True,
                skip_plugin_registration=True,
            )
            self.assertFalse((home / ".agents" / "plugins" / "marketplace.json").exists())
            self.assertTrue((home / ".codex" / "skills" / "linear-plan" / "SKILL.md").is_file())

    def test_managed_reinstall_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "value").write_text("one", encoding="utf-8")
            self.assertIsNone(MODULE.copy_managed(source, target))
            self.assertIsNone(MODULE.copy_managed(source, target))
            self.assertEqual((target / "value").read_text(), "one")
            self.assertEqual(list(root.glob("target.backup-*")), [])

    def test_unmanaged_target_is_backed_up_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            target = root / "target.txt"
            source.write_text("managed", encoding="utf-8")
            target.write_text("user", encoding="utf-8")
            backup = MODULE.copy_managed(source, target)
            self.assertIsNotNone(backup)
            self.assertEqual(backup.read_text(), "user")
            self.assertEqual(target.read_text(), "managed")

    def test_marketplace_replaces_same_name_and_preserves_other_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / ".agents" / "plugins" / "marketplace.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"plugins": [{"name": "other", "x": 1}, {"name": "linear-workflow"}]}))
            MODULE.update_marketplace(home, self.descriptor("linear-workflow"))
            plugins = json.loads(path.read_text())["plugins"]
            self.assertEqual([p["name"] for p in plugins], ["other", "linear-workflow"])
            self.assertEqual(plugins[0]["x"], 1)

    def test_drift_iterates_descriptor_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            descriptor = self.descriptor("linear-workflow")
            for source, target in MODULE.target_pairs(descriptor, ROOT, home):
                MODULE.copy_managed(source, target)
            drift = MODULE.drift_report(descriptor, ROOT, home, "unix")
            self.assertTrue(any("runtime" in item for item in drift))
            first_target = MODULE.target_pairs(descriptor, ROOT, home)[0][1]
            (first_target / "SKILL.md").write_text("drift", encoding="utf-8")
            drift = MODULE.drift_report(descriptor, ROOT, home, "unix")
            self.assertIn(str(first_target), drift)


if __name__ == "__main__":
    unittest.main()

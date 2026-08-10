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

    def test_descriptors_cover_both_products_without_product_specific_helper(self):
        goal = self.descriptor("goal-plan")
        linear = self.descriptor("linear-workflow")
        self.assertEqual(goal["resolved_version"], "0.3.0")
        self.assertEqual(linear["resolved_version"], (ROOT / "linear_workflow" / "VERSION").read_text().strip())
        self.assertNotEqual(goal["runtime"]["entrypoint"], linear["runtime"]["entrypoint"])

    def test_goal_plan_descriptor_preserves_existing_targets(self):
        descriptor = self.descriptor("goal-plan")
        destinations = {item["destination"] for group in ("codex_targets", "claude_targets") for item in descriptor[group]}
        self.assertEqual(destinations, {
            ".claude/skills/goal-plan",
            ".claude/commands/goal-plan.md",
            ".claude/agents/goal-plan-reviewer.md",
            ".codex/skills/goal-plan",
            "plugins/goal-plan",
            ".codex/plugins/cache/personal/goal-plan/{version}",
            ".codex/prompts/goal-plan.md",
        })
        self.assertEqual(descriptor["launcher"]["name"], "goal-plan-runtime")
        self.assertEqual(
            descriptor["legacy_policy"],
            "preserve-managed-compatibility-new-install-opt-in",
        )

    def test_goal_plan_deprecation_gate_requires_exact_pilot_evidence(self):
        descriptor = self.descriptor("goal-plan")
        self.assertEqual(MODULE.validate_deprecation_evidence(descriptor, ROOT), [])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = json.loads((ROOT / descriptor["deprecation_gate"]["evidence"]).read_text())
            evidence["linear_issue_status"] = "In Review"
            source = root / descriptor["deprecation_gate"]["evidence"]
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps(evidence), encoding="utf-8")
            runtime_module = (
                root / descriptor["runtime"]["source"] / "src" / "goal_plan_runtime"
            )
            runtime_module.mkdir(parents=True, exist_ok=True)
            (runtime_module / "deprecation.py").write_text(
                (ROOT / descriptor["runtime"]["source"] / "src" / "goal_plan_runtime" / "deprecation.py").read_text(),
                encoding="utf-8",
            )
            self.assertTrue(MODULE.validate_deprecation_evidence(descriptor, root))

    def test_managed_status_distinguishes_fresh_and_managed_homes(self):
        descriptor = self.descriptor("goal-plan")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertFalse(MODULE.managed_install_exists(descriptor, ROOT, home, "unix"))
            source, target = MODULE.target_pairs(descriptor, ROOT, home)[0]
            MODULE.copy_managed(source, target)
            self.assertTrue(MODULE.managed_install_exists(descriptor, ROOT, home, "unix"))

    def test_compat_install_can_skip_marketplace_registration(self):
        descriptor = self.descriptor("goal-plan")
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
            self.assertTrue((home / ".codex" / "skills" / "goal-plan" / "SKILL.md").is_file())

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
            path.write_text(json.dumps({"plugins": [{"name": "other", "x": 1}, {"name": "goal-plan"}]}))
            MODULE.update_marketplace(home, self.descriptor("goal-plan"))
            plugins = json.loads(path.read_text())["plugins"]
            self.assertEqual([p["name"] for p in plugins], ["other", "goal-plan"])
            self.assertEqual(plugins[0]["x"], 1)

    def test_drift_iterates_descriptor_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            descriptor = self.descriptor("goal-plan")
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

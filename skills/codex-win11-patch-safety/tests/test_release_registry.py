import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "release_registry.py"
SPEC = importlib.util.spec_from_file_location("release_registry", MODULE_PATH)
registry = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(registry)


class RegistryTests(unittest.TestCase):
    def make_registry(self, root: Path):
        releases = root / "releases"
        release = releases / "1.2.3"
        release.mkdir(parents=True)
        patcher = release / "patch.mjs"
        patcher.write_text("export {};\n")
        recipe = {
            "schemaVersion": 1,
            "releaseId": "r1",
            "status": "candidate",
            "application": {"packageVersion": "1.2.3", "packageFullName": "OpenAI.Codex_1", "sourceAsarSha256": "a" * 64},
            "patcher": {"entrypoint": "patch.mjs", "sha256": registry.sha256(patcher)},
            "verification": {"requiredReports": ["preflight.json"]},
        }
        registry.atomic_json(release / "recipe.json", recipe)
        index = releases / "index.json"
        registry.atomic_json(index, {"schemaVersion": 1, "releases": [{"releaseId": "r1", "packageVersion": "1.2.3", "sourceAsarSha256": "a" * 64, "status": "candidate", "recipe": "1.2.3/recipe.json"}]})
        return index, release, patcher

    def postflight(self, root: Path, ok=True):
        path = root / "postflight.json"
        categories = {name: {"ok": ok} for name in ("userConfiguration", "sshConnections", "projectMemoryAndPlanning", "ccSwitch")}
        registry.atomic_json(path, {"ok": ok, "categories": categories})
        return path

    def verdict(self, root: Path, recipe: Path, patcher: Path, package="OpenAI.Codex_1", source_hash="a" * 64):
        path = root / "verdict.json"
        registry.atomic_json(path, {
            "status": "PASS",
            "source": {"packageFullName": package, "sourceAsarSha256": source_hash},
            "release": {"releaseId": "r1", "recipeSha256": registry.sha256(recipe), "patcherSha256": registry.sha256(patcher), "requiredReports": ["preflight.json"]},
        })
        return path

    def approval(self, root: Path, recipe: Path, verdict: Path, postflight: Path, human=True):
        path = root / "approval.json"
        registry.atomic_json(path, {
            "releaseId": "r1",
            "recipeSha256": registry.sha256(recipe),
            "verdictSha256": registry.sha256(verdict),
            "postflightSha256": registry.sha256(postflight),
            "reviewer": "Alex Mercer",
            "reason": "Reviewed the exact default-profile candidate evidence.",
            "humanApproval": human,
        })
        return path

    def test_exact_select_never_uses_nearby_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, _, _ = self.make_registry(root)
            self.assertIsNotNone(registry.find_release(index, "1.2.3", "a" * 64))
            self.assertIsNone(registry.find_release(index, "1.2.4", "a" * 64))
            self.assertIsNone(registry.find_release(index, "1.2.3", "b" * 64))

    def test_selector_exit_codes_distinguish_candidate_and_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, release, _ = self.make_registry(root)
            detect = root / "detect.json"
            registry.atomic_json(
                detect,
                {
                    "packageVersion": "1.2.3",
                    "packageFullName": "OpenAI.Codex_1",
                    "sourceAsarSha256": "a" * 64,
                },
            )
            args = type("Args", (), {"index": index, "detect": detect})()
            self.assertEqual(registry.command_select(args), 4)

            detection = registry.load_json(detect)
            detection["sourceAsarSha256"] = "b" * 64
            registry.atomic_json(detect, detection)
            self.assertEqual(registry.command_select(args), 3)

    def test_candidate_promotion_requires_matching_pass_and_four_gates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, release, patcher = self.make_registry(root)
            recipe = release / "recipe.json"
            postflight = self.postflight(root)
            verdict = self.verdict(root, recipe, patcher)
            approval = self.approval(root, recipe, verdict, postflight)
            args = type("Args", (), {"index": index, "release_id": "r1", "verdict": verdict, "postflight": postflight, "approval": approval, "ledger": root / "ledger.jsonl"})()
            self.assertEqual(registry.command_promote(args), 0)
            self.assertEqual(registry.load_json(release / "recipe.json")["status"], "verified")
            detect = root / "detect.json"
            registry.atomic_json(
                detect,
                {
                    "packageVersion": "1.2.3",
                    "packageFullName": "OpenAI.Codex_1",
                    "sourceAsarSha256": "a" * 64,
                },
            )
            select_args = type("Args", (), {"index": index, "detect": detect})()
            self.assertEqual(registry.command_select(select_args), 0)

    def test_wrong_version_evidence_and_changed_patcher_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, release, patcher = self.make_registry(root)
            recipe = release / "recipe.json"
            postflight = self.postflight(root)
            wrong_verdict = self.verdict(root, recipe, patcher, package="OpenAI.Codex_2")
            wrong_approval = self.approval(root, recipe, wrong_verdict, postflight)
            base = {"index": index, "release_id": "r1", "postflight": postflight, "ledger": root / "ledger.jsonl"}
            wrong = type("Args", (), {**base, "verdict": wrong_verdict, "approval": wrong_approval})()
            with self.assertRaisesRegex(ValueError, "package identity"):
                registry.command_promote(wrong)
            patcher.write_text("throw new Error();\n")
            changed_verdict = self.verdict(root, recipe, patcher)
            changed_approval = self.approval(root, recipe, changed_verdict, postflight)
            changed = type("Args", (), {**base, "verdict": changed_verdict, "approval": changed_approval})()
            with self.assertRaisesRegex(ValueError, "patcher (changed|hash does not match)"):
                registry.command_promote(changed)

    def test_candidate_cannot_overwrite_existing_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, _, patcher = self.make_registry(root)
            detect = root / "detect.json"
            registry.atomic_json(detect, {"packageVersion": "1.2.3", "packageFullName": "OpenAI.Codex_1", "sourceAsarSha256": "a" * 64})
            args = type("Args", (), {"index": index, "detect": detect, "patcher": patcher, "author": "agent", "reason": "new probe", "ledger": root / "ledger.jsonl"})()
            with self.assertRaisesRegex(ValueError, "already exists"):
                registry.command_record_candidate(args)

    def test_selector_rejects_index_recipe_drift_and_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, _, _ = self.make_registry(root)
            payload = registry.load_json(index)
            payload["releases"][0]["status"] = "verified"
            registry.atomic_json(index, payload)
            with self.assertRaisesRegex(ValueError, "mismatch"):
                registry.validate_release_entry(index, payload["releases"][0])
            payload["releases"][0]["recipe"] = "../../outside.json"
            registry.atomic_json(index, payload)
            with self.assertRaisesRegex(ValueError, "escapes"):
                registry.validate_release_entry(index, payload["releases"][0])

    def test_selector_validates_companion_script_hash_and_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, release, _ = self.make_registry(root)
            companion = release / "helper.ps1"
            companion.write_text("Write-Output ok\n", encoding="utf-8")
            recipe_path = release / "recipe.json"
            recipe = registry.load_json(recipe_path)
            recipe["patcher"]["companionScripts"] = [
                {"entrypoint": "helper.ps1", "sha256": registry.sha256(companion)}
            ]
            registry.atomic_json(recipe_path, recipe)
            entry = registry.load_json(index)["releases"][0]
            registry.validate_release_entry(index, entry)
            companion.write_text("Write-Output changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "companion script hash"):
                registry.validate_release_entry(index, entry)

    def test_selector_validates_release_artifact_hash_and_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, release, _ = self.make_registry(root)
            artifact = release / "catalog.json"
            artifact.write_text('{"models":[]}', encoding="utf-8")
            recipe_path = release / "recipe.json"
            recipe = registry.load_json(recipe_path)
            recipe["patcher"]["artifacts"] = [
                {"path": "catalog.json", "sha256": registry.sha256(artifact)}
            ]
            registry.atomic_json(recipe_path, recipe)
            entry = registry.load_json(index)["releases"][0]
            registry.validate_release_entry(index, entry)
            artifact.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "release artifact hash"):
                registry.validate_release_entry(index, entry)

    def test_required_config_artifact_needs_exact_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, release, _ = self.make_registry(root)
            artifact = release / "catalog.json"
            artifact.write_text('{"models":[]}', encoding="utf-8")
            recipe_path = release / "recipe.json"
            recipe = registry.load_json(recipe_path)
            recipe["patcher"]["artifacts"] = [{
                "path": "catalog.json",
                "sha256": registry.sha256(artifact),
                "configKey": "model_catalog_json",
                "requiredWhileConfigured": True,
            }]
            registry.atomic_json(recipe_path, recipe)
            entry = registry.load_json(index)["releases"][0]
            with self.assertRaisesRegex(ValueError, "configKey/targetPath"):
                registry.validate_release_entry(index, entry)

    def test_promotion_requires_bound_human_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, release, patcher = self.make_registry(root)
            recipe = release / "recipe.json"
            postflight = self.postflight(root)
            verdict = self.verdict(root, recipe, patcher)
            approval = self.approval(root, recipe, verdict, postflight, human=False)
            args = type("Args", (), {"index": index, "release_id": "r1", "verdict": verdict, "postflight": postflight, "approval": approval, "ledger": root / "ledger.jsonl"})()
            with self.assertRaisesRegex(ValueError, "humanApproval"):
                registry.command_promote(args)
            payload = registry.load_json(approval)
            payload["humanApproval"] = True
            payload["verdictSha256"] = "0" * 64
            registry.atomic_json(approval, payload)
            with self.assertRaisesRegex(ValueError, "binding mismatch"):
                registry.command_promote(args)

    def test_promotion_rejects_unbacked_required_check_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, release, patcher = self.make_registry(root)
            recipe = release / "recipe.json"
            payload = registry.load_json(recipe)
            payload["verification"]["requiredCheckIds"] = ["wire-proof"]
            registry.atomic_json(recipe, payload)
            postflight = self.postflight(root)
            verdict = self.verdict(root, recipe, patcher)
            verdict_payload = registry.load_json(verdict)
            verdict_payload["release"]["requiredCheckIds"] = ["wire-proof"]
            verdict_payload["checks"] = []
            registry.atomic_json(verdict, verdict_payload)
            approval = self.approval(root, recipe, verdict, postflight)
            args = type("Args", (), {"index": index, "release_id": "r1", "verdict": verdict, "postflight": postflight, "approval": approval, "ledger": root / "ledger.jsonl"})()
            with self.assertRaisesRegex(ValueError, "lack bound PASS report evidence"):
                registry.command_promote(args)


if __name__ == "__main__":
    unittest.main()

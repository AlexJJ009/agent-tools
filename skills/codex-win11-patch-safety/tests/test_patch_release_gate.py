import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "patch_release_gate.py"
SPEC = importlib.util.spec_from_file_location("patch_release_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(gate)


class ReleaseGateTests(unittest.TestCase):
    def fixtures(self, root: Path):
        detect = root / "detect.json"
        snapshot = root / "manifest.json"
        source_asar = root / "source.asar"
        asar = root / "app.asar"
        exe = root / "ChatGPT.exe"
        check = root / "preflight.json"
        patcher = root / "patch.mjs"
        recipe = root / "recipe.json"
        source_asar.write_bytes(b"source")
        detect.write_text(json.dumps({"packageFullName": "OpenAI.Codex_1", "packageVersion": "1", "sourceAsarSha256": gate.sha256(source_asar)}))
        snapshot.write_text('{"schemaVersion":2}')
        asar.write_bytes(b"asar")
        exe.write_bytes(b"exe")
        check.write_text('{"ok":true}')
        patcher.write_text("export {};\n")
        recipe.write_text(json.dumps({
            "releaseId": "r1",
            "application": {"packageFullName": "OpenAI.Codex_1", "sourceAsarSha256": gate.sha256(source_asar)},
            "patcher": {"entrypoint": "patch.mjs", "sha256": gate.sha256(patcher)},
            "verification": {"requiredReports": ["preflight.json"]},
        }))
        return recipe, detect, snapshot, source_asar, asar, exe, check

    def test_pass_is_bound_to_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recipe, detect, snapshot, source_asar, asar, exe, check = self.fixtures(root)
            verdict = gate.build_verdict(recipe, detect, snapshot, source_asar, asar, exe, [check])
            self.assertEqual(verdict["status"], "PASS")
            path = root / "verdict.json"
            gate.atomic_json(path, verdict)
            self.assertTrue(gate.verify_verdict(path)["ok"])
            (root / "app.asar").write_bytes(b"changed")
            self.assertFalse(gate.verify_verdict(path)["ok"])

    def test_red_and_error_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recipe, detect, snapshot, source_asar, asar, exe, check = self.fixtures(root)
            check.write_text('{"ok":false}')
            self.assertEqual(gate.build_verdict(recipe, detect, snapshot, source_asar, asar, exe, [check])["status"], "RED")
            check.unlink()
            self.assertEqual(gate.build_verdict(recipe, detect, snapshot, source_asar, asar, exe, [check])["status"], "ERROR")

    def test_source_asar_must_match_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recipe, detect, snapshot, source_asar, asar, exe, check = self.fixtures(root)
            source_asar.write_bytes(b"updated source")
            verdict = gate.build_verdict(recipe, detect, snapshot, source_asar, asar, exe, [check])
            self.assertEqual(verdict["status"], "RED")

    def test_required_reports_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recipe, detect, snapshot, source_asar, asar, exe, _ = self.fixtures(root)
            verdict = gate.build_verdict(recipe, detect, snapshot, source_asar, asar, exe, [])
            self.assertEqual(verdict["status"], "ERROR")
            self.assertIn("required check reports", "\n".join(verdict["errorReasons"]))

    def test_required_semantic_check_ids_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recipe, detect, snapshot, source_asar, asar, exe, check = self.fixtures(root)
            payload = json.loads(recipe.read_text())
            payload["verification"]["requiredWireCases"] = ["terra-xhigh-priority"]
            payload["verification"]["requiredPluginChecks"] = ["github-and-figma-present"]
            recipe.write_text(json.dumps(payload))
            verdict = gate.build_verdict(recipe, detect, snapshot, source_asar, asar, exe, [check])
            self.assertEqual(verdict["status"], "ERROR")
            check.write_text(json.dumps({
                "ok": True,
                "checkIds": ["terra-xhigh-priority", "github-and-figma-present"],
            }))
            verdict = gate.build_verdict(recipe, detect, snapshot, source_asar, asar, exe, [check])
            self.assertEqual(verdict["status"], "PASS")
            verdict["checks"] = []
            path = root / "unbacked-verdict.json"
            gate.atomic_json(path, verdict)
            self.assertFalse(gate.verify_verdict(path)["ok"])


if __name__ == "__main__":
    unittest.main()

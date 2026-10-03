"""Packaging/provenance checks for the project-local upstream skill port."""
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents" / "skills"
BUILD = SKILLS / "build-eval"


class ProjectEvalSkillsTests(unittest.TestCase):
    def test_upstream_guides_are_preserved_verbatim(self):
        manifest = json.loads((BUILD / "UPSTREAM.json").read_text())
        for name, source in [("build-eval", "build-eval.md"), ("hillclimb", "eval-hillclimb.md")]:
            text = (SKILLS / name / "SKILL.md").read_text()
            # Everything from the original title onward is the upstream body.
            body = text[text.index("\n# ") + 1:]
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),
                             manifest["files"][f"shared/evals/{source}"])
            self.assertIn(f"name: {name}\n", text)

    def test_unchanged_support_files_match_pinned_source(self):
        manifest = json.loads((BUILD / "UPSTREAM.json").read_text())
        for source, expected in manifest["files"].items():
            if source.endswith(("/build-eval.md", "/eval-hillclimb.md", "/runner-scaffold.mjs")):
                continue
            self.assertEqual(hashlib.sha256((BUILD / source).read_bytes()).hexdigest(), expected, source)

    def test_codex_only_skills_are_not_exposed_to_claude(self):
        for name in ("build-eval", "hillclimb"):
            path = ROOT / ".claude" / "skills" / name
            self.assertFalse(path.exists() or path.is_symlink(), str(path))

    def test_shared_resources_resolve_inside_project(self):
        for name in ("build-eval", "hillclimb"):
            for relative in ("LICENSE.txt", "shared/codex-cli.md", "shared/model-migration.md",
                             "shared/cost-optimization.md", "shared/evals/build-eval.md",
                             "shared/evals/eval-hillclimb.md", "shared/evals/eval-audit.md",
                             "shared/evals/cost-hillclimb.md", "shared/evals/report/SCHEMA.md",
                             "shared/evals/report/runner-scaffold.mjs",
                             "shared/evals/report/codex-exec.mjs",
                             "shared/evals/report/build-report-lite.mjs"):
                p = SKILLS / name / relative
                self.assertTrue(p.is_file(), str(p))
                self.assertTrue(p.resolve().is_relative_to(SKILLS), str(p))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from pathlib import Path

# teaching-gate: fast


ROOT = Path(__file__).resolve().parents[1]


class NoAlphaEvolveAnswerFixtureTests(unittest.TestCase):
    def test_forward_acceptance_topic_is_absent_from_answer_bearing_assets(self) -> None:
        roots = (
            ROOT / "tests" / "fixtures" / "teaching",
            ROOT / "skills" / "teaching-reconstruction" / "assets",
        )
        violations = []
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and "alphaevolve" in path.read_text(encoding="utf-8", errors="ignore").lower():
                    violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

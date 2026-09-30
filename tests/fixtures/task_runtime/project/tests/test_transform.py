import json
from pathlib import Path
import unittest


class TransformTest(unittest.TestCase):
    def test_fixed_input(self):
        root = Path(__file__).resolve().parents[1]
        packet = json.loads((root / 'records/input.json').read_text())
        self.assertEqual([line.upper() for line in packet['lines']], packet['expected'])

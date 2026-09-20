"""Simulated environment adapter, not a Docker/GPU availability check."""
import json
from pathlib import Path

state = json.loads(Path('infra.json').read_text())
print(json.dumps({'environment': state}))

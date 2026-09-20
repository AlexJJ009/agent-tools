import json
from pathlib import Path
from consumer import generate

cfg = json.loads(Path('config.json').read_text())
override = json.loads(Path('override.json').read_text())
cfg.update(override)
print(json.dumps(generate(cfg)))

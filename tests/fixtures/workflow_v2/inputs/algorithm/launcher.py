"""Launch the local consumer; no workflow acceptance decisions live here."""

import argparse
import json
from pathlib import Path
from consumer import generate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--override", default="override.json")
    parser.add_argument("--effect")
    parser.add_argument("--run-id", default="local-demo")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    cfg = json.loads(config_path.read_text())
    cfg.update(json.loads(Path(args.override).read_text()))
    observation = generate(cfg, config_path.parent)
    observation["run_id"] = args.run_id
    if args.effect:
        Path(args.effect).write_text(json.dumps(observation, indent=2) + "\n")
    print(json.dumps(observation))


if __name__ == "__main__":
    main()

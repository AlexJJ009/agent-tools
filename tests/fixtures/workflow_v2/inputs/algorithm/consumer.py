"""Bounded CPU work whose output records values actually consumed."""

import json
import os
from pathlib import Path
import time


def generate(cfg, directory):
    sources = cfg["sources"]
    count = int(cfg["samples_per_source"])
    output_limit = int(cfg["max_response_length"])
    if not 0 <= count <= 32 or not 1 <= output_limit <= 32768:
        raise ValueError("This CPU example accepts at most 32 samples and 32768 tokens")
    responses = {source: [tuple(range(output_limit)) for _ in range(count)] for source in sources}
    if cfg["critic_initialization"] == "reference":
        weights = json.loads((Path(directory) / cfg["critic_weights_path"]).read_text())["weights"]
    elif cfg["critic_initialization"] == "zero":
        weights = [0.0, 0.0]
    else:
        raise ValueError("Unknown critic initialization")
    features = [2.0, 1.0]
    score = 1.0
    if cfg["reward_definition"] == "length_adjusted":
        score -= cfg["length_penalty_per_token"] * 7
    elif cfg["reward_definition"] != "outcome_only":
        raise ValueError("Unknown reward definition")
    lengths = [len(response) for group in responses.values() for response in group]
    return {
        "pid": os.getpid(),
        "observed_at_ns": time.time_ns(),
        "counts": {source: len(group) for source, group in responses.items()},
        "total_samples": sum(len(group) for group in responses.values()),
        "generated_token_lengths": lengths,
        "largest_generated_output": max(lengths, default=0),
        "prompt_plus_output": cfg["max_prompt_length"] + max(lengths, default=0),
        "capacity_ok": cfg["max_prompt_length"] + max(lengths, default=0) <= cfg["context_window"],
        "critic_weights": weights,
        "critic_prediction": sum(x * w for x, w in zip(features, weights)),
        "seven_token_correct_answer_reward": score,
        "effective_configuration": cfg,
        "evidence_kind": "sandbox_cpu_execution"
    }

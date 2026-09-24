"""Exercise real sample effects and deliberately broken copies before evaluation.

This is a fixture preflight, not a workflow candidate acceptance runner.
"""

import argparse
import json
import math
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def matches(actual, expected):
    return all(math.isclose(actual.get(key, float("nan")), value, rel_tol=0, abs_tol=1e-12)
               if isinstance(value, float) else actual.get(key) == value
               for key, value in expected.items())


def execute(directory, script, argv, receipt):
    command = [sys.executable, "-B", script, *map(str, argv)]
    proc = subprocess.Popen(command, cwd=directory, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate(timeout=5)
    result = {"argv": command, "pid": proc.pid, "returncode": proc.returncode,
              "stdout": stdout, "stderr": stderr}
    save(receipt, result)
    if proc.returncode != 0:
        raise AssertionError(result)
    return json.loads(stdout), result


def cpu_valid(observation, receipt, effect, expected):
    return (effect.is_file() and json.loads(effect.read_text()) == observation
            and observation.get("pid") == receipt["pid"] and matches(observation, expected))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    observations = json.loads((ROOT / "oracle/observables.json").read_text())
    checks = []
    cpu = args.output / "algorithm"
    shutil.copytree(ROOT / "inputs/algorithm", cpu)
    effect = cpu / "effect.json"

    def run_cpu(label, expected):
        if effect.exists():
            effect.unlink()
        observed, receipt = execute(cpu, "launcher.py", ["--effect", effect, "--run-id", label], args.output / f"cpu-{label}.json")
        return cpu_valid(observed, receipt, effect, expected), observed

    baseline = observations["algorithm"]["baseline"]
    valid, baseline_output = run_cpu("baseline", baseline)
    assert valid
    checks.append({"case": "cpu-baseline", "result": "observed", "counts": baseline_output["counts"], "output": baseline_output["largest_generated_output"]})
    save(cpu / "override.json", observations["algorithm"]["reference_override"])
    valid, reference = run_cpu("reference", observations["algorithm"]["reference_expected"])
    assert valid
    checks.append({"case": "cpu-reference", "result": "observed", "prediction": reference["critic_prediction"], "reward": reference["seven_token_correct_answer_reward"]})
    save(cpu / "override.json", {"samples_per_source": 2})
    valid, half = run_cpu("half-budget", baseline)
    assert not valid and half["counts"] == {"bare": 2, "privileged": 2}
    checks.append({"case": "half-budget-negative", "result": "rejected", "actual_counts": half["counts"]})
    save(cpu / "override.json", {"max_response_length": 17})
    valid, _ = run_cpu("short-output", {"largest_generated_output": 17})
    assert valid
    consumer_path = cpu / "consumer.py"
    original = consumer_path.read_text()
    consumer_path.write_text(original.replace('output_limit = int(cfg["max_response_length"])', 'output_limit = 5'))
    valid, unused = run_cpu("unused-field", {"largest_generated_output": 17})
    assert not valid and unused["largest_generated_output"] == 5
    checks.append({"case": "unused-output-field-negative", "result": "rejected", "actual_output": 5, "required_output": 17})
    consumer_path.write_text(original)
    valid, _ = run_cpu("repaired-field", {"largest_generated_output": 17})
    assert valid
    effect.unlink()
    assert not cpu_valid(baseline_output, {"pid": baseline_output["pid"]}, effect, baseline)
    checks.append({"case": "expected-echo-without-effect", "result": "rejected"})

    monitor = args.output / "monitor"
    shutil.copytree(ROOT / "inputs/monitor", monitor)
    journal = monitor / "requests.jsonl"
    service = subprocess.Popen([sys.executable, "-B", "server.py", "--journal", str(journal)],
                               cwd=monitor, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        if not select.select([service.stdout], [], [], 5)[0]:
            raise AssertionError("Local fixture did not start")
        startup = json.loads(service.stdout.readline())
        save(args.output / "server-startup.json", startup)
        base_url = startup["base_url"]

        def stats():
            with urllib.request.urlopen(base_url + "/stats", timeout=2) as response:
                return json.loads(response.read())

        def render(label, mode="cache", extra=()):
            page, _ = execute(monitor, "page.py", ["--base-url", base_url, "--state", "cache.json", "--mode", mode, *extra], args.output / f"page-{label}.json")
            save(args.output / f"server-after-{label}.json", stats())
            return page

        first = render("initial")
        assert stats()["count"] == 1 and first["displayed_status"] == "healthy"
        cached = render("cached")
        assert stats()["count"] == 1
        assert cached["last_observation_at_ns"] == first["last_observation_at_ns"]
        assert cached["display_refreshed_at_ns"] > first["display_refreshed_at_ns"]
        failure = render("rate-limited", "probe")
        assert stats()["count"] == 2 and failure["displayed_status"] == "unavailable"
        assert failure["latest_observation"]["http_status"] == 429
        assert failure["latest_observation"]["retry_after"] == "1"
        assert failure["last_success"]["request_count"] == 1
        still_failed = render("cached-failure")
        assert stats()["count"] == 2 and still_failed["displayed_status"] == "unavailable"
        recovered = render("recovered", "probe", ["--effect", "publication.json", "--version", "mvp-2"])
        publication = json.loads((monitor / "publication.json").read_text())
        assert stats()["count"] == 3 and publication["page"] == recovered and publication["version"] == "mvp-2"
        slow = render("timeout", "probe", ["--endpoint", "/slow", "--timeout", "0.02"])
        assert stats()["count"] == 4 and slow["displayed_status"] == "unavailable"
        assert slow["latest_observation"]["http_status"] is None
        checks.append({"case": "monitor-sequence", "result": "observed", "counts": [1, 1, 2, 2, 3, 4], "rate_limited_status": failure["displayed_status"], "timeout_status": slow["displayed_status"]})
        page_path = monitor / "page.py"
        original = page_path.read_text()
        page_path.write_text(original.replace('"healthy" if latest["http_status"] == 200 else "unavailable"', '"healthy" if state.get("last_success") else "unavailable"'))
        false_health = render("false-health", "probe")
        actual = stats()
        assert actual["count"] == 5 and actual["observations"][-1]["http_status"] == 429
        assert false_health["displayed_status"] == "healthy"
        assert false_health["displayed_status"] != "unavailable"
        checks.append({"case": "stale-success-negative", "result": "rejected", "server_status": 429, "page_status": "healthy"})
        page_path.write_text(original)
        repaired = render("repaired-cache")
        assert stats()["count"] == 5 and repaired["displayed_status"] == "unavailable"
    finally:
        service.terminate()
        try:
            _, stderr = service.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            service.kill()
            _, stderr = service.communicate(timeout=3)
        save(args.output / "server-exit.json", {"pid": service.pid, "returncode": service.returncode, "stderr": stderr})

    wanted = {"goal", "progress", "decisions", "evidence", "scope", "next_steps"}
    for name in ("draft_a.md", "draft_b.md", "draft_c.md", "draft_f.md"):
        ids = re.findall(r"^## .*\{#([a-z_]+)\}$", (ROOT / "inputs/writing" / name).read_text(), re.MULTILINE)
        assert len(ids) == 6 and set(ids) == wanted
    duplicate = re.findall(r"^## .*\{#([a-z_]+)\}$", (ROOT / "inputs/writing/draft_g.md").read_text(), re.MULTILINE)
    assert len(duplicate) != len(set(duplicate))
    checks.append({"case": "writing-fixture-shape", "result": "observed", "semantic_candidate_judging": "not_executed"})
    summary = {"kind": "fixture_preflight", "candidate_evaluated": False, "checks": checks,
               "limits": "No candidate workflow gate, natural agent discovery, host Hook, or independent writing Judge was evaluated."}
    save(args.output / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

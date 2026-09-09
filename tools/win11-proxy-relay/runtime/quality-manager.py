#!/usr/bin/env python3
"""
Manage v2rayN inner quality selectors with request reliability, short download
throughput metrics, and latency as a secondary signal.

This script only controls ai-quality, feitu-quality, ai-measure, and
feitu-measure. Outer selectors such as us-ai, ai-auto-fallback, and
server-feitu are intentionally read-only from this manager's point of view.

AI keeps its existing latency-led score. Feitu uses a server-only reliability
gate: zero failed HTTP delay probes, fresh Hugging Face/PyPI/Cloudflare payload
success through the isolated measurement port, then throughput-first ranking.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any
from urllib import error, parse, request

from settings import api_url, default_state_path, load_settings

DEFAULT_SETTINGS = load_settings()
DEFAULT_STATE = default_state_path("quality-manager-state.json", DEFAULT_SETTINGS)
DEFAULT_LOG = default_state_path("quality-manager.log", DEFAULT_SETTINGS)
GENERATE_204 = "https://www.gstatic.com/generate_204"
CHATGPT_TRACE = "https://chatgpt.com/cdn-cgi/trace"
CLOUDFLARE_TRACE = "https://www.cloudflare.com/cdn-cgi/trace"
SPEED_URL = "https://speed.cloudflare.com/__down?bytes=524288"
HF_CONFIG_URL = "https://huggingface.co/gpt2/resolve/main/config.json"
PYPI_SIX_JSON_URL = "https://pypi.org/pypi/six/1.17.0/json"
SPEED_BYTES = 524_288
SPEED_TTL_SECONDS = 30 * 60
FAILURE_MEMORY_SECONDS = 30 * 60
ASSESSMENT_INTERVAL_SECONDS = 5 * 60
CURRENT_CHECK_INTERVAL_SECONDS = 30
CURRENT_FAILED_CHECKS = 3
SWITCH_HOLD_SECONDS = 10 * 60
QUARANTINE_SECONDS = 10 * 60
API_TIMEOUT_SECONDS = 4.0
PRODUCTION_HEALTH_TIMEOUT_SECONDS = 6.0
DELAY_TIMEOUT_MS = 4000
DELAY_PROBES = 3
MAX_WORKERS = 8
SHORTLIST_SIZE = 3
MAX_SPEED_NODES_PER_POOL = 3
SPEED_TIMEOUT_SECONDS = 10.0
CHALLENGER_IMPROVEMENT = 0.20
REQUIRED_CHALLENGER_STREAK = 2


@dataclass(frozen=True)
class PoolConfig:
    name: str
    api_candidates: tuple[str, ...]
    managed_selector: str
    measure_selector: str
    native_fallback: str
    allow_native_fallback: bool
    measurement_port: int
    production_port: int | None
    production_health_url: str
    discovery_selector: str
    require_us_for_speed: bool
    delay_url: str
    reliability_first: bool = False
    site_probe_urls: tuple[tuple[str, str], ...] = ()
    production_selector: str | None = None


def build_pools(settings: dict[str, Any]) -> tuple[PoolConfig, ...]:
    main_apis = tuple(api_url(port) for port in settings["main_controller_ports"])
    feitu_api = api_url(settings["controller_port"])
    return (
    PoolConfig(
        name="ai",
        api_candidates=main_apis,
        managed_selector="ai-quality",
        measure_selector="ai-measure",
        native_fallback="us-ai-auto-READONLY",
        allow_native_fallback=True,
        measurement_port=settings["ai_measure_port"],
        production_port=settings["ai_primary_port"],
        production_health_url=CHATGPT_TRACE,
        discovery_selector="us-ai-auto-READONLY",
        require_us_for_speed=True,
        delay_url=CHATGPT_TRACE,
    ),
    PoolConfig(
        name="feitu",
        api_candidates=(feitu_api,),
        managed_selector="feitu-quality",
        measure_selector="feitu-measure",
        native_fallback="feitu-auto",
        allow_native_fallback=False,
        measurement_port=settings["feitu_measure_port"],
        production_port=settings["local_proxy_port"],
        production_health_url=CLOUDFLARE_TRACE,
        discovery_selector="feitu-auto",
        require_us_for_speed=False,
        delay_url=GENERATE_204,
        reliability_first=True,
        site_probe_urls=(
            ("hf_config", HF_CONFIG_URL),
            ("pypi_six_json", PYPI_SIX_JSON_URL),
            ("cloudflare_trace", CLOUDFLARE_TRACE),
        ),
        production_selector="server-feitu",
    ),
    )


POOLS = build_pools(DEFAULT_SETTINGS)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def now_ts() -> float:
    return time.time()


def setup_logging(path: Path, verbose: bool) -> logging.Logger:
    logger = logging.getLogger("quality-manager")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    stream = logging.StreamHandler()
    stream.setLevel(logging.DEBUG if verbose else logging.WARNING)
    stream.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(stream)
    return logger


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"pools": {}, "updated_at": None, "schema": 1}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pools": {}, "updated_at": None, "schema": 1, "last_error": "state_read_failed"}
    if not isinstance(data, dict):
        return {"pools": {}, "updated_at": None, "schema": 1, "last_error": "state_not_object"}
    data.setdefault("pools", {})
    data.setdefault("schema", 1)
    return data


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def api_request(api_url: str, method: str, path: str, timeout: float, data: dict[str, Any] | None = None) -> dict[str, Any]:
    url = api_url.rstrip("/") + path
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, method=method, headers=headers)
    opener = request.build_opener(request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        payload = resp.read()
    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))


def get_selector(api_url: str, selector: str, timeout: float) -> dict[str, Any]:
    return api_request(api_url, "GET", f"/proxies/{parse.quote(selector, safe='')}", timeout)


def put_selector(api_url: str, selector: str, member: str, timeout: float) -> None:
    api_request(api_url, "PUT", f"/proxies/{parse.quote(selector, safe='')}", timeout, {"name": member})
    after = get_selector(api_url, selector, timeout)
    if selected_member(after) != member:
        raise RuntimeError(f"selector {selector} readback did not match {member!r}")


def selected_member(selector_data: dict[str, Any]) -> str | None:
    for key in ("now", "name"):
        value = selector_data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def selector_members(selector_data: dict[str, Any]) -> list[str]:
    value = selector_data.get("all")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def choose_api(pool: PoolConfig, timeout: float) -> tuple[str | None, str | None]:
    last_error = None
    for api_url in pool.api_candidates:
        try:
            get_selector(api_url, pool.discovery_selector, timeout)
            return api_url, None
        except Exception as exc:
            last_error = repr(exc)
    return None, last_error


def discover_members(api_url: str, pool: PoolConfig, timeout: float) -> tuple[list[str], str | None, dict[str, Any] | None]:
    managed = None
    try:
        managed = get_selector(api_url, pool.managed_selector, timeout)
        members = selector_members(managed)
        leafs = [m for m in members if m != pool.native_fallback]
        if leafs:
            return leafs, None, managed
    except Exception:
        managed = None
    discovery = get_selector(api_url, pool.discovery_selector, timeout)
    members = selector_members(discovery)
    leafs = [m for m in members if m not in {pool.native_fallback, pool.managed_selector}]
    return leafs, None, managed


def delay_once(api_url: str, node: str, url: str, timeout_ms: int, timeout: float) -> int | None:
    path = (
        f"/proxies/{parse.quote(node, safe='')}/delay?"
        f"timeout={timeout_ms}&url={parse.quote(url, safe='')}"
    )
    data = api_request(api_url, "GET", path, timeout)
    delay = data.get("delay")
    if isinstance(delay, (int, float)) and delay >= 0:
        return int(delay)
    return None


def probe_node_delay(api_url: str, node: str, pool: PoolConfig, args: argparse.Namespace) -> dict[str, Any]:
    samples: list[int] = []
    errors: list[str] = []
    for _ in range(args.delay_probes):
        try:
            delay = delay_once(api_url, node, pool.delay_url, args.delay_timeout_ms, args.api_timeout)
            if delay is None:
                errors.append("missing_delay")
            else:
                samples.append(delay)
        except Exception as exc:
            errors.append(type(exc).__name__)
    failures = args.delay_probes - len(samples)
    median = statistics.median(samples) if samples else None
    p95 = max(samples) if samples else None
    jitter = (max(samples) - min(samples)) if len(samples) >= 2 else 0 if samples else None
    return {
        "node": node,
        "ok": failures <= 1 and bool(samples),
        "samples_ms": samples,
        "median_ms": median,
        "p95_ms": p95,
        "jitter_ms": jitter,
        "request_failures": failures,
        "request_failure_ratio": failures / float(args.delay_probes),
        "errors": errors[:3],
        "note": "request_failure_ratio is failed HTTP delay probes, not ICMP packet loss",
    }


def measure_delays(api_url: str, nodes: list[str], pool: PoolConfig, args: argparse.Namespace) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(probe_node_delay, api_url, node, pool, args) for node in nodes]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def decode_trace(body: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in body.decode("utf-8", errors="replace").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


def site_payload_ok(label: str, status: int, body: bytes) -> tuple[bool, str | None]:
    if status != 200 or not body:
        return False, f"bad_response status={status} bytes={len(body)}"
    if label == "cloudflare_trace":
        trace = decode_trace(body)
        if trace.get("ip"):
            return True, None
        return False, "cloudflare_trace_missing_ip"
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, f"{label}_invalid_json"
    if label == "hf_config":
        if isinstance(payload, dict) and payload.get("model_type") == "gpt2":
            return True, None
        return False, "hf_config_unexpected_payload"
    if label == "pypi_six_json":
        info = payload.get("info") if isinstance(payload, dict) else None
        if isinstance(info, dict) and info.get("name") == "six" and info.get("version") == "1.17.0":
            return True, None
        return False, "pypi_six_unexpected_payload"
    return True, None


def proxy_fetch(port: int, url: str, timeout: float, limit: int) -> tuple[int, bytes, float]:
    proxy = f"http://127.0.0.1:{port}"
    opener = request.build_opener(request.ProxyHandler({"http": proxy, "https": proxy}))
    req = request.Request(url, headers={"User-Agent": "quality-manager/1.0"})
    start = time.monotonic()
    with opener.open(req, timeout=timeout) as resp:
        body = resp.read(limit)
        status = getattr(resp, "status", resp.getcode())
    return status, body, time.monotonic() - start


def cached_speed(pool_state: dict[str, Any], node: str, ts: float, ttl: int) -> dict[str, Any] | None:
    speeds = pool_state.setdefault("speed_cache", {})
    item = speeds.get(node)
    if not isinstance(item, dict):
        return None
    measured_at = item.get("measured_at_ts")
    if isinstance(measured_at, (int, float)) and ts - float(measured_at) <= ttl:
        return item
    return None


def prune_quarantine(pool_state: dict[str, Any], ts: float) -> dict[str, Any]:
    raw = pool_state.setdefault("quarantine", {})
    if not isinstance(raw, dict):
        raw = {}
    active: dict[str, Any] = {}
    for node, item in raw.items():
        if not isinstance(node, str) or not isinstance(item, dict):
            continue
        until = item.get("until_ts")
        if isinstance(until, (int, float)) and float(until) > ts:
            active[node] = item
    pool_state["quarantine"] = active
    return active


def prune_recent_failures(pool_state: dict[str, Any], ts: float, args: argparse.Namespace) -> dict[str, Any]:
    window = getattr(args, "failure_memory_seconds", FAILURE_MEMORY_SECONDS)
    raw = pool_state.setdefault("last_failures", {})
    if not isinstance(raw, dict):
        raw = {}
    recent: dict[str, Any] = {}
    for node, item in raw.items():
        if not isinstance(node, str) or not isinstance(item, dict):
            continue
        failed_at_ts = item.get("failed_at_ts")
        if isinstance(failed_at_ts, (int, float)) and ts - float(failed_at_ts) <= window:
            recent[node] = item
    pool_state["last_failures"] = recent
    return recent


def record_node_failure(
    pool_state: dict[str, Any],
    node: str,
    ts: float,
    args: argparse.Namespace,
    reason: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failures = prune_recent_failures(pool_state, ts, args)
    entry = {
        "node": node,
        "reason": reason,
        "failed_at": utc_now(),
        "failed_at_ts": ts,
    }
    if detail is not None:
        entry["detail"] = detail
    failures[node] = entry
    pool_state["last_failures"] = failures
    return entry


def quarantine_node(
    pool_state: dict[str, Any],
    node: str,
    ts: float,
    args: argparse.Namespace,
    reason: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quarantine = prune_quarantine(pool_state, ts)
    record_node_failure(pool_state, node, ts, args, reason, detail)
    entry = {
        "node": node,
        "reason": reason,
        "started_at": utc_now(),
        "started_at_ts": ts,
        "until_ts": ts + args.quarantine_seconds,
    }
    quarantine[node] = entry
    pool_state["quarantine"] = quarantine
    pool_state.setdefault("speed_cache", {}).pop(node, None)
    return entry


def is_quarantined(pool_state: dict[str, Any], node: str, ts: float) -> bool:
    item = prune_quarantine(pool_state, ts).get(node)
    return isinstance(item, dict)


def delay_is_eligible(pool: PoolConfig, delay: dict[str, Any]) -> bool:
    if not delay.get("ok"):
        return False
    failure_ratio = float(delay.get("request_failure_ratio", 1.0))
    if pool.reliability_first:
        return failure_ratio == 0.0
    return failure_ratio <= 1 / 3


def recent_current_https_healthy(pool_state: dict[str, Any], node: str | None, ts: float, args: argparse.Namespace) -> bool:
    if not node:
        return False
    item = pool_state.get("last_current_https")
    if not isinstance(item, dict) or item.get("node") != node or not item.get("ok"):
        return False
    checked_at_ts = item.get("checked_at_ts")
    ttl = getattr(args, "failure_memory_seconds", FAILURE_MEMORY_SECONDS)
    return isinstance(checked_at_ts, (int, float)) and ts - float(checked_at_ts) <= ttl


def recently_verified_speed(pool_state: dict[str, Any], node: str, ts: float, ttl: int) -> dict[str, Any] | None:
    item = cached_speed(pool_state, node, ts, ttl)
    if item is None or not item.get("ok"):
        return None
    status = item.get("status")
    byte_count = item.get("bytes")
    expected_bytes = item.get("expected_bytes")
    if status == 200 and isinstance(byte_count, int) and isinstance(expected_bytes, int) and byte_count == expected_bytes:
        return item
    return None


def recovery_candidates_from_verified_cache(
    pool_state: dict[str, Any],
    members: list[str],
    current: str | None,
    ts: float,
    args: argparse.Namespace,
    pool: PoolConfig | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for node in members:
        if node == current or is_quarantined(pool_state, node, ts):
            continue
        speed = recently_verified_speed(pool_state, node, ts, args.speed_ttl_seconds)
        if speed is None:
            continue
        measured_at_ts = speed.get("measured_at_ts")
        if not isinstance(measured_at_ts, (int, float)):
            continue
        candidates.append({"node": node, "speed": speed, "measured_at_ts": float(measured_at_ts)})
    candidates.sort(key=lambda item: (-item["measured_at_ts"], -float(item["speed"].get("mbps") or 0.0)))
    # Emergency recovery must not stay on a dead node just because the bulk
    # speed budget is exhausted. Recent clean delay candidates still require a
    # fresh HTTPS payload below; they carry no invented throughput measurement.
    recent = pool_state.get('last_assessment', {})
    if ts - float(pool_state.get('last_assessment_ts', 0)) <= getattr(args, 'assessment_interval', ASSESSMENT_INTERVAL_SECONDS) * 2:
        known = {c['node'] for c in candidates}
        for item in sorted(recent.get('delay_metrics', []), key=lambda x: x.get('median_ms') or 999999):
            node = item['node']
            if node in members and node != current and node not in known and item.get('ok') and item.get('request_failure_ratio') == 0 and not is_quarantined(pool_state, node, ts):
                candidates.append({'node': node, 'speed': None, 'measured_at_ts': 0})
                known.add(node)
    return subscription_shortlist(pool, candidates, 3) if pool is not None else candidates[:3]


def freshly_verify_recovery(
    api_url: str,
    pool: PoolConfig,
    pool_state: dict[str, Any],
    candidates: list[dict[str, Any]],
    ts: float,
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    for candidate in candidates:
        node = candidate["node"]
        try:
            proof = verify_recovery_path(api_url, pool, node, args)
        except Exception as exc:
            proof = {"node": node, "ok": False, "error": repr(exc)}
        if proof.get("ok"):
            return {"node": node, "speed": candidate["speed"], "fresh_https": proof}
        quarantine_node(pool_state, node, ts, args, "recovery_fresh_verification_failed")
    return None


def site_payload_health(port: int, probes: tuple[tuple[str, str], ...], timeout: float) -> dict[str, Any]:
    successes: list[dict[str, Any]] = []
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    for label, url in probes:
        try:
            status, body, elapsed = proxy_fetch(port, url, timeout, 128 * 1024)
            ok, failure = site_payload_ok(label, status, body)
            result = {
                "label": label,
                "url": url,
                "ok": ok,
                "status": status,
                "bytes": len(body),
                "elapsed_seconds": elapsed,
            }
            if failure:
                result["error"] = failure
                errors.append(f"{label}:{failure}")
            else:
                successes.append(result)
            results.append(result)
        except Exception as exc:
            message = f"{label}:{type(exc).__name__}"
            errors.append(message)
            results.append({"label": label, "url": url, "ok": False, "error": message})
    failures = len(probes) - len(successes)
    return {
        "ok": failures == 0 and len(successes) == len(probes),
        "proxy_port": port,
        "successes": successes,
        "results": results,
        "request_failures": failures,
        "request_failure_ratio": failures / float(len(probes)) if probes else 1.0,
        "errors": errors[:3],
        "note": "fresh HTTPS payload requests through the proxy; this does not use sing-box URLTest cache",
    }


def verify_recovery_path(api_url: str, pool: PoolConfig, node: str, args: argparse.Namespace) -> dict[str, Any]:
    """Cheap fresh HTTPS validation; never refresh the cached speed timestamp."""
    put_selector(api_url, pool.measure_selector, node, args.api_timeout)
    if pool.reliability_first and pool.site_probe_urls:
        health = site_payload_health(pool.measurement_port, pool.site_probe_urls, args.production_health_timeout)
        health["node"] = node
        health["checked_at"] = utc_now()
        health["type"] = "fresh_site_probe"
        return health
    url = CHATGPT_TRACE if pool.require_us_for_speed else 'https://www.cloudflare.com/cdn-cgi/trace'
    status, body, elapsed = proxy_fetch(pool.measurement_port, url, args.speed_timeout, 8192)
    trace = decode_trace(body)
    ok = status == 200 and bool(trace.get('ip')) and (not pool.require_us_for_speed or trace.get('loc') == 'US')
    return {'node': node, 'ok': ok, 'status': status, 'bytes': len(body), 'seconds': elapsed, 'checked_at': utc_now()}


def measure_speed(api_url: str, pool: PoolConfig, node: str, args: argparse.Namespace) -> dict[str, Any]:
    put_selector(api_url, pool.measure_selector, node, args.api_timeout)
    loc = None
    if pool.require_us_for_speed:
        status, body, _ = proxy_fetch(pool.measurement_port, CHATGPT_TRACE, args.speed_timeout, 8192)
        trace = decode_trace(body)
        loc = trace.get("loc")
        if status != 200 or loc != "US":
            return {
                "node": node,
                "ok": False,
                "loc": loc,
                "error": f"chatgpt_trace_not_us status={status} loc={loc!r}",
                "measured_at": utc_now(),
                "measured_at_ts": now_ts(),
            }
    speed_url = args.speed_url
    expected_bytes = args.speed_bytes
    benchmark_fallback = False
    try:
        status, body, elapsed = proxy_fetch(pool.measurement_port, speed_url, args.speed_timeout, expected_bytes + 1)
    except error.HTTPError as exc:
        if not pool.reliability_first or speed_url != SPEED_URL or exc.code not in (403, 404):
            raise
        # A benchmark service denial is not evidence that package downloads fail.
        speed_url = "https://huggingface.co/gpt2/resolve/main/tokenizer.json"
        expected_bytes = 1355256
        benchmark_fallback = True
        status, body, elapsed = proxy_fetch(pool.measurement_port, speed_url, args.speed_timeout, expected_bytes + 1)
    ok = status == 200 and len(body) == expected_bytes and elapsed > 0
    if ok and benchmark_fallback:
        try:
            model = json.loads(body)["model"]
            ok = len(model["vocab"]) == 50257 and model["vocab"].get("<|endoftext|>") == 50256 and len(model["merges"]) == 50000
        except (ValueError, KeyError, TypeError):
            ok = False
    bytes_per_sec = len(body) / elapsed if ok else 0.0
    return {
        "node": node,
        "ok": ok,
        "loc": loc,
        "status": status,
        "bytes": len(body),
        "expected_bytes": expected_bytes,
        "url": speed_url,
        "benchmark_fallback": benchmark_fallback,
        "elapsed_seconds": elapsed,
        "bytes_per_second": bytes_per_sec,
        "mbps": bytes_per_sec * 8 / 1_000_000,
        "note": "short transfer throughput; not saturated link capacity",
        "measured_at": utc_now(),
        "measured_at_ts": now_ts(),
    }


def production_https_health(pool: PoolConfig, args: argparse.Namespace) -> dict[str, Any]:
    if pool.production_port is None:
        return {"ok": False, "error": "production_port_unset"}
    if pool.reliability_first and pool.site_probe_urls:
        health = site_payload_health(pool.production_port, pool.site_probe_urls, args.production_health_timeout)
        health["type"] = "production_site_probe"
        return health
    successes: list[dict[str, Any]] = []
    errors: list[str] = []
    for _ in range(args.production_health_probes):
        try:
            status, body, elapsed = proxy_fetch(
                pool.production_port,
                pool.production_health_url,
                args.production_health_timeout,
                8192,
            )
            ok = status == 200 and bool(body)
            if ok:
                successes.append({"status": status, "bytes": len(body), "elapsed_seconds": elapsed})
            else:
                errors.append(f"bad_response status={status} bytes={len(body)}")
        except Exception as exc:
            errors.append(type(exc).__name__)
    failures = args.production_health_probes - len(successes)
    return {
        "ok": failures <= 1 and bool(successes),
        "url": pool.production_health_url,
        "proxy_port": pool.production_port,
        "successes": successes,
        "request_failures": failures,
        "request_failure_ratio": failures / float(args.production_health_probes),
        "errors": errors[:3],
        "note": "fresh HTTPS requests through the production proxy port; this does not use sing-box URLTest cache",
    }


def score_candidate(delay: dict[str, Any], speed: dict[str, Any] | None, pool: PoolConfig | None = None) -> dict[str, Any]:
    failure_ratio = float(delay.get("request_failure_ratio", 0.0))
    if pool is not None and pool.reliability_first:
        if failure_ratio != 0.0 or not delay.get("ok"):
            return {"eligible": False, "score": math.inf, "reason": "nonzero_request_failures"}
    elif failure_ratio > (1.0 / 3.0) or not delay.get("ok"):
        return {"eligible": False, "score": math.inf, "reason": "failure_ratio_gt_1_of_3"}
    if not speed or not speed.get("ok"):
        return {"eligible": False, "score": math.inf, "reason": "speed_not_verified"}
    median = float(delay.get("median_ms") or 4000.0)
    jitter = float(delay.get("jitter_ms") or 0.0)
    p95 = float(delay.get("p95_ms") or median)
    mbps = float(speed.get("mbps") or 0.0)
    if pool is not None and pool.reliability_first:
        score = 1000.0 / max(mbps, 0.5) + 0.10 * median + 0.05 * jitter
        return {
            "eligible": True,
            "score": score,
            "median_ms": median,
            "jitter_ms": jitter,
            "request_failure_ratio": failure_ratio,
            "mbps": mbps,
        }
    inverse_throughput_penalty = 300.0 / max(mbps, 0.5)
    score = median + 0.35 * jitter + 0.15 * max(0.0, p95 - median) + 1500.0 * failure_ratio + inverse_throughput_penalty
    return {
        "eligible": True,
        "score": score,
        "median_ms": median,
        "jitter_ms": jitter,
        "request_failure_ratio": failure_ratio,
        "mbps": mbps,
    }


def prune_speed_attempts(pool_state: dict[str, Any], ts: float, window: int) -> list[float]:
    raw = pool_state.setdefault("speed_attempts", [])
    attempts = [float(item) for item in raw if isinstance(item, (int, float)) and ts - float(item) <= window]
    pool_state["speed_attempts"] = attempts
    return attempts


def speed_budget_remaining(pool_state: dict[str, Any], ts: float, args: argparse.Namespace) -> int:
    attempts = prune_speed_attempts(pool_state, ts, args.speed_ttl_seconds)
    return max(0, args.max_speed_nodes_per_pool - len(attempts))


def subscription_priority(pool: PoolConfig, node: str) -> int:
    # Server subscription preference never overrides the HTTPS eligibility gate.
    return int(pool.reliability_first and node.startswith("miaomiao-"))


def subscription_shortlist(pool: PoolConfig, healthy: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    if not pool.reliability_first or size < 2:
        return healthy[:size]
    primary = next((x for x in healthy if x["node"].startswith("feitu-")), None)
    backup = next((x for x in healthy if x["node"].startswith("miaomiao-")), None)
    heads = [x for x in (primary, backup) if x is not None]
    tags = {x["node"] for x in heads}
    return (heads + [x for x in healthy if x["node"] not in tags])[:size]


def decide_selection(
    *,
    pool: PoolConfig,
    pool_state: dict[str, Any],
    current: str | None,
    ranked: list[dict[str, Any]],
    ts: float,
    args: argparse.Namespace,
    current_recent_https_healthy_missing_rank: bool = False,
) -> dict[str, Any]:
    if not ranked:
        pool_state["challenger"] = None
        pool_state["challenger_streak"] = 0
        if pool.allow_native_fallback:
            return {"target": pool.native_fallback, "action": "fallback_no_healthy_candidates"}
        return {"target": current, "action": "no_verified_alternative_hold_current"}
    ranked = [item for item in ranked if not is_quarantined(pool_state, item["node"], ts)]
    if not ranked:
        pool_state["challenger"] = None
        pool_state["challenger_streak"] = 0
        if pool.allow_native_fallback:
            return {"target": pool.native_fallback, "action": "fallback_only_quarantined_candidates"}
        return {"target": current, "action": "only_quarantined_alternatives_hold_current"}
    ranked = sorted(ranked, key=lambda item: (subscription_priority(pool, item["node"]), item["score"]))
    best = ranked[0]
    if current is None or current == pool.native_fallback:
        pool_state["challenger"] = None
        pool_state["challenger_streak"] = 0
        return {"target": best["node"], "action": "select_best_from_fallback"}
    if current == best["node"]:
        pool_state["challenger"] = None
        pool_state["challenger_streak"] = 0
        return {"target": current, "action": "keep_current_best"}
    current_entry = next((item for item in ranked if item["node"] == current), None)
    if current_entry is None:
        if current_recent_https_healthy_missing_rank:
            pool_state["challenger"] = None
            pool_state["challenger_streak"] = 0
            return {"target": current, "action": "hold_current_recent_https_healthy_missing_speed"}
        pool_state["challenger"] = None
        pool_state["challenger_streak"] = 0
        return {"target": best["node"], "action": "switch_current_unhealthy"}
    last_switch_ts = float(pool_state.get("last_switch_ts") or 0.0)
    if ts - last_switch_ts < args.switch_hold_seconds:
        return {"target": current, "action": "hold_current", "challenger": best["node"]}
    better_by = 1.0 - (best["score"] / current_entry["score"])
    preferred_subscription = subscription_priority(pool, best["node"]) < subscription_priority(pool, current)
    if better_by < args.challenger_improvement and not preferred_subscription:
        pool_state["challenger"] = None
        pool_state["challenger_streak"] = 0
        return {"target": current, "action": "keep_current_within_hysteresis", "better_by": better_by}
    if pool_state.get("challenger") == best["node"]:
        pool_state["challenger_streak"] = int(pool_state.get("challenger_streak") or 0) + 1
    else:
        pool_state["challenger"] = best["node"]
        pool_state["challenger_streak"] = 1
    if int(pool_state["challenger_streak"]) >= args.required_challenger_streak:
        return {"target": best["node"], "action": "switch_challenger_better", "better_by": better_by}
    return {"target": current, "action": "wait_challenger_confirmation", "challenger": best["node"], "better_by": better_by}


def assess_pool(pool: PoolConfig, state: dict[str, Any], args: argparse.Namespace, logger: logging.Logger) -> dict[str, Any]:
    ts = now_ts()
    pool_state = state.setdefault("pools", {}).setdefault(pool.name, {})
    event: dict[str, Any] = {"pool": pool.name, "started_at": utc_now(), "actions": []}
    api_url, api_error = choose_api(pool, args.api_timeout)
    if api_url is None:
        event.update({"api_available": False, "api_error": api_error, "action": "api_unavailable"})
        return event
    event["api_url"] = api_url
    try:
        members, _, managed_data = discover_members(api_url, pool, args.api_timeout)
        current = selected_member(managed_data or {}) if managed_data else None
        event["selector_before"] = current
        event["candidate_count"] = len(members)
        if not members:
            if pool.allow_native_fallback:
                put_selector(api_url, pool.managed_selector, pool.native_fallback, args.api_timeout)
                event["action"] = "fallback_no_members"
                event["selector_after"] = pool.native_fallback
            else:
                event["action"] = "no_members_hold_current"
                event["selector_after"] = current
            return event

        active_quarantine = prune_quarantine(pool_state, ts)
        recent_failures = prune_recent_failures(pool_state, ts, args)
        candidate_members = [node for node in members if node not in active_quarantine]
        event["quarantine"] = active_quarantine
        event["recent_failures"] = recent_failures
        event["quarantined_candidates"] = [node for node in members if node in active_quarantine]
        if not candidate_members:
            if pool.allow_native_fallback:
                put_selector(api_url, pool.managed_selector, pool.native_fallback, args.api_timeout)
                event["action"] = "fallback_all_candidates_quarantined"
                event["selector_after"] = pool.native_fallback
            else:
                event["action"] = "all_candidates_quarantined_hold_current"
                event["selector_after"] = current
            return event

        delays = measure_delays(api_url, candidate_members, pool, args)
        by_node = {item["node"]: item for item in delays}
        healthy = sorted(
            [item for item in delays if delay_is_eligible(pool, item)],
            key=lambda item: (float(item.get("median_ms") or 999999), float(item.get("jitter_ms") or 999999)),
        )
        shortlist = subscription_shortlist(pool, healthy, args.shortlist_size)
        if current and current != pool.native_fallback:
            current_delay = by_node.get(current)
            if current_delay and current_delay.get("ok") and all(item["node"] != current for item in shortlist):
                # Spend one of the fixed probe slots on the incumbent, so a
                # missing speed refresh is not mistaken for a failed incumbent.
                shortlist = [current_delay] + shortlist[:max(0, args.shortlist_size - 1)]
        event["delay_metrics"] = delays
        event["shortlist"] = [item["node"] for item in shortlist]

        site_metrics: dict[str, Any] = {}
        if pool.reliability_first and pool.site_probe_urls:
            for item in shortlist:
                node = item["node"]
                try:
                    put_selector(api_url, pool.measure_selector, node, args.api_timeout)
                    site_health = site_payload_health(pool.measurement_port, pool.site_probe_urls, args.production_health_timeout)
                except Exception as exc:
                    site_health = {
                        "node": node,
                        "ok": False,
                        "error": repr(exc),
                        "request_failure_ratio": 1.0,
                        "errors": [type(exc).__name__],
                    }
                site_health["node"] = node
                site_health["checked_at"] = utc_now()
                site_health["checked_at_ts"] = now_ts()
                site_metrics[node] = site_health
                if site_health.get("ok"):
                    pool_state.setdefault("last_failures", {}).pop(node, None)
                else:
                    quarantine_node(pool_state, node, ts, args, "fresh_site_probe_failed", site_health)
            event["site_metrics"] = site_metrics

        speed_cache = pool_state.setdefault("speed_cache", {})
        speed_metrics: dict[str, Any] = {}
        attempts = prune_speed_attempts(pool_state, ts, args.speed_ttl_seconds)
        measured = 0
        for item in shortlist:
            node = item["node"]
            if pool.reliability_first and not site_metrics.get(node, {}).get("ok"):
                speed_metrics[node] = {"node": node, "ok": False, "skipped": "fresh_site_probe_failed"}
                continue
            cached = cached_speed(pool_state, node, ts, args.speed_ttl_seconds)
            if cached is not None:
                speed_metrics[node] = cached | {"cache_hit": True}
                continue
            if len(attempts) >= args.max_speed_nodes_per_pool:
                speed_metrics[node] = {"node": node, "ok": False, "skipped": "speed_probe_budget_exhausted"}
                continue
            attempts.append(ts)
            pool_state["speed_attempts"] = attempts
            try:
                speed = measure_speed(api_url, pool, node, args)
            except Exception as exc:
                speed = {"node": node, "ok": False, "error": repr(exc), "measured_at": utc_now(), "measured_at_ts": now_ts()}
            speed_cache[node] = speed
            speed_metrics[node] = speed
            measured += 1
        event["speed_metrics"] = speed_metrics
        event["speed_budget"] = {
            "nodes_measured_this_assessment": measured,
            "attempts_used_in_rolling_window": len(attempts),
            "remaining_attempts_in_rolling_window": speed_budget_remaining(pool_state, ts, args),
            "max_nodes_per_pool_per_30min": args.max_speed_nodes_per_pool,
            "bytes_per_probe": args.speed_bytes,
            "cache_ttl_seconds": args.speed_ttl_seconds,
            "rough_daily_budget_note": "up to 3 attempts per pool per 30min; default 512KiB, server benchmark 403/404 fallback may add 1.3MiB HF payload per attempt",
        }

        ranked = []
        shortlisted_nodes = {item["node"] for item in shortlist}
        for item in healthy:
            node = item["node"]
            if node not in shortlisted_nodes:
                continue
            if pool.reliability_first and not site_metrics.get(node, {}).get("ok"):
                continue
            scored = score_candidate(item, speed_metrics.get(node), pool)
            if scored["eligible"]:
                ranked.append({"node": node, **scored, "delay": by_node[node], "speed": speed_metrics.get(node)})
        ranked.sort(key=lambda item: (subscription_priority(pool, item["node"]), item["score"]))
        event["ranked"] = ranked
        current_delay = by_node.get(current) if current else None
        current_ranked = any(item["node"] == current for item in ranked)
        current_recent_healthy_missing_rank = (
            bool(current)
            and current != pool.native_fallback
            and not current_ranked
            and current_delay is not None
            and delay_is_eligible(pool, current_delay)
            and recent_current_https_healthy(pool_state, current, ts, args)
        )
        if current_recent_healthy_missing_rank:
            event["current_recent_https_hold"] = {
                "node": current,
                "reason": "current had recent production HTTPS success but no verified speed in this assessment",
            }
        decision = decide_selection(
            pool=pool,
            pool_state=pool_state,
            current=current,
            ranked=ranked,
            ts=ts,
            args=args,
            current_recent_https_healthy_missing_rank=current_recent_healthy_missing_rank,
        )
        target = decision["target"]
        event["decision"] = decision
        event["action"] = decision["action"]
        if pool.production_port is not None and target != current and target != pool.native_fallback:
            try:
                event['fresh_switch_check'] = verify_recovery_path(api_url, pool, target, args)
            except Exception as exc:
                event['fresh_switch_check'] = {'ok': False, 'error': repr(exc)}
            if not event['fresh_switch_check']['ok']:
                quarantine_node(pool_state, target, ts, args, 'pre_switch_https_failed')
                target = current
                event['action'] = 'fresh_https_failed_hold_current'
        if target != current:
            put_selector(api_url, pool.managed_selector, target, args.api_timeout)
            pool_state["last_switch_ts"] = ts
            event["selector_after"] = target
        else:
            event["selector_after"] = current
        pool_state["current"] = event["selector_after"]
        pool_state["last_assessment_ts"] = ts
        pool_state["last_assessment"] = event
        return event
    except Exception as exc:
        logger.exception("pool %s assessment failed", pool.name)
        event.update({"action": "assessment_error", "error": repr(exc)})
        return event


def check_current_pool(pool: PoolConfig, state: dict[str, Any], args: argparse.Namespace, logger: logging.Logger) -> dict[str, Any]:
    pool_state = state.setdefault("pools", {}).setdefault(pool.name, {})
    event: dict[str, Any] = {"pool": pool.name, "started_at": utc_now(), "type": "current_check"}
    api_url, api_error = choose_api(pool, args.api_timeout)
    if api_url is None:
        event.update({"action": "api_unavailable", "api_error": api_error})
        return event
    try:
        selector = get_selector(api_url, pool.managed_selector, args.api_timeout)
        current = selected_member(selector)
        if pool_state.get('current') != current:
            pool_state['last_switch_ts'] = now_ts()
        pool_state['current'] = current
        members = selector_members(selector)
        event["selector_before"] = current
        event["quarantine"] = prune_quarantine(pool_state, now_ts())
        if pool.production_selector:
            try:
                production_selector = get_selector(api_url, pool.production_selector, args.api_timeout)
                production_selector_now = selected_member(production_selector)
                event["production_selector"] = pool.production_selector
                event["production_selector_now"] = production_selector_now
                if production_selector_now and production_selector_now != pool.managed_selector:
                    event["action"] = "skip_manual_outer_selection"
                    event["note"] = (
                        f"production port {pool.production_port} follows {pool.production_selector}={production_selector_now}; "
                        f"not attributing production health to {pool.managed_selector}"
                    )
                    return event
            except Exception as exc:
                event["production_selector_warning"] = repr(exc)
        native_now = None
        if current == pool.native_fallback:
            native_data = get_selector(api_url, pool.native_fallback, args.api_timeout)
            native_now = selected_member(native_data)
            event["native_fallback_now"] = native_now
        effective_current = native_now or current
        if not effective_current:
            pool_state["current_failed_checks"] = 0
            event["action"] = "skip_unknown"
            return event

        production_health = None
        if pool.production_port is not None:
            production_health = production_https_health(pool, args)
            event["production_health"] = production_health

        if current == pool.native_fallback and production_health is None:
            delay = probe_node_delay(api_url, effective_current, pool, args)
        elif current == pool.native_fallback:
            if production_health is not None and production_health["ok"]:
                checked_ts = now_ts()
                pool_state["last_current_https"] = {
                    "node": effective_current,
                    "ok": True,
                    "checked_at": utc_now(),
                    "checked_at_ts": checked_ts,
                    "health": production_health,
                }
                pool_state["current_failed_checks"] = 0
                event["action"] = "fallback_current_healthy"
                return event
            if production_health is None:
                production_health = {"request_failure_ratio": 1.0, "errors": ["production_port_unset"]}
            delay = {
                "node": effective_current,
                "ok": False,
                "request_failure_ratio": production_health["request_failure_ratio"],
                "errors": production_health["errors"],
                "note": "native fallback effective leaf failed production HTTPS health",
            }
        elif production_health is not None:
            if production_health["ok"]:
                checked_ts = now_ts()
                pool_state["last_current_https"] = {
                    "node": effective_current,
                    "ok": True,
                    "checked_at": utc_now(),
                    "checked_at_ts": checked_ts,
                    "health": production_health,
                }
                pool_state["current_failed_checks"] = 0
                event["action"] = "current_production_healthy"
                return event
            delay = {
                "node": effective_current,
                "ok": False,
                "request_failure_ratio": production_health["request_failure_ratio"],
                "errors": production_health["errors"],
                "note": "explicit selected leaf failed production HTTPS health",
            }
        else:
            delay = probe_node_delay(api_url, effective_current, pool, args)
        event["delay_metric"] = delay
        if delay["ok"]:
            pool_state["current_failed_checks"] = 0
            event["action"] = "current_healthy"
            return event
        record_node_failure(pool_state, effective_current, now_ts(), args, "current_check_failed", delay)
        failed_checks = int(pool_state.get("current_failed_checks") or 0) + 1
        pool_state["current_failed_checks"] = failed_checks
        if failed_checks >= args.current_failed_checks:
            ts = now_ts()
            event["quarantined"] = quarantine_node(pool_state, effective_current, ts, args, "current_check_failed")
            pool_state["current_failed_checks"] = 0
            recovery_candidates = recovery_candidates_from_verified_cache(pool_state, members, effective_current, ts, args, pool=pool)
            event["recovery_candidates"] = [item["node"] for item in recovery_candidates]
            recovery = freshly_verify_recovery(api_url, pool, pool_state, recovery_candidates, ts, args)
            if recovery is not None:
                put_selector(api_url, pool.managed_selector, recovery["node"], args.api_timeout)
                pool_state["current"] = recovery["node"]
                pool_state["last_switch_ts"] = ts
                event["action"] = "switch_to_freshly_verified_after_current_failure"
                event["selector_after"] = recovery["node"]
                event["recovery_speed"] = recovery["speed"]
                event["recovery_https"] = recovery["fresh_https"]
            elif pool.allow_native_fallback:
                put_selector(api_url, pool.managed_selector, pool.native_fallback, args.api_timeout)
                pool_state["current"] = pool.native_fallback
                pool_state["last_switch_ts"] = ts
                event["action"] = "release_to_native_urltest"
                event["selector_after"] = pool.native_fallback
            else:
                pool_state["current"] = current
                event["action"] = "no_verified_alternative_hold_current"
                event["selector_after"] = current
        else:
            event["action"] = "current_check_failed"
            event["failed_checks"] = failed_checks
        return event
    except Exception as exc:
        logger.exception("pool %s current check failed", pool.name)
        event.update({"action": "current_check_error", "error": repr(exc)})
        return event


def finish(state_path: Path, state: dict[str, Any], event: dict[str, Any], logger: logging.Logger) -> dict[str, Any]:
    state["updated_at"] = utc_now()
    state["last_event"] = event
    atomic_write_json(state_path, state)
    status_path = state_path.with_name(f"{state_path.stem}-status.json")
    atomic_write_json(status_path, state)
    logger.info("event=%s", json.dumps(event, sort_keys=True))
    return state


def run_assessment(args: argparse.Namespace, logger: logging.Logger) -> dict[str, Any]:
    state = load_state(Path(args.state))
    event = {"type": "assessment", "started_at": utc_now(), "pools": []}
    for pool in POOLS:
        event["pools"].append(assess_pool(pool, state, args, logger))
    return finish(Path(args.state), state, event, logger)


def run_current_check(args: argparse.Namespace, logger: logging.Logger) -> dict[str, Any]:
    state = load_state(Path(args.state))
    event = {"type": "current_check", "started_at": utc_now(), "pools": []}
    for pool in POOLS:
        event["pools"].append(check_current_pool(pool, state, args, logger))
    return finish(Path(args.state), state, event, logger)


def run_loop(args: argparse.Namespace, logger: logging.Logger) -> int:
    saved = load_state(Path(args.state))
    previous = [saved.get('pools', {}).get(p.name, {}).get('last_assessment_ts', 0.0) for p in POOLS]
    next_assessment = min(previous) + args.assessment_interval if all(previous) else 0.0
    while True:
        try:
            ts = now_ts()
            if ts >= next_assessment:
                run_assessment(args, logger)
                next_assessment = ts + args.assessment_interval
            else:
                run_current_check(args, logger)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            logger.exception("unexpected loop failure: %r", exc)
        time.sleep(args.current_check_interval)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage ai-quality and feitu-quality with multi-metric proxy scoring.")
    parser.add_argument("--settings", default=None, help="Path to portable runtime settings.json.")
    parser.add_argument("--state", default=None, help="Atomic JSON state path.")
    parser.add_argument("--log", default=None, help="Rotating log path.")
    parser.add_argument("--once", action="store_true", help="Run one bounded full assessment and exit.")
    parser.add_argument("--check-current-once", action="store_true", help="Run one 30s-style current-node health check and exit.")
    parser.add_argument("--assessment-interval", type=float, default=ASSESSMENT_INTERVAL_SECONDS)
    parser.add_argument("--current-check-interval", type=float, default=CURRENT_CHECK_INTERVAL_SECONDS)
    parser.add_argument("--api-timeout", type=float, default=API_TIMEOUT_SECONDS)
    parser.add_argument("--production-health-timeout", type=float, default=PRODUCTION_HEALTH_TIMEOUT_SECONDS)
    parser.add_argument("--production-health-probes", type=int, default=CURRENT_FAILED_CHECKS)
    parser.add_argument("--delay-timeout-ms", type=int, default=DELAY_TIMEOUT_MS)
    parser.add_argument("--delay-probes", type=int, default=DELAY_PROBES)
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--shortlist-size", type=int, default=SHORTLIST_SIZE)
    parser.add_argument("--max-speed-nodes-per-pool", type=int, default=MAX_SPEED_NODES_PER_POOL)
    parser.add_argument("--speed-timeout", type=float, default=SPEED_TIMEOUT_SECONDS)
    parser.add_argument("--speed-url", default=SPEED_URL)
    parser.add_argument("--speed-bytes", type=int, default=SPEED_BYTES)
    parser.add_argument("--speed-ttl-seconds", type=int, default=SPEED_TTL_SECONDS)
    parser.add_argument("--failure-memory-seconds", type=int, default=FAILURE_MEMORY_SECONDS)
    parser.add_argument("--switch-hold-seconds", type=float, default=SWITCH_HOLD_SECONDS)
    parser.add_argument("--quarantine-seconds", type=float, default=QUARANTINE_SECONDS)
    parser.add_argument("--challenger-improvement", type=float, default=CHALLENGER_IMPROVEMENT)
    parser.add_argument("--required-challenger-streak", type=int, default=REQUIRED_CHALLENGER_STREAK)
    parser.add_argument("--current-failed-checks", type=int, default=CURRENT_FAILED_CHECKS)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    active_settings = load_settings(args.settings)
    global POOLS
    POOLS = build_pools(active_settings)
    if args.state is None:
        args.state = str(default_state_path("quality-manager-state.json", active_settings))
    if args.log is None:
        args.log = str(default_state_path("quality-manager.log", active_settings))
    if args.delay_probes < 1:
        parser.error("--delay-probes must be >= 1")
    if args.max_workers < 1:
        parser.error("--max-workers must be >= 1")
    if args.shortlist_size < 1:
        parser.error("--shortlist-size must be >= 1")
    if args.max_speed_nodes_per_pool < 0:
        parser.error("--max-speed-nodes-per-pool must be >= 0")
    if args.required_challenger_streak < 1:
        parser.error("--required-challenger-streak must be >= 1")
    if args.current_failed_checks < 1:
        parser.error("--current-failed-checks must be >= 1")
    if args.production_health_probes < 1:
        parser.error("--production-health-probes must be >= 1")
    if args.failure_memory_seconds <= 0:
        parser.error("--failure-memory-seconds must be > 0")
    if args.quarantine_seconds <= 0:
        parser.error("--quarantine-seconds must be > 0")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    logger = setup_logging(Path(args.log), args.verbose)
    if args.once:
        state = run_assessment(args, logger)
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0
    if args.check_current_once:
        state = run_current_check(args, logger)
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0
    return run_loop(args, logger)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""
Watch ChatGPT reachability through the US AI auto group and steer the inner
ai-auto-fallback selector between ai-quality and proxy.

The outer user-facing us-ai selector is intentionally left alone. This script
only updates ai-auto-fallback, so manual choices on us-ai remain manual.
"""

from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from settings import api_url, default_state_path, load_settings

TRACE_URL = "https://chatgpt.com/cdn-cgi/trace"
DEFAULT_API_URL = "auto"
DEFAULT_SELECTOR = "ai-auto-fallback"
PRIMARY_MEMBER = "ai-quality"
FALLBACK_MEMBER = "proxy"
DEFAULT_SETTINGS = load_settings()
DEFAULT_PRIMARY_PORT = DEFAULT_SETTINGS["ai_primary_port"]
DEFAULT_FALLBACK_PORT = DEFAULT_SETTINGS["ai_fallback_port"]
DEFAULT_TIMEOUT = 8.0
DEFAULT_INTERVAL = 30.0
DEFAULT_THRESHOLD = 3
DEFAULT_STATE = default_state_path("ai-fallback-state.json", DEFAULT_SETTINGS)
DEFAULT_LOG = default_state_path("ai-fallback.log", DEFAULT_SETTINGS)


class ProbeResult:
    def __init__(
        self,
        *,
        ok: bool,
        url: str,
        proxy_port: int,
        status: int | None = None,
        loc: str | None = None,
        error_text: str | None = None,
    ) -> None:
        self.ok = ok
        self.url = url
        self.proxy_port = proxy_port
        self.status = status
        self.loc = loc
        self.error_text = error_text

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "url": self.url,
            "proxy_port": self.proxy_port,
            "status": self.status,
            "loc": self.loc,
            "error": self.error_text,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "primary_failures": 0,
            "primary_successes": 0,
            "mode": "unknown",
            "last_action": None,
            "last_error": None,
            "updated_at": None,
        }
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {
            "primary_failures": 0,
            "primary_successes": 0,
            "mode": "unknown",
            "last_action": None,
            "last_error": "state_read_failed",
            "updated_at": None,
        }
    if not isinstance(data, dict):
        return {
            "primary_failures": 0,
            "primary_successes": 0,
            "mode": "unknown",
            "last_action": None,
            "last_error": "state_not_object",
            "updated_at": None,
        }
    data.setdefault("primary_failures", 0)
    data.setdefault("primary_successes", 0)
    data.setdefault("mode", "unknown")
    data.setdefault("last_action", None)
    data.setdefault("last_error", None)
    data.setdefault("updated_at", None)
    return data


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def setup_logging(path: Path, verbose: bool) -> logging.Logger:
    logger = logging.getLogger("ai-fallback")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=512_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    stream.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger.addHandler(stream)
    return logger


def decode_trace(body: bytes) -> dict[str, str]:
    text = body.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


def probe_trace(port: int, timeout: float, require_us: bool, url: str) -> ProbeResult:
    proxy_url = f"http://127.0.0.1:{port}"
    opener = request.build_opener(
        request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    )
    req = request.Request(
        url,
        headers={
            "User-Agent": "ai-fallback-watchdog/1.0",
            "Accept": "text/plain,*/*;q=0.8",
        },
    )
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = getattr(resp, "status", resp.getcode())
            trace = decode_trace(resp.read(8192))
    except Exception as exc:
        return ProbeResult(ok=False, url=url, proxy_port=port, error_text=repr(exc))

    loc = trace.get("loc")
    ok = status == 200 and (not require_us or loc == "US")
    error_text = None if ok else f"unexpected_trace status={status} loc={loc!r}"
    return ProbeResult(ok=ok, url=url, proxy_port=port, status=status, loc=loc, error_text=error_text)


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
    if get_selector(api_url, selector, timeout).get('now') != member:
        raise RuntimeError('Selector readback did not match requested member')


def selected_member(selector_data: dict[str, Any]) -> str | None:
    for key in ("now", "name"):
        value = selector_data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def reset_streaks(state: dict[str, Any], reason: str) -> None:
    state["primary_failures"] = 0
    state["primary_successes"] = 0
    state["last_error"] = reason


def run_once(args: argparse.Namespace, logger: logging.Logger) -> dict[str, Any]:
    state_path = Path(args.state)
    state = load_state(state_path)
    started_at = utc_now()
    event: dict[str, Any] = {
        "started_at": started_at,
        "api_url": args.api_url,
        "selector": args.selector,
        "primary_member": args.primary_member,
        "fallback_member": args.fallback_member,
        "action": "none",
    }

    try:
        api_url = args.api_url
        if api_url == 'auto':
            for candidate in args.api_candidates:
                try:
                    selector_before = get_selector(candidate, args.selector, 2)
                    api_url = candidate
                    break
                except (error.URLError, TimeoutError, OSError, json.JSONDecodeError):
                    continue
            if api_url == 'auto':
                raise OSError('No active v2rayN AI controller found')
        else:
            selector_before = get_selector(api_url, args.selector, args.timeout)
        event['api_url'] = api_url
        current = selected_member(selector_before)
        if current not in (args.primary_member, args.fallback_member):
            reset_streaks(state, f"selector_unexpected_member:{current}")
            event["selector_before"] = current
            event["api_available"] = True
            event["action"] = "reset_unexpected_selector_member"
            state["mode"] = current or "unknown"
            return finish(state_path, state, event, logger)
    except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        reset_streaks(state, "api_unavailable")
        event["api_available"] = False
        event["api_error"] = repr(exc)
        event["action"] = "reset_api_unavailable"
        return finish(state_path, state, event, logger)

    primary = probe_trace(args.primary_port, args.timeout, True, args.url)
    event["api_available"] = True
    event["selector_before"] = current
    event["primary_probe"] = primary.to_json()

    if primary.ok:
        state["primary_failures"] = 0
        state["primary_successes"] = int(state.get("primary_successes", 0)) + 1
        state["last_error"] = None
        if current == args.fallback_member and state["primary_successes"] >= args.threshold:
            try:
                put_selector(api_url, args.selector, args.primary_member, args.timeout)
                state["mode"] = args.primary_member
                state["last_action"] = "restore_primary"
                event["action"] = "restore_primary"
                event["selector_after"] = args.primary_member
            except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                reset_streaks(state, "api_unavailable")
                event["action"] = "reset_api_unavailable"
                event["api_error"] = repr(exc)
        else:
            state["mode"] = current or "unknown"
            event["selector_after"] = current
    else:
        state["primary_failures"] = int(state.get("primary_failures", 0)) + 1
        state["primary_successes"] = 0
        state["last_error"] = primary.error_text
        if current == args.primary_member and state["primary_failures"] >= args.threshold:
            fallback = probe_trace(args.fallback_port, args.timeout, False, args.url)
            event["fallback_probe"] = fallback.to_json()
            if fallback.ok:
                try:
                    put_selector(api_url, args.selector, args.fallback_member, args.timeout)
                    state["mode"] = args.fallback_member
                    state["last_action"] = "switch_fallback"
                    event["action"] = "switch_fallback"
                    event["selector_after"] = args.fallback_member
                except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                    reset_streaks(state, "api_unavailable")
                    event["action"] = "reset_api_unavailable"
                    event["api_error"] = repr(exc)
            else:
                state["mode"] = current or "unknown"
                event["action"] = "fallback_probe_failed"
                event["selector_after"] = current
        else:
            state["mode"] = current or "unknown"
            event["selector_after"] = current

    return finish(state_path, state, event, logger)


def finish(state_path: Path, state: dict[str, Any], event: dict[str, Any], logger: logging.Logger) -> dict[str, Any]:
    state["updated_at"] = utc_now()
    state["last_event"] = event
    atomic_write_json(state_path, state)
    status_path = state_path.with_name(f"{state_path.stem}-status.json")
    atomic_write_json(status_path, state)
    logger.info(
        "action=%s mode=%s failures=%s successes=%s",
        event.get("action"),
        state.get("mode"),
        state.get("primary_failures"),
        state.get("primary_successes"),
    )
    return state


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail over ai-auto-fallback when the US AI auto group is unhealthy.")
    parser.add_argument("--settings", default=None, help="Path to portable runtime settings.json.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Clash-compatible API base URL.")
    parser.add_argument("--selector", default=DEFAULT_SELECTOR, help="Inner selector to manage.")
    parser.add_argument("--primary-member", default=PRIMARY_MEMBER, help="Healthy/default selector member.")
    parser.add_argument("--fallback-member", default=FALLBACK_MEMBER, help="Fallback selector member.")
    parser.add_argument("--primary-port", type=int, default=None, help="Mixed port forced through primary.")
    parser.add_argument("--fallback-port", type=int, default=None, help="Mixed port forced through fallback.")
    parser.add_argument("--url", default=TRACE_URL, help="Trace endpoint to probe.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Probe/API timeout in seconds.")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="Loop interval in seconds.")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help="Consecutive primary probe threshold.")
    parser.add_argument("--state", default=None, help="State JSON path.")
    parser.add_argument("--log", default=None, help="Rotating log path.")
    parser.add_argument("--once", action="store_true", help="Run exactly one probe cycle.")
    parser.add_argument("--verbose", action="store_true", help="Also write debug output to stderr.")
    args = parser.parse_args(argv)
    active_settings = load_settings(args.settings)
    args.api_candidates = [api_url(port) for port in active_settings["main_controller_ports"]]
    if args.primary_port is None:
        args.primary_port = active_settings["ai_primary_port"]
    if args.fallback_port is None:
        args.fallback_port = active_settings["ai_fallback_port"]
    if args.state is None:
        args.state = str(default_state_path("ai-fallback-state.json", active_settings))
    if args.log is None:
        args.log = str(default_state_path("ai-fallback.log", active_settings))
    if args.threshold < 1:
        parser.error("--threshold must be >= 1")
    if args.interval <= 0:
        parser.error("--interval must be > 0")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    logger = setup_logging(Path(args.log), args.verbose)
    while True:
        try:
            state = run_once(args, logger)
            if args.once:
                print(json.dumps(state, indent=2, sort_keys=True))
                return 0
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            logger.exception("unexpected failure: %r", exc)
            if args.once:
                return 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

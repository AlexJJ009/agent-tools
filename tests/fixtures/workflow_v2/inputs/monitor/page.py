"""Render cached or freshly observed local health, preserving failed probes."""

import argparse
import json
from pathlib import Path
import socket
import time
import urllib.error
import urllib.parse
import urllib.request


def refresh(base_url, state_path, mode, timeout=1.0, endpoint="/probe"):
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username:
        raise ValueError("Only the loopback sample is supported")
    path = Path(state_path)
    state = json.loads(path.read_text()) if path.exists() else {}
    if mode == "probe" or not state:
        try:
            try:
                response = urllib.request.urlopen(base_url + endpoint, timeout=timeout)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                latest = json.loads(response.read())
                latest["retry_after"] = response.headers.get("Retry-After")
        except (TimeoutError, socket.timeout, urllib.error.URLError) as error:
            latest = {"http_status": None, "error": type(error).__name__, "observed_at_ns": time.time_ns()}
        state["latest_observation"] = latest
        if latest["http_status"] == 200:
            state["last_success"] = latest
        path.write_text(json.dumps(state, indent=2) + "\n")
    latest = state["latest_observation"]
    return {"display_refreshed_at_ns": time.time_ns(), "last_observation_at_ns": latest["observed_at_ns"],
            "displayed_status": "healthy" if latest["http_status"] == 200 else "unavailable",
            "latest_observation": latest, "last_success": state.get("last_success"),
            "refresh_mode": mode}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--mode", choices=("cache", "probe"), default="cache")
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--endpoint", default="/probe")
    parser.add_argument("--effect")
    parser.add_argument("--version", default="mvp-1")
    args = parser.parse_args()
    page = refresh(args.base_url, args.state, args.mode, args.timeout, args.endpoint)
    if args.effect:
        Path(args.effect).write_text(json.dumps({"version": args.version, "kind": "sandbox_publication", "page": page}, indent=2) + "\n")
    print(json.dumps(page))


if __name__ == "__main__":
    main()

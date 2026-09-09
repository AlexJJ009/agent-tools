"""Portable runtime settings shared by the proxy relay scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
INSTALL_ROOT = RUNTIME_DIR.parent
DEFAULT_SETTINGS_PATH = INSTALL_ROOT / "settings.json"
DEFAULT_STATE_DIR = INSTALL_ROOT / "state"


DEFAULTS: dict[str, Any] = {
    "v2rayn_dir": str(INSTALL_ROOT / "v2rayN-windows-64"),
    "core_exe": "",
    "ssh_host": "phai-lgx-dev",
    "local_proxy_port": 17897,
    "remote_proxy_port": 17890,
    "controller_port": 17903,
    "state_dir": str(DEFAULT_STATE_DIR),
    "owner_home": "",
    "ssh_config": "",
    "ssh_identity_file": "",
    "ssh_known_hosts": "",
    "main_controller_ports": [7903, 7902],
    "main_ai_subscriptions": [],
    "ai_primary_port": 17911,
    "ai_fallback_port": 17912,
    "ai_measure_port": 17913,
    "feitu_measure_port": 17914,
}


def _resolve_path(value: str, base: Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return str(path)


def load_settings(path: str | Path | None = None) -> dict[str, Any]:
    settings_path = Path(path) if path else DEFAULT_SETTINGS_PATH
    data: dict[str, Any] = {}
    if settings_path.exists():
        raw = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError(f"settings must be a JSON object: {settings_path}")
        data = raw

    merged = DEFAULTS | data
    base = settings_path.resolve().parent if settings_path.exists() else INSTALL_ROOT
    merged["v2rayn_dir"] = _resolve_path(str(merged["v2rayn_dir"]), base)
    merged["state_dir"] = _resolve_path(str(merged["state_dir"]), base)
    if merged.get("core_exe"):
        merged["core_exe"] = _resolve_path(str(merged["core_exe"]), base)
    else:
        merged["core_exe"] = str(Path(merged["v2rayn_dir"]) / "bin" / "sing_box" / "sing-box.exe")
    for key in ("owner_home", "ssh_config", "ssh_identity_file", "ssh_known_hosts"):
        if merged.get(key):
            merged[key] = _resolve_path(str(merged[key]), base)

    merged["main_controller_ports"] = [int(port) for port in merged.get("main_controller_ports", [])]
    main_ai_subscriptions = merged.get("main_ai_subscriptions", [])
    if isinstance(main_ai_subscriptions, str):
        main_ai_subscriptions = [main_ai_subscriptions]
    merged["main_ai_subscriptions"] = [
        str(name).strip() for name in main_ai_subscriptions if str(name).strip()
    ]
    for key in (
        "local_proxy_port",
        "remote_proxy_port",
        "controller_port",
        "ai_primary_port",
        "ai_fallback_port",
        "ai_measure_port",
        "feitu_measure_port",
    ):
        merged[key] = int(merged[key])
    return merged


def api_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def default_state_path(name: str, settings: dict[str, Any] | None = None) -> Path:
    active = settings or load_settings()
    return Path(active["state_dir"]) / name

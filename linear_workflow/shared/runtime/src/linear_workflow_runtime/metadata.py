"""Read-only version metadata for Linear Workflow clients."""

from __future__ import annotations

from typing import Any

from . import __version__
from .contracts import SCHEMA_NAMES, load_schema


def _canonical_schema_version() -> int:
    versions: dict[str, int] = {}
    for name in SCHEMA_NAMES:
        schema = load_schema(name)
        version_field = schema.get("properties", {}).get("schema_version")
        if version_field is None:
            continue
        enum = version_field.get("enum")
        if not isinstance(enum, list) or len(enum) != 1 or type(enum[0]) is not int:
            raise RuntimeError(
                f"canonical schema {name!r} must declare exactly one integer schema_version"
            )
        versions[name] = enum[0]

    if not versions:
        raise RuntimeError("canonical schemas do not declare a schema_version")
    unique = set(versions.values())
    if len(unique) != 1:
        detail = ", ".join(f"{name}={version}" for name, version in versions.items())
        raise RuntimeError(f"canonical schema versions disagree: {detail}")
    return next(iter(unique))


def version_metadata() -> dict[str, Any]:
    """Return canonical installed workflow/schema versions without external I/O."""

    return {
        "workflow_version": __version__,
        "schema_version": _canonical_schema_version(),
    }

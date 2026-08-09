from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


SCHEMA_NAMES = ("prd", "issue", "batch", "evidence", "review-verdict")


@dataclass(frozen=True)
class Violation:
    object_id: str
    field: str
    rule_id: str
    message: str
    remediation: str

    def render(self) -> str:
        return (
            f"{self.object_id}: field={self.field} rule={self.rule_id}: "
            f"{self.message}; fix: {self.remediation}"
        )


def load_schema(name: str) -> dict[str, Any]:
    if name not in SCHEMA_NAMES:
        raise ValueError(f"unknown schema: {name}")
    source_schema = Path(__file__).resolve().parents[3] / "schemas" / f"{name}.schema.json"
    if source_schema.is_file():
        return json.loads(source_schema.read_text(encoding="utf-8"))
    packaged = resources.files("linear_workflow_runtime").joinpath(
        "schemas", f"{name}.schema.json"
    )
    return json.loads(packaged.read_text(encoding="utf-8"))


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "boolean": type(value) is bool,
        "null": value is None,
    }[expected]


def _validate_node(value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    expected = schema.get("type")
    if expected:
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(_matches_type(value, item) for item in allowed):
            errors.append(f"{path}: expected {' or '.join(allowed)}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: expected one of {schema['enum']!r}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            errors.append(f"{path}: does not match {schema['pattern']!r}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: expected at least {schema['minItems']} items")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, sort_keys=True) for item in value]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{path}: items must be unique")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_node(item, item_schema, f"{path}[{index}]", errors)
    if isinstance(value, dict):
        for field in schema.get("required", []):
            if field not in value:
                errors.append(f"{path}.{field}: required field missing")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for field in value:
                if field not in properties:
                    errors.append(f"{path}.{field}: unexpected field")
        for field, child in value.items():
            if field in properties:
                _validate_node(child, properties[field], f"{path}.{field}", errors)


def validate_schema(value: dict[str, Any], name: str) -> list[str]:
    errors: list[str] = []
    _validate_node(value, load_schema(name), "$", errors)
    return errors

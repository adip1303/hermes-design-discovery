"""Validate Track A data files with a stdlib-only JSON Schema subset."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(reference: str, current: Path) -> Any:
    filename, _, pointer = reference.partition("#")
    document_path = (current.parent / filename).resolve() if filename else current.resolve()
    value = load(document_path)
    for segment in filter(None, pointer.split("/")):
        value = value[segment.replace("~1", "/").replace("~0", "~")]
    return value, document_path


def validate(value: Any, schema: dict[str, Any], path: Path, schema_path: Path, errors: list[str]) -> None:
    if "$ref" in schema:
        target, target_path = resolve(schema["$ref"], schema_path)
        validate(value, target, path, target_path, errors)
        return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")
    expected = schema.get("type")
    if expected:
        choices = expected if isinstance(expected, list) else [expected]
        type_map = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}
        if not any(isinstance(value, type_map[item]) and not (item == "integer" and isinstance(value, bool)) for item in choices):
            errors.append(f"{path}: expected {expected}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} is not allowed")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0): errors.append(f"{path}: too short")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value): errors.append(f"{path}: does not match {schema['pattern']}")
    if isinstance(value, int) and value < schema.get("minimum", value): errors.append(f"{path}: below minimum")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0): errors.append(f"{path}: too few items")
        if len(value) > schema.get("maxItems", len(value)): errors.append(f"{path}: too many items")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value): errors.append(f"{path}: duplicate items")
        if "items" in schema:
            for index, item in enumerate(value): validate(item, schema["items"], path / str(index), schema_path, errors)
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value: errors.append(f"{path}: missing {name}")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties: errors.append(f"{path}: unexpected {name}")
        for name, child in properties.items():
            if name in value: validate(value[name], child, path / name, schema_path, errors)


def main() -> int:
    checks = [(DATA / "fonts.json", DATA / "schema" / "font.json", True), (DATA / "conflicts.json", DATA / "schema" / "conflict-rule.json", True)]
    checks.extend((path, DATA / "schema" / "archetype.json", False) for path in sorted((DATA / "archetypes").glob("*.json")))
    errors: list[str] = []
    for data_path, schema_path, is_collection in checks:
        if not data_path.exists():
            continue
        value = load(data_path)
        values = value if is_collection and isinstance(value, list) else [value]
        for index, item in enumerate(values): validate(item, load(schema_path), data_path / str(index), schema_path, errors)
    if errors:
        print("Data validation failed:\n" + "\n".join(errors))
        return 1
    print("Data validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

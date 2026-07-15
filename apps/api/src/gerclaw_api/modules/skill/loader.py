"""Strict SKILL.md parser and bounded parameter-schema validator."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, cast

import frontmatter
from pydantic import ValidationError

from gerclaw_api.modules.skill.models import SkillDefinition
from gerclaw_api.modules.skill.security import enforce_skill_safety, normalize_skill_text
from gerclaw_api.security import JsonValue

ALLOWED_PARAMETER_TYPES = frozenset({"string", "number", "integer", "boolean", "array"})
ALLOWED_SCHEMA_KEYS = frozenset(
    {
        "type",
        "description",
        "default",
        "enum",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "items",
    }
)
DEFAULT_ALLOWED_TOOLS = frozenset({"search_knowledge", "web_search", "search_memory"})
DEFAULT_MINIMUM_NUMBER = -1_000_000_000_000
DEFAULT_MAXIMUM_NUMBER = 1_000_000_000_000


class SkillFormatError(ValueError):
    """Raised for malformed or unsupported Skill documents."""


def _json_mapping(value: object, *, field: str) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise SkillFormatError(f"{field} must be an object with string keys")
    return cast(dict[str, JsonValue], dict(value))


def _validate_parameter(name: str, schema: JsonValue) -> dict[str, JsonValue]:
    value = _json_mapping(schema, field=f"parameters.{name}")
    unknown = set(value) - ALLOWED_SCHEMA_KEYS
    if unknown:
        raise SkillFormatError(f"parameters.{name} contains unsupported schema keywords")
    parameter_type = value.get("type")
    if parameter_type not in ALLOWED_PARAMETER_TYPES:
        raise SkillFormatError(f"parameters.{name}.type is unsupported")
    description = value.get("description")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 300:
        raise SkillFormatError(f"parameters.{name}.description is required")
    enum = value.get("enum")
    if enum is not None and (not isinstance(enum, list) or not 1 <= len(enum) <= 50):
        raise SkillFormatError(f"parameters.{name}.enum must contain 1 to 50 values")
    if parameter_type == "string":
        maximum = value.get("maxLength", 1_000)
        minimum = value.get("minLength", 0)
        if (
            isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or not 1 <= maximum <= 4_000
            or isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or not 0 <= minimum <= maximum
        ):
            raise SkillFormatError(f"parameters.{name} has invalid string bounds")
        value["minLength"] = minimum
        value["maxLength"] = maximum
    if parameter_type in {"number", "integer"}:
        minimum_number = value.get("minimum", DEFAULT_MINIMUM_NUMBER)
        maximum_number = value.get("maximum", DEFAULT_MAXIMUM_NUMBER)
        for bound_name, bound in (("minimum", minimum_number), ("maximum", maximum_number)):
            if bound is None:
                raise SkillFormatError(f"parameters.{name}.{bound_name} is invalid")
            valid_type = (
                isinstance(bound, int)
                if parameter_type == "integer"
                else isinstance(bound, (int, float))
            )
            finite = not isinstance(bound, float) or math.isfinite(bound)
            if (
                isinstance(bound, bool)
                or not valid_type
                or not finite
                or cast(int | float, bound) < DEFAULT_MINIMUM_NUMBER
                or cast(int | float, bound) > DEFAULT_MAXIMUM_NUMBER
            ):
                raise SkillFormatError(f"parameters.{name}.{bound_name} is invalid")
        typed_minimum = cast(int | float, minimum_number)
        typed_maximum = cast(int | float, maximum_number)
        if typed_minimum > typed_maximum:
            raise SkillFormatError(f"parameters.{name} has invalid numeric bounds")
        value["minimum"] = typed_minimum
        value["maximum"] = typed_maximum
    if parameter_type == "array":
        items = value.get("items")
        if (
            not isinstance(items, Mapping)
            or set(items) != {"type"}
            or items.get("type") not in ALLOWED_PARAMETER_TYPES - {"array"}
        ):
            raise SkillFormatError(f"parameters.{name}.items requires a scalar type")
        item_schema: dict[str, JsonValue] = {"type": cast(str, items["type"])}
        if items["type"] == "string":
            item_schema.update({"minLength": 0, "maxLength": 1_000})
        elif items["type"] in {"number", "integer"}:
            item_schema.update(
                {"minimum": DEFAULT_MINIMUM_NUMBER, "maximum": DEFAULT_MAXIMUM_NUMBER}
            )
        value["items"] = item_schema
        minimum_items = value.get("minItems", 0)
        maximum_items = value.get("maxItems", 20)
        if (
            isinstance(minimum_items, bool)
            or not isinstance(minimum_items, int)
            or minimum_items < 0
            or isinstance(maximum_items, bool)
            or not isinstance(maximum_items, int)
            or not 1 <= maximum_items <= 100
            or minimum_items > maximum_items
        ):
            raise SkillFormatError(f"parameters.{name} has invalid array bounds")
        value["minItems"] = minimum_items
        value["maxItems"] = maximum_items
    if enum is not None:
        if parameter_type == "array":
            raise SkillFormatError(f"parameters.{name}.enum is unsupported for arrays")
        for enum_value in enum:
            _validate_scalar_value(name, parameter_type, enum_value, value, label="enum value")
    if "default" in value:
        if parameter_type == "array":
            _validate_array_value(name, value["default"], value, label="default")
        else:
            _validate_scalar_value(name, parameter_type, value["default"], value, label="default")
        if enum is not None and value["default"] not in enum:
            raise SkillFormatError(f"parameters.{name}.default is outside its enum")
    return value


def _validate_scalar_value(
    name: str,
    parameter_type: JsonValue,
    value: JsonValue,
    schema: Mapping[str, JsonValue],
    *,
    label: str = "value",
) -> None:
    if parameter_type == "string":
        if not isinstance(value, str):
            raise SkillFormatError(f"parameter {name} {label} must be text")
        minimum = cast(int, schema.get("minLength", 0))
        maximum = cast(int, schema.get("maxLength", 1_000))
        if not minimum <= len(value) <= maximum:
            raise SkillFormatError(f"parameter {name} {label} violates its length bounds")
    elif parameter_type == "boolean":
        if not isinstance(value, bool):
            raise SkillFormatError(f"parameter {name} {label} must be boolean")
    elif parameter_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SkillFormatError(f"parameter {name} {label} must be an integer")
    elif parameter_type == "number":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise SkillFormatError(f"parameter {name} {label} must be a finite number")
    else:  # pragma: no cover - all callers are guarded by schema validation
        raise SkillFormatError(f"parameter {name} has an unsupported scalar type")
    if parameter_type in {"number", "integer"}:
        minimum_number = schema.get("minimum")
        maximum_number = schema.get("maximum")
        if minimum_number is not None and cast(int | float, value) < cast(
            int | float, minimum_number
        ):
            raise SkillFormatError(f"parameter {name} {label} is below its minimum")
        if maximum_number is not None and cast(int | float, value) > cast(
            int | float, maximum_number
        ):
            raise SkillFormatError(f"parameter {name} {label} exceeds its maximum")


def _validate_array_value(
    name: str,
    value: JsonValue,
    schema: Mapping[str, JsonValue],
    *,
    label: str = "value",
) -> None:
    minimum = cast(int, schema.get("minItems", 0))
    maximum = cast(int, schema.get("maxItems", 20))
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise SkillFormatError(f"parameter {name} {label} must be a bounded array")
    items = cast(Mapping[str, JsonValue], schema["items"])
    for item in value:
        _validate_scalar_value(name, items["type"], item, items, label="array item")


def validate_parameter_schema(value: object) -> dict[str, JsonValue]:
    """Validate the supported object-property JSON Schema subset."""

    parameters = _json_mapping(value, field="parameters")
    if len(parameters) > 20:
        raise SkillFormatError("a Skill can declare at most 20 parameters")
    properties: dict[str, JsonValue] = {}
    required: list[JsonValue] = []
    for name, schema in parameters.items():
        if not name.isidentifier() or len(name) > 64:
            raise SkillFormatError("parameter names must be identifiers up to 64 characters")
        validated = _validate_parameter(name, schema)
        optional = "default" in validated
        properties[name] = validated
        if not optional:
            required.append(name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def parse_skill_markdown(
    source_markdown: str,
    *,
    source: str,
    origin: str,
    enabled: bool = True,
    revision: int = 1,
    allowed_tools: frozenset[str] = DEFAULT_ALLOWED_TOOLS,
) -> SkillDefinition:
    """Parse and policy-check one complete Markdown + YAML frontmatter document."""

    normalized = normalize_skill_text(source_markdown).strip()
    if not normalized or len(normalized) > 10_000:
        raise SkillFormatError("SKILL.md must contain 1 to 10,000 characters")
    try:
        document = frontmatter.loads(normalized)
    except Exception as error:
        raise SkillFormatError("SKILL.md frontmatter could not be parsed") from error
    metadata: dict[str, Any] = dict(document.metadata)
    required_metadata = {"id", "name", "description", "version"}
    if not required_metadata.issubset(metadata):
        raise SkillFormatError("SKILL.md frontmatter is missing required metadata")
    body = document.content.strip()
    if len(body) < 20:
        raise SkillFormatError("SKILL.md instructions must contain at least 20 characters")
    raw_tools = metadata.get("tools", [])
    if not isinstance(raw_tools, list) or any(not isinstance(item, str) for item in raw_tools):
        raise SkillFormatError("SKILL.md tools must be a string list")
    tools = list(dict.fromkeys(raw_tools))
    if len(tools) != len(raw_tools):
        raise SkillFormatError("SKILL.md tools must be unique")
    denied_tools = set(tools) - allowed_tools
    if denied_tools:
        raise SkillFormatError("SKILL.md requests tools outside the server allowlist")
    parameter_schema = validate_parameter_schema(metadata.get("parameters", {}))
    try:
        definition = SkillDefinition(
            skill_id=metadata["id"],
            name=metadata["name"],
            description=metadata["description"],
            version=metadata["version"],
            parameter_schema=parameter_schema,
            tool_names=tools,
            category=metadata.get("category", "general"),
            source=source,
            origin=origin,
            enabled=enabled,
            revision=revision,
            source_markdown=normalized,
        )
    except ValidationError as error:
        raise SkillFormatError("SKILL.md metadata failed schema validation") from error
    enforce_skill_safety(definition)
    return definition


def validate_skill_params(
    definition: SkillDefinition, params: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    """Validate runtime parameters against the bounded schema subset."""

    schema = definition.parameter_schema
    properties = cast(dict[str, dict[str, JsonValue]], schema.get("properties", {}))
    required = cast(list[str], schema.get("required", []))
    missing = set(required) - set(params)
    unknown = set(params) - set(properties)
    if missing:
        raise SkillFormatError("required Skill parameters are missing")
    if unknown:
        raise SkillFormatError("unknown Skill parameters were supplied")
    validated: dict[str, JsonValue] = {}
    for name, value in params.items():
        parameter = properties[name]
        parameter_type = parameter["type"]
        if parameter_type == "array":
            _validate_array_value(name, value, parameter)
        else:
            _validate_scalar_value(name, parameter_type, value, parameter)
        enum = parameter.get("enum")
        if isinstance(enum, list) and value not in enum:
            raise SkillFormatError(f"parameter {name} is outside its enum")
        validated[name] = value
    return validated

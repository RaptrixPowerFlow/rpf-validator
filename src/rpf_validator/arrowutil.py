"""Arrow type helpers for the vendored contract snapshot."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

_PRIMITIVE = {
    "null": pa.null(),
    "bool": pa.bool_(),
    "int8": pa.int8(),
    "int16": pa.int16(),
    "int32": pa.int32(),
    "int64": pa.int64(),
    "uint8": pa.uint8(),
    "uint16": pa.uint16(),
    "uint32": pa.uint32(),
    "uint64": pa.uint64(),
    "float16": pa.float16(),
    "float32": pa.float32(),
    "float64": pa.float64(),
    "utf8": pa.utf8(),
    "large_utf8": pa.large_utf8(),
}

_UTC_ALIASES = {"utc", "z", "+00:00", "+0000", "00:00"}


def to_pa_type(spec: dict[str, Any]) -> pa.DataType:
    kind = spec["kind"]
    if kind in _PRIMITIVE:
        return _PRIMITIVE[kind]
    if kind == "timestamp":
        return pa.timestamp(spec["unit"], tz=spec.get("tz"))
    if kind == "dictionary":
        return pa.dictionary(to_pa_type(spec["key"]), to_pa_type(spec["value"]))
    if kind == "list":
        return pa.list_(
            pa.field(
                spec["item_name"],
                to_pa_type(spec["item"]),
                nullable=spec["item_nullable"],
            )
        )
    if kind == "large_list":
        return pa.large_list(
            pa.field(
                spec["item_name"],
                to_pa_type(spec["item"]),
                nullable=spec["item_nullable"],
            )
        )
    if kind == "map":
        entries = spec["entries"]["fields"]
        key_type = next(to_pa_type(field["type"]) for field in entries if field["name"] == "key")
        value_type = next(
            to_pa_type(field["type"]) for field in entries if field["name"] == "value"
        )
        return pa.map_(key_type, value_type, keys_sorted=bool(spec.get("keys_sorted", False)))
    if kind == "struct":
        return pa.struct(
            [
                pa.field(field["name"], to_pa_type(field["type"]), nullable=field["nullable"])
                for field in spec["fields"]
            ]
        )
    raise TypeError(f"unsupported contract type kind {kind!r}")


def _tz_compatible(expected: str | None, actual: str | None) -> bool:
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    left = expected.strip()
    right = actual.strip()
    if left == right:
        return True
    return left.lower() in _UTC_ALIASES and right.lower() in _UTC_ALIASES


def types_compatible(expected: dict[str, Any], actual: pa.DataType) -> bool:
    """Match the reader rule in ``rpf_types_compatible``.

    List and large-list are interchangeable. Nested field nullability is not
    compared. Map entry names and list item names are not compared.
    """

    kind = expected["kind"]
    if kind in ("list", "large_list"):
        if not (pa.types.is_list(actual) or pa.types.is_large_list(actual)):
            return False
        return types_compatible(expected["item"], actual.value_type)
    if kind == "map":
        if not pa.types.is_map(actual):
            return False
        entries = {field["name"]: field["type"] for field in expected["entries"]["fields"]}
        return types_compatible(entries["key"], actual.key_type) and types_compatible(
            entries["value"], actual.item_type
        )
    if kind == "struct":
        if not pa.types.is_struct(actual):
            return False
        expected_fields = expected["fields"]
        if actual.num_fields != len(expected_fields):
            return False
        for spec, field in zip(expected_fields, list(actual), strict=True):
            if spec["name"] != field.name or not types_compatible(spec["type"], field.type):
                return False
        return True
    if kind == "dictionary":
        if not pa.types.is_dictionary(actual):
            return False
        return types_compatible(expected["key"], actual.index_type) and types_compatible(
            expected["value"], actual.value_type
        )
    if kind == "timestamp":
        if not pa.types.is_timestamp(actual):
            return False
        if actual.unit != spec_unit(expected["unit"]):
            return False
        return _tz_compatible(expected.get("tz"), actual.tz)
    primitive = _PRIMITIVE.get(kind)
    return primitive is not None and actual == primitive


def spec_unit(unit: str) -> str:
    return unit


def match_variant(actual: pa.DataType, variant: dict[str, Any]) -> str | None:
    """Return an error detail when ``actual`` is not a compatible prefix of ``variant``."""

    if not pa.types.is_struct(actual):
        return f"expected a struct, found {actual}"
    expected_fields = variant["fields"]
    actual_fields = list(actual)
    if len(actual_fields) > len(expected_fields):
        return (
            f"expected at most {len(expected_fields)} fields, found {len(actual_fields)}"
        )
    for index, field in enumerate(actual_fields):
        expected = expected_fields[index]
        if field.name != expected["name"] or not types_compatible(expected["type"], field.type):
            return (
                f"field {index} expected {expected['name']!r}, found {field.name!r} ({field.type})"
            )
    for expected in expected_fields[len(actual_fields) :]:
        if not expected["nullable"]:
            return f"missing non-nullable field {expected['name']!r}"
    return None


def struct_field(array: pa.StructArray, name: str) -> pa.Array | None:
    try:
        index = array.type.get_field_index(name)
    except AttributeError:
        index = -1
    if index < 0:
        names = [field.name for field in array.type]
        if name not in names:
            return None
        index = names.index(name)
    return array.field(index)


def column_python(array: pa.Array) -> list[Any]:
    # Windows CPython has no IANA time zone data unless tzdata is installed.
    # Compare and report timestamps as integer microseconds instead.
    if pa.types.is_timestamp(array.type):
        return array.cast(pa.int64()).to_pylist()
    return array.to_pylist()


def as_param_map(value: Any) -> dict[str, Any] | None:
    """Normalize a pyarrow map cell to a dict. ``None`` stays ``None``."""

    if value is None:
        return None
    if isinstance(value, dict):
        if value and set(value) <= {"key", "value"} and "key" in value:
            return {value["key"]: value["value"]}
        return dict(value)
    if isinstance(value, list):
        mapped: dict[str, Any] = {}
        for item in value:
            if isinstance(item, dict) and "key" in item:
                mapped[item["key"]] = item["value"]
            elif isinstance(item, (tuple, list)) and len(item) == 2:
                mapped[item[0]] = item[1]
            else:
                raise TypeError(f"unrecognized map entry {item!r}")
        return mapped
    raise TypeError(f"unrecognized map value {value!r}")

"""Mutate a synthetic .rpf file for negative tests."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from rpf_validator.contract import load_contract
from tests.fixture_writer import _table_array


def rewrite(src: Path, dest: Path, mutate) -> None:
    reader = pa.ipc.open_file(src)
    schema = reader.schema
    batch = reader.get_batch(0)
    schema, batch = mutate(schema, batch)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with pa.OSFile(str(dest), "wb") as handle:
        writer = pa.ipc.new_file(handle, schema)
        writer.write_batch(batch)
        writer.close()


def _with_metadata(schema: pa.Schema, updates: dict[str, str]) -> pa.Schema:
    metadata = dict(schema.metadata or {})
    for key, value in updates.items():
        metadata[key.encode("utf-8")] = value.encode("utf-8")
    return schema.with_metadata(metadata)


def replace_struct_field(struct: pa.StructArray, field_name: str, values: pa.Array) -> pa.StructArray:
    arrays = []
    fields = []
    for index, field in enumerate(struct.type):
        if field.name == field_name:
            arrays.append(values)
            fields.append(pa.field(field_name, values.type, nullable=field.nullable))
        else:
            arrays.append(struct.field(index))
            fields.append(field)
    return pa.StructArray.from_arrays(arrays, fields=fields)


def replace_table_field(schema: pa.Schema, batch: pa.RecordBatch, table: str, field_name: str, values: pa.Array):
    table_index = schema.get_field_index(table)
    updated = replace_struct_field(batch.column(table_index), field_name, values)
    columns = []
    fields = []
    for index, field in enumerate(schema):
        if index == table_index:
            columns.append(updated)
            fields.append(pa.field(field.name, updated.type, nullable=field.nullable))
        else:
            columns.append(batch.column(index))
            fields.append(field)
    new_schema = pa.schema(fields, metadata=schema.metadata)
    return new_schema, pa.record_batch(columns, schema=new_schema)


def bad_version(schema, batch):
    return _with_metadata(schema, {"raptrix.version": "v0.14.4", "rpf_version": "v0.14.4"}), batch


def drop_dc_converters(schema, batch):
    keep = [index for index, field in enumerate(schema) if field.name != "dc_converters"]
    new_schema = pa.schema([schema.field(index) for index in keep], metadata=schema.metadata)
    return new_schema, pa.record_batch([batch.column(index) for index in keep], schema=new_schema)


def inflate_bus_rows(schema, batch):
    return _with_metadata(schema, {"rpf.rows.buses": "99999"}), batch


def bad_branch_bus(schema, batch):
    table_index = schema.get_field_index("branches")
    struct = batch.column(table_index)
    field_index = struct.type.get_field_index("from_bus_id")
    values = struct.field(field_index).to_pylist()
    values[0] = 99999
    return replace_table_field(
        schema,
        batch,
        "branches",
        "from_bus_id",
        pa.array(values, type=pa.int32()),
    )


def _replace_dynamics_params(schema, batch, params, model_type=None):
    table_index = schema.get_field_index("dynamics_models")
    struct = batch.column(table_index)
    field_index = struct.type.get_field_index("params")
    values = struct.field(field_index).to_pylist()
    values[0] = list(params.items())
    schema, batch = replace_table_field(
        schema,
        batch,
        "dynamics_models",
        "params",
        pa.array(values, type=struct.field(field_index).type),
    )
    if model_type is None:
        return schema, batch
    struct = batch.column(schema.get_field_index("dynamics_models"))
    model_index = struct.type.get_field_index("model_type")
    models = struct.field(model_index).to_pylist()
    models[0] = model_type
    return replace_table_field(
        schema,
        batch,
        "dynamics_models",
        "model_type",
        pa.array(models, type=pa.dictionary(pa.int32(), pa.utf8())),
    )


def dynamics_named_with_positional(schema, batch):
    return _replace_dynamics_params(
        schema,
        batch,
        {"params_named": 1.0, "source_dyr": 1.0, "p1": 1.0, "p2": 2.0, "H": 5.0},
    )


def dynamics_wttqa1_current(schema, batch):
    return _replace_dynamics_params(
        schema,
        batch,
        {
            "params_named": 1.0,
            "p1": 1.0,
            "p2": 2.0,
            "pwr1": 0.2,
            "pwr2": 0.4,
            "pwr3": 0.6,
            "pwr4": 0.8,
        },
        model_type="WTTQA1",
    )


def dynamics_wttqa1_old(schema, batch):
    return _replace_dynamics_params(
        schema,
        batch,
        {"params_named": 1.0, "p1": 0.2, "p2": 0.4, "p3": 0.6, "p4": 0.8},
        model_type="WTTQA1",
    )


def dynamics_p0(schema, batch):
    table_index = schema.get_field_index("dynamics_models")
    struct = batch.column(table_index)
    field_index = struct.type.get_field_index("params")
    values = struct.field(field_index).to_pylist()
    values[0] = [("p0", 1.0)]
    return replace_table_field(
        schema,
        batch,
        "dynamics_models",
        "params",
        pa.array(values, type=struct.field(field_index).type),
    )


def add_buses_solved(schema, batch):
    contract = load_contract()
    array = _table_array(contract, "buses_solved", [{"bus_id": 1, "v_mag_pu": 1.0}], batch.num_rows)
    fields = list(schema)
    columns = [batch.column(index) for index in range(batch.num_columns)]
    fields.append(pa.field("buses_solved", array.type, nullable=True))
    columns.append(array)
    new_schema = _with_metadata(
        pa.schema(fields, metadata=schema.metadata),
        {"rpf.rows.buses_solved": "1"},
    )
    return new_schema, pa.record_batch(columns, schema=new_schema)


def hour_ahead(schema, batch):
    schema = _with_metadata(schema, {"rpf.case_mode": "hour_ahead_advisory"})
    table_index = schema.get_field_index("metadata")
    struct = batch.column(table_index)
    field_index = struct.type.get_field_index("case_mode")
    values = struct.field(field_index).to_pylist()
    values[0] = "hour_ahead_advisory"
    updated = pa.array(values, type=pa.dictionary(pa.int32(), pa.utf8()))
    return replace_table_field(schema, batch, "metadata", "case_mode", updated)


def blank_table_fingerprint(schema, batch):
    table_index = schema.get_field_index("metadata")
    struct = batch.column(table_index)
    field_index = struct.type.get_field_index("case_fingerprint")
    values = struct.field(field_index).to_pylist()
    values[0] = ""
    return replace_table_field(
        schema,
        batch,
        "metadata",
        "case_fingerprint",
        pa.array(values, type=pa.utf8()),
    )


def converter_export_mode(schema, batch):
    schema = _with_metadata(schema, {"rpf.validation_mode": "converter_export"})
    table_index = schema.get_field_index("metadata")
    struct = batch.column(table_index)
    field_index = struct.type.get_field_index("validation_mode")
    values = struct.field(field_index).to_pylist()
    values[0] = "converter_export"
    updated = pa.array(values, type=pa.dictionary(pa.int32(), pa.utf8()))
    return replace_table_field(schema, batch, "metadata", "validation_mode", updated)


def unprefixed_version(schema, batch):
    return _with_metadata(schema, {"raptrix.version": "0.14.5", "rpf_version": "0.14.5"}), batch


def swap_bus_name_and_type(schema, batch):
    """Keep each column's values, but exchange their positions in the struct."""

    table_index = schema.get_field_index("buses")
    struct = batch.column(table_index)
    names = [field.name for field in struct.type]
    name_index = names.index("name")
    type_index = names.index("type")
    order = list(range(len(names)))
    order[name_index], order[type_index] = order[type_index], order[name_index]
    arrays = [struct.field(index) for index in order]
    fields = [struct.type[index] for index in order]
    swapped = pa.StructArray.from_arrays(arrays, fields=fields)
    columns = []
    schema_fields = []
    for index, field in enumerate(schema):
        if index == table_index:
            columns.append(swapped)
            schema_fields.append(pa.field(field.name, swapped.type, nullable=field.nullable))
        else:
            columns.append(batch.column(index))
            schema_fields.append(field)
    new_schema = pa.schema(schema_fields, metadata=schema.metadata)
    return new_schema, pa.record_batch(columns, schema=new_schema)

"""
Schema management for SQLite and Postgres (Supabase).

SQLModel's create_all creates missing tables but never adds columns to tables
that already exist, so ensure_schema() also adds any missing (nullable) columns.
On Postgres it enables Row Level Security on every table with no policies: the
Supabase REST/anon key can then read nothing, and only the backend's direct
database credentials can reach patient data.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, literal_column, text
from sqlalchemy.schema import CreateColumn, CreateIndex
from sqlmodel import SQLModel

log = logging.getLogger("vitalyn.schema")


def add_missing_columns(engine) -> list[str]:
    """ALTER TABLE ... ADD COLUMN for model columns the database does not have yet."""
    added: list[str] = []
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    preparer = engine.dialect.identifier_preparer
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = str(CreateColumn(col).compile(dialect=engine.dialect))
                if not col.nullable and col.server_default is None:
                    # Existing rows need a value: use the model's scalar default if it has one.
                    default = getattr(col.default, "arg", None) if col.default is not None else None
                    if default is None or callable(default):
                        log.warning("Cannot auto-add NOT NULL column %s.%s", table.name, col.name)
                        continue
                    literal = literal_column(repr(default) if not isinstance(default, str)
                                             else "'" + default.replace("'", "''") + "'")
                    ddl += f" DEFAULT {literal.name}"
                conn.execute(text(f"ALTER TABLE {preparer.format_table(table)} ADD COLUMN {ddl}"))
                added.append(f"{table.name}.{col.name}")
    return added


def add_missing_indexes(engine) -> list[str]:
    """create_all skips indexes on tables that already exist, so add any the models declare."""
    created: list[str] = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in insp.get_table_names():
                continue
            have = {i["name"] for i in insp.get_indexes(table.name)}
            for index in table.indexes:
                if index.name and index.name not in have:
                    conn.execute(CreateIndex(index, if_not_exists=True))
                    created.append(index.name)
    return created


def enable_row_level_security(engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            conn.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))
        # Defence in depth: the public API roles get no table privileges at all.
        for role in ("anon", "authenticated"):
            try:
                conn.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}"))
            except Exception:  # role absent on plain Postgres
                pass


def ensure_schema(engine) -> list[str]:
    """Create tables, add new columns, lock down Postgres. Safe to run on every start."""
    SQLModel.metadata.create_all(engine)
    added = add_missing_columns(engine)
    if added:
        log.info("Added columns: %s", ", ".join(added))
    add_missing_indexes(engine)
    enable_row_level_security(engine)
    return added

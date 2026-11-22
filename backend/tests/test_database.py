"""Database layer: URL handling, schema upgrades, Postgres compatibility (no server needed)."""
import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from sqlmodel import SQLModel

import database
from schema import add_missing_columns, enable_row_level_security, ensure_schema
from models import Room, Bed, FallEvent


def test_default_is_local_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database.database_url().startswith("sqlite:///")
    assert database.is_postgres() is False


@pytest.mark.parametrize("raw", ["postgres://u:p@db.x.supabase.co:5432/postgres",
                                 "postgresql://u:p@db.x.supabase.co:5432/postgres"])
def test_supabase_urls_get_a_driver(monkeypatch, raw):
    monkeypatch.setenv("DATABASE_URL", raw)
    assert database.database_url().startswith("postgresql+psycopg://u:p@")
    assert database.is_postgres()


def test_describe_database_never_leaks_password(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:SuperSecret123@db.abc.supabase.co:5432/postgres")
    text_ = database.describe_database()
    assert "SuperSecret123" not in text_ and "db.abc.supabase.co" in text_


def test_models_compile_to_valid_postgres_ddl_with_native_uuid():
    ddl = str(CreateTable(Room.__table__).compile(dialect=postgresql.dialect()))
    assert "UUID" in ddl and "CHAR(36)" not in ddl
    fk = str(CreateTable(FallEvent.__table__).compile(dialect=postgresql.dialect()))
    assert "UUID" in fk


def test_sqlite_keeps_hyphenated_char36():
    ddl = str(CreateTable(Room.__table__).compile(dialect=create_engine("sqlite://").dialect))
    assert "CHAR(36)" in ddl


def test_add_missing_columns_upgrades_an_old_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/old.db")
    with engine.begin() as c:                      # a table from an older version: no "status" column
        c.execute(text("CREATE TABLE room (id CHAR(36) PRIMARY KEY, room_number VARCHAR, floor VARCHAR, created_at DATETIME)"))
        c.execute(text("INSERT INTO room (id, room_number, floor) VALUES ('11111111-1111-1111-1111-111111111111','1','1')"))
    added = add_missing_columns(engine)
    assert "room.status" in added
    assert "status" in {c["name"] for c in inspect(engine).get_columns("room")}
    assert add_missing_columns(engine) == []       # idempotent


def test_ensure_schema_creates_everything_and_is_repeatable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/fresh.db")
    ensure_schema(engine)
    ensure_schema(engine)
    assert {"room", "bed", "alert", "fall_event"} <= set(inspect(engine).get_table_names())


def test_row_level_security_is_a_noop_on_sqlite(tmp_path):
    enable_row_level_security(create_engine(f"sqlite:///{tmp_path}/x.db"))   # must not raise


def test_tests_never_use_the_real_database():
    assert "vitalyn-tests-" in database.database_url()


def test_https_project_url_gives_a_clear_error_without_echoing_it(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "https://abcdefgh.supabase.co")
    with pytest.raises(RuntimeError) as e:
        database.database_url()
    msg = str(e.value)
    assert "postgresql://" in msg and "'https'" in msg and "abcdefgh" not in msg

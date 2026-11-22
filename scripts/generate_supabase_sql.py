"""
Generate the Supabase (Postgres) schema SQL from the app's own models.

    python3 scripts/generate_supabase_sql.py            # writes backend/supabase/schema.sql
    python3 scripts/generate_supabase_sql.py --print    # also prints it

Paste the result into Supabase > SQL Editor > New query > Run. It is safe to run
more than once (IF NOT EXISTS). The backend creates the same tables automatically
on startup, so this is optional and mainly useful to see/inspect the schema.
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)

from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import models  # noqa: E402,F401  (registers every table)

dialect = postgresql.dialect()
out = [
    "-- VITALYN schema for Supabase (Postgres). Generated from backend/models.py.",
    "-- Safe to run more than once. Run in: Supabase > SQL Editor > New query.",
    "",
]
tables = list(SQLModel.metadata.sorted_tables)           # parents before children
for table in tables:
    out.append(str(CreateTable(table, if_not_exists=True).compile(dialect=dialect)).strip() + ";")
    for index in sorted(table.indexes, key=lambda i: i.name or ""):
        out.append(str(CreateIndex(index, if_not_exists=True).compile(dialect=dialect)).strip() + ";")
    out.append("")

out += [
    "-- Row Level Security: ON with NO policies, so Supabase's public (anon / authenticated)",
    "-- API keys can read and write nothing. Only the backend's direct database login can.",
]
for table in tables:
    out.append(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY;')
out += [
    "",
    "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;",
    "",
]

sql = "\n".join(out)
path = os.path.join(BACKEND, "supabase", "schema.sql")
with open(path, "w") as f:
    f.write(sql)
print(f"Wrote {os.path.relpath(path)} ({len(tables)} tables)")
if "--print" in sys.argv:
    print()
    print(sql)

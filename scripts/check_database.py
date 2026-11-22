"""
Check the VITALYN database connection (SQLite or Supabase) without printing secrets.

    python3 scripts/check_database.py

Reads DATABASE_URL from backend/.env (or the environment). It only reads: it does
not create tables or change anything. Share the output freely: the password is
never printed.
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)

from sqlalchemy import inspect, text  # noqa: E402

try:
    import database  # noqa: E402
except RuntimeError as exc:           # e.g. DATABASE_URL has the wrong format (message never contains the URL)
    print("Configuration problem:", exc)
    sys.exit(1)


def main() -> int:
    url = database.database_url()
    print("Database:", database.describe_database())
    if url.startswith("sqlite"):
        print("DATABASE_URL is empty, so the local SQLite file is used.")
        print("To use Supabase, paste the connection string into backend/.env and run this again.")
        return 0

    try:
        with database.engine.connect() as conn:
            version = conn.execute(text("select version()")).scalar() or ""
            print("Connected: yes")
            print("Server:", version.split(" on ")[0])
            tables = inspect(database.engine).get_table_names()
            print(f"Tables present: {len(tables)}", f"({', '.join(sorted(tables))})" if tables else "(none yet)")
            if tables:
                rows = conn.execute(text(
                    "select relname, relrowsecurity from pg_class c "
                    "join pg_namespace n on n.oid = c.relnamespace "
                    "where n.nspname = 'public' and c.relkind = 'r'"
                )).all()
                missing = sorted(r[0] for r in rows if not r[1])
                print("Row Level Security: " + ("on for every table" if not missing else "OFF for " + ", ".join(missing)))
        return 0
    except Exception as exc:
        msg = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        # Never echo the URL: SQLAlchemy messages can include it.
        for part in (url, getattr(database.engine.url, "password", None) or ""):
            if part:
                msg = msg.replace(part, "***")
        print("Connected: NO")
        print("Reason:", msg[:300])
        print("Tips: use the 'Session pooler' string (IPv4); check the password; make sure the project is not paused.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""
Database engine for VITALYN (shared by the API and the ML engine).

DATABASE_URL selects the database:
  * unset                      -> local SQLite file backend/vitalyn.db (development, tests)
  * postgresql://...           -> Supabase (or any Postgres); needs `psycopg`

Keep the URL, which contains the database password, in the git-ignored
backend/.env file or the process environment. Never commit it.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlmodel import Session, create_engine

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

# Existing environment variables win over .env, so tests and CI can override safely.
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

DEFAULT_SQLITE_URL = f"sqlite:///{os.path.join(BACKEND_DIR, 'vitalyn.db')}"


def database_url() -> str:
    url = (os.getenv("DATABASE_URL") or DEFAULT_SQLITE_URL).strip()
    # Supabase hands out postgres:// or postgresql:// URLs; SQLAlchemy needs a driver name.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    if not url.startswith(("sqlite", "postgresql+")):
        scheme = url.split("://", 1)[0] if "://" in url else "(no scheme)"
        raise RuntimeError(
            f"DATABASE_URL must start with postgresql:// (it starts with '{scheme}'). "
            "In Supabase use Connect > 'Session pooler' (a postgresql:// string), "
            "not the project URL (https://...) or the API keys."
        )
    return url


def is_postgres(url: str | None = None) -> bool:
    return (url or database_url()).startswith("postgresql")


def make_engine(url: str | None = None):
    url = url or database_url()
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(
        url,
        pool_pre_ping=True,          # drop dead connections (Supabase closes idle ones)
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
        connect_args={"connect_timeout": 10},
    )


engine = make_engine()


def get_engine():
    return engine


def describe_database() -> str:
    """Safe-to-log description (never includes the password)."""
    url = database_url()
    if url.startswith("sqlite"):
        return "SQLite (local file)"
    try:
        from sqlalchemy.engine import make_url
        u = make_url(url)
        return f"Postgres ({u.host})"
    except Exception:
        return "Postgres"


def get_session():
    """FastAPI-compatible dependency: yields a SQLModel session."""
    with Session(engine) as session:
        yield session

"""
SQLAlchemy engine/session setup for the project registry.

Two modes, chosen by whether settings.DATABASE_URL is set:
- Local dev (default): SQLite file (registry.db) in WORKSPACE_DIR. Zero setup,
  matches the original "single student, single machine" deployment.
- Production/Vercel: Supabase Postgres, via DATABASE_URL (the connection
  string from Supabase's Project Settings -> Database -> Connection string;
  use the "Transaction" pooler URI on Vercel, since serverless functions
  open a new connection per invocation and Postgres has a connection limit).

Everything that reads/writes project records goes through core/workspace.py,
which is the only file that needs to know this module exists -- the mode
switch below is transparent to callers either way.
"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.config import settings


def _sqlite_database_path() -> Path:
    path = Path(settings.WORKSPACE_DIR) / "registry.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


if settings.DATABASE_URL:
    DATABASE_URL = settings.DATABASE_URL
    # SQLAlchemy needs a "+psycopg" driver suffix to use psycopg (v3) instead
    # of the default psycopg2 -- Supabase's dashboard gives you a plain
    # postgresql:// URL, so it's added here rather than making you hand-edit
    # the connection string yourself.
    if DATABASE_URL.startswith("postgresql://"):
        engine_url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    elif DATABASE_URL.startswith("postgres://"):
        engine_url = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    else:
        engine_url = DATABASE_URL
    # pool_pre_ping avoids "server closed the connection" errors from
    # Supabase's pooler recycling idle connections; pool_size kept small
    # since serverless invocations are short-lived and concurrent.
    engine = create_engine(engine_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
else:
    DATABASE_URL = f"sqlite:///{_sqlite_database_path()}"
    # check_same_thread=False: FastAPI's background tasks run in a threadpool,
    # not the main request thread, so the default sqlite3 same-thread guard
    # would reject writes from run_pipeline()'s background task otherwise.
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Session:
    return SessionLocal()


def init_db() -> None:
    # Imported here (not at module top) to avoid a circular import between
    # core.db and core.models at module load time.
    import core.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

"""Database engine / session management."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models.base import Base

_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def build_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    if url.startswith("sqlite"):
        return create_engine(
            url, future=True, connect_args={"check_same_thread": False}
        )
    return create_engine(url, future=True, pool_pre_ping=True)


def init_engine(url: str | None = None) -> Engine:
    """Create the global engine/session factory and ensure tables exist."""
    global _engine, SessionLocal
    _engine = build_engine(url)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(_engine)
    _ensure_columns(_engine)
    return _engine


def _ensure_columns(engine: Engine) -> None:
    """Lightweight additive migration for existing SQLite databases."""
    if engine.dialect.name != "sqlite":
        return
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "video_jobs" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("video_jobs")}
    if "clip_length" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE video_jobs ADD COLUMN clip_length INTEGER NOT NULL DEFAULT 60"))


def get_session() -> Session:
    if SessionLocal is None:
        init_engine()
    return SessionLocal()

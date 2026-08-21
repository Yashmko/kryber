"""Test configuration.

Environment is pinned BEFORE any app import so the cached settings are the
test settings (SQLite + in-memory queue + rate limiting disabled).
"""
from __future__ import annotations

import os
import tempfile

_TEST_TMP = tempfile.mkdtemp(prefix="kryber_test_")

os.environ["KRYBER_DATABASE_URL"] = f"sqlite:///{_TEST_TMP}/test.db"
os.environ["KRYBER_QUEUE_BACKEND"] = "memory"
os.environ["KRYBER_RATE_LIMIT_JOBS_PER_MINUTE"] = "0"
os.environ["KRYBER_STORAGE_LOCAL_ROOT"] = f"{_TEST_TMP}/storage"
os.environ["KRYBER_TMP_ROOT"] = f"{_TEST_TMP}/tmp"
os.environ["KRYBER_LLM_PROVIDER"] = "mock"
os.environ["KRYBER_TRANSCRIPTION_PROVIDER"] = "mock"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.main import app  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.services.queue import InMemoryJobQueue, set_queue  # noqa: E402


@pytest.fixture()
def db_session():
    """Fresh in-memory SQLite session per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db_session):
    """API test client backed by a fresh DB + fresh in-memory queue."""
    set_queue(InMemoryJobQueue())

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:  # noqa: F841
        yield c
    app.dependency_overrides.clear()

"""Worker/queue visibility: startup diagnostics and health reporting.

The failure mode being guarded against: ``POST /api/jobs`` succeeds, but the
API is running without a worker, so the job stays QUEUED forever and the UI
sits on "Preparing your video…". These tests pin the behaviour that makes that
state observable instead of silent.

Covers:
- queue_status() worker/backend reporting for every backend + worker combination
- /healthz exposing queue+worker diagnostics (API healthy vs worker unavailable)
- startup warning when the memory queue has no in-process worker
- KRYBER_INPROC_WORKER=1 still starting the in-process worker
- the standalone-worker-on-memory-queue misconfiguration warning
"""
from __future__ import annotations

import logging

import pytest

import app.main as main_mod
import app.services.queue as queue_mod
import app.workers.video_worker as worker_mod
from app.config import Settings
from app.services.queue import (
    InMemoryJobQueue,
    mark_worker_active,
    mark_worker_inactive,
    queue_status,
    set_queue,
    worker_active,
)


def _settings(**overrides) -> Settings:
    base = {"queue_backend": "memory", "inproc_worker": False}
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture(autouse=True)
def _clean_worker_flag():
    """Worker registration is process-wide; never leak it between tests."""
    mark_worker_inactive()
    yield
    mark_worker_inactive()


# ── queue_status() ────────────────────────────────────────────────────────

def test_memory_queue_without_worker_reports_unavailable(monkeypatch):
    monkeypatch.setattr(queue_mod, "get_settings", lambda: _settings())
    set_queue(InMemoryJobQueue())

    status = queue_status()

    assert status["backend"] == "memory"
    assert status["worker"] == "unavailable"
    assert status["processing_available"] is False
    assert "KRYBER_INPROC_WORKER=1" in status["detail"]


def test_memory_queue_with_worker_reports_running(monkeypatch):
    monkeypatch.setattr(queue_mod, "get_settings", lambda: _settings())
    set_queue(InMemoryJobQueue())
    mark_worker_active()

    status = queue_status()

    assert status["worker"] == "running"
    assert status["processing_available"] is True
    assert status["detail"] is None


def test_redis_backend_reports_external_worker(monkeypatch):
    monkeypatch.setattr(queue_mod, "get_settings", lambda: _settings(queue_backend="redis"))
    set_queue(InMemoryJobQueue())  # stand-in; we only assert on the reporting

    status = queue_status()

    assert status["backend"] == "redis"
    # Liveness of another process is not observable — don't claim otherwise.
    assert status["worker"] == "external"
    assert status["processing_available"] is True


def test_queue_status_reports_depth(monkeypatch):
    monkeypatch.setattr(queue_mod, "get_settings", lambda: _settings())
    queue = InMemoryJobQueue()
    queue.enqueue("kr_one")
    queue.enqueue("kr_two")
    set_queue(queue)

    assert queue_status()["depth"] == 2


def test_queue_status_survives_unreachable_backend(monkeypatch):
    """A broken Redis must not take down health reporting."""
    class Exploding(InMemoryJobQueue):
        def size(self) -> int:
            raise ConnectionError("redis is down")

    monkeypatch.setattr(queue_mod, "get_settings", lambda: _settings(queue_backend="redis"))
    set_queue(Exploding())

    status = queue_status()

    assert status["depth"] is None
    assert status["worker"] == "external"


def test_worker_active_flag_round_trips():
    assert worker_active() is False
    mark_worker_active()
    assert worker_active() is True
    mark_worker_inactive()
    assert worker_active() is False


# ── /healthz ──────────────────────────────────────────────────────────────

def test_healthz_reports_worker_unavailable(client):
    body = client.get("/healthz").json()

    # The API itself is healthy...
    assert body["status"] == "ok"
    # ...but nothing can process jobs, and that is now visible.
    assert body["queue"]["worker"] == "unavailable"
    assert body["queue"]["processing_available"] is False
    assert "KRYBER_INPROC_WORKER=1" in body["queue"]["detail"]


def test_healthz_reports_worker_running(client):
    mark_worker_active()

    body = client.get("/healthz").json()

    assert body["status"] == "ok"
    assert body["queue"]["worker"] == "running"
    assert body["queue"]["processing_available"] is True


def test_queued_job_is_visible_in_health_depth(client, monkeypatch):
    """A job accepted with no worker shows up as queue depth, not silence."""
    monkeypatch.setattr(
        "app.services.jobs.validate_source_url", lambda url: ("youtube", url)
    )
    resp = client.post(
        "/api/jobs",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "clip_length": 60},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "queued"

    body = client.get("/healthz").json()
    assert body["queue"]["depth"] == 1
    assert body["queue"]["processing_available"] is False


# ── startup diagnostics ───────────────────────────────────────────────────

def test_startup_warns_when_memory_queue_has_no_worker(caplog):
    from fastapi.testclient import TestClient

    with caplog.at_level(logging.WARNING, logger="kryber.main"):
        with TestClient(main_mod.app):
            pass

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("no worker will process jobs" in m for m in warnings)
    assert any("KRYBER_INPROC_WORKER=1" in m for m in warnings)


def test_inproc_worker_setting_still_starts_a_worker(monkeypatch):
    """KRYBER_QUEUE_BACKEND=memory + KRYBER_INPROC_WORKER=1 must keep working."""
    from fastapi.testclient import TestClient

    started: list[dict] = []

    def fake_run_worker(in_process: bool = False):
        started.append({"in_process": in_process})

    monkeypatch.setattr(worker_mod, "run_worker", fake_run_worker)
    monkeypatch.setattr(
        main_mod, "get_settings", lambda: _settings(inproc_worker=True)
    )

    with TestClient(main_mod.app):
        pass

    assert started == [{"in_process": True}]


def test_no_startup_warning_when_inproc_worker_enabled(monkeypatch, caplog):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(worker_mod, "run_worker", lambda in_process=False: None)
    monkeypatch.setattr(
        main_mod, "get_settings", lambda: _settings(inproc_worker=True)
    )

    with caplog.at_level(logging.WARNING, logger="kryber.main"):
        with TestClient(main_mod.app):
            pass

    assert not any(
        "no worker will process jobs" in r.getMessage() for r in caplog.records
    )


# ── worker-side diagnostics ───────────────────────────────────────────────

def test_standalone_worker_on_memory_queue_warns(monkeypatch, caplog):
    """A separate worker process + memory queue can never receive jobs."""
    monkeypatch.setattr(worker_mod, "get_settings", lambda: _settings())
    monkeypatch.setattr(worker_mod, "get_queue", lambda: InMemoryJobQueue())
    monkeypatch.setattr(worker_mod, "recover_stuck_jobs", lambda: 0)

    # Break out of the consume loop immediately.
    monkeypatch.setattr(
        worker_mod, "run_job", lambda job_id: (_ for _ in ()).throw(RuntimeError)
    )

    class StopLoop(Exception):
        pass

    def one_shot_dequeue(timeout=None):
        raise StopLoop

    queue = InMemoryJobQueue()
    monkeypatch.setattr(queue, "dequeue", one_shot_dequeue)
    monkeypatch.setattr(worker_mod, "get_queue", lambda: queue)

    with caplog.at_level(logging.WARNING, logger="kryber.worker"):
        with pytest.raises(StopLoop):
            worker_mod.run_worker(in_process=False)

    messages = [r.getMessage() for r in caplog.records]
    assert any("will NEVER receive jobs" in m for m in messages)


def test_in_process_worker_does_not_warn_and_registers(monkeypatch, caplog):
    monkeypatch.setattr(worker_mod, "get_settings", lambda: _settings(inproc_worker=True))
    monkeypatch.setattr(worker_mod, "recover_stuck_jobs", lambda: 0)

    seen: list[bool] = []

    class StopLoop(Exception):
        pass

    def one_shot_dequeue(timeout=None):
        # Observed from inside the running loop: the worker is registered.
        seen.append(worker_active())
        raise StopLoop

    queue = InMemoryJobQueue()
    monkeypatch.setattr(queue, "dequeue", one_shot_dequeue)
    monkeypatch.setattr(worker_mod, "get_queue", lambda: queue)

    with caplog.at_level(logging.WARNING, logger="kryber.worker"):
        with pytest.raises(StopLoop):
            worker_mod.run_worker(in_process=True)

    assert seen == [True]
    assert not any("will NEVER receive jobs" in r.getMessage() for r in caplog.records)
    # ...and deregistered once the loop exits, so health stops claiming a worker.
    assert worker_active() is False

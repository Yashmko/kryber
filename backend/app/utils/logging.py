"""Structured logging.

Every log line can carry ``job_id`` and ``stage`` plus arbitrary key=value
fields, e.g.::

    12:00:01 INFO  kryber.worker: transcription done  [job=kr_abc123 stage=transcribing segments=182 chars=14382]

Use context managers to bind values for a whole block, or pass them per-call.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

_job_id: ContextVar[str | None] = ContextVar("kryber_job_id", default=None)
_stage: ContextVar[str | None] = ContextVar("kryber_stage", default=None)

_CONFIGURED = False


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        job = getattr(record, "job_id", None) or _job_id.get()
        stage = getattr(record, "stage", None) or _stage.get()
        fields = getattr(record, "fields", None) or {}

        parts = []
        if job:
            parts.append(f"job={job}")
        if stage:
            parts.append(f"stage={stage}")
        for key, value in fields.items():
            parts.append(f"{key}={value}")

        line = (
            f"{self.formatTime(record, self.datefmt)} "
            f"{record.levelname:<7} {record.name}: {record.getMessage()}"
        )
        if parts:
            line += "  [" + " ".join(parts) + "]"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter(datefmt="%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers = [handler]
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    job_id: str | None = None,
    stage: str | None = None,
    **fields,
) -> None:
    logger.log(level, message, extra={"job_id": job_id, "stage": stage, "fields": fields})


def info(logger: logging.Logger, message: str, **kwargs) -> None:
    log(logger, logging.INFO, message, **kwargs)


def warning(logger: logging.Logger, message: str, **kwargs) -> None:
    log(logger, logging.WARNING, message, **kwargs)


def error(logger: logging.Logger, message: str, **kwargs) -> None:
    log(logger, logging.ERROR, message, **kwargs)


class JobContext:
    """Context manager binding a job_id to all logs inside the block."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self._token = None

    def __enter__(self):
        self._token = _job_id.set(self.job_id)
        return self

    def __exit__(self, *exc):
        _job_id.reset(self._token)
        return False


class StageContext:
    """Context manager binding a pipeline stage to all logs inside the block."""

    def __init__(self, stage: str):
        self.stage = stage
        self._token = None

    def __enter__(self):
        self._token = _stage.set(self.stage)
        return self

    def __exit__(self, *exc):
        _stage.reset(self._token)
        return False

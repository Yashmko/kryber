"""Typed domain errors.

Every user-facing failure carries a stable ``code``, a human ``message`` and a
``stage`` so the frontend can say *exactly* which part of the pipeline failed.
"""
from __future__ import annotations


class KryberError(Exception):
    """Base class for all expected, user-reportable errors."""

    code: str = "KRYBER_ERROR"
    stage: str | None = None
    status_code: int = 500

    def __init__(self, message: str, *, stage: str | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        if stage is not None:
            self.stage = stage
        if code is not None:
            self.code = code

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "stage": self.stage,
            }
        }


class URLValidationError(KryberError):
    code = "URL_VALIDATION_FAILED"
    stage = "validation"
    status_code = 400


class JobNotFoundError(KryberError):
    code = "JOB_NOT_FOUND"
    status_code = 404


class ClipNotFoundError(KryberError):
    code = "CLIP_NOT_FOUND"
    status_code = 404


class InvalidStateTransitionError(KryberError):
    code = "INVALID_STATE_TRANSITION"
    status_code = 409


class RateLimitedError(KryberError):
    code = "RATE_LIMITED"
    stage = "validation"
    status_code = 429


class InvalidClipLengthError(KryberError):
    code = "INVALID_CLIP_LENGTH"
    stage = "validation"
    status_code = 400


class StageError(KryberError):
    """A pipeline stage failed. ``code`` is one of the stage failure codes."""

    status_code = 500

    def __init__(self, stage: str, code: str, message: str):
        super().__init__(message, stage=stage, code=code)


class IngestionFailedError(StageError):
    def __init__(self, message: str):
        super().__init__("ingesting", "INGESTION_FAILED", message)


class TranscriptionFailedError(StageError):
    def __init__(self, message: str):
        super().__init__("transcribing", "TRANSCRIPTION_FAILED", message)


class AnalysisFailedError(StageError):
    def __init__(self, message: str):
        super().__init__("analyzing", "ANALYSIS_FAILED", message)


class RenderFailedError(StageError):
    def __init__(self, message: str):
        super().__init__("rendering", "RENDERING_FAILED", message)

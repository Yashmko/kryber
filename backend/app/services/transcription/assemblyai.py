"""AssemblyAI transcription provider (pre-recorded transcription API).

Audio file → POST /v2/upload (local bytes) → POST /v2/transcript → poll
GET /v2/transcript/{id}. Result preserves utterance + word timestamps.
"""
from __future__ import annotations

import time

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ...config import get_settings
from ...errors import TranscriptionFailedError
from ...utils import logging as logmod
from ..transcription.base import Transcript, TranscriptionProvider
from .normalize import normalize_assemblyai

logger = logmod.get_logger("kryber.transcription.assemblyai")

# Exceptions worth retrying (transient network / server errors).
_RETRYABLE = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


class AssemblyAITranscriptionProvider(TranscriptionProvider):
    name = "assemblyai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.resolve_assemblyai_key()
        self.base_url = (base_url or settings.assemblyai_base_url).rstrip("/")
        if not self.api_key:
            raise TranscriptionFailedError(
                "ASSEMBLYAI_API_KEY is not set. Add it to the environment to enable transcription."
            )

    def _headers(self) -> dict:
        return {"authorization": self.api_key}

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _request(self, method: str, path: str, headers: dict | None = None, **kwargs) -> httpx.Response:
        merged = {"authorization": self.api_key}
        if headers:
            merged.update(headers)
        resp = httpx.request(
            method, f"{self.base_url}{path}", headers=merged, timeout=60.0, **kwargs
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise httpx.RemoteProtocolError(f"AssemblyAI HTTP {resp.status_code}: {resp.text[:200]}")
        return resp

    def _upload(self, audio_path: str) -> str:
        with open(audio_path, "rb") as f:
            data = f.read()
        resp = self._request(
            "POST",
            "/v2/upload",
            content=data,
            headers={"content-type": "application/octet-stream"},
        )
        if resp.status_code != 200:
            raise TranscriptionFailedError(f"AssemblyAI upload failed (HTTP {resp.status_code}): {resp.text[:300]}")
        upload_url = resp.json().get("upload_url")
        if not upload_url:
            raise TranscriptionFailedError("AssemblyAI upload returned no upload_url.")
        return upload_url

    def transcribe(self, audio_path: str) -> Transcript:
        settings = get_settings()
        started = time.monotonic()
        upload_url = self._upload(audio_path)
        logmod.info(logger, "audio uploaded to AssemblyAI", stage="transcribing")

        create = self._request(
            "POST",
            "/v2/transcript",
            json={"audio_url": upload_url, "speaker_labels": False},
        )
        if create.status_code != 200:
            raise TranscriptionFailedError(f"AssemblyAI transcript creation failed (HTTP {create.status_code}): {create.text[:300]}")
        transcript_id = create.json().get("id")
        if not transcript_id:
            raise TranscriptionFailedError("AssemblyAI returned no transcript id.")

        while True:
            if time.monotonic() - started > settings.assemblyai_poll_timeout_seconds:
                raise TranscriptionFailedError("AssemblyAI transcription timed out.")
            poll = self._request("GET", f"/v2/transcript/{transcript_id}")
            if poll.status_code != 200:
                raise TranscriptionFailedError(f"AssemblyAI polling failed (HTTP {poll.status_code}): {poll.text[:300]}")
            result = poll.json()
            status = result.get("status")
            if status == "completed":
                transcript = normalize_assemblyai(result)
                logmod.info(
                    logger,
                    "AssemblyAI transcription done",
                    stage="transcribing",
                    segments=len(transcript.segments),
                    characters=transcript.character_count,
                    elapsed_s=round(time.monotonic() - started, 1),
                )
                return transcript
            if status == "error":
                raise TranscriptionFailedError(f"AssemblyAI failed: {result.get('error')}")
            time.sleep(settings.assemblyai_poll_interval_seconds)

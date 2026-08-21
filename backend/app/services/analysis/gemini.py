"""Google Gemini LLM provider.

Uses the generateContent REST endpoint with structured JSON output
(``response_mime_type`` + ``response_schema``). Key is read from the
GEMINI_API_KEY environment variable — never hard-coded, never sent to the
frontend.
"""
from __future__ import annotations

import json
import time

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ...config import get_settings
from ...errors import AnalysisFailedError
from ...utils import logging as logmod
from .base import LLMProvider

logger = logmod.get_logger("kryber.analysis.gemini")

_RETRYABLE = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


class GeminiLLMProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.resolve_gemini_key()
        self.model = model or settings.gemini_model
        self.base_url = settings.gemini_base_url.rstrip("/")
        if not self.api_key:
            raise AnalysisFailedError(
                "GEMINI_API_KEY is not set. Add it to the environment to enable clip analysis."
            )

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _post(self, payload: dict) -> httpx.Response:
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        resp = httpx.post(
            url,
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=120.0,
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise httpx.RemoteProtocolError(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")
        return resp

    def complete_json(self, system_prompt: str, user_prompt: str, response_schema: dict | None = None) -> dict:
        started = time.monotonic()
        generation_config = {
            "response_mime_type": "application/json",
        }
        if response_schema is not None:
            generation_config["response_schema"] = response_schema

        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": generation_config,
        }

        resp = self._post(payload)
        if resp.status_code != 200:
            raise AnalysisFailedError(f"Gemini request failed (HTTP {resp.status_code}): {resp.text[:300]}")

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AnalysisFailedError("Gemini returned a non-JSON response.") from exc

        candidates = data.get("candidates") or []
        if not candidates:
            finish = data.get("promptFeedback", {}).get("blockReason")
            raise AnalysisFailedError(f"Gemini returned no candidates (blockReason={finish}).")

        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            finish = candidates[0].get("finishReason")
            raise AnalysisFailedError(f"Gemini returned empty content (finishReason={finish}).")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AnalysisFailedError(f"Gemini output was not valid JSON: {text[:200]!r}") from exc

        logmod.info(
            logger,
            "Gemini response parsed",
            stage="analyzing",
            model=self.model,
            elapsed_s=round(time.monotonic() - started, 1),
            bytes=len(text),
        )
        return parsed

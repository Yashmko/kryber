"""Application configuration.

All settings are read from environment variables prefixed with ``KRYBER_``
(plus an optional ``.env`` file). The two external API keys are read from
their plain, conventional names (``GEMINI_API_KEY`` / ``ASSEMBLYAI_API_KEY``)
and are NEVER hard-coded or exposed to the frontend.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KRYBER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    app_name: str = "Kryber"
    environment: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite:///./kryber.db"

    # Queue
    redis_url: str = "redis://localhost:6379/0"
    queue_backend: str = "memory"  # "redis" | "memory"
    # Run a worker thread inside the API process (dev only, memory queue).
    inproc_worker: bool = False

    # Storage
    storage_backend: str = "local"  # "local" | "s3"
    storage_local_root: str = "/tmp/kryber/storage"
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "kryber"
    s3_region: str = "us-east-1"

    # ── LLM (clip analysis + hooks) ─────────────────────────────
    # provider: "gemini" | "mock"
    llm_provider: str = "gemini"
    gemini_model: str = "gemini-3.6-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    # Optional fallback if GEMINI_API_KEY (plain name) is not present.
    gemini_api_key: str | None = None

    # ── Transcription ───────────────────────────────────────────
    # provider: "assemblyai" | "mock"
    transcription_provider: str = "assemblyai"
    assemblyai_base_url: str = "https://api.assemblyai.com"
    assemblyai_poll_interval_seconds: float = 2.0
    assemblyai_poll_timeout_seconds: int = 600
    # Optional fallback if ASSEMBLYAI_API_KEY (plain name) is not present.
    assemblyai_api_key: str | None = None

    # ── Clip engine tuning ──────────────────────────────────────
    clip_min_duration: float = 20.0
    clip_max_duration: float = 60.0
    clip_max_candidates: int = 10
    clip_target_count: int = 5

    # ── Job / safety limits ─────────────────────────────────────
    job_timeout_seconds: int = 3600
    max_video_duration_seconds: int = 4 * 3600
    rate_limit_jobs_per_minute: int = 6

    # ── Media / ingestion ───────────────────────────────────────
    ffmpeg_binary: str | None = None  # auto-detect when unset
    ffprobe_binary: str | None = None
    ytdlp_binary: str | None = None  # auto-detect (yt-dlp → python -m yt_dlp)
    ytdlp_format: str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    # Optional comma-separated yt-dlp player clients to try, e.g. "android,ios,tv".
    # Leave empty for yt-dlp's default behavior.
    ytdlp_player_clients: str = ""
    # Optional path to a Netscape-format cookies.txt exported from your OWN
    # browser (while signed into YouTube). Passed to yt-dlp via --cookies at
    # runtime — the standard remedy for YouTube's "Sign in to confirm you're
    # not a bot" check on datacenter IPs (e.g. GitHub Codespaces). The file
    # itself is a secret: keep it outside the repository and set this via
    # environment variables only. Unset = anonymous downloads (default).
    ytdlp_cookies_file: str | None = None
    # JavaScript runtimes yt-dlp may use to solve YouTube's player challenge
    # (EJS solver). yt-dlp enables only "deno" by default, so a machine with
    # Node.js but no Deno has NO challenge provider and loses formats. Unset
    # = auto-detect what is installed (node 22+, deno, quickjs, bun) and pass
    # it via --js-runtimes. Accepts a comma-separated list with optional
    # paths, e.g. "node" or "node:/usr/local/bin/node". Use "none" to disable
    # and keep yt-dlp's own defaults.
    ytdlp_js_runtimes: str = ""
    ingestion_timeout_seconds: int = 600
    ingestion_retries: int = 3
    ingestion_min_interval_seconds: float = 2.0
    # Max size for a directly-linked video file (bytes).
    direct_max_size_bytes: int = 2 * 1024**3

    # ── Rendering ───────────────────────────────────────────────
    render_timeout_seconds: int = 900
    render_parallelism: int = 2
    # Medium preset + CRF 23 ≈ half the file size of veryfast/CRF 20 with
    # visually near-identical quality for talking-head short-form content.
    render_preset: str = "medium"
    render_crf: int = 23
    render_audio_bitrate: str = "96k"
    caption_font_dir: str = "/usr/share/fonts/truetype/dejavu"
    caption_font_name: str = "DejaVu Sans"
    caption_font_size: int = 88

    # Temp working dir (per-job workspace lives under this)
    tmp_root: str = "/tmp/kryber"

    # CORS
    cors_origins: str = "*"

    # ── Convenience ─────────────────────────────────────────────
    def resolve_gemini_key(self) -> str | None:
        return os.getenv("GEMINI_API_KEY") or self.gemini_api_key

    def resolve_assemblyai_key(self) -> str | None:
        return os.getenv("ASSEMBLYAI_API_KEY") or self.assemblyai_api_key

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

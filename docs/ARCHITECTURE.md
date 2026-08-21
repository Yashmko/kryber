# Kryber — Architecture & Implementation Plan

> **KRYBER = URL → BEST MOMENTS → HOOKS → 9:16 EDIT → CAPTIONS → SHORTS.**
> One workflow. No extras.

## 1. Repository inspection (what existed)

- Workspace was **empty** — fresh repository, nothing pre-existing.
- Environment available for local dev/testing:
  - Python 3.13.14 + pip (PyPI reachable) ✅
  - Node 20.20.2 / npm 10.8.2 ✅
  - ffmpeg — not installed; static binary (7.0.2) pulled via `imageio-ffmpeg` for tests ✅
  - Docker — **not available in sandbox** (files shipped for deployment)
  - PostgreSQL / Redis — **not available in sandbox** (shipped via docker-compose; dev mode uses SQLite + in-memory queue)

## 2. Proposed architecture

```
Browser
  ↓  (HTTPS + JSON)
Next.js  (frontend — minimal dark UI, polls /api/jobs/{id})
  ↓  server-side rewrite /api/* →
FastAPI  (backend — job API, validation, scheduling)
  ↓
PostgreSQL  (VideoJob, Clip)
  ↓
Redis queue  (claim/dispatch)
  ↓
Worker  (Python background process, horizontal)
  ┌────────────────────────────┐
  │ 1. Video Ingestion (yt-dlp)│   source_url → source.mp4
  │ 2. FFmpeg audio extraction │   source.mp4 → audio.wav (16kHz mono)
  │ 3. Transcription (Whisper) │   audio.wav → transcript.json (segments + words)
  │ 4. AI Clip Engine (LLM)    │   transcript → candidate clips (JSON)
  │ 5. Hook generation         │   clip + transcript → grounded hook
  │ 6. Caption timing          │   words → 2–5 word caption groups
  │ 7. Video rendering (FFmpeg)│   9:16 crop, trim, loudness, captions → MP4
  │ 8. Object storage (S3/local)│  upload, presigned/local URL
  └────────────────────────────┘
  ↓
Frontend → preview + download Shorts
```

Key design decisions:

- **Provider abstractions** (`VideoSource`, `TranscriptionProvider`, `LLMProvider`, `StorageBackend`, `JobQueue`) so YouTube→other sources, Whisper→other ASR, OpenAI→Anthropic/Gemini, local→S3, memory→Redis can all be swapped without touching the pipeline.
- **The LLM never receives an empty transcript** — hard validation gate before any LLM call.
- **The LLM is never trusted on timestamps** — every clip is re-validated against real audio/video duration.
- **Deterministic FFmpeg rendering** — captions are burned server-side, never browser-side.
- **Honest progress** — derived from pipeline stages, not fabricated percentages.
- **Honest failures** — every stage failure stores `error_code` + `error_message` + `stage`.

## 3. Directory tree

```
/home/user                          (project root = "kryber")
├── README.md
├── .env.example
├── .gitignore
├── pyproject.toml                  (pytest config)
├── docs/
│   └── ARCHITECTURE.md
├── docker/
│   ├── docker-compose.yml
│   ├── backend.Dockerfile
│   └── frontend.Dockerfile
├── backend/
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── requirements-whisper.txt    (optional heavy dep)
│   └── app/
│       ├── __init__.py
│       ├── main.py                 (FastAPI app factory, routes, error handlers)
│       ├── config.py               (env-driven settings, KRYBER_ prefix)
│       ├── db.py                   (engine/session factory)
│       ├── errors.py               (typed domain errors)
│       ├── api/
│       │   ├── deps.py             (get_db, get_queue, rate limit)
│       │   ├── jobs.py             (POST/GET /api/jobs, clips)
│       │   └── clips.py            (GET /api/clips/{id}, /download)
│       ├── models/
│       │   ├── base.py
│       │   ├── job.py              (VideoJob)
│       │   └── clip.py             (Clip)
│       ├── schemas/
│       │   ├── jobs.py
│       │   └── clips.py
│       ├── services/
│       │   ├── jobs.py             (creation, dedupe, state machine)
│       │   ├── queue.py            (JobQueue: Redis + InMemory)
│       │   ├── pipeline.py         (stage orchestrator — filled Phase 3+)
│       │   ├── ingestion/          (VideoSource ABC, youtube adapter, registry)
│       │   ├── transcription/      (TranscriptionProvider ABC, whisper, mock)
│       │   ├── analysis/           (LLMProvider ABC, openai/anthropic/gemini, clip_engine)
│       │   ├── hooks/              (generator, grounding)
│       │   ├── captions/           (grouping/timing)
│       │   ├── rendering/          (ffmpeg renderer, 9:16 cropper)
│       │   └── storage/            (StorageBackend ABC, local, s3)
│       ├── workers/
│       │   └── video_worker.py     (dequeue → run pipeline)
│       └── utils/
│           ├── ffmpeg.py           (binary discovery + helpers)
│           ├── validation.py       (URL validation, path safety)
│           └── logging.py          (structured logs with job_id/stage)
├── tests/
│   ├── conftest.py
│   ├── test_url_validation.py
│   ├── test_job_creation.py
│   ├── test_state_transitions.py
│   └── test_duplicate_jobs.py
└── frontend/
    ├── package.json
    ├── next.config.mjs
    ├── tsconfig.json
    ├── tailwind.config.ts
    ├── postcss.config.mjs
    ├── app/
    │   ├── layout.tsx
    │   ├── globals.css
    │   ├── page.tsx               (hero + URL form)
    │   └── jobs/[id]/page.tsx     (progress + results)
    ├── components/
    │   ├── ui/button.tsx
    │   ├── ui/input.tsx
    │   ├── UrlForm.tsx
    │   └── JobProgress.tsx
    └── lib/
        ├── api.ts
        └── utils.ts
```

## 4. Dependencies

**Backend (Python):** FastAPI, uvicorn, SQLAlchemy 2.x, psycopg (Postgres driver), pydantic + pydantic-settings, redis-py, httpx, tenacity (retries/backoff), yt-dlp (ingestion), python-multipart, openai-whisper (optional, heavy), pytest + httpx (tests).

**Media:** FFmpeg (system package in Docker; static binary for sandbox tests).

**Frontend (Node):** Next.js 14, React 18, TypeScript, Tailwind CSS 3, postcss/autoprefixer, clsx + tailwind-merge (shadcn-style primitives vendored in `components/ui/`).

**Infra:** PostgreSQL 16, Redis 7, S3-compatible storage (any), Docker.

## 5. Missing infrastructure (sandbox vs. production)

| Component | Sandbox (this workspace) | Production (docker-compose) |
|---|---|---|
| PostgreSQL | SQLite (dev fallback) | postgres:16 |
| Redis | In-memory queue | redis:7 |
| FFmpeg | static binary via imageio-ffmpeg | apt package in worker image |
| Whisper | mock provider (torch too heavy for sandbox) | real Whisper in worker image |
| LLM | mock/deterministic provider | OpenAI/Anthropic/Gemini via env keys |
| Storage | local filesystem backend | S3-compatible via env |

Everything is **provider-swappable via environment variables**, so the exact same code runs in both environments.

## 6. Phased implementation plan

| Phase | Scope | Exit criteria (tests) |
|---|---|---|
| **1. Scaffolding** | Repo, backend skeleton, frontend skeleton, Docker, env, README | app imports, `GET /healthz` |
| **2. Job API** | Models, URL validation, POST/GET /api/jobs, state machine, queue, dedupe | url validation, job creation, state transitions, duplicate jobs |
| **3. Ingestion** | VideoSource ABC, YouTube adapter, metadata, download, video validation | video validation, ingestion |
| **4. Transcription** | FFmpeg audio extraction, Whisper provider, segment normalization, empty-transcript gate | audio extraction, transcript parsing, empty transcript |
| **5. Clip discovery** | LLM provider ABC, transcript→JSON scoring, timestamp validation, selection | llm json validation, timestamp validation, clip duration |
| **6. Rendering** | FFmpeg trim, 9:16 crop, audio normalize, render + validate + upload | rendering |
| **7. Captions** | Word timestamps, caption grouping, animated/burned-in captions | caption segmentation |
| **8. Frontend integration** | URL → progress → results → download | E2E via UI |
| **9. Polish** | Error handling, structured logs, cleanup, rate limit, full test suite | full suite green + E2E |

Each phase: implement → run tests → verify → report (WHAT WAS BUILT / FILES CHANGED / TESTS RUN / RESULT / CURRENT BLOCKER).

# KRYBER

**Turn long videos into Shorts.**

Paste a YouTube URL. Kryber finds the moments worth watching — then automatically produces edited, vertical 9:16 Shorts with strong hooks and animated captions.

```
PASTE VIDEO URL → DOWNLOAD/INGEST → TRANSCRIBE → ANALYZE → FIND BEST MOMENTS
→ CREATE HOOK → EDIT → ADD CAPTIONS → EXPORT SHORTS
```

Kryber has **one job**: turn long videos into Shorts. No avatars, no dubbing, no scheduling, no CRM.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14 · TypeScript · Tailwind CSS · shadcn-style UI |
| Backend | Python · FastAPI · SQLAlchemy 2 |
| Workers | Python background worker · Redis queue (in-memory fallback for dev) |
| Database | PostgreSQL (SQLite fallback for local dev) |
| Storage | S3-compatible (local filesystem fallback) |
| Media | FFmpeg |
| Ingestion | yt-dlp as a subprocess (YouTube adapter, swappable `VideoSource`) |
| Transcription | AssemblyAI pre-recorded API (swappable `TranscriptionProvider`) |
| LLM | Google Gemini `generateContent` with structured JSON (swappable `LLMProvider`) |

## Quickstart (Docker)

```bash
cp .env.example .env         # set GEMINI_API_KEY and ASSEMBLYAI_API_KEY
docker compose -f docker/docker-compose.yml up --build
```

- Frontend → http://localhost:3000
- API → http://localhost:8000 (docs at /docs)

## Quickstart (local dev, no Docker)

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export GEMINI_API_KEY=...  ASSEMBLYAI_API_KEY=...      # real AI (required for real runs)
export KRYBER_DATABASE_URL=sqlite:///./kryber.db
export KRYBER_QUEUE_BACKEND=memory
export KRYBER_INPROC_WORKER=1                          # run worker inside the API (dev)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# OR run a separate worker (production style):
# python -m app.workers.video_worker

# frontend
cd frontend
npm install
npm run dev                  # http://localhost:3000 (proxies /api/* → :8000)
```

### Running without API keys (mock mode)

Set `KRYBER_TRANSCRIPTION_PROVIDER=mock` and `KRYBER_LLM_PROVIDER=mock` to exercise
the full pipeline (real yt-dlp download + real FFmpeg rendering, deterministic
transcript/clip selection) without calling AssemblyAI/Gemini. Real providers are
used automatically when their API keys are present.

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/jobs` | `{"url": "https://www.youtube.com/watch?v=..."}` → `{"job_id","status"}` |
| `GET` | `/api/jobs/{id}` | job status, stage, progress, error |
| `GET` | `/api/jobs/{id}/clips` | generated clips |
| `GET` | `/api/clips/{id}` | clip metadata |
| `GET` | `/api/clips/{id}/download` | rendered MP4 |
| `GET` | `/healthz` | liveness |

## Testing

```bash
pytest                       # from repo root
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and phased plan.

## Status

The full pipeline is implemented and tested end-to-end:

```
POST /api/jobs → queue → yt-dlp ingest → validate → FFmpeg audio → AssemblyAI
→ transcript validation → Gemini clip selection → clip validation → hook grounding
→ FFmpeg 9:16 render + captions + loudness → storage → completed
```

Every stage failure stores `error_code` + `stage` + `error_message` (never a generic
"something went wrong"), and the frontend reflects real pipeline status.
`pytest` covers URL validation, job lifecycle, ingestion/audio validation, transcript
normalization & empty-transcript gates, clip/timestamp validation, caption grouping,
hook grounding, pipeline failure handling, and a full end-to-end render test.

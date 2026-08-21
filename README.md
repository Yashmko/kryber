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

## Troubleshooting: YouTube "Sign in to confirm you're not a bot"

GitHub Codespaces run on **datacenter IPs**, which YouTube often challenges
with a sign-in / bot check. Kryber does not attempt to circumvent bot
protection — the job fails cleanly with an `INGESTION_FAILED` error that
explains the fix. The standard remedy is to let yt-dlp reuse **your own**
browser session, at runtime only (nothing committed to the repo):

1. On your **local PC** (signed into YouTube), export a `cookies.txt` file
   (Netscape format) with a browser extension such as
   [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   or `cookie-editor`.
2. Upload that file to your Codespace **outside the repository**
   (e.g. `~/cookies.txt`). Cookie files are git-ignored — never commit them.
3. Set the environment variable (in your git-ignored `.env` or in Codespace
   environment variables) and restart the backend:

   ```bash
   KRYBER_YTDLP_COOKIES_FILE=/home/user/cookies.txt
   ```

4. Retry the job. If YouTube still asks for sign-in, the cookie file is
   stale — re-export it and update the file (no code changes needed).

Unset the variable to return to anonymous downloads (works for most videos
from residential IPs). The cookie file is only ever passed to yt-dlp via
`--cookies`; it is never logged and never sent anywhere except YouTube.

> **Docker:** the file must be visible *inside* the container — mount it
> read-only (e.g. `volumes: ["~/cookies.txt:/cookies/cookies.txt:ro"]`) and
> set `KRYBER_YTDLP_COOKIES_FILE=/cookies/cookies.txt` in `.env`.

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

CI (GitHub Actions) runs the backend tests and the frontend build on every push.

## Publishing to GitHub

```bash
# 1. Create an empty repo at https://github.com/new (e.g. "kryber"), then:
git remote add origin https://github.com/YOUR_USERNAME/kryber.git
git branch -M main
git push -u origin main
```

Rendered Shorts (`data/`), the local SQLite DB and `node_modules/` are git-ignored
— only source code, tests, config templates and the bundled caption font are
committed. API keys are read from environment variables only (see `.env.example`).

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

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
| YouTube JS challenge | yt-dlp EJS solver (`yt-dlp-ejs`) run on Node.js 22+ / Deno |
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

Prerequisites: Python 3.12+, FFmpeg, Node.js 20+ (frontend) and a JavaScript
runtime for yt-dlp's YouTube challenge solver — **Node.js 22+** or Deno (see
[YouTube requires a JavaScript runtime](#youtube-requires-a-javascript-runtime-nodejs-22-or-deno)).

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

## YouTube requires a JavaScript runtime (Node.js 22+ or Deno)

YouTube protects its player with JavaScript challenges (`n` / signature).
yt-dlp solves them with the **EJS solver**, which needs two things:

1. **The solver scripts** — shipped by the `yt-dlp-ejs` package, already a
   declared dependency in `backend/requirements.txt`. Nothing to do.
2. **A JavaScript runtime to execute them** — *not* bundled. You must have one
   installed.

> yt-dlp only enables **`deno`** by default. On a machine that has Node.js but
> no Deno, yt-dlp finds no runtime, silently falls back to JS-less clients and
> downloads fail or lose formats. Kryber therefore **detects the runtimes you
> actually have installed** and passes `--js-runtimes` to yt-dlp for both the
> metadata and download calls.

**Install a runtime** (any one of these):

```bash
# Node.js 22+ (recommended — Codespaces and the backend Docker image ship it)
nvm install 22 && nvm use 22
node --version        # must be v22.0.0 or newer

# ...or Deno
curl -fsSL https://deno.land/install.sh | sh
```

Auto-detection covers Node.js 22+, Deno, QuickJS and Bun. To pin one
explicitly, set `KRYBER_YTDLP_JS_RUNTIMES` (in your git-ignored `.env` or the
environment):

```bash
KRYBER_YTDLP_JS_RUNTIMES=node                     # by name
KRYBER_YTDLP_JS_RUNTIMES=node:/usr/local/bin/node # pin an exact binary
KRYBER_YTDLP_JS_RUNTIMES=none                     # disable, use yt-dlp defaults
```

If no runtime is available the job fails with an `INGESTION_FAILED` error that
names the fix rather than a bare extraction failure. Node.js older than 22 is
ignored during detection, because that is yt-dlp's minimum supported version.

## Troubleshooting: YouTube "Sign in to confirm you're not a bot"GitHub Codespaces run on **datacenter IPs**, which YouTube often challenges
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

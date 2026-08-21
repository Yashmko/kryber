"""Kryber FastAPI application."""
from __future__ import annotations

import logging as stdlib_logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import clips, jobs
from .config import get_settings
from .db import init_engine
from .errors import KryberError
from .services.queue import WORKER_MISSING_HINT, get_queue, queue_status
from .utils import logging as logmod

logger = logmod.get_logger("kryber.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logmod.setup_logging(settings.log_level)
    init_engine()
    get_queue()  # eager init so config errors surface at startup

    # Dev mode: run the worker in-process when using the memory queue so the
    # whole pipeline works without Redis. (Production uses a separate worker.)
    if settings.inproc_worker and settings.queue_backend == "memory":
        import threading
        from functools import partial

        from .workers.video_worker import run_worker

        thread = threading.Thread(
            target=partial(run_worker, in_process=True),
            daemon=True,
            name="kryber-inproc-worker",
        )
        thread.start()
        logmod.info(logger, "in-process worker started")
    elif settings.queue_backend == "memory":
        # Jobs would be accepted and then sit in QUEUED forever, which looks
        # like a frozen UI ("Preparing your video…"). Make it visible.
        logmod.warning(
            logger,
            "no worker will process jobs: " + WORKER_MISSING_HINT,
            queue_backend=settings.queue_backend,
            inproc_worker=settings.inproc_worker,
        )
    else:
        logmod.info(
            logger,
            "expecting an external worker process to consume the queue",
            queue_backend=settings.queue_backend,
        )

    logmod.info(logger, "backend started", environment=settings.environment)
    yield
    logmod.info(logger, "backend stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Kryber API",
        version="0.1.0",
        description="Turn long videos into Shorts.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(jobs.router)
    app.include_router(clips.router)

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict:
        """API liveness plus queue/worker diagnostics.

        ``status`` describes the API itself (it stays "ok" so liveness probes
        keep working); ``queue`` tells you whether submitted jobs can actually
        be processed, so "API healthy but worker unavailable" is no longer
        indistinguishable from a healthy pipeline.
        """
        return {"status": "ok", "app": settings.app_name, "queue": queue_status()}

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "app": settings.app_name,
            "message": "Kryber API — the web UI is served by the frontend on port 3000.",
            "docs": "/docs",
            "health": "/healthz",
        }

    @app.exception_handler(KryberError)
    async def kryber_error_handler(request: Request, exc: KryberError):
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        # Our handlers raise HTTPException with a {"code","message","stage"} detail.
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logmod.error(logger, "unhandled error", error_type=type(exc).__name__, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": f"Unexpected error: {type(exc).__name__}",
                    "stage": None,
                }
            },
        )

    return app


app = create_app()

# Ensure root logger has a handler when running under uvicorn without lifespan side effects.
if not stdlib_logging.getLogger().handlers:
    logmod.setup_logging(get_settings().log_level)

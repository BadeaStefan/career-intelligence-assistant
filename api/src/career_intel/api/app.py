"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from career_intel.api.routes import analyses, chat, config, documents, prep, traces
from career_intel.db import get_session_factory
from career_intel.ingest.pipeline import fail_orphaned_pending_rows
from career_intel.observability import RequestIdMiddleware, configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Settle rows orphaned by a previous process before serving traffic.

    Background enrichment runs in-process, so anything left ``pending`` at
    boot had its task die with the previous process and will never complete.
    Sweeping here turns a permanent spinner in the UI into a visible,
    retryable failure. Spec section 3.
    """
    async with get_session_factory()() as session:
        await fail_orphaned_pending_rows(session)

    yield


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title="Career Intelligence Assistant", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(config.router)
    app.include_router(documents.router)
    app.include_router(analyses.router)
    app.include_router(chat.router)
    app.include_router(prep.router)
    app.include_router(traces.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app

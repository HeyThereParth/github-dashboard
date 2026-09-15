"""FastAPI application entrypoint.

Exposes a ``create_app`` application factory and a module-level ``app``
instance for running under Uvicorn (``uvicorn app.main:app``).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import dispose_engine
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: configure logging on startup, release resources on shutdown."""
    configure_logging()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Backend for GitHub Intelligence (foundation).",
        lifespan=lifespan,
    )

    # Browser origins allowed to call the API, configurable via CORS_ORIGINS.
    # Explicit origins only (never "*") so credentialed requests remain supported.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Liveness probe indicating the API is up."""
        return {"status": "ok"}

    application.include_router(api_router)

    return application


app = create_app()

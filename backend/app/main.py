from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import enrichment
from app.config import get_settings
from app.loudness import ensure_backfill


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Best-effort loudness backfill for tracks missing data. No-op when
        # LOUDNESS_LOOKUP_ENABLED is false (tests, offline installs) or when
        # a backfill is already running.
        ensure_backfill()
        # Same best-effort background fill for track details. Also a no-op in
        # tests and when ENRICHMENT_ENABLED is false.
        enrichment.ensure_backfill()
        yield

    app = FastAPI(title="Nakout Radio", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    from app.routers import admin, now, queue, schedule, genres, tracks, ws

    app.include_router(genres.router)
    app.include_router(schedule.router)
    app.include_router(now.router)
    app.include_router(tracks.router)
    app.include_router(tracks.studio_router)
    app.include_router(admin.router)
    app.include_router(ws.router)
    app.include_router(queue.router)

    return app


app = create_app()

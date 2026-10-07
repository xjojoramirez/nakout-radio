from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Nakout Radio")

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

    from app.routers import admin, now, queue, schedule, genres, ws

    app.include_router(genres.router)
    app.include_router(schedule.router)
    app.include_router(now.router)
    app.include_router(admin.router)
    app.include_router(ws.router)
    app.include_router(queue.router)

    return app


app = create_app()

"""FastAPI application factory."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Career Intelligence Assistant")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app

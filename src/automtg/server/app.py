"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from automtg import __version__
from automtg.cards.registry import GameData, default_registry

from .routes import router
from .sessions import SessionRegistry

#: The Vite dev server and any local preview build.
LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


def create_app(data: GameData | None = None) -> FastAPI:
    app = FastAPI(
        title="Auto MTG",
        version=__version__,
        description="A Magic: The Gathering Commander engine, exposed for a local playtest client.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=LOCAL_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.sessions = SessionRegistry(data if data is not None else default_registry())
    app.include_router(router)

    @app.get("/health")
    def health() -> dict:
        registry = app.state.sessions
        return {
            "status": "ok",
            "version": __version__,
            "cards": len(registry.data.registry),
            "decks": sorted(registry.data.decks),
            "games": len(registry),
        }

    return app


app = None


def get_app() -> FastAPI:
    """Lazily built module-level app, for ``uvicorn automtg.server.app:get_app``."""
    global app
    if app is None:
        app = create_app()
    return app

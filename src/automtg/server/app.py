"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from automtg import __version__
from automtg.cards.images import load_index
from automtg.cards.registry import GameData, default_registry

from .art import build_store
from .routes import art_router, router
from .sessions import SessionRegistry

#: The Vite dev server and any local preview build.
LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


def create_app(data: GameData | None = None, *, allow_art_fetch: bool = True) -> FastAPI:
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
    game_data = data if data is not None else default_registry()
    app.state.sessions = SessionRegistry(game_data)

    # Both are optional. A fresh clone that has not run the build script must
    # still deal a game -- it simply renders text frames, which is what the
    # client did before any of this existed.
    app.state.card_index = load_index()
    app.state.art = build_store(
        game_data.registry, app.state.card_index, allow_fetch=allow_art_fetch
    )

    app.include_router(router)
    app.include_router(art_router)

    @app.get("/health")
    def health() -> dict:
        registry = app.state.sessions
        index = app.state.card_index
        return {
            "status": "ok",
            "version": __version__,
            "cards": len(registry.data.registry),
            "decks": sorted(registry.data.decks),
            "games": len(registry),
            # Which bulk dump the committed index came from, so "is our art
            # stale" is answerable without opening the database.
            # `rows` last so the live count wins over the build-time note.
            "catalog": (None if index is None else {**index.meta(), "rows": len(index)}),
            "art": {
                "cached": len(app.state.art.cached_ids()),
                "known": len(app.state.art.images),
                "artless": sum(
                    1 for a in app.state.art.images.values() if not a.has_printing
                ),
            },
        }

    return app


app = None


def get_app() -> FastAPI:
    """Lazily built module-level app, for ``uvicorn automtg.server.app:get_app``."""
    global app
    if app is None:
        app = create_app()
    return app

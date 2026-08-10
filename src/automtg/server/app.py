"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from automtg import __version__
from automtg.cards.images import load_index
from automtg.cards.registry import GameData, server_registry

from .art import build_store
from .lobby import PodRegistry
from .pod_routes import router as pod_router
from .routes import art_router, router
from .sessions import SessionRegistry

#: The Vite dev server and any local preview build.
LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

#: Pods are played across a room, so the client is served to the other players'
#: machines and its origin is a LAN address nobody can enumerate in advance.
#: A regex over the private ranges rather than ``*``: this stays an app you can
#: only reach from a network you are already on.
LAN_ORIGIN_RE = (
    r"^http://("
    r"localhost|127\.0\.0\.1"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r")(:\d+)?$"
)


def create_app(data: GameData | None = None, *, allow_art_fetch: bool = True) -> FastAPI:
    app = FastAPI(
        title="Auto MTG",
        version=__version__,
        description="A Magic: The Gathering Commander engine, exposed for a local playtest client.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=LOCAL_ORIGINS,
        allow_origin_regex=LAN_ORIGIN_RE,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # `server_registry` rather than `default_registry`: the server is the one
    # caller that should see imported decks. Everything else -- tests, the
    # trainer, the arena -- stays on the authored layer.
    pinned = data is not None
    game_data = data if pinned else server_registry()
    app.state.sessions = SessionRegistry(game_data)
    # Handed the session registry rather than the GameData: a pod must read
    # decks through `sessions.data` so an imported deck shows up in the lobby
    # the moment `reload()` rebinds it.
    app.state.pods = PodRegistry(app.state.sessions)

    # Both are optional. A fresh clone that has not run the build script must
    # still deal a game -- it simply renders text frames, which is what the
    # client did before any of this existed.
    app.state.card_index = load_index()
    app.state.art = build_store(
        game_data.registry, app.state.card_index, allow_fetch=allow_art_fetch
    )

    def reload() -> None:
        """Pick up cards and decks that an import just wrote to disk.

        Clearing the ``lru_cache`` is not sufficient: ``SessionRegistry`` holds
        the ``GameData`` it was constructed with, so the new one has to be
        rebound onto it.  That rebinding is a single attribute assignment and so
        atomic under the GIL -- a concurrent reader sees the old registry or the
        new one, never a half-built one.  Games already in progress keep their
        own reference and are deliberately untouched: swapping the card pool
        under a running game is not a refresh, it is a corruption.
        """
        if pinned:
            # An explicitly-passed GameData is a test fixture or a script's
            # curated pool.  Reloading would silently replace it with whatever
            # is on disk, which is the opposite of what pinning asked for.
            return
        server_registry.cache_clear()
        fresh = server_registry()
        app.state.sessions.data = fresh
        app.state.art.reload(fresh.registry, app.state.card_index)

    app.state.reload = reload

    app.include_router(router)
    app.include_router(pod_router)
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
            "pods": len(app.state.pods),
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

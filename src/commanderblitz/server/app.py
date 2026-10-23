"""FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from commanderblitz import __version__
from commanderblitz.cards.images import load_index
from commanderblitz.cards.registry import GameData, generated_dir, server_registry

from .art import build_store
from .connectivity import RemoteProbe
from .lobby import PodRegistry
from .persist import session_store
from .pod_routes import router as pod_router
from .routes import art_router, router
from .sessions import SessionRegistry
from .settings import ServerSettings, settings_from_env

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

#: Where ``npm run build`` leaves the client, when this is a checkout.  Under a
#: site-packages install that walk lands nowhere, which is why ``client_dir``
#: and ``COMMANDERBLITZ_CLIENT_DIR`` exist -- the default is a convenience, not a rule.
CLIENT_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"

#: First segments the SPA fallback must never answer for.  A mistyped ``/api``
#: path has to stay a 404 the client can read, not an HTML document it will try
#: to ``JSON.parse`` and report as a syntax error three layers away from here.
SERVER_PREFIXES = frozenset(
    {"api", "art", "health", "docs", "redoc", "openapi.json"}
)


def _serve_client(app: FastAPI, root: Path) -> None:
    """Serve the built client, and every client route, from ``root``.

    The client is a single page with real addresses -- ``/pods/GYRE-8412``,
    ``/games/abc`` -- and nothing on disk sits at those paths.  So anything that
    is not a file and not the server's own is answered with ``index.html``, and
    react-router picks the screen once it is running.  Vite does this for
    ``dev`` and ``preview`` already; this is the same rule for a real deployment.

    Registered last, after every router, so it can only ever see a path that
    nothing else claimed.  ``GET`` only, so a ``POST`` to a typo stays a 405
    rather than being handed a document.
    """
    index = root / "index.html"
    base = root.resolve()

    @app.get("/{client_path:path}", include_in_schema=False)
    def client(client_path: str) -> FileResponse:
        if client_path.split("/", 1)[0] in SERVER_PREFIXES:
            raise HTTPException(status_code=404, detail="not found")
        target = (root / client_path).resolve()
        # One rule covers the hashed bundles, the mana symbols and the favicon:
        # a real file inside `dist` is served as itself.  `is_relative_to` is
        # the traversal guard -- a `..` resolves out of the directory and so
        # stops being a candidate before it is ever opened.
        if client_path and target.is_file() and target.is_relative_to(base):
            return FileResponse(target)
        # The document must not be cached: its whole job is to name the current
        # hashed bundles, and a stale one names bundles that no longer exist.
        return FileResponse(index, headers={"Cache-Control": "no-store"})


def create_app(
    data: GameData | None = None,
    *,
    allow_art_fetch: bool = True,
    serve_client: bool = False,
    client_dir: Path | None = None,
    settings: ServerSettings | None = None,
    probe: RemoteProbe | None = None,
    sessions_dir: Path | None = None,
) -> FastAPI:
    # Hosted unless told otherwise.  Every existing caller -- the tests, the
    # Docker image, the scripts -- passes nothing and gets the server it had.
    settings = settings or ServerSettings()
    app = FastAPI(
        title="Commander Blitz",
        version=__version__,
        description="A Magic: The Gathering Commander engine, and the client that plays it.",
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
    app.state.settings = settings
    # The probe is what `/api/config` means by "online".  Injectable so a test
    # can be offline without unplugging anything.
    app.state.probe = probe or RemoteProbe(settings.remote_origin)
    # Games and pods on disk only when asked (ADR 0023): the deployment entry
    # points pass a directory, and an app a test builds stays in memory unless
    # the test is about surviving a restart.
    games, pods = session_store(sessions_dir) if sessions_dir else (None, None)
    app.state.sessions = SessionRegistry(game_data, games)
    # Handed the session registry rather than the GameData: a pod must read
    # decks through `sessions.data` so an imported deck shows up in the lobby
    # the moment `reload()` rebinds it.
    app.state.pods = PodRegistry(app.state.sessions, pods)

    # Both are optional. A fresh clone that has not run the build script must
    # still deal a game -- it simply renders text frames, which is what the
    # client did before any of this existed.
    app.state.card_index = load_index()
    # A sidecar's lazy fill asks the site's art store before Scryfall
    # (ADR 0021); the site itself has nobody to ask.
    app.state.art = build_store(
        game_data.registry,
        app.state.card_index,
        allow_fetch=allow_art_fetch,
        upstream=settings.remote_origin if settings.mode == "desktop" else None,
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
                # How far the crawl has got and when it last ran, as it left
                # them, and how often this process still went to the lazy fill.
                "store": {
                    **app.state.art.store_state,
                    "fell_through": app.state.art.fell_through,
                },
            },
        }

    # Last, so the catch-all only sees what nothing else claimed.  Opt-in rather
    # than "on whenever `dist` happens to exist": a route table that depends on
    # whether somebody has run `npm run build` is one that behaves differently
    # on two machines, and `create_app` is called directly by the test suite.
    if serve_client:
        root = client_dir or Path(os.environ.get("COMMANDERBLITZ_CLIENT_DIR", CLIENT_DIR))
        if (root / "index.html").is_file():
            _serve_client(app, root)

    return app


app = None


def get_app() -> FastAPI:
    """Lazily built module-level app, for ``uvicorn commanderblitz.server.app:get_app``.

    Serves the built client too, because this is the entry point a deployment
    uses -- one process on one origin, so a deep link resolves without a second
    server in front of it.  A checkout with no ``frontend/dist`` simply has no
    such route, and Vite goes on serving the client in development.
    """
    global app
    if app is None:
        app = create_app(
            serve_client=True,
            settings=settings_from_env(),
            sessions_dir=generated_dir() / "sessions",
        )
    return app

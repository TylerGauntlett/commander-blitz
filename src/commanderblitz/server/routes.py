"""HTTP routes.

The client never reconstructs an action: it receives a list of
:class:`~commanderblitz.server.schemas.LegalActionDTO` with opaque ids and echoes one id
back.  Desync between client and engine is therefore structurally impossible, and
the whole rules vocabulary can grow without touching the frontend.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse

from commanderblitz import __version__
from commanderblitz.cards import importer, moxfield
from commanderblitz.cards.bundle import adopt_bundle, build_bundle
from commanderblitz.cards.images import CardIndex, IndexEntry
from commanderblitz.engine.errors import IllegalActionError
from commanderblitz.engine.serialize import event_log, event_log_for, full_view, player_view

from .art import ArtStore, deck_art_requests, spread_across_faces, with_other_faces
from .deckinfo import deck_detail, deck_summary
from .schemas import (
    AppConfig,
    ApplyActionRequest,
    ArtPrefetchDTO,
    CardResponse,
    CatalogCardDTO,
    CatalogResponse,
    ChooseRequest,
    DeckBundle,
    DeckCompletionDTO,
    DeckDetail,
    DeckImportResponse,
    DeckSummary,
    DeclareRequest,
    GameCreatedResponse,
    ImageRefDTO,
    ImagesResponse,
    ImportDeckRequest,
    ImportedCardDTO,
    NewGameRequest,
    OptionsRequest,
    StateResponse,
)
from .sessions import MAX_POLL_SECONDS, GameSession, SessionRegistry, StaleActionError
from .upstream import Site, SiteUnavailable

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)

#: An import failure is not one status code.  "Private" sends somebody to their
#: Moxfield settings and "not found" sends them back to the address bar, so
#: collapsing them into a single 400 sends them to neither.
_IMPORT_STATUS = {
    "bad_url": 400,
    "private": 403,
    "not_found": 404,
    "unreachable": 502,
    "no_catalog": 503,
}

#: Who is asking, for the purposes of "my decks".
#:
#: There are no accounts here -- the only other identity in the server is a pod
#: token, which is scoped to one lobby and gone when it ends.  So a client mints
#: a random id once into its own ``localStorage`` and sends it on every request,
#: and that id is the whole of ownership: an import stamps it on the deck, the
#: catalogue filters on it, and delete checks it.
#:
#: A header rather than a cookie, for the reason ``pod_routes._TOKEN`` gives:
#: CORS here is ``allow_credentials=False`` by design.  ``None`` is an ordinary
#: state, not an error -- the CLI, ``curl`` and a browser with storage disabled
#: all get the shared view.
_LIBRARY = Header(None, alias="X-Library-Id")

#: Art is served from the app root rather than under ``/api`` so it reads as a
#: static asset to the browser, the dev proxy and any future cache in front.
art_router = APIRouter()


def _registry(request: Request) -> SessionRegistry:
    return request.app.state.sessions


def _art(request: Request) -> ArtStore:
    return request.app.state.art


def _index(request: Request) -> CardIndex:
    index = getattr(request.app.state, "card_index", None)
    if index is None:
        raise HTTPException(
            status_code=503,
            detail="no card catalog; run scripts/build_card_index.py",
        )
    return index


def _session(request: Request, game_id: str) -> GameSession:
    try:
        return _registry(request).get(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no game {game_id}") from None


def _state_response(session: GameSession, seat: int, since: int = 0) -> StateResponse:
    with session._lock:
        state = session.game.state
        return StateResponse(
            state=player_view(state, seat),
            actions=session.actions_for(seat),
            events=event_log_for(state, seat, since),
            event_cursor=len(state.events),
            version=session.version,
            your_seat=seat,
            human_seats=session.human_seats,
        )


# ----------------------------------------------------------------------
# static data
# ----------------------------------------------------------------------


@router.get("/config", response_model=AppConfig)
def app_config(request: Request) -> AppConfig:
    """Which server this is, and whether the hosted one can be reached.

    Cheap to poll: the probe behind ``online`` remembers its answer for
    ``connectivity.PROBE_TTL`` seconds, so the client's periodic refetch is
    one outbound request a half-minute, not one per poll.
    """
    settings = request.app.state.settings
    return AppConfig(
        mode=settings.mode,
        online=request.app.state.probe.online(),
        remote_origin=settings.remote_origin,
        app_version=__version__,
        content_version=settings.content_version,
    )


def _visible_to(deck, library: str | None) -> bool:
    """Precons are everyone's, ownerless imports are everyone's, yours are yours."""
    return deck.source != "moxfield" or not deck.owner or deck.owner == library


@router.get("/decks", response_model=list[DeckSummary])
def list_decks(request: Request, library: str | None = _LIBRARY) -> list[DeckSummary]:
    """Every deck this caller is entitled to see.

    Filtered here rather than in ``GameData``, which stays whole: a pod seat
    holding a teammate's deck must still resolve its id when the table is dealt.
    Hiding somebody else's import from the *rack* is the point; making it
    unplayable is not.
    """
    data = _registry(request).data
    return [
        deck_summary(deck, data)
        for deck in data.decks.values()
        if _visible_to(deck, library)
    ]


@router.get("/decks/{deck_id}", response_model=DeckDetail)
def get_deck(request: Request, deck_id: str) -> DeckDetail:
    """One deck, with the dossier's essays and derived numbers."""
    data = _registry(request).data
    deck = data.decks.get(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail=f"no deck {deck_id}")
    return deck_detail(deck, data, _art(request))


@router.post("/decks/import", response_model=DeckImportResponse, status_code=201)
def import_deck(
    request: Request, body: ImportDeckRequest, library: str | None = _LIBRARY
) -> DeckImportResponse:
    """Import a public Moxfield deck.

    Cards the engine already implements are reused whole; the rest are generated
    with their rules text inert, and the response says exactly how many of each.
    On success the deck is a ``deck_id`` like any other, so starting a game with
    it goes through ``POST /api/games`` unchanged.
    """
    settings = request.app.state.settings
    # The desktop build marks its import incomplete until the art is in: an
    # interrupted prefetch then leaves a deck that says so (ADR 0022).
    complete = False if settings.eager_art and not body.dry_run else None
    try:
        report = None
        if settings.mode == "desktop" and settings.remote_origin and not body.dry_run:
            report = _import_through_site(request, body.url, library, complete)
        if report is None:
            report = importer.import_deck(
                moxfield.load(body.url),
                # The *authored* layer, deliberately. Handed the server's merged
                # registry, a re-import would find the proxies the first import
                # wrote and report them as hand-written cards.
                importer.authored_layer(),
                getattr(request.app.state, "card_index", None),
                dry_run=body.dry_run,
                owner=library or "",
                complete=complete,
            )
    except moxfield.ImportFailed as exc:
        raise HTTPException(
            status_code=_IMPORT_STATUS.get(exc.code, 422),
            detail={"detail": exc.message, "code": exc.code},
        ) from None

    if not body.dry_run:
        # Picks up the files the import just wrote.  Without this the deck is on
        # disk and invisible until somebody restarts the server.
        request.app.state.reload()

    data = _registry(request).data
    deck = data.decks.get(report.deck_id)
    prefetch = None
    if deck is not None and settings.eager_art:
        # The desktop asks for this: the next launch may be offline, and the
        # lazy fill would leave the deck a grid of grey plates until then.
        prefetch = _finish_art(request, deck)
        data = _registry(request).data
        deck = data.decks.get(report.deck_id)
    summary = (
        deck_summary(deck, data)
        if deck is not None
        else DeckSummary(
            id=report.deck_id,
            name=report.deck_name,
            commanders=[],
            commander_names=[],
            color_identity=[],
            card_count=report.total,
            source="moxfield",
            playable=report.playable,
            simplified=report.simplified,
        )
    )
    return DeckImportResponse(
        deck=summary,
        source_id=report.source_id,
        total=report.total,
        playable=report.playable,
        simplified=report.simplified,
        lands=report.lands,
        lands_producing_mana=report.lands_producing_mana,
        lands_inert=report.lands_inert,
        cards=[
            ImportedCardDTO(
                name=c.name, qty=c.qty, card_id=c.card_id,
                origin=c.origin, notes=list(c.notes),
            )
            for c in report.cards
        ],
        problems=report.problems,
        art_prefetch=prefetch,
    )


def _import_through_site(request: Request, url: str, library: str | None, complete):
    """The sidecar's import, done by the site and adopted here, or ``None``
    when the site could not be asked and Moxfield should be read directly."""
    try:
        report, bundle = Site(request.app.state.settings.remote_origin).import_deck(url, library)
    except SiteUnavailable as exc:
        log.info("import through the site failed, reading Moxfield directly: %s", exc)
        return None
    return adopt_bundle(
        bundle,
        importer.authored_layer(),
        getattr(request.app.state, "card_index", None),
        owner=library or "",
        complete=complete,
        problems=report.get("problems") or (),
    )


def _finish_art(request: Request, deck) -> ArtPrefetchDTO:
    """Fetch what ``deck`` is missing and record the verdict in its file.

    `data.registry`, not the authored layer -- the deck's proxies and their
    faces live only in the merged pool.  Reloads when the verdict changed, so
    the next deck list says what the file says.
    """
    data = _registry(request).data
    art = _art(request)
    wanted = deck_art_requests(deck, data.registry, art)
    found = art.prefetch(wanted)
    missing = art.missing(wanted)
    complete = not missing
    if deck.complete is not complete and importer.mark_complete(deck.id, complete):
        request.app.state.reload()
    return ArtPrefetchDTO(
        fetched=found.fetched,
        cached=found.cached,
        failed=found.failed,
        complete=complete,
        missing=missing,
    )


@router.post("/decks/complete", response_model=list[DeckCompletionDTO])
def complete_decks(request: Request, library: str | None = _LIBRARY) -> list[DeckCompletionDTO]:
    """Finish every imported deck whose art is not all on this machine.

    The desktop door calls this before it draws, whenever the site answers: a
    deck an earlier import left half fetched -- the app closed, the network
    dropped -- is finished here, and one already complete costs nothing.  A
    deck that has never been checked (``complete`` absent) is checked once.
    Failures from earlier in this process are retried, not remembered.
    """
    if not request.app.state.settings.eager_art:
        return []
    _art(request).forget_misses()
    out: list[DeckCompletionDTO] = []
    for deck in list(_registry(request).data.decks.values()):
        if deck.source != "moxfield" or deck.complete or not _visible_to(deck, library):
            continue
        verdict = _finish_art(request, deck)
        out.append(
            DeckCompletionDTO(
                deck_id=deck.id,
                fetched=verdict.fetched,
                complete=verdict.complete,
                missing=verdict.missing,
            )
        )
    return out


@router.get("/decks/{deck_id}/bundle", response_model=DeckBundle)
def get_bundle(request: Request, deck_id: str, library: str | None = _LIBRARY) -> DeckBundle:
    """An imported deck with every card definition behind it (ADR 0022).

    What a desktop build fetches after asking the site to import a deck, so
    the deck plays on the device with the site's rules for every card.  Only
    imports have one; a precon ships with every build.
    """
    data = _registry(request).data
    deck = data.decks.get(deck_id)
    if deck is None or deck.source != "moxfield":
        raise HTTPException(status_code=404, detail=f"no imported deck {deck_id}")
    if not _visible_to(deck, library):
        raise HTTPException(status_code=403, detail=f"{deck_id} belongs to another library")
    try:
        return DeckBundle(**build_bundle(deck, data.registry, _art(request).images))
    except LookupError:
        raise HTTPException(status_code=404, detail=f"no imported deck {deck_id}") from None


@router.delete("/decks/{deck_id}", status_code=204)
def delete_deck(request: Request, deck_id: str, library: str | None = _LIBRARY) -> None:
    """Remove an imported deck.  Precons are not deletable, and neither is
    somebody else's import."""
    data = _registry(request).data
    deck = data.decks.get(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail=f"no deck {deck_id}")
    # Before the ownership check, deliberately: a precon belongs to nobody, and
    # "that is not yours" is the wrong answer to "why can I not delete Aesi".
    if deck.source != "moxfield":
        raise HTTPException(status_code=400, detail=f"{deck_id} ships with the engine")
    if deck.owner and deck.owner != library:
        raise HTTPException(status_code=403, detail=f"{deck_id} belongs to another library")
    importer.delete_deck(deck_id)
    request.app.state.reload()


@router.get("/cards/{card_id}", response_model=CardResponse)
def get_card(request: Request, card_id: str) -> CardResponse:
    registry = _registry(request).data.registry
    if card_id not in registry:
        raise HTTPException(status_code=404, detail=f"no card {card_id}")
    card = registry.get(card_id)
    art = _art(request)
    return CardResponse(
        id=card.id,
        name=card.name,
        type_line=card.type_line,
        mana_cost=str(card.mana_cost),
        mana_value=card.mana_value,
        oracle_text=card.oracle_text,
        power=card.power,
        toughness=card.toughness,
        keywords=sorted(card.keywords),
        colors=sorted(card.colors),
        color_identity=sorted(card.color_identity),
        art_url=art.url_for(card.id),
        artist=art.artist_for(card.id),
    )


@router.get("/images", response_model=ImagesResponse)
def list_images(request: Request, game_id: str | None = Query(None)) -> ImagesResponse:
    """Card art locations, in one cacheable response.

    Static for the life of the process, so the client fetches it once rather
    than receiving it inside every state poll.  A ``null`` value is meaningful:
    that card has no printing anywhere and the client should draw its "no art"
    plate rather than request an image that will 404.

    ``?game_id=`` narrows it to the cards reachable from that game's decks.
    Unscoped this was ~17 KB for the two precons; with imported decks in the
    registry it grows without bound, and no game needs more than its own ~200
    cards.  The unscoped form is kept byte-identical -- scripts depend on it, and
    "every card the engine has" is a genuinely different question.
    """
    art = _art(request)
    registry = _registry(request).data.registry
    seats: dict[str, dict[str, ImageRefDTO]] = {}
    if game_id is not None:
        session = _session(request, game_id)
        wanted = sorted(_wanted_ids(session, registry))
        for pid, seat in enumerate(session.seats):
            overrides = _seat_overrides(session.data.deck(seat.deck_id), registry, art)
            if overrides:
                seats[str(pid)] = overrides
    else:
        wanted = registry.ids()
    images: dict[str, ImageRefDTO | None] = {}
    for card_id in wanted:
        url = art.url_for(card_id)
        images[card_id] = (
            None
            if url is None
            else ImageRefDTO(card_id=card_id, art=url, artist=art.artist_for(card_id))
        )
    return ImagesResponse(images=images, seats=seats)


def _seat_overrides(deck, registry, art) -> dict[str, ImageRefDTO]:
    """The cards this deck prints differently from the catalog's pick.

    Only the differences: a deck that happens to agree with the catalog adds
    nothing here, which keeps its cards on the bytes this repository already
    ships instead of sending the client to a second URL for the same picture.

    The artist is the deck's own or nothing.  The catalog keeps one row per card
    name and essentially never the row the author picked, so there is nothing to
    look up -- and the base card's illustrator is a *false* credit on someone
    else's painting, which is worse than no credit at all.
    """
    overrides: dict[str, ImageRefDTO] = {}
    for card_id, printing in spread_across_faces(deck.printings, registry, art).items():
        url = art.url_for(card_id, printing=printing.get("scryfall_id"))
        if url is None or "?p=" not in url:
            continue
        overrides[card_id] = ImageRefDTO(
            card_id=card_id, art=url, artist=printing.get("artist") or None
        )
    return overrides


def _wanted_ids(session: GameSession, registry) -> set[str]:
    """Every card that can appear in this game.

    The seats' decks, plus every token they can make -- a token is never in a
    deck list but is very much on the board, and missing one is a blank plate
    the first time somebody attacks.  And every other face of those cards,
    for the reason ``art.with_other_faces`` gives.
    """
    ids: set[str] = set()
    for seat in session.seats:
        ids |= session.data.deck(seat.deck_id).unique_ids()
    for card in registry:
        if card.is_token:
            ids.add(card.id)
    return with_other_faces(ids, registry)


# ----------------------------------------------------------------------
# catalog
# ----------------------------------------------------------------------


def _catalog_dto(entry: IndexEntry) -> CatalogCardDTO:
    return CatalogCardDTO(
        name=entry.name,
        scryfall_id=entry.scryfall_id,
        oracle_id=entry.oracle_id,
        type_line=entry.type_line,
        mana_cost=entry.mana_cost,
        cmc=entry.cmc,
        power=entry.power,
        toughness=entry.toughness,
        colors=list(entry.colors),
        color_identity=list(entry.color_identity),
        rarity=entry.rarity,
        set_code=entry.set_code,
        layout=entry.layout,
        is_token=entry.is_token,
        artist=entry.artist,
        # Keyed on the Scryfall uuid, not a slug of the name: slugs are not
        # reversible, and `/art` has to be able to work out what to fetch. The
        # lazy fill is what makes this path work on first hover.
        art_url=f"/art/{entry.scryfall_id}.jpg",
    )


@router.get("/catalog", response_model=CatalogResponse)
def search_catalog(
    request: Request,
    q: str = Query("", max_length=80),
    colors: str | None = Query(None, pattern=r"^[WUBRGCwubrgc]{1,6}$"),
    types: str | None = Query(None, max_length=40),
    limit: int = Query(50, ge=1, le=200),
) -> CatalogResponse:
    """Search the Scryfall-derived catalog.

    This is a *reference* surface, not a playable one -- the engine can only
    play the cards in ``data/cards/``.  ``limit`` is capped server-side so a
    client cannot ask for all 33k rows in one response.
    """
    index = _index(request)
    total, results = index.search(q, colors=colors, types=types, limit=limit)
    return CatalogResponse(total=total, results=[_catalog_dto(e) for e in results])


@router.get("/catalog/{scryfall_id}", response_model=CatalogCardDTO)
def get_catalog_card(request: Request, scryfall_id: str) -> CatalogCardDTO:
    index = _index(request)
    entry = index.by_scryfall_id(scryfall_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"no catalog card {scryfall_id}")
    return _catalog_dto(entry)


# ----------------------------------------------------------------------
# art
# ----------------------------------------------------------------------


@art_router.get("/art/{filename}")
def get_art(
    request: Request, filename: str, p: str | None = Query(None)
) -> FileResponse:
    """One card's art, from disk.

    ``FileResponse`` gives ETag, Last-Modified and range handling for free,
    which is why this is a route rather than a ``StaticFiles`` mount -- the
    mount could not also do the lazy fill below.

    ``?p=`` is a deck's chosen printing.  It is validated as a Scryfall uuid
    before it reaches the filesystem, and an unusable one is ignored rather than
    fatal -- the card falls back to its own art, so a stale printing id costs
    the right illustration, never the card.
    """
    if not filename.endswith(".jpg"):
        raise HTTPException(status_code=404, detail="not an image")
    card_id = filename[: -len(".jpg")]
    path = _art(request).resolve(card_id, printing=p)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no art for {card_id}")
    return FileResponse(path, media_type="image/jpeg")


# ----------------------------------------------------------------------
# games
# ----------------------------------------------------------------------


@router.post("/games", response_model=GameCreatedResponse, status_code=201)
def new_game(request: Request, body: NewGameRequest) -> GameCreatedResponse:
    registry = _registry(request)
    for seat in body.seats:
        if seat.deck_id not in registry.data.decks:
            raise HTTPException(status_code=400, detail=f"unknown deck {seat.deck_id!r}")
    session = registry.create(body.seats, seed=body.seed, max_turns=body.max_turns)
    seat = session.primary_seat
    return GameCreatedResponse(
        game_id=session.game_id,
        your_seat=seat,
        state=player_view(session.game.state, seat),
        actions=session.actions_for(seat),
        version=session.version,
    )


@router.get("/games/{game_id}/state", response_model=StateResponse)
def get_state(
    request: Request,
    game_id: str,
    seat: int | None = Query(None, description="Omit to be told your seat by your token."),
    since: int = Query(0, description="Event cursor -- events before this are omitted."),
    since_version: int = Query(
        0,
        ge=0,
        description="Block until the session's version passes this, or the poll ages out.",
    ),
    timeout: float = Query(MAX_POLL_SECONDS, ge=0, le=MAX_POLL_SECONDS),
) -> StateResponse:
    """This seat's view of the game, optionally waiting for it to change.

    ``since`` and ``since_version`` are different cursors and both are useful at
    once: the first says which events you have already rendered (the
    ``event_cursor`` of the last response you absorbed), the second says
    which *state* you have already seen.  With ``since_version`` omitted this is
    the immediate read it has always been; with it, the request blocks until
    another player moves, which is how a second human learns it is their turn
    without polling in a loop.
    """
    session = _session(request, game_id)
    seat = _resolve_seat(request, session, seat)
    _authorise(request, session, seat)
    if since_version:
        session.wait_for_change(since_version, timeout)
    return _state_response(session, seat, since)


@router.get("/games/{game_id}/actions")
def get_actions(request: Request, game_id: str, seat: int = Query(0)):
    session = _session(request, game_id)
    _authorise(request, session, seat)
    return session.actions_for(seat)


#: ``?ai_steps=N`` bounds how many AI decisions a call resolves.  Omitted, the
#: server runs the opponents all the way to the next human decision -- which is
#: right for a script but collapses whole turns into one response.  A client
#: that animates those turns passes 1 and polls.
_AI_STEPS = Query(
    None,
    ge=1,
    description="Resolve at most this many AI decisions; omit to run to the next human turn.",
)


@router.post("/games/{game_id}/actions", response_model=StateResponse)
def apply_action(
    request: Request,
    game_id: str,
    body: ApplyActionRequest,
    ai_steps: int | None = _AI_STEPS,
) -> StateResponse:
    session = _session(request, game_id)
    _authorise(request, session, body.seat)
    # The cursor, the mutation and the reply under one lock: read outside it,
    # a second client's mutation could land in between and this reply would
    # carry that client's events as well as its own -- or none of its own.
    with session._lock:
        since = len(session.game.state.events)
        try:
            session.apply_action_id(
                body.seat, body.action_id, version=body.version, ai_steps=ai_steps
            )
        except StaleActionError as exc:
            # Not the player's mistake: they clicked a list the game had already
            # moved past (a double click, a click racing its own response).  A
            # 409 with a code, so the client can quietly fetch the current list
            # instead of toasting an error about an id nobody chose to type.
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "stale_action",
                    "detail": str(exc),
                    "version": session.version,
                },
            ) from None
        except IllegalActionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return _state_response(session, body.seat, since)


@router.post("/games/{game_id}/declare", response_model=StateResponse)
def declare(
    request: Request,
    game_id: str,
    body: DeclareRequest,
    ai_steps: int | None = _AI_STEPS,
) -> StateResponse:
    session = _session(request, game_id)
    _authorise(request, session, body.seat)
    with session._lock:
        since = len(session.game.state.events)
        try:
            session.declare(body.seat, body.kind, body.pairs, ai_steps=ai_steps)
        except IllegalActionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return _state_response(session, body.seat, since)


@router.post("/games/{game_id}/choose", response_model=StateResponse)
def choose(
    request: Request,
    game_id: str,
    body: ChooseRequest,
    ai_steps: int | None = _AI_STEPS,
) -> StateResponse:
    session = _session(request, game_id)
    _authorise(request, session, body.seat)
    with session._lock:
        since = len(session.game.state.events)
        try:
            session.choose(body.seat, body.choices, ai_steps=ai_steps)
        except IllegalActionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return _state_response(session, body.seat, since)


@router.post("/games/{game_id}/advance", response_model=StateResponse)
def advance(
    request: Request,
    game_id: str,
    seat: int = Body(0, embed=True),
    ai_steps: int | None = _AI_STEPS,
) -> StateResponse:
    """Let the AI seats act.

    With ``ai_steps`` omitted this is normally unnecessary -- applying an action
    already drives the AI.  With ``ai_steps=1`` it becomes the client's
    "advance the opponents by one decision" pump, so their turns can be watched
    rather than arriving pre-collapsed.
    """
    session = _session(request, game_id)
    _authorise(request, session, seat)
    with session._lock:
        since = len(session.game.state.events)
        session.drive_ai(ai_steps)
        return _state_response(session, seat, since)


@router.post("/games/{game_id}/options", response_model=StateResponse)
def set_options(request: Request, game_id: str, body: OptionsRequest) -> StateResponse:
    """Change this seat's play settings.

    Turning full control on can open a priority window the engine was about to
    auto-pass, so the response carries the fresh state and action list rather
    than expecting the client to guess.
    """
    session = _session(request, game_id)
    _authorise(request, session, body.seat)
    if body.seat not in session.human_seats:
        # An AI seat has no stops to configure -- it is offered every window
        # already, and pretending otherwise would silently do nothing.
        raise HTTPException(status_code=400, detail=f"seat {body.seat} is not human")
    with session._lock:
        since = len(session.game.state.events)
        session.set_full_control(body.seat, body.full_control)
        if body.manual_mana is not None:
            session.set_manual_mana(body.seat, body.manual_mana)
        return _state_response(session, body.seat, since)


@router.post("/games/{game_id}/undo", response_model=StateResponse)
def undo(request: Request, game_id: str, seat: int = Body(0, embed=True)) -> StateResponse:
    """Rewind this seat's last action.  Single-player only.

    Undo rebuilds the ``Game`` by replaying the tape, which produces a new state
    object with a shorter event log.  A second human is already holding the
    events being rewound and has no way to reconcile them, so this refuses
    rather than silently corrupting the other client's view.
    """
    session = _session(request, game_id)
    _authorise(request, session, seat)
    if session.multiplayer:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "undo is not available with more than one player",
                "code": "multiplayer_undo",
            },
        )
    if not session.undo():
        raise HTTPException(status_code=400, detail="nothing to undo")
    return _state_response(session, seat)


@router.get("/games/{game_id}/events")
def get_events(request: Request, game_id: str, since: int = Query(0)):
    session = _session(request, game_id)
    state = session.game.state
    return {"events": event_log(state, since), "cursor": len(state.events)}


@router.get("/games/{game_id}/debug")
def debug(request: Request, game_id: str):
    """Full state, hidden zones included.  Development only."""
    session = _session(request, game_id)
    return full_view(session.game.state)


@router.delete("/games/{game_id}", status_code=204)
def delete_game(request: Request, game_id: str) -> None:
    _registry(request).delete(game_id)


def _resolve_seat(request: Request, session: GameSession, seat: int | None) -> int:
    """Which seat is the caller asking about?

    A pod compacts its four chairs down to the players who are actually in the
    game, so the seat somebody had in the lobby is generally *not* the seat they
    have at the table.  Rather than make the client work that out, an omitted
    ``?seat=`` means "whichever seat my token holds" -- and falls back to 0 for
    the single-player callers that never had a token.
    """
    if seat is not None:
        return seat
    from_token = session.seat_for_token(request.headers.get("X-Player-Token"))
    return session.primary_seat if from_token is None else from_token


def _authorise(request: Request, session: GameSession, seat: int) -> None:
    """Is the caller allowed to act as this seat?

    Two regimes, chosen by whether the session has a token map.

    A session dealt from a pod has one, and then the ``X-Player-Token`` header
    must resolve to exactly this seat -- otherwise anybody holding a ``game_id``
    could read a rival's hand with ``?seat=1``.

    A session created straight through ``POST /api/games`` has no token map, and
    keeps the bounds-check-only behaviour it has always had.  That is not an
    oversight: the CLI, ``scripts/smoke_http.py``, single-player and every
    existing test drive a game with no token at all, and requiring one would
    break all of them to protect a seat nobody else can reach.
    """
    if not 0 <= seat < len(session.seats):
        raise HTTPException(status_code=400, detail=f"no seat {seat}")
    if not session.tokens:
        return
    token = request.headers.get("X-Player-Token")
    if session.seat_for_token(token) != seat:
        raise HTTPException(
            status_code=403,
            detail={"detail": f"seat {seat} is not yours", "code": "not_your_seat"},
        )
    session.last_seen = time.monotonic()

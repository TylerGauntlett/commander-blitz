"""HTTP routes.

The client never reconstructs an action: it receives a list of
:class:`~automtg.server.schemas.LegalActionDTO` with opaque ids and echoes one id
back.  Desync between client and engine is therefore structurally impossible, and
the whole rules vocabulary can grow without touching the frontend.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse

from automtg.cards.images import CardIndex, IndexEntry
from automtg.engine.errors import IllegalActionError
from automtg.engine.serialize import event_log, full_view, player_view

from .art import ArtStore
from .schemas import (
    ApplyActionRequest,
    CardResponse,
    CatalogCardDTO,
    CatalogResponse,
    DeckSummary,
    DeclareRequest,
    GameCreatedResponse,
    ImageRefDTO,
    ImagesResponse,
    NewGameRequest,
    OptionsRequest,
    StateResponse,
)
from .sessions import GameSession, SessionRegistry

router = APIRouter(prefix="/api")

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
    state = session.game.state
    return StateResponse(
        state=player_view(state, seat),
        actions=session.actions_for(seat),
        events=event_log(state, since),
        event_cursor=len(state.events),
    )


# ----------------------------------------------------------------------
# static data
# ----------------------------------------------------------------------


@router.get("/decks", response_model=list[DeckSummary])
def list_decks(request: Request) -> list[DeckSummary]:
    data = _registry(request).data
    out = []
    for deck in data.decks.values():
        out.append(
            DeckSummary(
                id=deck.id,
                name=deck.name,
                commanders=list(deck.commanders),
                commander_names=[data.registry.get(c).name for c in deck.commanders],
                color_identity=sorted(deck.color_identity),
                card_count=deck.total_cards(),
                notes=deck.notes,
            )
        )
    return out


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
def list_images(request: Request) -> ImagesResponse:
    """Every engine card's art location, in one cacheable response.

    Static for the life of the process, so the client fetches it once at boot
    rather than receiving it inside every state poll.  A ``null`` value is
    meaningful: that card has no printing anywhere and the client should draw
    its "no art" plate rather than request an image that will 404.
    """
    art = _art(request)
    registry = _registry(request).data.registry
    images: dict[str, ImageRefDTO | None] = {}
    for card_id in registry.ids():
        url = art.url_for(card_id)
        images[card_id] = (
            None
            if url is None
            else ImageRefDTO(card_id=card_id, art=url, artist=art.artist_for(card_id))
        )
    return ImagesResponse(images=images)


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
    entry = next((e for e in index.iter_all() if e.scryfall_id == scryfall_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"no catalog card {scryfall_id}")
    return _catalog_dto(entry)


# ----------------------------------------------------------------------
# art
# ----------------------------------------------------------------------


@art_router.get("/art/{filename}")
def get_art(request: Request, filename: str) -> FileResponse:
    """One card's art, from disk.

    ``FileResponse`` gives ETag, Last-Modified and range handling for free,
    which is why this is a route rather than a ``StaticFiles`` mount -- the
    mount could not also do the lazy fill below.
    """
    if not filename.endswith(".jpg"):
        raise HTTPException(status_code=404, detail="not an image")
    card_id = filename[: -len(".jpg")]
    path = _art(request).resolve(card_id)
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
    )


@router.get("/games/{game_id}/state", response_model=StateResponse)
def get_state(
    request: Request, game_id: str, seat: int = Query(0), since: int = Query(0)
) -> StateResponse:
    session = _session(request, game_id)
    _check_seat(session, seat)
    return _state_response(session, seat, since)


@router.get("/games/{game_id}/actions")
def get_actions(request: Request, game_id: str, seat: int = Query(0)):
    session = _session(request, game_id)
    _check_seat(session, seat)
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
    _check_seat(session, body.seat)
    since = len(session.game.state.events)
    try:
        session.apply_action_id(body.seat, body.action_id, ai_steps=ai_steps)
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
    _check_seat(session, body.seat)
    since = len(session.game.state.events)
    try:
        session.declare(body.seat, body.kind, body.pairs, ai_steps=ai_steps)
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
    _check_seat(session, seat)
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
    _check_seat(session, body.seat)
    if body.seat not in session.human_seats:
        # An AI seat has no stops to configure -- it is offered every window
        # already, and pretending otherwise would silently do nothing.
        raise HTTPException(status_code=400, detail=f"seat {body.seat} is not human")
    since = len(session.game.state.events)
    session.set_full_control(body.seat, body.full_control)
    return _state_response(session, body.seat, since)


@router.post("/games/{game_id}/undo", response_model=StateResponse)
def undo(request: Request, game_id: str, seat: int = Body(0, embed=True)) -> StateResponse:
    session = _session(request, game_id)
    _check_seat(session, seat)
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


def _check_seat(session: GameSession, seat: int) -> None:
    if not 0 <= seat < len(session.seats):
        raise HTTPException(status_code=400, detail=f"no seat {seat}")

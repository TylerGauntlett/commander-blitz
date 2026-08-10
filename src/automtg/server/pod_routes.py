"""Pod routes -- everything before the game starts.

Its own module rather than more of ``routes.py``: these share nothing with the
game routes but the app state, and the two halves have genuinely different rules
(a pod authorises by token and blocks on a condition; a game does neither).

Every handler is a plain sync ``def``.  Starlette runs those in a thread pool, so
a long poll parks a pool thread rather than an event loop -- which is what makes
the 25-second block affordable at pod scale and lets ``TestClient`` drive the
whole thing without an async fixture in sight.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from .lobby import MAX_POLL_SECONDS, Pod, PodError, PodRegistry
from .schemas import (
    CreatePodRequest,
    JoinPodRequest,
    PodCredentials,
    PodView,
    SeatAdminRequest,
    SeatUpdateRequest,
    StartPodRequest,
)

router = APIRouter(prefix="/api")

#: A pod failure is not one status code.  "That pod is full" sends somebody back
#: to the home screen to ask for a different code; "that pod already dealt" sends
#: them to the table.  Collapsing them into a single 400 sends them to neither.
_POD_STATUS = {
    "not_found": 404,
    "bad_token": 401,
    "not_host": 403,
    "not_your_seat": 403,
    "pod_full": 409,
    "already_started": 409,
    "not_ready": 409,
    "unknown_deck": 400,
    "pod_closed": 410,
}


def _pods(request: Request) -> PodRegistry:
    return request.app.state.pods


def _http(exc: PodError) -> HTTPException:
    return HTTPException(
        status_code=_POD_STATUS.get(exc.code, 400),
        detail={"detail": exc.message, "code": exc.code, **exc.detail},
    )


def _pod(request: Request, code: str) -> Pod:
    try:
        return _pods(request).get(code)
    except PodError as exc:
        raise _http(exc) from None


def _member(request: Request, code: str, token: str | None) -> tuple[Pod, str]:
    """The pod and the caller's ``player_id``, or 401."""
    pod = _pod(request, code)
    try:
        player = _pods(request).authenticate(pod, token)
    except PodError as exc:
        raise _http(exc) from None
    return pod, player.player_id


#: The pod token travels in a header rather than a cookie: CORS here is
#: ``allow_credentials=False`` by design, so a cookie would not be sent
#: cross-origin from the Vite dev server at all.
_TOKEN = Header(None, alias="X-Player-Token")


@router.post("/pods", response_model=PodCredentials, status_code=201)
def create_pod(request: Request, body: CreatePodRequest) -> PodCredentials:
    """Open a pod and take seat 0.

    The token comes back exactly once, here.  It is the only thing that proves
    a later request is the same person, so a client that loses it has to rejoin.
    """
    try:
        pod, player = _pods(request).create(
            host_name=body.name, deck_id=body.deck_id, seed=body.seed
        )
    except PodError as exc:
        raise _http(exc) from None
    return PodCredentials(player_token=player.token, pod=pod.view_for(player.player_id))


@router.post("/pods/{code}/join", response_model=PodCredentials, status_code=201)
def join_pod(
    request: Request,
    code: str,
    body: JoinPodRequest,
    token: str | None = _TOKEN,
) -> PodCredentials:
    """Take a chair in somebody else's pod.

    Passing a token you already hold is how reconnecting works: it returns the
    seat you already had rather than taking a second one, so a refreshed tab is
    indistinguishable from one that never left.
    """
    try:
        pod, player = _pods(request).join(code, name=body.name, token=token)
    except PodError as exc:
        raise _http(exc) from None
    return PodCredentials(player_token=player.token, pod=pod.view_for(player.player_id))


@router.get("/pods/{code}", response_model=PodView)
def get_pod(
    request: Request,
    code: str,
    since: int = Query(0, ge=0),
    timeout: float = Query(MAX_POLL_SECONDS, ge=0, le=MAX_POLL_SECONDS),
    token: str | None = _TOKEN,
) -> PodView:
    """The pod, optionally waiting for it to change.

    ``since=0`` returns immediately -- that is the first fetch.  Any other value
    blocks until the version passes it or ``timeout`` elapses, and a timeout
    returns the current view with a 200: the client cannot tell a long poll from
    a slow one, which is exactly the point.

    The token is optional.  Without one this is the blind view -- every seat's
    deck hidden unless they locked in -- which is what an invite link renders
    before anybody has joined.
    """
    pods = _pods(request)
    pod = _pod(request, code)
    player_id = None
    if token:
        try:
            player_id = pods.authenticate(pod, token).player_id
        except PodError:
            # A stale token from a swept player still gets to *watch*; it simply
            # sees nothing privileged. Refusing here would turn a reconnect into
            # a dead end instead of a rejoin.
            player_id = None
    pods.wait(pod, since, timeout)
    return pod.view_for(player_id)


@router.patch("/pods/{code}/seat", response_model=PodView)
def update_seat(
    request: Request,
    code: str,
    body: SeatUpdateRequest,
    token: str | None = _TOKEN,
) -> PodView:
    """Your own chair: pick a deck, lock in, unlock."""
    pod, player_id = _member(request, code, token)
    try:
        _pods(request).update_seat(
            pod, player_id, deck_id=body.deck_id, locked=body.locked
        )
    except PodError as exc:
        raise _http(exc) from None
    return pod.view_for(player_id)


@router.patch("/pods/{code}/seats/{index}", response_model=PodView)
def admin_seat(
    request: Request,
    code: str,
    index: int,
    body: SeatAdminRequest,
    token: str | None = _TOKEN,
) -> PodView:
    """A chair that is not yours.  Host only, and never another human's."""
    pod, player_id = _member(request, code, token)
    try:
        _pods(request).admin_seat(
            pod,
            player_id,
            index,
            action=body.action,
            deck_id=body.deck_id,
            agent=body.agent,
        )
    except PodError as exc:
        raise _http(exc) from None
    return pod.view_for(player_id)


@router.post("/pods/{code}/start", response_model=PodView)
def start_pod(
    request: Request,
    code: str,
    body: StartPodRequest | None = None,
    token: str | None = _TOKEN,
) -> PodView:
    """Deal the pod.

    The pod is not deleted: it flips to ``in_game`` and holds the ``game_id``.
    Everybody polling it learns where the table is from the same response, which
    is how four browsers arrive at the game together.

    The body is optional so a bare ``POST`` still deals -- ``smoke_http.py`` and
    anything driving this by hand should not have to send ``{}`` to say nothing.
    """
    pod, player_id = _member(request, code, token)
    try:
        _pods(request).start(pod, player_id, seed=body.seed if body else None)
    except PodError as exc:
        raise _http(exc) from None
    return pod.view_for(player_id)


@router.post("/pods/{code}/leave", status_code=204)
def leave_pod(request: Request, code: str, token: str | None = _TOKEN) -> Response:
    pod, player_id = _member(request, code, token)
    _pods(request).leave(pod, player_id)
    return Response(status_code=204)

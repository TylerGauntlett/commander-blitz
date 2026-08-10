"""Pods -- the pre-game world.

Everything that happens before ``SessionRegistry.create`` gets called: a code
somebody can read down a phone line, four chairs, a token per player, and a
version counter that clients long-poll on.

Three ideas carry the whole module.

**One lock per pod.**  Starlette runs sync handlers in a thread pool, so two
people claiming the last chair really are concurrent.  Every mutation happens
inside ``pod._lock``, and every check that guards a mutation happens inside the
same ``with`` block as the mutation it guards -- checking outside and mutating
inside is the bug this design exists to make impossible.

**One rendering.**  :meth:`Pod.view_for` is the only way a pod reaches the wire,
exactly as ``player_view`` is for a game.  A deck a player has not locked in is
nobody else's business, and a token is nobody's business at all.

**Versioned long-polling.**  Every mutation bumps ``version`` and wakes the
condition.  A client passes the version it last saw and the server blocks until
the number moves or the poll ages out.  No sockets, no reconnection state
machine, and every handler stays a plain sync ``def`` that ``TestClient`` can
drive.  See ``docs/adr/0007-versioned-long-polling.md``.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from .deckinfo import deck_summary
from .schemas import MAX_NAME_LENGTH, DeckSummary, PodSeatView, PodView, SeatConfig

if TYPE_CHECKING:  # pragma: no cover
    from .sessions import GameSession, SessionRegistry

#: Every pod has four chairs whether or not anybody sits in them, so the client
#: can draw the empty ones rather than reflowing the hand as people arrive.
POD_SEATS = 4

#: Longest a long-poll may block.  Comfortably under the 30 s that proxies and
#: browsers treat as a dead connection.
MAX_POLL_SECONDS = 25.0

#: A player who has not made a request in this long has closed their tab.  Long
#: enough to survive a laptop lid and a long poll, short enough that their chair
#: reopens before the rest of the pod gives up on them.
PLAYER_TTL_SECONDS = 90.0

#: An untouched pod is an abandoned one.
POD_TTL_SECONDS = 30 * 60.0

#: A closed pod is kept this long before its code is recycled.  Long enough that
#: the players who were in it -- including anybody with a poll in flight -- are
#: told the pod *closed* rather than that it never existed, which are two very
#: different things to read on a screen.
CLOSED_LINGER_SECONDS = 60.0

SeatKind = Literal["empty", "cpu", "open", "human"]
PodStatus = Literal["open", "starting", "in_game", "closed"]

#: The word half of a pod code.  Short, unambiguous when read aloud, and
#: Magic-flavoured so a code sounds like it belongs to this app.  A module
#: constant rather than a data file: 128 strings do not need a loader, a schema
#: and a test that the loader works.
#:
#: Nothing here is one letter away from anything else here, and nothing spells
#: something unfortunate against a four-digit number.
POD_WORDS = (
    "AGATE", "AMBER", "ANGEL", "ANVIL", "ARBOR", "ARMOR", "ASHES", "AVEN",
    "BASALT", "BEACON", "BLADE", "BLOOM", "BOLT", "BRAMBLE", "BRINE", "BRUSH",
    "CAIRN", "CANDLE", "CAVERN", "CHALICE", "CINDER", "CLIFF", "CLOAK", "COMET",
    "CORAL", "CRAG", "CROWN", "CRYPT", "CURSE", "DAWN", "DELTA", "DRAKE",
    "DRIFT", "DRUID", "DUNE", "DUSK", "EAGLE", "EMBER", "FALCON", "FATHOM",
    "FERAL", "FLINT", "FOREST", "FORGE", "FROST", "GARDEN", "GLADE", "GLYPH",
    "GRAVE", "GROVE", "GYRE", "HARBOR", "HAVEN", "HEARTH", "HOLLOW", "HYDRA",
    "IVORY", "JADE", "KELP", "KNIGHT", "LANTERN", "LEDGE", "LOTUS", "MARSH",
    "MEADOW", "MENTOR", "MIRAGE", "MOSS", "MYSTIC", "NEEDLE", "NEXUS", "NOMAD",
    "OASIS", "OMEN", "ONYX", "ORACLE", "ORCHARD", "OTTER", "PEAK", "PHOENIX",
    "PILGRIM", "PLAINS", "PRISM", "QUARRY", "QUILL", "RAPTOR", "RAVEN", "REEF",
    "RELIC", "RIDGE", "RIVER", "RUNE", "SAGE", "SANCTUM", "SAPLING", "SCEPTER",
    "SCOUT", "SEDGE", "SENTRY", "SERAPH", "SHRINE", "SIGIL", "SILVER", "SKYLARK",
    "SLATE", "SPHINX", "SPIRE", "SPRITE", "STORM", "SUMMIT", "TALON", "TEMPLE",
    "THICKET", "THRONE", "TIDE", "TIMBER", "TITAN", "TOTEM", "TOWER", "TUNDRA",
    "VAULT", "VERGE", "VESPER", "VINE", "WARDEN", "WILLOW", "WISP", "ZEPHYR",
)

_CODE_RE = re.compile(r"^([A-Z]+)-?(\d{4,6})$")


def default_name(seat: int) -> str:
    """What an unnamed chair is called.

    Numbered by seat rather than by role, because "You" is only true for one
    reader: a host who never renames would otherwise have the rest of the pod
    reading "Waiting on You" about somebody else.
    """
    return f"Player {seat + 1}"


def clean_name(raw: str) -> str:
    """Collapse whitespace and cap.  Returns "" if there is nothing left."""
    return " ".join(raw.split())[:MAX_NAME_LENGTH]


class PodError(Exception):
    """A pod rule was broken.

    ``code`` is machine-readable and maps to a status in ``pod_routes``.  The
    client shows a different screen for "that pod is full" than for "that pod
    does not exist", so collapsing them into one 400 helps nobody.
    """

    def __init__(self, code: str, message: str = "", **detail) -> None:
        self.code = code
        self.message = message or code.replace("_", " ")
        self.detail = detail
        super().__init__(self.message)


# ----------------------------------------------------------------------
# codes
# ----------------------------------------------------------------------


def make_code(taken: set[str] | None = None) -> str:
    """``WORD-NNNN``, e.g. ``GYRE-8412``.

    Drawn from ``secrets`` rather than the engine's seeded RNG: a pod code is
    not part of a reproducible game, and ``tests/unit/test_determinism_hygiene``
    polices ``random`` inside the engine for exactly that reason.

    ~128 x 9000 = 1.15M codes.  Collisions only matter against *live* pods, of
    which there will be single digits, so ten tries is generous; the sixth digit
    is there so the function is total rather than as a real fallback.
    """
    taken = taken or set()
    for _ in range(10):
        code = f"{secrets.choice(POD_WORDS)}-{secrets.randbelow(9000) + 1000}"
        if code not in taken:
            return code
    return f"{secrets.choice(POD_WORDS)}-{secrets.randbelow(900000) + 100000}"


def normalise_code(raw: str) -> str:
    """Make a code somebody typed or heard match one the server issued.

    Case, stray whitespace and a missing hyphen are all things that happen when
    a code is read down a phone line, and none of them mean "wrong pod".
    """
    squashed = re.sub(r"[\s_]+", "", (raw or "").strip().upper())
    match = _CODE_RE.match(squashed)
    if match is None:
        return squashed
    return f"{match.group(1)}-{match.group(2)}"


# ----------------------------------------------------------------------
# the pod
# ----------------------------------------------------------------------


@dataclass
class PodSeat:
    kind: SeatKind = "empty"
    #: Humans only, and never rendered for anybody but its owner.
    player_id: str | None = None
    name: str | None = None
    deck_id: str | None = None
    #: A human who pressed "Lock in".  Until then their deck is theirs alone.
    locked: bool = False
    #: CPU seats only.
    agent: str = "heuristic"

    @property
    def ready(self) -> bool:
        """Would the game be waiting on this seat?

        A CPU is ready the moment it is seated -- the host chose its deck, and
        it is not going to change its mind.  An open chair is a chair somebody
        has been invited to and has not taken, so it is never ready; the host
        clears it or fills it with a CPU to deal.
        """
        if self.kind == "cpu":
            return self.deck_id is not None
        if self.kind == "human":
            return self.locked and self.deck_id is not None
        return False

    @property
    def filled(self) -> bool:
        """Would this seat become a player in the game?"""
        return self.kind in ("cpu", "human")

    def vacate(self) -> None:
        self.kind = "empty"
        self.player_id = None
        self.name = None
        self.deck_id = None
        self.locked = False
        self.agent = "heuristic"


@dataclass
class PodPlayer:
    player_id: str
    #: Bearer credential.  Sent to its owner exactly once and never rendered
    #: into a view -- see :meth:`Pod.view_for`.
    token: str
    name: str
    seat: int
    #: ``time.monotonic()`` of this player's last authenticated request.
    last_seen: float = field(default_factory=time.monotonic)


@dataclass
class Pod:
    """One lobby.  Four chairs, a code, and a version counter."""

    code: str
    host_id: str
    created: float = field(default_factory=time.monotonic)
    seats: list[PodSeat] = field(default_factory=lambda: [PodSeat() for _ in range(POD_SEATS)])
    players: dict[str, PodPlayer] = field(default_factory=dict)
    version: int = 1
    status: PodStatus = "open"
    #: ``time.monotonic()`` at which ``status`` became ``closed``.
    closed_at: float | None = None
    game_id: str | None = None
    seed: int | None = None
    #: ``deck_id -> DeckSummary``, injected by the registry.  A callable rather
    #: than a cached dict so an imported deck is visible in the lobby the moment
    #: ``app.state.reload()`` rebinds the registry.
    decks: Callable[[str], DeckSummary | None] | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _changed: threading.Condition = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._changed = threading.Condition(self._lock)

    # -- helpers; all assume the caller holds ``_lock`` --------------------

    def _bump(self) -> None:
        self.version += 1
        self._changed.notify_all()

    def _close(self) -> None:
        self.status = "closed"
        self.closed_at = time.monotonic()

    def seat_of(self, player_id: str | None) -> int | None:
        player = self.players.get(player_id) if player_id else None
        return None if player is None else player.seat

    def is_host(self, player_id: str | None) -> bool:
        return player_id is not None and player_id == self.host_id

    @property
    def humans(self) -> list[PodPlayer]:
        return sorted(self.players.values(), key=lambda p: p.seat)

    @property
    def filled_seats(self) -> list[int]:
        return [i for i, seat in enumerate(self.seats) if seat.filled]

    def free_seat(self) -> int | None:
        """The chair a new arrival takes.

        An ``open`` chair first -- it was deliberately held for somebody -- then
        the first genuinely empty one.
        """
        for want in ("open", "empty"):
            for i, seat in enumerate(self.seats):
                if seat.kind == want:
                    return i
        return None

    # -- rendering ---------------------------------------------------------

    def view_for(self, player_id: str | None) -> PodView:
        """The pod as one viewer is allowed to see it.

        The lobby's hidden-information contract, and the mirror of
        ``serialize.player_view``: another human's deck is invisible until they
        lock in, another human's ``player_id`` is never sent at all, and no
        token appears in any view for anybody.

        A CPU is always fully visible -- the host chose its deck, so there is
        nothing to hide and a face-down CPU would just be confusing.
        """
        with self._lock:
            you = self.seat_of(player_id)
            seats = []
            for index, seat in enumerate(self.seats):
                mine = you is not None and index == you
                revealed = seat.kind == "cpu" or mine or seat.locked
                seats.append(
                    PodSeatView(
                        index=index,
                        kind=seat.kind,
                        name=seat.name,
                        deck=self._deck(seat.deck_id) if revealed else None,
                        locked=seat.locked,
                        ready=seat.ready,
                        is_you=mine,
                        is_host=(
                            seat.player_id is not None and seat.player_id == self.host_id
                        ),
                        agent=seat.agent if seat.kind == "cpu" else None,
                    )
                )
            return PodView(
                code=self.code,
                version=self.version,
                status=self.status,
                seats=seats,
                your_seat=you,
                you_are_host=self.is_host(player_id),
                game_id=self.game_id,
                invite_link=f"/pods/{self.code}",
            )

    def _deck(self, deck_id: str | None) -> DeckSummary | None:
        if deck_id is None or self.decks is None:
            return None
        return self.decks(deck_id)


# ----------------------------------------------------------------------
# the registry
# ----------------------------------------------------------------------


class PodRegistry:
    """All live pods in this process.  The analogue of ``SessionRegistry``."""

    def __init__(self, sessions: SessionRegistry) -> None:
        self.sessions = sessions
        self._pods: dict[str, Pod] = {}
        self._lock = threading.RLock()

    # -- deck lookup, always through the live registry ---------------------

    def _deck_summary(self, deck_id: str):
        """``deck_id -> DeckSummary | None``.

        Reads ``self.sessions.data`` on every call rather than caching it:
        ``app.state.reload()`` rebinds that attribute after a deck import, and a
        cached reference would leave the deck somebody just imported invisible
        in the lobby.
        """
        data = self.sessions.data
        deck = data.decks.get(deck_id)
        return None if deck is None else deck_summary(deck, data)

    def _known_deck(self, deck_id: str) -> None:
        if deck_id not in self.sessions.data.decks:
            raise PodError("unknown_deck", f"unknown deck {deck_id!r}")

    # -- lifecycle ---------------------------------------------------------

    def create(
        self,
        *,
        host_name: str | None = None,
        deck_id: str | None = None,
        seed: int | None = None,
    ) -> tuple[Pod, PodPlayer]:
        self.sweep()
        if deck_id is not None:
            self._known_deck(deck_id)
        host_id = secrets.token_urlsafe(9)
        with self._lock:
            pod = Pod(
                code=make_code(set(self._pods)),
                host_id=host_id,
                seed=seed,
                decks=self._deck_summary,
            )
            self._pods[pod.code] = pod
        player = PodPlayer(
            player_id=host_id,
            token=secrets.token_urlsafe(24),
            name=clean_name(host_name or "") or default_name(0),
            seat=0,
        )
        with pod._lock:
            pod.players[host_id] = player
            pod.seats[0] = PodSeat(
                kind="human", player_id=host_id, name=player.name, deck_id=deck_id
            )
            pod._bump()
        return pod, player

    def get(self, code: str) -> Pod:
        pod = self._pods.get(normalise_code(code))
        if pod is None:
            raise PodError("not_found", f"no pod {normalise_code(code)}")
        return pod

    def join(
        self, code: str, *, name: str | None = None, token: str | None = None
    ) -> tuple[Pod, PodPlayer]:
        """Take a chair, or take back the one you already had.

        Rejoining with a token you already hold is idempotent, which is the
        whole reconnect story: a refreshed tab hands back the token it kept in
        ``sessionStorage`` and lands in the same chair with the same deck.
        """
        self.sweep()
        pod = self.get(code)
        with pod._lock:
            # Status first, even for a token we recognise: a member coming back
            # after the deal is not rejoining the lobby, they are being routed
            # to the table, and ``already_started`` carries the ``game_id`` that
            # gets them there.
            self._require_open(pod)
            existing = self._player_by_token(pod, token) if token else None
            if existing is not None:
                existing.last_seen = time.monotonic()
                return pod, existing
            index = pod.free_seat()
            if index is None:
                raise PodError("pod_full", "that pod is full")

            player_id = secrets.token_urlsafe(9)
            player = PodPlayer(
                player_id=player_id,
                token=secrets.token_urlsafe(24),
                name=clean_name(name or "") or default_name(index),
                seat=index,
            )
            pod.players[player_id] = player
            pod.seats[index] = PodSeat(
                kind="human", player_id=player_id, name=player.name
            )
            pod._bump()
            return pod, player

    @staticmethod
    def _player_by_token(pod: Pod, token: str) -> PodPlayer | None:
        return next((p for p in pod.players.values() if p.token == token), None)

    def authenticate(self, pod: Pod, token: str | None) -> PodPlayer:
        player = self._player_by_token(pod, token) if token else None
        if player is None:
            raise PodError("bad_token", "that token does not belong to this pod")
        player.last_seen = time.monotonic()
        return player

    def wait(self, pod: Pod, since: int, timeout: float = MAX_POLL_SECONDS) -> None:
        """Block until the pod's version passes ``since``, or the poll ages out.

        A timeout is not an error: the caller returns the current view and the
        client immediately re-polls, which keeps a long poll indistinguishable
        from a slow one and costs at most one round trip when a connection
        drops.  ``since=0`` returns immediately -- that is the first fetch.

        ``Condition.wait_for`` releases the pod lock while it blocks, which is
        the single rule that keeps this from deadlocking against a mutation.
        """
        if since <= 0:
            return
        with pod._lock:
            pod._changed.wait_for(
                lambda: pod.version > since, timeout=max(0.0, min(timeout, MAX_POLL_SECONDS))
            )

    # -- seats -------------------------------------------------------------

    def update_seat(
        self,
        pod: Pod,
        player_id: str,
        *,
        deck_id: str | None = None,
        locked: bool | None = None,
        name: str | None = None,
    ) -> None:
        """Your own chair: say who you are, pick a deck, lock in, unlock.

        Renaming is not gated on ``locked`` -- the lock commits a *deck*, and
        the pod is already refused outright once it has dealt, which is the
        gate that matters.
        """
        if deck_id is not None:
            self._known_deck(deck_id)
        with pod._lock:
            self._require_open(pod)
            index = pod.seat_of(player_id)
            if index is None:
                raise PodError("not_your_seat", "you are not in this pod")
            seat = pod.seats[index]
            if name is not None:
                trimmed = clean_name(name)
                if not trimmed:
                    raise PodError("bad_name", "a seat needs a name")
                seat.name = trimmed
                # Two fields, one fact. ``view_for`` and the ``SeatConfig`` built
                # at deal time both read ``seat.name``; ``PodPlayer.name`` is the
                # identity record the seat was seeded from at join. Leaving it
                # stale would leave the pod holding two answers to "who is this",
                # and nothing would ever reconcile them.
                player = pod.players.get(player_id)
                if player is not None:
                    player.name = trimmed
            if deck_id is not None:
                seat.deck_id = deck_id
            if locked is not None:
                if locked and seat.deck_id is None:
                    raise PodError("not_ready", "choose a deck before locking in")
                seat.locked = locked
            if deck_id is not None:
                self._dedupe_cpu_decks(pod)
            pod._bump()

    def admin_seat(
        self,
        pod: Pod,
        player_id: str,
        index: int,
        *,
        action: str,
        deck_id: str | None = None,
        agent: str | None = None,
    ) -> None:
        """A chair that is not yours.  Host only."""
        if deck_id is not None:
            self._known_deck(deck_id)
        with pod._lock:
            self._require_open(pod)
            if not pod.is_host(player_id):
                raise PodError("not_host", "only the host can change that seat")
            if not 0 <= index < POD_SEATS:
                raise PodError("not_found", f"no seat {index}")
            seat = pod.seats[index]
            if seat.kind == "human":
                # Not even the host reaches into somebody else's chair: they
                # chose that deck privately and may not have locked it in yet.
                raise PodError("not_your_seat", f"seat {index} belongs to a player")

            if action == "add_cpu":
                previous_deck = seat.deck_id if seat.kind == "cpu" else None
                seat.kind = "cpu"
                seat.name = f"CPU {index}"
                seat.deck_id = deck_id or previous_deck or self._free_deck(pod)
                seat.agent = agent or seat.agent
                seat.locked = True
            elif action == "open_chair":
                seat.vacate()
                seat.kind = "open"
                seat.name = "Open"
            elif action == "clear":
                seat.vacate()
            elif action == "set_deck":
                if deck_id is None:
                    raise PodError("unknown_deck", "set_deck needs a deck_id")
                if seat.kind != "cpu":
                    raise PodError("not_ready", f"seat {index} has no deck to set")
                seat.deck_id = deck_id
            elif action == "set_agent":
                if seat.kind != "cpu":
                    raise PodError("not_ready", f"seat {index} is not a CPU")
                seat.agent = agent or seat.agent
            else:  # pragma: no cover -- the schema is a Literal
                raise PodError("not_ready", f"unknown action {action!r}")
            pod._bump()

    def _commander_of(self, deck_id: str | None) -> tuple[str, ...]:
        deck = self.sessions.data.decks.get(deck_id) if deck_id else None
        return () if deck is None else tuple(deck.commanders)

    def _free_deck(self, pod: Pod) -> str:
        """A deck nobody at this table is already playing.

        Deterministic, deliberately: a seeded pod has to deal the same game
        twice, and a deck chosen at random would be a source of variation the
        seed does not cover.

        Distinctness is measured by **commander, not deck id**.  Two imported
        lists can share a commander with each other and with a precon -- the
        shipped registry on a machine with imports usually does -- and two seats
        playing the same commander from two different lists is still a mirror
        match, and still renders two identical cards on the table.

        Falls back through "any deck nobody holds" to "the first deck", which
        with four chairs and four shipped decks needs a pod that seats five.
        """
        decks = sorted(self.sessions.data.decks)
        if not decks:  # pragma: no cover -- the server always ships four
            raise PodError("unknown_deck", "no decks are loaded")
        seated_ids = {seat.deck_id for seat in pod.seats if seat.deck_id}
        seated_commanders = {self._commander_of(deck_id) for deck_id in seated_ids}
        for deck_id in decks:
            if self._commander_of(deck_id) not in seated_commanders:
                return deck_id
        for deck_id in decks:
            if deck_id not in seated_ids:
                return deck_id
        return decks[0]

    def _clashes(self, pod: Pod, index: int) -> bool:
        """Is a *person* at this table already playing this seat's commander?"""
        mine = self._commander_of(pod.seats[index].deck_id)
        if not mine:
            return False
        return any(
            other.kind == "human" and self._commander_of(other.deck_id) == mine
            for i, other in enumerate(pod.seats)
            if i != index
        )

    def _dedupe_cpu_decks(self, pod: Pod) -> None:
        """Move a CPU off a commander a person has taken.

        The CPU is the one that moves, because a person chose theirs and the
        CPU's was assigned.  Caller holds ``pod._lock``.
        """
        for index, seat in enumerate(pod.seats):
            if seat.kind != "cpu" or not self._clashes(pod, index):
                continue
            # Cleared first so the seat's own deck does not count as taken.
            seat.deck_id = None
            seat.deck_id = self._free_deck(pod)

    @staticmethod
    def _require_open(pod: Pod) -> None:
        if pod.status == "closed":
            raise PodError("pod_closed", "that pod has closed")
        if pod.status != "open":
            raise PodError(
                "already_started", "that pod has already dealt", game_id=pod.game_id
            )

    # -- leaving -----------------------------------------------------------

    def leave(self, pod: Pod, player_id: str) -> None:
        """Give up a chair.

        A guest's chair reverts to ``open`` rather than ``empty``: they were
        invited, and the pod should stay joinable at the same code.  The host
        leaving passes the pod to the next human by seat order, and a pod with
        no humans left closes -- every poller wakes with ``status: "closed"``
        rather than hanging until their poll ages out.
        """
        with pod._lock:
            player = pod.players.pop(player_id, None)
            if player is None:
                return
            seat = pod.seats[player.seat]
            seat.vacate()
            seat.kind = "open"
            seat.name = "Open"

            remaining = pod.humans
            if remaining:
                if pod.host_id == player_id:
                    pod.host_id = remaining[0].player_id
            elif pod.status == "open":
                pod._close()
            pod._bump()

    # -- the handoff into a real game --------------------------------------

    def start(self, pod: Pod, player_id: str, *, seed: int | None = None) -> GameSession:
        """Deal the pod.

        Every precondition is re-checked under the lock, because each one is a
        race in its own right: a guest can unlock, or a deck can be deleted by
        an import, between the host's button going live and the request landing.
        """
        with pod._lock:
            if seed is not None:
                pod.seed = seed
            self._require_open(pod)
            if not pod.is_host(player_id):
                raise PodError("not_host", "only the host can deal")

            # An open chair nobody took becomes a CPU. The lobby promises this,
            # and it is the difference between "the pod is stuck" and "we start".
            for index, seat in enumerate(pod.seats):
                if seat.kind == "open":
                    seat.kind = "cpu"
                    seat.name = seat.name if seat.name != "Open" else f"CPU {index}"
                    seat.deck_id = seat.deck_id or self._free_deck(pod)
                    seat.locked = True

            filled = [pod.seats[i] for i in pod.filled_seats]
            if len(filled) < 2:
                raise PodError("not_ready", "a pod needs at least two players")
            for index in pod.filled_seats:
                seat = pod.seats[index]
                if not seat.ready:
                    raise PodError("not_ready", f"seat {index} is not ready")
                if seat.deck_id not in self.sessions.data.decks:
                    raise PodError(
                        "unknown_deck", f"seat {index} has an unknown deck {seat.deck_id!r}"
                    )
            if pod.seat_of(pod.host_id) is None:
                raise PodError("not_ready", "the host has left")

            pod.status = "starting"

            # Compacted, not padded: a pod holding [you, empty, cpu, empty] is a
            # two-player game, not a four-player game with two dead seats.
            configs = [
                SeatConfig(
                    deck_id=seat.deck_id,
                    kind="human" if seat.kind == "human" else "ai",
                    agent=seat.agent,
                    name=seat.name,
                )
                for seat in filled
            ]
            tokens = {
                pod.players[seat.player_id].token: game_seat
                for game_seat, seat in enumerate(filled)
                if seat.kind == "human" and seat.player_id in pod.players
            }
            try:
                session = self.sessions.create(configs, seed=pod.seed, tokens=tokens)
            except Exception:
                # Leaving a pod wedged in "starting" would strand everybody in
                # it with no way back to the lobby.
                pod.status = "open"
                pod._bump()
                raise

            pod.status = "in_game"
            pod.game_id = session.game_id
            pod._bump()
            return session

    # -- housekeeping ------------------------------------------------------

    def sweep(self, *, now: float | None = None) -> int:
        """Evict idle players and dead pods.  Returns how many pods went.

        Called opportunistically from ``create`` and ``join`` rather than from a
        background thread: there is nothing to start, nothing to shut down
        cleanly, and the only moment anybody cares whether a chair is stale is
        the moment somebody tries to take one.
        """
        stamp = time.monotonic() if now is None else now
        with self._lock:
            pods = list(self._pods.values())
        dead: list[str] = []
        for pod in pods:
            with pod._lock:
                if pod.status == "open":
                    for player in list(pod.players.values()):
                        if stamp - player.last_seen > PLAYER_TTL_SECONDS:
                            self._evict(pod, player)
                idle = stamp - max(
                    [pod.created] + [p.last_seen for p in pod.players.values()]
                )
                closed_for = (
                    None if pod.closed_at is None else stamp - pod.closed_at
                )
                if idle > POD_TTL_SECONDS or (
                    closed_for is not None and closed_for > CLOSED_LINGER_SECONDS
                ):
                    dead.append(pod.code)
        with self._lock:
            for code in dead:
                self._pods.pop(code, None)
        self.sessions.sweep(now=now)
        return len(dead)

    @staticmethod
    def _evict(pod: Pod, player: PodPlayer) -> None:
        """Drop an idle player.  Caller holds ``pod._lock``."""
        pod.players.pop(player.player_id, None)
        seat = pod.seats[player.seat]
        seat.vacate()
        seat.kind = "open"
        seat.name = "Open"
        remaining = pod.humans
        if remaining:
            if pod.host_id == player.player_id:
                pod.host_id = remaining[0].player_id
        else:
            pod._close()
        pod._bump()

    def __len__(self) -> int:
        return len(self._pods)

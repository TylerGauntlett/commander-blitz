"""In-memory game sessions.

Single process, no auth, no database -- this is a local app.  A session owns one
``Game``, the agents sitting in the AI seats, and the tape of actions applied so
far (which is how undo works: replay from the seed minus the last human action).
"""

from __future__ import annotations

import re
import secrets
import threading
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from commanderblitz.ai.agents.base import Agent, agent_by_name
from commanderblitz.cards.registry import GameData, default_registry
from commanderblitz.engine.actions import Action
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import IllegalActionError
from commanderblitz.engine.game import create_game
from commanderblitz.engine.legality import legal_actions
from commanderblitz.engine.structs import TargetRef

from .schemas import LegalActionDTO, SeatConfig

#: How many AI decisions to resolve in one request before giving up.
MAX_AI_STEPS = 20_000

#: Longest a long-poll may block.  Comfortably under the 30 s that proxies and
#: browsers treat as a dead connection, so a poll that finds nothing still
#: returns a real response rather than being cut.
MAX_POLL_SECONDS = 25.0

#: The shape :meth:`GameSession._action_id` mints.  An id of this shape that is
#: not in the current list was almost certainly *a* real id once -- read off a
#: list the game has since moved past -- rather than a typo.  Only consulted
#: when the client sent no version: see :meth:`GameSession.apply_action_id`.
_ACTION_ID_SHAPE = re.compile(
    r"a\d+-(?:{})".format("|".join(re.escape(kind.value) for kind in ActionKind))
)


class StaleActionError(IllegalActionError):
    """The action was chosen from a list the game has since replaced.

    Action ids are positional (``a{index}-{kind}``), so they only mean anything
    against the list they were read from.  A double click, a drop followed by
    its own click, or a keypress that lands while the previous request is still
    in flight all send an id from the list *before* the move that just landed.
    Against the new list that id is either missing -- a baffling
    ``unknown action id`` -- or, worse, present and naming something else: a
    second ``a0-pass`` passes the *next* window too, which is how a
    double-tapped Pass skips the rest of a main phase.

    A subclass, not a sibling, so every caller that already treats an illegal
    action as a refusal keeps doing so; only the HTTP layer tells them apart,
    because a stale click wants a quiet refresh rather than an error toast.
    """


@dataclass(frozen=True)
class TapeEntry:
    """One applied action, tagged with who took it.

    ``full_control`` is the seat's stops setting at the moment the action was
    taken.  Undo replays the tape, and that setting decides which priority
    windows exist, so replaying under today's value could make a recorded Pass
    illegal.  Recording it per entry keeps replay deterministic.

    ``manual_mana`` is recorded for the same reason and is the sharper case: it
    decides which *actions* exist, not merely which windows, so a tape recorded
    with it on and replayed with it off cannot find the tap it recorded.
    """

    action: Action
    seat: int
    human: bool
    full_control: bool = False
    manual_mana: bool = False


@dataclass
class GameSession:
    """One game in progress."""

    game_id: str
    seats: list[SeatConfig]
    seed: int
    data: GameData
    max_turns: int | None = None
    game: object = None
    agents: dict[int, Agent] = field(default_factory=dict)
    #: Every action applied, in order.  Replayed verbatim to implement undo.
    tape: list[TapeEntry] = field(default_factory=list)
    #: Action id -> Action, rebuilt whenever the legal action list changes.
    _action_ids: dict[str, Action] = field(default_factory=dict)
    #: seat -> "stop at every priority window".  Survives the rebuild in undo().
    full_control: dict[int, bool] = field(default_factory=dict)
    #: Seat -> whether that seat taps its own lands.  Kept beside `full_control`
    #: because both survive the replay that `undo` performs.
    manual_mana: dict[int, bool] = field(default_factory=dict)
    #: ``player_token -> seat``.  Written by the lobby when it hands a pod off to
    #: a game; empty for the CLI, the smoke script and single-player, which is
    #: what keeps those callers on the old bounds-check-only authorisation.
    tokens: dict[str, int] = field(default_factory=dict)
    #: Bumped by every mutation.  Clients long-poll on ``?since_version=``.
    version: int = 1
    #: The first ``version`` whose state response carried the current
    #: ``_action_ids``.  A client that read its actions at any version from
    #: here on read *these* ids; one that read them earlier read a list that
    #: has been replaced, and its click is stale.  Compared against this rather
    #: than ``version`` itself so that a bump that leaves the list alone -- the
    #: other seat flipping its own stops -- does not void a list still on screen.
    actions_version: int = 1
    #: What ``_action_ids`` meant when it was last minted; see
    #: :meth:`_refresh_actions`.
    _actions_fingerprint: object = None
    #: Set by a ``_refresh_actions`` that minted a new list, consumed by the
    #: ``_bump`` that always follows it.
    _actions_dirty: bool = False
    #: ``time.monotonic()`` of the last mutation or authenticated read.  Only
    #: read by :meth:`SessionRegistry.sweep`.
    last_seen: float = field(default_factory=time.monotonic)
    #: Guards ``game``, ``tape`` and ``_action_ids``.  Starlette runs sync
    #: handlers in a thread pool, so with two humans on one game these are
    #: genuinely concurrent -- a ``_refresh_actions()`` can empty ``_action_ids``
    #: underneath a reader.  Reentrant because the mutators nest (apply -> drive).
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _changed: threading.Condition = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._changed = threading.Condition(self._lock)

    # ------------------------------------------------------------------

    @property
    def human_seats(self) -> list[int]:
        return [i for i, seat in enumerate(self.seats) if seat.kind == "human"]

    @property
    def primary_seat(self) -> int:
        humans = self.human_seats
        return humans[0] if humans else 0

    @property
    def multiplayer(self) -> bool:
        """More than one person is watching this game."""
        return len(self.human_seats) > 1

    def seat_for_token(self, token: str | None) -> int | None:
        return self.tokens.get(token) if token else None

    # ------------------------------------------------------------------
    # versioning
    # ------------------------------------------------------------------

    def _bump(self) -> None:
        """Announce a change.  Callers hold ``_lock``."""
        self.version += 1
        # `_refresh_actions` runs *before* this, under the old number, but the
        # first response to carry the new list is the one built after it -- so
        # the list belongs to the version being minted here, not the old one.
        if self._actions_dirty:
            self.actions_version = self.version
            self._actions_dirty = False
        self.last_seen = time.monotonic()
        self._changed.notify_all()

    def wait_for_change(self, since: int, timeout: float) -> int:
        """Block until ``version`` passes ``since``, then return it.

        A timeout is not an error: the caller returns the current state and the
        client re-polls, so a long poll is indistinguishable from a slow one and
        a dropped connection costs at most one round trip.
        """
        with self._lock:
            if since <= 0:
                return self.version
            self._changed.wait_for(
                lambda: self.version > since, timeout=min(timeout, MAX_POLL_SECONDS)
            )
            return self.version

    def start(self) -> None:
        with self._lock:
            self._start_locked()
            self._bump()

    def _start_locked(self) -> None:
        self.game = create_game(
            [seat.deck_id for seat in self.seats],
            data=self.data,
            seed=self.seed,
            names=[seat.name or f"Player {i}" for i, seat in enumerate(self.seats)],
            max_turns=self.max_turns,
        )
        self.agents = {
            i: agent_by_name(seat.agent, seed=self.seed * 31 + i)
            for i, seat in enumerate(self.seats)
            if seat.kind == "ai"
        }
        # Human seats skip priority windows with nothing to respond to. AI seats
        # keep every window so training and the golden tests are unaffected.
        #
        # `offer_all_abilities` rides along for the same reason and is not a
        # preference: a human clicks permanents, and a permanent that can do two
        # things has to show both. An AI seat picks from a list and would only
        # tap its rocks for mana it has nothing to spend on.
        for pid in self.human_seats:
            player = self.game.state.players[pid]
            player.auto_pass = True
            player.offer_all_abilities = True
            player.full_control = self.full_control.get(pid, False)
            player.manual_mana = self.manual_mana.get(pid, False)
        self.drive_ai()

    def set_full_control(self, seat: int, value: bool) -> None:
        """Stop at every priority window for this seat, or go back to smart stops."""
        with self._lock:
            self.full_control[seat] = value
            self.game.state.players[seat].full_control = value
            # Both settings change what `legality` offers, and `actions_for`
            # serves the cached `_action_ids` -- so without this the toggle only
            # took effect after the *next* action, and `POST /options` returned
            # the list from before it was flipped.
            self._refresh_actions()
            self._bump()

    def set_manual_mana(self, seat: int, value: bool) -> None:
        """Offer this seat's tap-only mana abilities instead of solving for them."""
        with self._lock:
            self.manual_mana[seat] = value
            self.game.state.players[seat].manual_mana = value
            self._refresh_actions()
            self._bump()

    # ------------------------------------------------------------------

    def drive_ai(self, max_steps: int | None = None) -> list:
        """Let AI seats act until a human must decide, or the game ends.

        ``max_steps`` bounds how many AI decisions are resolved in this call.
        The default (``None``) runs to the next human decision, which is what
        every non-interactive caller wants.  A client that wants to *animate*
        the opponents' turns passes 1 and calls again, so it receives one
        decision's worth of events at a time instead of three whole turns
        collapsed into a single response.
        """
        with self._lock:
            mark = len(self.game.state.events)
            budget = MAX_AI_STEPS if max_steps is None else max(0, max_steps)
            for _ in range(budget):
                if self.game.over:
                    break
                decision = self.game.pending()
                if decision is None or decision.player not in self.agents:
                    break
                actions = self.game.legal_actions()
                if not actions:
                    break
                chosen = self.agents[decision.player].act(self.game, decision.player, actions)
                self.game.apply(chosen)
                self.tape.append(self._entry(chosen, decision.player, human=False))
            self._refresh_actions()
            self._bump()
            return self.game.state.events[mark:]

    def _entry(self, action: Action, seat: int, *, human: bool) -> TapeEntry:
        return TapeEntry(
            action,
            seat,
            human,
            self.full_control.get(seat, False),
            self.manual_mana.get(seat, False),
        )

    def _refresh_actions(self) -> None:
        self._action_ids = {}
        if not (self.game.over or self.game.pending() is None):
            for index, action in enumerate(legal_actions(self.game.state)):
                self._action_ids[self._action_id(index, action)] = action
        # Whether this is a *new* list, which is not the same as a different
        # one.  Identical ids with something applied in between are new: Pass
        # in precombat main and Pass at beginning of combat are the same
        # `a0-pass`, and a double-tapped Pass that matched the second would
        # walk the player out of their main phase.  So the tape length (and the
        # game object, which undo replaces) is part of the fingerprint, and only
        # a refresh that applied nothing *and* changed nothing keeps the list.
        fingerprint = (id(self.game), len(self.tape), self._action_ids)
        if fingerprint != self._actions_fingerprint:
            self._actions_fingerprint = fingerprint
            self._actions_dirty = True

    @staticmethod
    def _action_id(index: int, action: Action) -> str:
        return f"a{index}-{action.kind.value}"

    def actions_for(self, seat: int) -> list[LegalActionDTO]:
        """The legal actions, but only if it is this seat's decision."""
        with self._lock:
            decision = self.game.pending()
            if decision is None or decision.player != seat or self.game.over:
                return []
            return [
                LegalActionDTO(
                    id=action_id,
                    kind=action.kind.value,
                    label=action.label or action.kind.value,
                    base_label=action.base_label or action.label or action.kind.value,
                    option_label=action.option_label,
                    source_oid=action.source,
                    ability_index=action.ability_index,
                    targets=[t.to_dict() for t in action.targets],
                    choice=action.choice,
                    x=action.x,
                    pays=list(action.pays),
                )
                for action_id, action in self._action_ids.items()
            ]

    def apply_action_id(
        self,
        seat: int,
        action_id: str,
        *,
        version: int | None = None,
        ai_steps: int | None = None,
    ) -> list:
        """Apply the action the client knows as ``action_id``.

        ``version`` is the session version of the state response the id was read
        from.  Checked *first*, before the id is even looked up: a stale id that
        happens to exist in the new list names whatever now sits at that index,
        so "it resolved" is no evidence that it means what the player clicked.

        A client that sends no version (an older build, a script) still gets
        the stale answer when the id is one this session would have minted and
        is not in the current list -- the best guess available without one.
        A truly malformed id stays a plain :class:`IllegalActionError`.
        """
        with self._lock:
            if version is not None and version < self.actions_version:
                raise StaleActionError(
                    f"action {action_id!r} is from version {version}; "
                    f"the actions have changed since (now version {self.version})"
                )
            decision = self.game.pending()
            if decision is None:
                raise IllegalActionError("the game is not waiting on a decision")
            if decision.player != seat:
                raise IllegalActionError(
                    f"it is seat {decision.player}'s decision, not {seat}'s"
                )
            action = self._action_ids.get(action_id)
            if action is None:
                if version is None and _ACTION_ID_SHAPE.fullmatch(action_id):
                    raise StaleActionError(
                        f"unknown action id {action_id!r}; the actions have changed"
                    )
                raise IllegalActionError(f"unknown action id {action_id!r}")

            mark = len(self.game.state.events)
            self.game.apply(action)
            self.tape.append(self._entry(action, seat, human=True))
            self.drive_ai(ai_steps)
            return self.game.state.events[mark:]

    def declare(
        self,
        seat: int,
        kind: str,
        pairs: Sequence[Sequence[int]],
        *,
        ai_steps: int | None = None,
    ) -> list:
        """Submit a whole attacker/blocker declaration.

        The engine declares incrementally; this loops the increments server-side
        so a client can present "select all, confirm".

        Shape errors are rejected *before* anything is applied. A pair that turns
        out to be illegal only once earlier pairs are in place still raises
        mid-loop; the declaration decision stays open in that case, so the client
        can simply submit a corrected set.
        """

        sources = [int(pair[0]) for pair in pairs]
        duplicates = {oid for oid in sources if sources.count(oid) > 1}
        if duplicates:
            # One creature attacks one player and blocks one attacker. Catching
            # this up front keeps a malformed request from half-applying.
            raise IllegalActionError(
                f"{sorted(duplicates)} appears more than once in the declaration"
            )

        with self._lock:
            mark = len(self.game.state.events)
            want = ActionKind.ADD_ATTACKER if kind == "attackers" else ActionKind.ADD_BLOCKER
            for pair in pairs:
                source, target = int(pair[0]), int(pair[1])
                ref = (
                    TargetRef.player(target) if kind == "attackers" else TargetRef.obj(target)
                )
                match = next(
                    (
                        a
                        for a in legal_actions(self.game.state)
                        if a.kind is want and a.source == source and a.targets == (ref,)
                    ),
                    None,
                )
                if match is None:
                    raise IllegalActionError(f"{source} cannot be declared against {target}")
                self.game.apply(match)
                self.tape.append(self._entry(match, seat, human=True))

            finish = next(
                (
                    a
                    for a in legal_actions(self.game.state)
                    if a.kind is ActionKind.FINISH_DECLARATION
                ),
                None,
            )
            if finish is None:
                raise IllegalActionError(
                    "that declaration is not legal (menace, for example)"
                )
            self.game.apply(finish)
            self.tape.append(self._entry(finish, seat, human=True))
            self.drive_ai(ai_steps)
            return self.game.state.events[mark:]

    def choose(
        self,
        seat: int,
        choices: Sequence[int],
        *,
        ai_steps: int | None = None,
    ) -> list:
        """Answer a pick-several decision with the whole set at once.

        The engine takes a multi-pick one `CHOOSE` at a time and closes it on
        the last allowed pick, which is right for an agent and wrong for a
        person: there is no way to change your mind, and with "up to two" the
        second click is a commitment. The client toggles cards locally and
        sends the set; this loops the increments, then `Done` if the set is
        smaller than the ceiling. The same shape `declare` has for combat.

        Every check is made before anything is applied, so a bad set never
        half-applies.
        """

        with self._lock:
            decision = self.game.pending()
            if decision is None or decision.player != seat:
                raise IllegalActionError("it is not this seat's decision")
            picks = [int(c) for c in choices]
            if len(set(picks)) != len(picks):
                raise IllegalActionError("an option was chosen more than once")
            if any(c < 0 or c >= len(decision.options) for c in picks):
                raise IllegalActionError("no such option")
            if decision.selected:
                raise IllegalActionError("this decision already has picks in it")
            if not decision.min_count <= len(picks) <= decision.max_count:
                raise IllegalActionError(
                    f"choose between {decision.min_count} and {decision.max_count}"
                )

            mark = len(self.game.state.events)
            for choice in picks:
                match = next(
                    (
                        a
                        for a in legal_actions(self.game.state)
                        if a.kind is ActionKind.CHOOSE and a.choice == choice
                    ),
                    None,
                )
                if match is None:  # pragma: no cover - guarded above
                    raise IllegalActionError(f"option {choice} cannot be chosen")
                self.game.apply(match)
                self.tape.append(self._entry(match, seat, human=True))
            # The last allowed pick closes the decision by itself; anything
            # short of it needs `Done`.
            if self.game.pending() is decision:
                finish = next(
                    a
                    for a in legal_actions(self.game.state)
                    if a.kind is ActionKind.FINISH_DECLARATION
                )
                self.game.apply(finish)
                self.tape.append(self._entry(finish, seat, human=True))
            self.drive_ai(ai_steps)
            return self.game.state.events[mark:]

    def undo(self) -> bool:
        """Rewind to before the last human action by replaying the tape.

        Replay rather than a state snapshot: the engine never clones state, so
        replay is the only representation that cannot silently miss a field.
        O(game length) is irrelevant at local-app scale.

        Single-human sessions only.  See :meth:`multiplayer` and the refusal in
        ``POST /undo``: replay builds a *new* ``Game``, and a second player who
        has already seen the rewound events has no way to reconcile.
        """
        with self._lock:
            cut = next(
                (i for i in range(len(self.tape) - 1, -1, -1) if self.tape[i].human), None
            )
            if cut is None:
                return False

            history = self.tape[:cut]
            self.tape = []
            self._start_locked()
            # start() already replayed the opening AI moves and re-recorded them,
            # so resume the tape from where it left off rather than re-applying.
            history = history[len(self.tape) :]
            for entry in history:
                if self.game.over or self.game.pending() is None:
                    break
                # The stops setting decides which priority windows exist, so
                # replay each action under the setting it was originally taken
                # with.
                if entry.seat in self.full_control:
                    self.game.state.players[entry.seat].full_control = entry.full_control
                if entry.seat in self.manual_mana:
                    self.game.state.players[entry.seat].manual_mana = entry.manual_mana
                match = next(
                    (a for a in legal_actions(self.game.state) if a == entry.action), None
                )
                if match is None:
                    # The replay diverged (it should not); stop rather than guess.
                    break
                self.game.apply(match)
                self.tape.append(
                    TapeEntry(
                        match, entry.seat, entry.human, entry.full_control, entry.manual_mana
                    )
                )
            for pid, value in self.full_control.items():
                self.game.state.players[pid].full_control = value
            for pid, value in self.manual_mana.items():
                self.game.state.players[pid].manual_mana = value
            self.drive_ai()
            return True


#: Upper bound on a generated seed.  Wide enough that two games never collide
#: in practice, small enough to stay a number a human can read back off a
#: screen and type into the seed box to deal the same game again.
MAX_SEED = 2**31 - 1


def new_seed() -> int:
    """A fresh seed for a game nobody asked to reproduce.

    Drawn from ``secrets`` rather than the engine's :class:`Rng`, for the same
    reason pod codes are: picking the seed is not part of the reproducible game,
    it is the thing the reproducible game is reproduced *from*.  Seeding it from
    the engine would need a seed to pick a seed.
    """
    return secrets.randbelow(MAX_SEED) + 1


#: A game nobody has touched for this long is abandoned.  Two hours is longer
#: than any real Commander game's *gap between actions*, not longer than a game.
SESSION_TTL_SECONDS = 2 * 60 * 60


class SessionRegistry:
    """All live sessions in this process."""

    def __init__(self, data: GameData | None = None) -> None:
        self.data = data if data is not None else default_registry()
        self._sessions: dict[str, GameSession] = {}
        #: ``_sessions`` is mutated from the request thread pool once pods exist.
        self._lock = threading.RLock()

    def create(
        self,
        seats: list[SeatConfig],
        *,
        seed: int | None = None,
        max_turns: int | None = None,
        tokens: dict[str, int] | None = None,
    ) -> GameSession:
        game_id = uuid.uuid4().hex[:12]
        session = GameSession(
            game_id=game_id,
            seats=seats,
            seed=new_seed() if seed is None else int(seed),
            data=self.data,
            max_turns=max_turns,
            tokens=dict(tokens or {}),
        )
        session.start()
        with self._lock:
            self._sessions[game_id] = session
        return session

    def get(self, game_id: str) -> GameSession:
        try:
            return self._sessions[game_id]
        except KeyError:
            raise KeyError(game_id) from None

    def delete(self, game_id: str) -> None:
        with self._lock:
            self._sessions.pop(game_id, None)

    def sweep(self, *, now: float | None = None, ttl: float = SESSION_TTL_SECONDS) -> int:
        """Drop sessions nobody has touched in ``ttl`` seconds.

        Single-player leaked one session per abandoned tab and nobody noticed.
        A lobby invites four people to abandon the same process, so the pod
        registry calls this opportunistically rather than adding a reaper thread.
        """
        cutoff = (time.monotonic() if now is None else now) - ttl
        with self._lock:
            dead = [gid for gid, s in self._sessions.items() if s.last_seen < cutoff]
            for gid in dead:
                del self._sessions[gid]
        return len(dead)

    def __len__(self) -> int:
        return len(self._sessions)

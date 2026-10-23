"""Game sessions.

Single process, no auth, no database.  A session owns one ``Game``, the agents
sitting in the AI seats, and the tape of actions applied so far (which is how
undo works: replay from the seed minus the last human action).  Given a
:class:`~.persist.JsonStore`, the registry also keeps each session on disk as
that tape, so a game outlives the process that dealt it (ADR 0023).
"""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from commanderblitz.ai.agents.base import Agent, agent_by_name
from commanderblitz.cards.registry import GameData, default_registry
from commanderblitz.engine.actions import Action
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import IllegalActionError
from commanderblitz.engine.game import create_game
from commanderblitz.engine.legality import legal_actions
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.targeting import target_refusal

from .persist import JsonStore
from .schemas import LegalActionDTO, SeatConfig

log = logging.getLogger(__name__)

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


class RestoreError(Exception):
    """A session's tape does not replay to the end under this build.

    Raised rather than restoring what did replay: a shortened game would rewind
    a table that has already watched it move on (ADR 0023).
    """


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

    def to_record(self) -> dict[str, Any]:
        return {
            "action": self.action.to_record(),
            "seat": self.seat,
            "human": self.human,
            "full_control": self.full_control,
            "manual_mana": self.manual_mana,
        }

    @staticmethod
    def from_record(raw: dict[str, Any]) -> TapeEntry:
        return TapeEntry(
            Action.from_record(raw["action"]),
            int(raw["seat"]),
            bool(raw["human"]),
            bool(raw.get("full_control", False)),
            bool(raw.get("manual_mana", False)),
        )


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
    #: Where every ``_bump`` writes this session; ``None`` keeps it in memory.
    store: JsonStore | None = field(default=None, repr=False)
    #: ``st_mtime_ns`` of the last file this process wrote or read for it.  A
    #: file with another stamp was written by somebody else.
    _stamp: int | None = field(default=None, repr=False)
    #: Set when the registry replaced this object with a newer copy read off
    #: disk, so a long poll parked on it returns instead of waiting out its
    #: timeout on a session nothing will ever bump again.
    superseded: bool = False

    def __post_init__(self) -> None:
        self._changed = threading.Condition(self._lock)

    # ------------------------------------------------------------------
    # on disk
    # ------------------------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        """Everything a replay needs, and nothing a replay would recompute."""
        with self._lock:
            return {
                "game_id": self.game_id,
                "seats": [seat.model_dump() for seat in self.seats],
                "seed": self.seed,
                "max_turns": self.max_turns,
                "tokens": dict(self.tokens),
                "full_control": {str(k): v for k, v in self.full_control.items()},
                "manual_mana": {str(k): v for k, v in self.manual_mana.items()},
                "version": self.version,
                "actions_version": self.actions_version,
                "tape": [entry.to_record() for entry in self.tape],
            }

    @classmethod
    def restore(cls, record: dict[str, Any], data: GameData) -> GameSession:
        """Deal the recorded game again and replay every entry of its tape.

        All or nothing: :class:`RestoreError` if any entry is not legal where it
        falls, which is a build whose rules no longer agree with the one the
        game was played under.  No AI is driven past the end of the tape --
        a client animating the opponents one step at a time asks for the next.
        """
        try:
            session = cls(
                game_id=str(record["game_id"]),
                seats=[SeatConfig(**seat) for seat in record["seats"]],
                seed=int(record["seed"]),
                data=data,
                max_turns=record.get("max_turns"),
                tokens={str(k): int(v) for k, v in record.get("tokens", {}).items()},
                full_control={int(k): bool(v) for k, v in record["full_control"].items()},
                manual_mana={int(k): bool(v) for k, v in record["manual_mana"].items()},
            )
            history = [TapeEntry.from_record(raw) for raw in record["tape"]]
            version = int(record["version"])
            actions_version = int(record["actions_version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RestoreError(f"malformed record: {exc}") from exc
        with session._lock:
            try:
                session._start_locked()
            except (KeyError, ValueError) as exc:
                # A deck deleted, or re-imported with a list that no longer deals.
                raise RestoreError(f"cannot deal it again: {exc}") from exc
            opening = len(session.tape)
            if [e.action for e in session.tape] != [e.action for e in history[:opening]]:
                raise RestoreError("the opening moves no longer replay")
            if not session._replay_locked(history[opening:]):
                raise RestoreError(
                    f"the tape stops replaying at entry {len(session.tape)} of {len(history)}"
                )
            session._refresh_actions()
            session._actions_dirty = False
            session.version = version
            session.actions_version = actions_version
            session.last_seen = time.monotonic()
        return session

    def _persist(self) -> None:
        """Write this session to its store.  Callers hold ``_lock``."""
        if self.store is not None:
            self._stamp = self.store.save(self.game_id, self.to_record())

    def _supersede(self) -> None:
        with self._lock:
            self.superseded = True
            self._changed.notify_all()

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
        # After the counters move and before anybody is told: the file is what
        # another process reads, and it must never be behind what a response
        # from this one has shown (ADR 0023).
        self._persist()
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
                lambda: self.version > since or self.superseded,
                timeout=min(timeout, MAX_POLL_SECONDS),
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
            refusals = self._target_refusals(seat)
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
                    untargetable=(
                        refusals.get((action.kind, action.source, action.ability_index), {})
                        if action.targets
                        else {}
                    ),
                )
                for action_id, action in self._action_ids.items()
            ]

    def _target_refusals(self, seat: int) -> dict[tuple, dict[str, str]]:
        """Why each permanent a targeted action never names cannot be named.

        Keyed the way the client groups one spell's or ability's actions while
        it is choosing a target -- kind, source and ability -- and computed once
        per group, since every action in it would carry the same map. Only the
        permanents `target_refusal` has a reason for: hexproof, shroud and
        protection are rare on a board, so the map is almost always empty.
        """
        state = self.game.state
        named: dict[tuple, set[int]] = {}
        for action in self._action_ids.values():
            if not action.targets:
                continue
            ids = named.setdefault((action.kind, action.source, action.ability_index), set())
            ids.update(ref.id for ref in action.targets if ref.kind == "object")
        out: dict[tuple, dict[str, str]] = {}
        for key, ids in named.items():
            out[key] = {
                str(oid): reason
                for oid in state.battlefield
                if oid not in ids
                and (reason := target_refusal(state, seat, oid, source_oid=key[1])) is not None
            }
        return out

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
            self._replay_locked(history[len(self.tape) :])
            self.drive_ai()
            return True

    def _replay_locked(self, history: Sequence[TapeEntry]) -> bool:
        """Apply ``history`` onto the current game; whether all of it applied.

        Shared by undo and by a restore from disk.  Each action is replayed
        under the stops and mana settings it was taken with, because those
        decide which windows and which actions exist; afterwards every seat is
        put back on its current setting.  Callers hold ``_lock``.
        """
        complete = True
        for entry in history:
            if self.game.over or self.game.pending() is None:
                complete = False
                break
            if entry.seat in self.full_control:
                self.game.state.players[entry.seat].full_control = entry.full_control
            if entry.seat in self.manual_mana:
                self.game.state.players[entry.seat].manual_mana = entry.manual_mana
            match = next(
                (a for a in legal_actions(self.game.state) if a == entry.action), None
            )
            if match is None:
                # The replay diverged; stop rather than guess.
                complete = False
                break
            self.game.apply(match)
            self.tape.append(
                TapeEntry(match, entry.seat, entry.human, entry.full_control, entry.manual_mana)
            )
        for pid, value in self.full_control.items():
            self.game.state.players[pid].full_control = value
        for pid, value in self.manual_mana.items():
            self.game.state.players[pid].manual_mana = value
        return complete


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
    """All live sessions in this process, and on disk when given a store."""

    def __init__(self, data: GameData | None = None, store: JsonStore | None = None) -> None:
        self.data = data if data is not None else default_registry()
        self.store = store
        self._sessions: dict[str, GameSession] = {}
        #: ``_sessions`` is mutated from the request thread pool once pods exist.
        self._lock = threading.RLock()
        #: Serialises restores, which replay a whole game, without holding
        #: ``_lock`` -- and so every other game -- for the length of one.
        self._loading = threading.Lock()

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
            store=self.store,
        )
        session.start()
        with self._lock:
            self._sessions[game_id] = session
        return session

    def get(self, game_id: str) -> GameSession:
        """The session, read from disk when this process has none or an old one.

        The memory copy is a cache of the file (ADR 0023): a miss loads it, and
        a file another process has rewritten since replaces the copy here.
        """
        with self._lock:
            session = self._sessions.get(game_id)
        if self.store is None or (session is not None and self._current(session)):
            if session is None:
                raise KeyError(game_id)
            return session
        with self._loading:
            with self._lock:
                session = self._sessions.get(game_id)
            if session is not None and self._current(session):
                return session
            loaded = self.store.load(game_id)
            if loaded is None:
                if session is None:
                    raise KeyError(game_id)
                return session
            record, stamp = loaded
            if session is not None and int(record.get("version", 0)) <= session.version:
                # Not newer than what is here: this process's own write, seen
                # between its save and its stamp.
                session._stamp = stamp
                return session
            try:
                fresh = GameSession.restore(record, self.data)
            except RestoreError as exc:
                log.warning("dropping game %s: %s", game_id, exc)
                self.store.delete(game_id)
                if session is not None:
                    self._drop(game_id, session)
                raise KeyError(game_id) from None
            fresh.store = self.store
            fresh._stamp = stamp
            with self._lock:
                self._sessions[game_id] = fresh
            if session is not None:
                session._supersede()
            return fresh

    def _current(self, session: GameSession) -> bool:
        """Is the file on disk the one this process last wrote or read?"""
        with session._lock:
            stamp = self.store.stamp(session.game_id)
            return stamp is None or stamp == session._stamp

    def _drop(self, game_id: str, session: GameSession) -> None:
        with self._lock:
            if self._sessions.get(game_id) is session:
                del self._sessions[game_id]
        session._supersede()

    def delete(self, game_id: str) -> None:
        with self._lock:
            self._sessions.pop(game_id, None)
        if self.store is not None:
            self.store.delete(game_id)

    def sweep(self, *, now: float | None = None, ttl: float = SESSION_TTL_SECONDS) -> int:
        """Drop sessions nobody has touched in ``ttl`` seconds.

        Single-player leaked one session per abandoned tab and nobody noticed.
        A lobby invites four people to abandon the same process, so the pod
        registry calls this opportunistically rather than adding a reaper thread.

        A file goes with its session only if nobody has written it since this
        process did; one another process is still moving is not this one's to
        delete.  Files no process holds age out by their modification time.
        """
        cutoff = (time.monotonic() if now is None else now) - ttl
        with self._lock:
            dead = [(gid, s) for gid, s in self._sessions.items() if s.last_seen < cutoff]
            for gid, _ in dead:
                del self._sessions[gid]
            held = set(self._sessions)
        if self.store is not None:
            for gid, session in dead:
                if self.store.stamp(gid) == session._stamp:
                    self.store.delete(gid)
            self.store.sweep(ttl, keep=held)
        return len(dead)

    def __len__(self) -> int:
        return len(self._sessions)

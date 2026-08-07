"""In-memory game sessions.

Single process, no auth, no database -- this is a local app.  A session owns one
``Game``, the agents sitting in the AI seats, and the tape of actions applied so
far (which is how undo works: replay from the seed minus the last human action).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from automtg.ai.agents.base import Agent, agent_by_name
from automtg.cards.registry import GameData, default_registry
from automtg.engine.actions import Action
from automtg.engine.errors import IllegalActionError
from automtg.engine.game import create_game
from automtg.engine.legality import legal_actions

from .schemas import LegalActionDTO, SeatConfig

#: How many AI decisions to resolve in one request before giving up.
MAX_AI_STEPS = 20_000


@dataclass(frozen=True)
class TapeEntry:
    """One applied action, tagged with who took it."""

    action: Action
    seat: int
    human: bool


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

    # ------------------------------------------------------------------

    @property
    def human_seats(self) -> list[int]:
        return [i for i, seat in enumerate(self.seats) if seat.kind == "human"]

    @property
    def primary_seat(self) -> int:
        humans = self.human_seats
        return humans[0] if humans else 0

    def start(self) -> None:
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
        self.drive_ai()

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
            self.tape.append(TapeEntry(chosen, decision.player, human=False))
        self._refresh_actions()
        return self.game.state.events[mark:]

    def _refresh_actions(self) -> None:
        self._action_ids = {}
        if self.game.over or self.game.pending() is None:
            return
        for index, action in enumerate(legal_actions(self.game.state)):
            self._action_ids[self._action_id(index, action)] = action

    @staticmethod
    def _action_id(index: int, action: Action) -> str:
        return f"a{index}-{action.kind.value}"

    def actions_for(self, seat: int) -> list[LegalActionDTO]:
        """The legal actions, but only if it is this seat's decision."""
        decision = self.game.pending()
        if decision is None or decision.player != seat or self.game.over:
            return []
        return [
            LegalActionDTO(
                id=action_id,
                kind=action.kind.value,
                label=action.label or action.kind.value,
                source_oid=action.source,
                ability_index=action.ability_index,
                targets=[t.to_dict() for t in action.targets],
                choice=action.choice,
                x=action.x,
            )
            for action_id, action in self._action_ids.items()
        ]

    def apply_action_id(self, seat: int, action_id: str, *, ai_steps: int | None = None) -> list:
        decision = self.game.pending()
        if decision is None:
            raise IllegalActionError("the game is not waiting on a decision")
        if decision.player != seat:
            raise IllegalActionError(f"it is seat {decision.player}'s decision, not {seat}'s")
        action = self._action_ids.get(action_id)
        if action is None:
            raise IllegalActionError(f"unknown action id {action_id!r}")

        mark = len(self.game.state.events)
        self.game.apply(action)
        self.tape.append(TapeEntry(action, seat, human=True))
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
        from automtg.engine.enums import ActionKind
        from automtg.engine.structs import TargetRef

        sources = [int(pair[0]) for pair in pairs]
        duplicates = {oid for oid in sources if sources.count(oid) > 1}
        if duplicates:
            # One creature attacks one player and blocks one attacker. Catching
            # this up front keeps a malformed request from half-applying.
            raise IllegalActionError(
                f"{sorted(duplicates)} appears more than once in the declaration"
            )

        mark = len(self.game.state.events)
        want = ActionKind.ADD_ATTACKER if kind == "attackers" else ActionKind.ADD_BLOCKER
        for pair in pairs:
            source, target = int(pair[0]), int(pair[1])
            ref = TargetRef.player(target) if kind == "attackers" else TargetRef.obj(target)
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
            self.tape.append(TapeEntry(match, seat, human=True))

        finish = next(
            (
                a
                for a in legal_actions(self.game.state)
                if a.kind is ActionKind.FINISH_DECLARATION
            ),
            None,
        )
        if finish is None:
            raise IllegalActionError("that declaration is not legal (menace, for example)")
        self.game.apply(finish)
        self.tape.append(TapeEntry(finish, seat, human=True))
        self.drive_ai(ai_steps)
        return self.game.state.events[mark:]

    def undo(self) -> bool:
        """Rewind to before the last human action by replaying the tape.

        Replay rather than a state snapshot: the engine never clones state, so
        replay is the only representation that cannot silently miss a field.
        O(game length) is irrelevant at local-app scale.
        """
        cut = next(
            (i for i in range(len(self.tape) - 1, -1, -1) if self.tape[i].human), None
        )
        if cut is None:
            return False

        history = self.tape[:cut]
        self.tape = []
        self.start()
        # start() already replayed the opening AI moves and re-recorded them, so
        # resume the tape from where it left off rather than re-applying them.
        history = history[len(self.tape) :]
        for entry in history:
            if self.game.over or self.game.pending() is None:
                break
            match = next(
                (a for a in legal_actions(self.game.state) if a == entry.action), None
            )
            if match is None:
                # The replay diverged (it should not); stop rather than guess.
                break
            self.game.apply(match)
            self.tape.append(TapeEntry(match, entry.seat, entry.human))
        self.drive_ai()
        return True


class SessionRegistry:
    """All live sessions in this process."""

    def __init__(self, data: GameData | None = None) -> None:
        self.data = data if data is not None else default_registry()
        self._sessions: dict[str, GameSession] = {}

    def create(
        self, seats: list[SeatConfig], *, seed: int | None = None, max_turns: int | None = None
    ) -> GameSession:
        game_id = uuid.uuid4().hex[:12]
        session = GameSession(
            game_id=game_id,
            seats=seats,
            seed=0 if seed is None else int(seed),
            data=self.data,
            max_turns=max_turns,
        )
        session.start()
        self._sessions[game_id] = session
        return session

    def get(self, game_id: str) -> GameSession:
        try:
            return self._sessions[game_id]
        except KeyError:
            raise KeyError(game_id) from None

    def delete(self, game_id: str) -> None:
        self._sessions.pop(game_id, None)

    def __len__(self) -> int:
        return len(self._sessions)

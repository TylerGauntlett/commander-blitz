"""Putting the game into an exact, hand-specified position.

Known hands, known battlefields, a known top of library -- so a caller can assert
one thing without playing ten turns first.

This lives in ``src`` rather than in ``tests`` because it is not test-only: the
card-authoring verifier (``automtg.cards.authoring``) has to stand a candidate
card up in a real position and watch what it does, and production code importing
from the test suite is backwards.
"""

from __future__ import annotations

from collections.abc import Sequence

from automtg.cards.registry import CardRegistry
from automtg.engine.enums import Step, Zone
from automtg.engine.game import Game
from automtg.engine.player import PlayerState
from automtg.engine.rng import Rng
from automtg.engine.state import GameState, new_object

#: Library filler so a position never loses to decking by accident.
FILLER_CARD = "island"
FILLER_COUNT = 40


class GameBuilder:
    """Construct a game in an exact position, skipping setup and mulligans.

    Example::

        game = (GameBuilder(reg, players=2, seed=7)
                .hand(0, ["t_counterspell", "island", "island"])
                .battlefield(0, ["island", "island"])
                .battlefield(1, ["t_bear"])
                .life(1, 3)
                .step(Step.PRECOMBAT_MAIN)
                .build())
    """

    def __init__(self, registry: CardRegistry, *, players: int = 2, seed: int = 0) -> None:
        self.registry = registry
        self.state = GameState(
            registry=registry,
            players=[PlayerState(pid=i, name=f"P{i}") for i in range(players)],
            rng=Rng(seed),
        )
        self.state.turn = 1
        self.state.round = 1
        self.state.step = Step.PRECOMBAT_MAIN
        self.state.active_idx = 0
        self.state.starting_player = 0
        self._explicit_library: set[int] = set()

    # -- zone population ----------------------------------------------------

    def hand(self, pid: int, card_ids: Sequence[str]) -> GameBuilder:
        for card_id in card_ids:
            obj = new_object(self.state, card_id, owner=pid, zone=Zone.HAND)
            self.state.players[pid].hand.append(obj.oid)
        return self

    def battlefield(
        self,
        pid: int,
        card_ids: Sequence[str],
        *,
        tapped: bool = False,
        sick: bool = False,
        counters: dict[str, int] | None = None,
    ) -> GameBuilder:
        for card_id in card_ids:
            obj = new_object(self.state, card_id, owner=pid, zone=Zone.BATTLEFIELD)
            obj.tapped = tapped
            # Permanents start having been controlled since before this turn, so
            # creatures can attack unless a test explicitly asks for sickness.
            obj.entered_turn = self.state.turn if sick else self.state.turn - 1
            if counters:
                obj.counters = dict(counters)
            # A permanent placed here has to look like one that *entered*, and
            # for a planeswalker that means its starting loyalty. Placed without
            # it, the zero-loyalty state-based action bins it the moment the
            # game starts -- which is correct behaviour reading a board that was
            # never legal.
            loyalty = self.state.registry.get(card_id).loyalty
            if loyalty is not None and "loyalty" not in obj.counters:
                obj.counters["loyalty"] = loyalty
            self.state.battlefield.append(obj.oid)
        self.state.bump_chars()
        return self

    def library(self, pid: int, card_ids: Sequence[str]) -> GameBuilder:
        """Set the exact top of this player's library (index 0 is the top card)."""
        self._explicit_library.add(pid)
        for card_id in card_ids:
            obj = new_object(self.state, card_id, owner=pid, zone=Zone.LIBRARY)
            self.state.players[pid].library.append(obj.oid)
        return self

    def graveyard(self, pid: int, card_ids: Sequence[str]) -> GameBuilder:
        for card_id in card_ids:
            obj = new_object(self.state, card_id, owner=pid, zone=Zone.GRAVEYARD)
            self.state.players[pid].graveyard.append(obj.oid)
        return self

    def commander(self, pid: int, card_ids: Sequence[str]) -> GameBuilder:
        for card_id in card_ids:
            obj = new_object(
                self.state, card_id, owner=pid, zone=Zone.COMMAND, is_commander=True
            )
            self.state.players[pid].command.append(obj.oid)
            self.state.players[pid].commanders.append(obj.oid)
        return self

    # -- scalar state -------------------------------------------------------

    def life(self, pid: int, amount: int) -> GameBuilder:
        self.state.players[pid].life = amount
        return self

    def step(self, step: Step) -> GameBuilder:
        self.state.step = step
        return self

    def turn(self, turn: int) -> GameBuilder:
        self.state.turn = turn
        return self

    def active(self, pid: int) -> GameBuilder:
        self.state.active_idx = pid
        return self

    def lands_played(self, pid: int, count: int) -> GameBuilder:
        self.state.players[pid].lands_played = count
        return self

    def max_turns(self, turns: int) -> GameBuilder:
        self.state.max_turns = turns
        return self

    # -- build --------------------------------------------------------------

    def build(self, *, advance: bool = True) -> Game:
        """Finish the position and hand back a ``Game``.

        ``advance=False`` leaves the game frozen exactly as described.  Use it
        when the assertion is about the position itself: advancing runs the
        engine's auto-pass, which will happily roll several turns forward when
        nobody has a real decision to make.
        """
        state = self.state
        for player in state.players:
            if player.pid not in self._explicit_library:
                for _ in range(FILLER_COUNT):
                    obj = new_object(state, FILLER_CARD, owner=player.pid, zone=Zone.LIBRARY)
                    player.library.append(obj.oid)
            player.has_kept_hand = True

        state.started = True
        state.step_started = True
        state.bump_chars()
        game = Game(state)
        if advance:
            game._advance()
        return game

"""Putting the game into an exact, hand-specified position.

Known hands, known battlefields, a known top of library -- so a caller can assert
one thing without playing ten turns first.

This lives in ``src`` rather than in ``tests`` because it is not test-only: the
card-authoring verifier (``commanderblitz.cards.authoring``) has to stand a candidate
card up in a real position and watch what it does, and production code importing
from the test suite is backwards.
"""

from __future__ import annotations

from collections.abc import Sequence

from commanderblitz.cards.registry import CardRegistry
from commanderblitz.engine.battles import DEFENSE
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.game import Game
from commanderblitz.engine.player import PlayerState
from commanderblitz.engine.rng import Rng
from commanderblitz.engine.sagas import LORE
from commanderblitz.engine.state import GameState, new_object

#: Library filler so a position never loses to decking by accident.
FILLER_CARD = "island"
FILLER_COUNT = 40
#: How many turns each seat of a built position has begun: past every
#: "during your first turns of the game" restriction a card prints.
IN_PROGRESS_TURNS_BEGUN = 10


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
        # A built position is a game in progress, so every seat is past the
        # opening turns a "can't cast during your first turns" card counts
        # (Serra Avenger). `turns_begun` puts a seat back in them.
        for player in self.state.players:
            player.turns_begun = IN_PROGRESS_TURNS_BEGUN
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
        level: int = 1,
    ) -> GameBuilder:
        for card_id in card_ids:
            obj = new_object(self.state, card_id, owner=pid, zone=Zone.BATTLEFIELD)
            obj.tapped = tapped
            # A Class part-way up its ladder (716), the way `counters=` stands a
            # Saga part-way through its story. Placed, not bought: no level
            # ability resolves and nothing that watches for a level fires.
            obj.class_level = level
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
            card = self.state.registry.get(card_id)
            loyalty = card.loyalty
            if loyalty is not None and "loyalty" not in obj.counters:
                obj.counters["loyalty"] = loyalty
            # And for a Saga, the lore counter it entered with (714.2b) -- the
            # same argument: a Saga standing on the battlefield with none is a
            # position no legal game reaches. `counters=` still overrides, which
            # is how a test puts one part-way through its story.
            #
            # No chapter fires from here, exactly as no enters trigger does:
            # this places permanents rather than playing them.
            if card.final_chapter is not None and LORE not in obj.counters:
                obj.counters[LORE] = 1
            # And for a battle, its printed defense (310.3). The third of the
            # three, and the argument is the loyalty one word for word: the
            # zero-defense state-based action (704.5x) bins a battle placed
            # without counters before the position is ever looked at.
            if card.defense is not None and DEFENSE not in obj.counters:
                obj.counters[DEFENSE] = card.defense
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

    def deck(self, pid: int, deck_id: str) -> GameBuilder:
        """Name the deck this seat is playing -- which CPU strategy pilots it.

        Only the label: nothing is dealt from the list, so a test still builds
        the exact position it wants.
        """
        self.state.players[pid].deck_id = deck_id
        return self

    def life(self, pid: int, amount: int) -> GameBuilder:
        self.state.players[pid].life = amount
        return self

    def step(self, step: Step) -> GameBuilder:
        self.state.step = step
        return self

    def turn(self, turn: int) -> GameBuilder:
        self.state.turn = turn
        return self

    def turns_begun(self, pid: int, turns: int) -> GameBuilder:
        """How many turns ``pid`` has begun, the current one included."""
        self.state.players[pid].turns_begun = turns
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

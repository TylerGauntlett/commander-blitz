"""Edgar, Master Machinist — a permanent that lets you cast out of your graveyard.

    Once during each of your turns, you may cast an artifact spell from your
    graveyard. If you cast a spell this way, that artifact enters tapped.

Every existing route out of a graveyard is a property of the **card being
cast** -- flashback, retrace, escape, aftermath -- read off `card.flashback` and
friends. This is a permission granted by a *permanent*, so legality has to ask
the board instead, and none of them could be narrowed by card type or rate
limited anyway.

`play_lands_from_graveyard` is the only graveyard-play permission that existed
and it is strictly narrower: `legality` reads it solely through
`player_plays_lands_from_graveyard` for the **land drop**, it cannot authorise a
spell cast, it takes no type filter, and it carries no per-turn count.

Three things the printed line turns on, and each is asserted:

- **which spells** -- `affects_spells`, the same filter `spell_cost_reduction`
  matches a card in hand with, and required: a permission naming no type would
  free the whole graveyard;
- **once during each of your turns** -- required too, since a permission with no
  rate limit is an unbounded engine rather than a card. Counted per *granting
  permanent*, so two Edgars are two casts, the way two Welcoming Vampires each
  draw;
- **that artifact enters tapped** -- a rider applied to the permanent that was
  cast, not to the one granting it. `self_enters_tapped` is a card's own
  replacement and is the wrong permanent entirely, which is what the free
  template tier originally got wrong on this card.

The spell is offered at its **printed** price, which is what separates this from
flashback's alternative cost.

`t_untapped_machinist` is the same permission without the rider, so the tapped
assertion is measured against a card that differs in exactly that field.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind

MACHINIST = "t_machinist"
UNTAPPED = "t_untapped_machinist"
ARTIFACT = "sol_ring"
CREATURE = "t_bear"


def board(builder, *, machinist: str | None = MACHINIST, buried=(ARTIFACT,)):
    b = (
        builder(players=2)
        .battlefield(0, ["plains"] * 4)
        .hand(0, ["forest"])
        .graveyard(0, list(buried))
        .library(0, ["forest"] * 10)
    )
    if machinist is not None:
        b = b.battlefield(0, [machinist])
    return b.build()


def castable(game):
    state = game.state
    return [
        state.card_of(state.objects[a.source]).id
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
    ]


def cast_first(game):
    action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST)
    source = action.source
    game.apply(action)
    state = game.state
    for _ in range(20):
        if not state.stack:
            break
        actions = game.legal_actions()
        if not actions:
            break
        game.apply(actions[0])
    return source


class TestThePermissionIsGrantedByThePermanent:
    def test_the_artifact_is_castable_from_the_graveyard(self, builder):
        assert castable(board(builder)) == [ARTIFACT]

    def test_without_the_permanent_it_is_not(self, builder):
        """The permission is the permanent's, not the card's."""
        assert castable(board(builder, machinist=None)) == []


class TestItIsNarrowedByType:
    def test_a_creature_card_is_not_freed(self, builder):
        """"an **artifact** spell" -- `affects_spells` is required for this."""
        assert castable(board(builder, buried=(CREATURE,))) == []

    def test_the_loader_refuses_a_permission_with_no_filter(self):
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="affects_spells"):
            compile_card(_permission(affects_spells=None), source="test")

    def test_the_loader_refuses_a_permission_with_no_rate_limit(self):
        """Without one it is an unbounded engine rather than the printed line."""
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="max_per_turn"):
            compile_card(_permission(static_max_per_turn=None), source="test")


class TestOncePerTurn:
    def test_the_second_cast_is_not_offered(self, builder):
        game = board(builder, buried=(ARTIFACT, "mind_stone"))
        assert len(castable(game)) == 2, "both are artifacts to begin with"
        cast_first(game)
        assert castable(game) == [], "the permission is spent for the turn"


class TestTheEntersTappedRider:
    def test_it_enters_tapped(self, builder):
        game = board(builder)
        oid = cast_first(game)
        assert game.state.objects[oid].tapped

    def test_without_the_rider_it_does_not(self, builder):
        """Same permission, one field different."""
        game = board(builder, machinist=UNTAPPED)
        oid = cast_first(game)
        assert not game.state.objects[oid].tapped

    def test_the_granting_permanent_is_untouched(self, builder):
        """The rider is about the artifact, not about Edgar.

        The free template tier mis-templated this clause onto Edgar himself,
        which is a different card and an easy one to ship.
        """
        game = board(builder)
        state = game.state
        edgar = next(
            o.oid
            for o in state.battlefield_objects(0)
            if state.card_of(o).id == MACHINIST
        )
        cast_first(game)
        assert not state.objects[edgar].tapped


class TestItCountsAsCastFromAGraveyard:
    def test_the_flag_is_set(self, builder):
        """"If you cast a spell this way" and every other
        `cast_from_graveyard` condition asks that question, not "was it
        flashed back"."""
        game = board(builder)
        oid = cast_first(game)
        assert game.state.objects[oid].cast_from_graveyard


def _permission(**overrides):
    from commanderblitz.cards.schema import CardModel

    static = {
        "kind": "static",
        "text": "Once during each of your turns, you may cast an artifact spell from your graveyard.",
        "effect": "cast_from_graveyard",
        "affects_player": "you",
        "affects_spells": {"types": ["Artifact"]},
        "static_max_per_turn": 1,
    }
    for key, value in overrides.items():
        if value is None:
            static.pop(key, None)
        else:
            static[key] = value
    return CardModel.model_validate(
        {
            "id": "t_bad_permission",
            "name": "Test Bad Permission",
            "oracle_text": static["text"],
            "mana_cost": "{2}{W}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [static],
        }
    )


class TestTheArrivalClause:
    """Banon: "…put there **from anywhere other than the battlefield this turn**".

    A fact about *this copy* of the card -- when it reached the graveyard and
    from where -- so it cannot live in `affects_spells`, which may only read the
    printed face. `TurnLedger.cards_to_graveyard` is the only this-turn
    graveyard fact the engine kept and it is a bare integer over every yard at
    the table: it retains neither which card arrived nor whence, so a selector
    reading it could only see the whole graveyard and Banon would recur a
    creature that died in combat five turns ago.

    Written as a complement (`!battlefield`) because the printed line is one:
    listing the four zones a card could otherwise have come from would silently
    miss the fifth.
    """

    PRAY = "t_pray"
    GREEN_BEAR = "t_bear"

    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [self.PRAY])
            .battlefield(0, ["forest"] * 4)
            .hand(0, ["plains"])
            .library(0, [self.GREEN_BEAR] + ["forest"] * 10)
            .build()
        )

    def bury(self, game, *, via: str):
        from commanderblitz.engine.enums import Zone
        from commanderblitz.engine.zones import move_object

        state = game.state
        oid = state.players[0].library[0]
        if via == "battlefield":
            move_object(state, oid, Zone.BATTLEFIELD, to_player=0, cause="test")
        move_object(state, oid, Zone.GRAVEYARD, to_player=0, cause="test")
        return game

    def test_a_milled_creature_is_castable(self, builder):
        game = self.bury(self.board(builder), via="library")
        assert castable(game) == [self.GREEN_BEAR]

    def test_one_that_died_on_the_battlefield_is_not(self, builder):
        """The clause's whole content, and the case a plain graveyard selector
        would have let through."""
        game = self.bury(self.board(builder), via="battlefield")
        assert castable(game) == []

    def test_the_arrival_is_recorded_on_the_card(self, builder):
        game = self.bury(self.board(builder), via="library")
        oid = game.state.players[0].graveyard[0]
        obj = game.state.objects[oid]
        assert obj.graveyard_from == "library"
        assert obj.graveyard_turn == game.state.turn

    def test_a_permission_without_the_clause_takes_either(self, builder):
        """Edgar has no arrival clause, and every card in the yard qualifies."""
        game = (
            builder(players=2)
            .battlefield(0, [MACHINIST])
            .battlefield(0, ["plains"] * 4)
            .hand(0, ["forest"])
            .library(0, [ARTIFACT] + ["forest"] * 10)
            .build()
        )
        self.bury(game, via="battlefield")
        assert castable(game) == [ARTIFACT]

    def test_the_loader_refuses_an_unknown_zone(self):
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="unknown zone"):
            compile_card(_permission(arrived_this_turn_from=["!nowhere"]), source="t")

    def test_the_loader_refuses_an_empty_list(self):
        """Nothing in the graveyard would ever qualify."""
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="names no zone"):
            compile_card(_permission(arrived_this_turn_from=[]), source="t")


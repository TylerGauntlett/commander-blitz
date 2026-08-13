"""Prowl — a condition about a creature that may no longer exist.

    "Prowl {1}{U} (You may cast this spell for its prowl cost if a player was
    dealt combat damage this turn by a Faerie or a Rogue.)"

`alternative_cost` already shipped for spectacle, so the cheaper cast line and
the condition gating it both existed. What did not is the condition itself, and
the census named the gap exactly: the ledger keeps *how much* damage each player
took and nothing about **who dealt it**.

The board cannot stand in, and the reason is the reason the whole ledger exists.
By the time a prowl spell is cast the Faerie that got through may be dead,
bounced, or no longer a Faerie — and none of those undo the damage the condition
is about. `exists` over Faeries you control is the near miss and is a different
card: it is true with a Faerie sitting at home that never attacked, and false
after the one that connected traded in combat.

So `combat_damage_types` joins the turn ledger, folded in `emit` beside the
other six, and read off **derived** subtypes at the moment the damage lands —
so a changeling and a creature granted the type both count, which is most of
what the decks printing prowl are built on.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError
from automtg.engine.effects.conditions import validate_condition
from automtg.engine.enums import ActionKind, Step
from automtg.engine.primitives import damage_player
from tests.conftest import _default_answer, only_oid, pass_until

ISLAND = "island"
PROWLER = "t_prowler"      # {3}{U}, prowl {1}{U}, a Faerie Rogue
BEAR = "t_bear"            # a Bear


def position(builder, lands: int = 2):
    """A board parked at *your own* main phase, with priority.

    Two things force that and both would make every assertion below pass for the
    wrong reason. The Prowler is a creature, so a cast line only exists at
    sorcery speed; and legality answers for whoever currently holds priority, so
    a position where the opponent has it offers nothing whatever the ledger says.
    """
    game = (
        builder(players=2)
        .battlefield(0, [ISLAND] * lands)
        .battlefield(0, [BEAR])
        .hand(0, [PROWLER])
        .library(0, [ISLAND] * 20)
        .library(1, [ISLAND] * 20)
        .build()
    )
    to_my_main(game)
    return game


def to_my_main(game, turn: int = 3) -> None:
    """Run to your own precombat main on ``turn``, stopping while you hold priority.

    Turn 3 rather than turn 1 because `build` has already advanced past turn 1's
    main phases, and the ledger has to be *fresh* -- a later turn is exactly what
    "this turn" excludes.
    """
    pass_until(
        game,
        lambda g: (
            g.state.turn >= turn
            and g.state.step is Step.PRECOMBAT_MAIN
            and (d := g.pending()) is not None
            and d.player == 0
        ),
    )


def cast_lines(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == PROWLER
    ]


def deal_combat_damage(game, attacker_types: list[str]) -> None:
    """Give the ledger a combat hit from a creature with these subtypes.

    Driven through `damage_player` rather than a real combat, because the claim
    is about what the ledger records and combat is a long way round to say it.
    """
    bear = only_oid(game, BEAR)
    obj = game.state.objects[bear]
    obj.added_subtypes = tuple(attacker_types)
    game.state.bump_chars()
    damage_player(game.state, 1, 1, bear, is_combat=True)


class TestWhenTheProwlLineIsOffered:
    def test_it_is_not_offered_before_anything_connects(self, builder):
        game = position(builder)
        assert cast_lines(game) == [], "{3}{U} is unaffordable, and prowl is not on"

    def test_a_faerie_getting_through_turns_it_on(self, builder):
        game = position(builder)
        deal_combat_damage(game, ["Faerie"])

        assert len(cast_lines(game)) == 1, "the prowl line, at {1}{U}"

    def test_a_rogue_turns_it_on_too(self, builder):
        """The condition is a list -- either type satisfies it."""
        game = position(builder)
        deal_combat_damage(game, ["Rogue"])

        assert len(cast_lines(game)) == 1

    def test_another_type_does_not(self, builder):
        game = position(builder)
        deal_combat_damage(game, ["Goblin"])

        assert cast_lines(game) == []


class TestItIsAboutTheDamageAndNotTheBoard:
    def test_it_survives_the_creature_dying(self, builder):
        """The whole reason it is a ledger entry. `exists` would go false here."""
        from automtg.engine.zones import destroy

        game = position(builder)
        deal_combat_damage(game, ["Faerie"])
        destroy(game.state, only_oid(game, BEAR))

        assert len(cast_lines(game)) == 1

    def test_it_reads_derived_subtypes(self, builder):
        """A Bear made a Faerie counts, which is the changeling case."""
        game = position(builder)
        deal_combat_damage(game, ["Faerie"])

        assert "Faerie" in game.state.turn_ledger.combat_damage_types

    def test_noncombat_damage_does_not_count(self, builder):
        """"…dealt **combat** damage". A burn spell from a Faerie is not it."""
        game = position(builder)
        bear = only_oid(game, BEAR)
        game.state.objects[bear].added_subtypes = ("Faerie",)
        game.state.bump_chars()
        damage_player(game.state, 1, 1, bear, is_combat=False)

        assert cast_lines(game) == []

    def test_it_clears_at_end_of_turn(self, builder):
        """"…this turn". A ledger that outlived the turn would make prowl free."""
        game = position(builder)
        deal_combat_damage(game, ["Faerie"])
        assert game.state.turn_ledger.combat_damage_types

        started = game.state.turn
        for _ in range(900):
            if game.state.turn > started:
                break
            decision = game.pending()
            if decision is None:
                break
            game.apply(_default_answer(game, decision))

        assert game.state.turn > started, "the turn really ended"
        assert not game.state.turn_ledger.combat_damage_types


class TestTheFullPriceLineIsUnaffected:
    def test_both_lines_are_offered_with_the_mana_for_both(self, builder):
        game = position(builder, lands=4)
        assert len(cast_lines(game)) == 1, "only the printed cost, so far"

        deal_combat_damage(game, ["Faerie"])
        assert len(cast_lines(game)) == 2, "and now the prowl line beside it"


class TestTheLoaderGuard:
    def test_a_subtype_list_loads(self):
        validate_condition({"combat_damage_by": ["Faerie", "Rogue"]}, "test")

    def test_a_bare_subtype_loads(self):
        validate_condition({"combat_damage_by": "Rogue"}, "test")

    def test_an_empty_list_is_refused(self):
        """It would match nothing, so the alternative cost is never offered."""
        with pytest.raises(DslError, match="combat_damage_by"):
            validate_condition({"combat_damage_by": []}, "test")

    def test_a_non_string_entry_is_refused(self):
        with pytest.raises(DslError, match="combat_damage_by"):
            validate_condition({"combat_damage_by": ["Faerie", 3]}, "test")

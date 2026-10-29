"""A spell an effect casts from a graveyard, exiled instead of returning there.

Helmut Zemo, Mastermind: "Whenever Helmut Zemo attacks, you may cast target
instant or sorcery card with mana value less than or equal to his power from
your graveyard. If that spell would be put into your graveyard, exile it
instead. If you cast a spell this way, put a +1/+1 counter on Helmut Zemo."

The second sentence is a replacement on the **spell** (614.1a), not a
resolution rider: it holds whether the spell resolves, fizzles (608.2b) or is
countered, the way flashback's does (702.34a). Without it the card would be
back in the graveyard for the next attack, every attack -- a strictly better
card. It is `cast_card`'s ``exiles``, carried on the stack item
(`StackItem.exiles_instead`) and not on the card, because it is the effect
that says it: the same card cast from the graveyard another way goes back to
the graveyard as usual.

"You may cast" with no "without paying" is a cast at the card's mana cost,
made during the trigger's resolution (608.2g, 601.2), which `cast_card`
already is; "if you cast a spell this way" reads its ``as`` binding.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import (
    action_for_card,
    activations,
    find_action,
    oids_of,
    only_oid,
    pass_until,
    plus_one_counters,
    settle,
)

ZEMO = "t_cce_zemo"
RECAST = "t_cce_regrowth"
BOLT = "t_bolt"
DIVINATION = "t_draw_spell"


def position(builder, *, graveyard=(BOLT,), lands=("mountain",), theirs=("t_bear",), hand1=()):
    """Player 0's Zemo stand-in (a 2/3), ``lands`` and ``graveyard``, facing
    player 1's ``theirs`` with two Islands and a Mountain and ``hand1``, at
    player 0's untap step. Returns ``(game, zemo)``."""
    game = (
        builder(players=2)
        .battlefield(0, [ZEMO, *lands])
        .battlefield(1, [*theirs, "island", "island", "mountain"])
        .graveyard(0, list(graveyard))
        .hand(1, list(hand1))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(0)
        .step(Step.UNTAP)
        .build()
    )
    return game, only_oid(game, ZEMO, 0)


def attack(game, zemo) -> None:
    """Attack player 1 with Zemo and pass until his trigger's resolution asks."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=zemo, targets=(TargetRef.player(1),))
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is not DecisionKind.PRIORITY,
    )


def cast_bolt_at_their_bear(game) -> None:
    """Answer the trigger's "you may" yes and aim the Bolt at player 1's Bear.

    With no response possible the table passes on the players' behalf, so the
    Bolt may already have resolved when this returns."""
    assert game.pending().kind is DecisionKind.MAY, game.pending().prompt
    game.apply(find_action(game, ActionKind.YES))
    # Zemo and every Bear are legal targets, so the cast asks for one.
    bear = only_oid(game, "t_bear", 1)
    decision = game.pending()
    if decision.kind is DecisionKind.CHOOSE_OBJECTS:
        index = next(i for i, o in enumerate(decision.options) if o.ref and o.ref.id == bear)
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
        )
        if game.pending() is decision:
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    assert any(
        e.type == "spell_cast" and e.data.get("card") == BOLT for e in game.state.events
    )


def zone_of(game, oid) -> Zone:
    return game.state.objects[oid].zone


def graveyard_bolt(game) -> int:
    return next(
        oid for oid in game.state.players[0].graveyard if game.state.objects[oid].def_id == BOLT
    )


class TestTheSpellIsExiled:
    def test_resolved_it_is_exiled_not_returned(self, builder):
        game, zemo = position(builder)
        bolt = graveyard_bolt(game)
        attack(game, zemo)
        cast_bolt_at_their_bear(game)
        settle(game)
        assert oids_of(game, "t_bear", 1) == [], "the Bolt resolved"
        assert zone_of(game, bolt) is Zone.EXILE
        assert bolt not in game.state.players[0].graveyard

    def test_countered_it_is_exiled(self, builder):
        game, zemo = position(builder, hand1=("t_counterspell",))
        bolt = graveyard_bolt(game)
        attack(game, zemo)
        cast_bolt_at_their_bear(game)
        pass_until(game, lambda g: g.pending().player == 1)
        game.apply(action_for_card(game, ActionKind.CAST, "t_counterspell"))
        settle(game)
        assert any(e.type == "spell_countered" for e in game.state.events)
        assert zone_of(game, bolt) is Zone.EXILE
        # The Bear lived: the Bolt really was countered rather than resolved.
        assert only_oid(game, "t_bear", 1)

    def test_fizzled_it_is_exiled(self, builder):
        game, zemo = position(builder, hand1=(BOLT,))
        bolt = graveyard_bolt(game)
        attack(game, zemo)
        cast_bolt_at_their_bear(game)
        # Player 1 kills their own Bear in response: the target is gone (608.2b).
        pass_until(game, lambda g: g.pending().player == 1)
        bear = only_oid(game, "t_bear", 1)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == BOLT
                and a.targets
                and a.targets[0].id == bear
            )
        )
        settle(game)
        assert any(e.type == "spell_fizzled" for e in game.state.events)
        assert zone_of(game, bolt) is Zone.EXILE


class TestTheCounter:
    def test_a_spell_cast_this_way_puts_the_counter_on(self, builder):
        game, zemo = position(builder)
        attack(game, zemo)
        cast_bolt_at_their_bear(game)
        settle(game)
        assert plus_one_counters(game, zemo) == 1

    def test_declined_no_counter_and_the_card_stays(self, builder):
        game, zemo = position(builder)
        bolt = graveyard_bolt(game)
        attack(game, zemo)
        game.apply(find_action(game, ActionKind.NO))
        settle(game)
        assert plus_one_counters(game, zemo) == 0
        assert zone_of(game, bolt) is Zone.GRAVEYARD

    def test_unpayable_no_offer_no_counter(self, builder):
        game, zemo = position(builder, lands=("forest",))
        bolt = graveyard_bolt(game)
        attack(game, zemo)
        settle(game)
        assert plus_one_counters(game, zemo) == 0
        assert zone_of(game, bolt) is Zone.GRAVEYARD

    def test_mana_value_above_his_power_is_no_target(self, builder):
        # Test Divination is mana value 3 against a power of 2.
        game, zemo = position(builder, graveyard=(DIVINATION,), lands=("island",) * 3)
        attack(game, zemo)
        settle(game)
        assert plus_one_counters(game, zemo) == 0
        assert [game.state.objects[o].def_id for o in game.state.players[0].graveyard] == [
            DIVINATION
        ]


class TestTheRiderIsTheEffects:
    def test_the_same_card_cast_another_way_returns_to_the_graveyard(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [RECAST, "mountain"])
            .battlefield(1, ["t_bear"])
            .graveyard(0, [BOLT])
            .hand(0, ["forest"])
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .build()
        )
        bolt = graveyard_bolt(game)
        game.apply(activations(game, only_oid(game, RECAST, 0))[0])
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is not DecisionKind.PRIORITY,
        )
        cast_bolt_at_their_bear(game)
        settle(game)
        assert oids_of(game, "t_bear", 1) == [], "the Bolt resolved"
        assert zone_of(game, bolt) is Zone.GRAVEYARD


class TestTheLoaderGuard:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_cce_probe",
                "name": "Test Cast Card Exiles Probe",
                "mana_cost": "{2}",
                "types": ["Sorcery"],
                "oracle_text": "Probe.",
                "spell_effects": [effect],
            }
        )

    def test_the_printed_form_loads(self):
        compile_card(
            self._card({"op": "cast_card", "objects": {"binding": "x"}, "exiles": True})
        )

    @pytest.mark.parametrize("value", ["true", 1, None])
    def test_a_non_boolean_is_refused(self, value):
        with pytest.raises(DslError):
            compile_card(
                self._card({"op": "cast_card", "objects": {"binding": "x"}, "exiles": value})
            )

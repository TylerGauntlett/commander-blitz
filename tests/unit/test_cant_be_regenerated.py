"""«It can't be regenerated.» — 701.15c, a clause three shipped cards dropped.

    "Destroy target creature. **It can't be regenerated.**" (Terminate, Pongify)
    "Destroy all creatures. **They can't be regenerated.**" (Wrath of God)

`op_destroy` read only `objects` and called `zones.destroy`, which spends a
regeneration shield unconditionally. So the sentence had nowhere to be written,
and every card that printed it shipped without it: Terminate, Wrath of God and
Rapid Hybridization were all spells a Drudge Skeletons walks away from. Nothing
announced that — the clause is not an ability, so the residual gate has no `text`
to attribute and no line went unclaimed.

The three things this deliberately does **not** do are the point, because each is
a card that would otherwise read wrong:

* **the shield is not spent.** 701.15c stops the shield being *applied*; it does
  not consume it. A creature that survives on indestructible keeps it.
* **indestructible still wins.** That is a different replacement, and Terminate
  has never beaten it.
* **totem armor still applies**, for the same reason.

And it is a parameter on the destruction rather than a mark on the permanent,
which is the whole reading of the sentence: "it can't be regenerated" is about
*this* destruction. Marked on the creature for the turn, an indestructible one
Terminated would go on being unregeneratable afterwards — a rule the card does
not print.

The turn-long form ("a creature dealt damage this way can't be regenerated this
turn") is a different sentence and is not implemented; there is no `destroy` for
it to hang off.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader import DslError, _validate_effect
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Keyword, Zone
from automtg.engine.primitives import attach
from automtg.engine.zones import destroy
from tests.conftest import only_oid

FOREST = "forest"
TROLL = "t_regenerator"
AURA = "t_totem_armor"


def board(builder, *cards: str):
    return (
        builder(players=2)
        .battlefield(0, [FOREST] * 3)
        .battlefield(0, list(cards))
        .build(advance=False)
    )


def shield(game, oid: int, amount: int = 1) -> None:
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    gen = OPS["regenerate"](
        ctx,
        {
            "op": "regenerate",
            "amount": {"const": amount},
            "objects": {"zone": "battlefield", "self_only": True},
        },
    )
    with contextlib.suppress(StopIteration):
        next(gen)


def run_destroy(game, oid: int, **spec) -> None:
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    gen = OPS["destroy"](ctx, {"op": "destroy", "objects": {"oids": [oid]}, **spec})
    with contextlib.suppress(StopIteration):
        next(gen)


class TestTheShieldDoesNotApply:
    def test_a_shielded_creature_dies_anyway(self, builder):
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll)

        assert destroy(game.state, troll, no_regeneration=True) is True
        assert game.state.objects[troll].zone is Zone.GRAVEYARD

    def test_without_the_clause_the_same_creature_survives(self, builder):
        """The control. Without it this file proves nothing about the flag."""
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll)

        assert destroy(game.state, troll) is False
        assert game.state.objects[troll].zone is Zone.BATTLEFIELD

    def test_two_shields_do_not_help_either(self, builder):
        """Not "one shield is skipped" — shields are not applied at all."""
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll, amount=2)

        assert destroy(game.state, troll, no_regeneration=True) is True

    def test_it_is_not_tapped_and_not_removed_from_combat(self, builder):
        """701.15a's three consequences are the *shield's*, and it never ran."""
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll)
        game.state.objects[troll].damage = 2
        destroy(game.state, troll, no_regeneration=True)

        obj = game.state.objects[troll]
        assert obj.zone is Zone.GRAVEYARD
        assert not obj.tapped


class TestWhatItLeavesAlone:
    def test_indestructible_still_saves_the_creature(self, builder):
        """A different replacement. Terminate has never beaten it."""
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        game.state.objects[troll].granted_keywords.add(Keyword.INDESTRUCTIBLE.value)
        game.state.bump_chars()
        shield(game, troll)

        assert destroy(game.state, troll, no_regeneration=True) is False
        assert game.state.objects[troll].zone is Zone.BATTLEFIELD

    def test_a_shield_survives_a_destruction_it_was_not_applied_to(self, builder):
        """701.15c stops the shield being *applied*; it does not spend it. So
        the creature saved by indestructible can still regenerate afterwards."""
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        game.state.objects[troll].granted_keywords.add(Keyword.INDESTRUCTIBLE.value)
        game.state.bump_chars()
        shield(game, troll)
        destroy(game.state, troll, no_regeneration=True)

        assert game.state.objects[troll].regeneration_shields == 1

    def test_totem_armor_still_replaces_the_destruction(self, builder):
        """Also a different replacement, and it lives on the Aura."""
        game = board(builder, TROLL, AURA)
        troll = only_oid(game, TROLL)
        aura = only_oid(game, AURA)
        attach(game.state, aura, troll)

        assert destroy(game.state, troll, no_regeneration=True) is False
        assert game.state.objects[troll].zone is Zone.BATTLEFIELD
        assert game.state.objects[aura].zone is Zone.GRAVEYARD


class TestTheOp:
    def test_the_flag_reaches_the_destruction(self, builder):
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll)
        run_destroy(game, troll, no_regeneration=True)

        assert game.state.objects[troll].zone is Zone.GRAVEYARD

    def test_the_op_without_it_still_regenerates(self, builder):
        game = board(builder, TROLL)
        troll = only_oid(game, TROLL)
        shield(game, troll)
        run_destroy(game, troll)

        assert game.state.objects[troll].zone is Zone.BATTLEFIELD


class TestTheShippedCardsThatPrintIt:
    """Terminate, Wrath of God and Rapid Hybridization all print the clause and
    all shipped without it. They are the witnesses, so they are asserted on."""

    @pytest.mark.parametrize(
        "card_id", ["terminate", "wrath_of_god", "rapid_hybridization"]
    )
    def test_the_card_says_it(self, registry, card_id):
        card = registry.get(card_id)
        assert "can't be regenerated" in card.oracle_text
        destroys = [e for e in card.spell_effects if e.get("op") == "destroy"]
        assert destroys, f"{card_id} prints a destruction"
        assert all(e.get("no_regeneration") for e in destroys)


class TestTheLoaderGuard:
    def test_it_loads_on_destroy(self):
        _validate_effect(
            {"op": "destroy", "objects": {"self_only": True}, "no_regeneration": True},
            "test",
            {},
        )

    def test_it_is_refused_anywhere_else(self):
        """Written on an op that performs no destruction it is read by nobody —
        which is exactly how the clause came to be dropped in the first place."""
        with pytest.raises(DslError, match="only works on 'destroy'"):
            _validate_effect(
                {"op": "regenerate", "objects": {"self_only": True},
                 "no_regeneration": True},
                "test",
                {},
            )

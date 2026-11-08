"""Maskwood Nexus -- a type grant that reaches past the battlefield.

    Creatures you control are every creature type. The same is true for
    creature spells you control and creature cards you own that aren't on
    the battlefield.

The `add_subtype` static with ``off_battlefield``. Without the flag the grant
is layer 4 on permanents only, so a creature card in a hand, a library or a
graveyard keeps its printed type line: a tutor for "a Squirrel card" passes
it by and a "Squirrel spells cost {1} less" never discounts it -- which is the
half of the card the second sentence prints. The rules behind it:

* **"Creature spells you control"** -- a spell on the stack is its
  controller's, and 601.2f locks its cost in while it is already there, so a
  cost reduction and a cast trigger see the type.
* **"Creature cards you own"** -- every other zone is its owner's (108.3), so
  an opponent's cards are untouched, and a noncreature card is not a creature
  card.
* **611.3a** -- the effect is the permanent's static, so it ends the moment the
  source leaves the battlefield.
* **ADR 0001** -- a static's filter reads printed characteristics, so a
  Squirrel lord's anthem does not see a Squirrel the Nexus made.

`t_ob_nexus` in `tests/data/off_battlefield_subtype.cards.json` is Maskwood
Nexus's line narrowed to Squirrel; Maskwood Nexus itself is the shipped
witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import matches
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import spell_cost_reduction
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, only_oid, pt, settle, static_probe

NEXUS = "t_ob_nexus"
BATTLEFIELD_NEXUS = "t_ob_bad_nexus"
PATRON = "t_ob_patron"
LORD = "t_ob_lord"
BEARS = "grizzly_bears"
BOLT = "lightning_bolt"


def card(game, card_id: str, pid: int) -> int:
    """The one object of ``card_id`` that ``pid`` owns, in whatever zone it is."""
    [oid] = [
        o.oid for o in game.state.objects.values() if o.def_id == card_id and o.owner == pid
    ]
    return oid


def is_squirrel(game, oid: int, zone: str, controller: str = "you") -> bool:
    """Would a selector searching ``zone`` for a Squirrel card find ``oid``?"""
    ctx = EffectContext(state=game.state, controller=0)
    selector = {"zone": zone, "controller": controller, "subtypes": ["Squirrel"]}
    return matches(ctx, oid, selector)


def position(builder, *, nexus=NEXUS, mine=(), zone="hand", theirs=(BEARS,)):
    """Player 0 with the Nexus and ``mine`` in ``zone``; player 1 holds ``theirs``.

    Returns the game.
    """
    b = builder(players=2).battlefield(0, [nexus, "forest"]).hand(1, list(theirs))
    b = getattr(b, zone)(0, list(mine)) if zone != "battlefield" else b.battlefield(0, list(mine))
    return b.build()


class TestOnTheBattlefield:
    def test_a_creature_you_control_is_a_squirrel(self, builder):
        game = position(builder, mine=[BEARS], zone="battlefield")
        bears = card(game, BEARS, 0)

        assert "Squirrel" in chars(game.state, bears).subtypes
        assert "Bear" in chars(game.state, bears).subtypes
        assert is_squirrel(game, bears, "battlefield")

    def test_an_opponents_creature_is_not(self, builder):
        game = builder(players=2).battlefield(0, [NEXUS]).battlefield(1, [BEARS]).build()

        assert "Squirrel" not in chars(game.state, card(game, BEARS, 1)).subtypes


class TestOffTheBattlefield:
    @pytest.mark.parametrize("zone", ["hand", "graveyard", "library"])
    def test_a_creature_card_you_own_is_a_squirrel(self, builder, zone):
        game = position(builder, mine=[BEARS], zone=zone)
        bears = card(game, BEARS, 0)

        assert "Squirrel" in chars(game.state, bears).subtypes
        assert is_squirrel(game, bears, zone)

    def test_a_creature_card_in_exile_is_a_squirrel(self, builder):
        game = position(builder, mine=[BEARS], zone="graveyard")
        bears = card(game, BEARS, 0)
        move_object(game.state, bears, Zone.EXILE)

        assert is_squirrel(game, bears, "exile")

    def test_without_the_flag_the_grant_stops_at_the_battlefield(self, builder):
        """The near miss: the same static, battlefield only."""
        game = position(builder, nexus=BATTLEFIELD_NEXUS, mine=[BEARS], zone="hand")
        bears = card(game, BEARS, 0)

        assert "Squirrel" not in chars(game.state, bears).subtypes
        assert not is_squirrel(game, bears, "hand")

    def test_an_opponents_card_is_untouched(self, builder):
        game = position(builder)
        theirs = card(game, BEARS, 1)

        assert "Squirrel" not in chars(game.state, theirs).subtypes
        assert not is_squirrel(game, theirs, "hand", controller="opponent")

    def test_a_noncreature_card_is_untouched(self, builder):
        game = position(builder, mine=[BOLT], zone="hand")
        bolt = card(game, BOLT, 0)

        assert "Squirrel" not in chars(game.state, bolt).subtypes
        assert not is_squirrel(game, bolt, "hand")


class TestOnTheStack:
    def test_a_creature_spell_costs_less_as_a_squirrel_spell(self, builder):
        """{1}{G} less {1} is castable off one Forest -- only as a Squirrel."""
        game = (
            builder(players=2).battlefield(0, [NEXUS, PATRON, "forest"]).hand(0, [BEARS]).build()
        )
        bears = card(game, BEARS, 0)

        assert spell_cost_reduction(game.state, 0, game.state.card_of(game.state.objects[bears])) == 1
        action_for_card(game, ActionKind.CAST, BEARS)

    def test_casting_it_triggers_on_a_squirrel_spell(self, builder):
        game = (
            builder(players=2).battlefield(0, [NEXUS, PATRON, "forest"]).hand(0, [BEARS]).build()
        )
        life = game.state.players[0].life
        game.apply(action_for_card(game, ActionKind.CAST, BEARS))
        bears = card(game, BEARS, 0)

        assert "Squirrel" in chars(game.state, bears).subtypes
        settle(game)

        assert game.state.players[0].life == life + 1
        assert game.state.objects[bears].zone is Zone.BATTLEFIELD

    def test_without_the_nexus_it_is_neither(self, builder):
        game = builder(players=2).battlefield(0, [PATRON, "forest"]).hand(0, [BEARS]).build()
        bears = card(game, BEARS, 0)

        assert spell_cost_reduction(game.state, 0, game.state.card_of(game.state.objects[bears])) == 0
        with pytest.raises(AssertionError):
            action_for_card(game, ActionKind.CAST, BEARS)

    def test_an_opponents_spell_is_not_discounted(self, builder):
        game = builder(players=2).battlefield(0, [NEXUS]).battlefield(1, [PATRON]).build()
        bears_card = game.state.registry.get(BEARS)

        assert spell_cost_reduction(game.state, 1, bears_card) == 0
        assert spell_cost_reduction(game.state, 0, bears_card) == 0


class TestTheGrantEnds:
    def test_when_the_nexus_leaves(self, builder):
        game = position(builder, mine=[BEARS], zone="graveyard")
        bears = card(game, BEARS, 0)
        assert is_squirrel(game, bears, "graveyard")

        move_object(game.state, only_oid(game, NEXUS, 0), Zone.GRAVEYARD)

        assert "Squirrel" not in chars(game.state, bears).subtypes
        assert not is_squirrel(game, bears, "graveyard")


class TestStaticsDoNotReadIt:
    def test_a_squirrel_lord_does_not_pump_a_squirrel_the_nexus_made(self, builder):
        """ADR 0001: another static's filter reads the printed face."""
        game = builder(players=2).battlefield(0, [NEXUS, LORD, BEARS]).build()
        bears = only_oid(game, BEARS, 0)

        assert "Squirrel" in chars(game.state, bears).subtypes
        assert pt(game, bears) == (2, 2)


NEXUS_STATIC = {
    "effect": "add_subtype",
    "affects": {"types": ["Creature"]},
    "subtypes": ["Squirrel"],
    "off_battlefield": True,
}


def compile_probe(static: dict) -> None:
    compile_card(CardModel.model_validate(static_probe(static)))


class TestTheLoaderRefuses:
    def test_the_nexus_static_loads(self):
        compile_probe(NEXUS_STATIC)

    def test_the_flag_on_another_static(self):
        with pytest.raises(DslError, match="off_battlefield"):
            compile_probe(
                {"effect": "buff", "affects": {"types": ["Creature"]}, "power": {"const": 1},
                 "toughness": {"const": 1}, "off_battlefield": True}
            )

    def test_without_affects(self):
        with pytest.raises(DslError, match="needs 'affects'"):
            compile_probe({k: v for k, v in NEXUS_STATIC.items() if k != "affects"})

    def test_a_self_only_grant(self):
        with pytest.raises(DslError, match="changeling"):
            compile_probe({**NEXUS_STATIC, "affects": {"self_only": True}})

    @pytest.mark.parametrize("key", [{"tapped": True}, {"any_of": [{"attacking": True}, {"subtypes": ["Elf"]}]}])
    def test_a_board_state_clause(self, key):
        with pytest.raises(DslError, match="printed face"):
            compile_probe({**NEXUS_STATIC, "affects": {"types": ["Creature"], **key}})

    def test_an_opponents_cards(self):
        with pytest.raises(DslError, match="controller"):
            compile_probe(
                {**NEXUS_STATIC, "affects": {"types": ["Creature"], "controller": "opponent"}}
            )

    def test_a_granted_copy(self):
        probe = static_probe(
            {"effect": "grant_ability", "affects": {"types": ["Creature"]}, "ability": 0}
        )
        probe["grantable_abilities"] = [{"kind": "static", "text": "Probe.", **NEXUS_STATIC}]
        with pytest.raises(DslError, match="granted one"):
            compile_card(CardModel.model_validate(probe))

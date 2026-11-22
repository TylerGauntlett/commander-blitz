"""A discount for abilities of cards in your graveyard that stops at one mana.

    "As long as you control your commander, activated abilities of cards in
    your graveyard cost {2} less to activate. This effect can't reduce the
    mana in that ability's activation cost to less than one mana."
                                        -- Convergence of Dominion

Two clauses `ability_cost_reduction` did not have. ``from_graveyard`` picks the
activation out by where its **source** is -- a card in the static's
controller's graveyard (an unearth, a Reassembling Skeleton) -- and never a
permanent with the same ability. ``mana_floor`` bounds this static's cut so the
cost keeps at least that many mana symbols, coloured pips counted: {2} becomes
{1}, {1}{B} becomes {B}, and {B} stays {B}. Rule 601.2f clamps every reduction
at zero generic; without the floor a {2} graveyard ability would be free, which
the card forbids, and without ``from_graveyard`` it would discount the
battlefield too, a stronger card.

The floor is this effect's alone: an unfloored discount beside it still reaches
zero, so the floored cut is applied after the others and only takes what they
left above the floor.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import ability_mana
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, only_oid, settle

NODE = "t_acf_node"  # floored {2} discount, gated on controlling your commander
PLAIN = "t_acf_plain"  # the same discount with no floor and no condition
TWO = "t_acf_two"  # graveyard: {2}
PIP = "t_acf_pip"  # graveyard: {B}
ENGINE = "t_acf_engine"  # battlefield: {2}
SKELETON = "reassembling_skeleton"  # graveyard: {1}{B}
COMMANDER = "grizzly_bears"


def position(builder, *, mine=(NODE, COMMANDER), graveyard=(TWO, PIP, SKELETON), theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 6 + list(mine))
        .battlefield(1, ["island", *theirs])
        .graveyard(0, list(graveyard))
        .graveyard(1, [TWO])
        .library(0, ["swamp"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    if COMMANDER in mine:
        game.state.objects[only_oid(game, COMMANDER, 0)].is_commander = True
    return game


def in_graveyard(game, card_id: str, pid: int = 0) -> int:
    return next(
        oid
        for oid in game.state.players[pid].graveyard
        if game.state.objects[oid].def_id == card_id
    )


def price(game, oid: int, pid: int = 0) -> tuple[int, int]:
    """(generic, total mana) of what activating ``oid``'s first ability costs now."""
    ability = game.state.card_of(game.state.objects[oid]).abilities[0]
    req = ability_mana(game.state, pid, ability.cost, 0, oid, ability=ability)
    return req.generic, req.total


class TestTheFloor:
    def test_two_generic_stops_at_one(self, builder):
        game = position(builder)
        assert price(game, in_graveyard(game, TWO)) == (1, 1)

    def test_a_coloured_pip_counts_toward_the_floor(self, builder):
        game = position(builder)
        assert price(game, in_graveyard(game, SKELETON)) == (0, 1)

    def test_a_single_pip_is_untouched(self, builder):
        game = position(builder)
        assert price(game, in_graveyard(game, PIP)) == (0, 1)

    def test_without_the_floor_two_is_free(self, builder):
        game = position(builder, mine=(PLAIN,))
        assert price(game, in_graveyard(game, TWO)) == (0, 0)

    def test_an_unfloored_discount_still_reaches_zero_beside_it(self, builder):
        """The floor bounds this effect's cut, not the other one's."""
        game = position(builder, mine=(NODE, PLAIN, COMMANDER))
        assert price(game, in_graveyard(game, TWO)) == (0, 0)

    def test_it_is_charged_at_the_floored_price(self, builder):
        game = position(builder)
        two = in_graveyard(game, TWO)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == two
        )
        game.apply(action)
        settle(game)
        assert sum(game.state.objects[o].tapped for o in oids_of(game, "swamp", 0)) == 1
        assert oids_of(game, TWO, 0)


class TestWhichAbilities:
    def test_a_permanents_ability_is_not_discounted(self, builder):
        game = position(builder, mine=(NODE, COMMANDER, ENGINE))
        assert price(game, only_oid(game, ENGINE, 0)) == (2, 2)

    def test_an_opponents_graveyard_is_not_yours(self, builder):
        game = position(builder)
        theirs = in_graveyard(game, TWO, 1)
        assert price(game, theirs, pid=1) == (2, 2)

    def test_it_lifts_without_your_commander(self, builder):
        game = position(builder, mine=(NODE,))
        assert price(game, in_graveyard(game, TWO)) == (2, 2)


class TestTheLoader:
    def _static(self, **over):
        static = {
            "kind": "static",
            "text": "Activated abilities of cards in your graveyard cost {2} less to activate.",
            "effect": "ability_cost_reduction",
            "affects_abilities": {"any": True},
            "activated_by": "you",
            "from_graveyard": True,
            "mana_floor": 1,
            "amount": {"const": 2},
        }
        static.update(over)
        return {k: v for k, v in static.items() if v is not None}

    def compile(self, static):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "t_probe_acf",
                    "name": "Probe Ability Cost Floor",
                    "mana_cost": "{0}",
                    "types": ["Enchantment"],
                    "abilities": [static],
                }
            )
        )

    def test_the_line_loads(self):
        self.compile(self._static())

    def test_any_needs_targeting_without_from_graveyard(self):
        with pytest.raises(DslError, match="'any' needs a 'targeting'"):
            self.compile(self._static(from_graveyard=None))

    def test_affects_is_refused_beside_it(self):
        with pytest.raises(DslError, match="describe permanents"):
            self.compile(self._static(affects={"types": ["Creature"]}))

    def test_only_you_activate_from_your_graveyard(self):
        with pytest.raises(DslError, match="activated_by"):
            self.compile(self._static(activated_by="any"))

    def test_a_floor_below_one_is_refused(self):
        with pytest.raises(DslError, match="mana_floor"):
            self.compile(self._static(mana_floor=0))

    def test_on_another_static_it_is_refused(self):
        with pytest.raises(DslError, match="'from_graveyard' and 'mana_floor' only mean"):
            self.compile(
                {
                    "kind": "static",
                    "text": "Creatures you control get +1/+1.",
                    "effect": "buff",
                    "affects": {"controller": "you"},
                    "power": {"const": 1},
                    "toughness": {"const": 1},
                    "mana_floor": 1,
                }
            )

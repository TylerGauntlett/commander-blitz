"""``colorless: true`` -- a filter for objects with no colour at all.

    "Colorless creatures you control get +2/+2.
     Whenever you cast a colorless spell, you gain 2 life."  -- Forsaken Monument

Rule 105.2c: a colorless object has no colour, and colorless is not a colour.
So none of the colour keys could say it. `colors` is a membership test, and an
empty list is no filter at all -- written that way, the Monument would pump and
pay off every creature and spell. `colors: ["C"]` names no colour. The
effect-side selector could already say it the long way, `not_colors` over all
five. Static, trigger and cost-reduction filters had no way to say it.

One key, `true` only, read the way protection's `from_colorless` reads it, by
what the object lacks:

- **Static filters** read the printed face, like `colors`, because a static may
  not read a colour another static writes.
- **Trigger filters** read the printed face of the spell, as `colors` and
  `min_colors` do.
- **The effect-side selector** reads the derived colours, as `not_colors` does.

`false` is refused at load time rather than read as "no filter". "Colored" is
`min_colors: 1`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy
from tests.conftest import (
    action_for_card,
    cost_reduction_probe,
    oids_of,
    pt,
    settle,
    static_probe,
)

MONUMENT = "t_cl_monument"
PURGE = "t_cl_purge"
CONSTRUCT = "t_construct"  # a colorless 1/1 artifact creature
BEAR = "t_bear"  # a green 2/2


def board(builder, *, hand=(), lands=("island",) * 4, mine=(CONSTRUCT, BEAR)):
    return (
        builder(players=2)
        .hand(0, list(hand))
        .battlefield(0, [MONUMENT, *mine])
        .battlefield(0, list(lands))
        .build()
    )


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


def cast(game, card_id: str) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    settle(game)


class TestTheStatic:
    def test_a_colorless_creature_gets_the_bonus(self, builder):
        game = board(builder)
        assert pt(game, oids_of(game, CONSTRUCT)[0]) == (3, 3)

    def test_a_coloured_creature_does_not(self, builder):
        game = board(builder)
        assert pt(game, oids_of(game, BEAR)[0]) == (2, 2)

    def test_an_opponents_colorless_creature_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [MONUMENT])
            .battlefield(1, [CONSTRUCT])
            .build()
        )
        assert pt(game, oids_of(game, CONSTRUCT, 1)[0]) == (1, 1)

    def test_it_wears_off_with_the_source(self, builder):
        game = board(builder)
        destroy(game.state, oids_of(game, MONUMENT)[0])
        assert pt(game, oids_of(game, CONSTRUCT)[0]) == (1, 1)


class TestTheTrigger:
    def test_a_colorless_spell_gains_two(self, builder):
        game = board(builder, hand=["sol_ring"])
        before = life(game)
        cast(game, "sol_ring")
        assert life(game) == before + 2

    def test_a_colorless_creature_spell_gains_two_and_arrives_pumped(self, builder):
        game = board(builder, hand=[CONSTRUCT], mine=())
        before = life(game)
        cast(game, CONSTRUCT)
        assert life(game) == before + 2
        assert pt(game, oids_of(game, CONSTRUCT)[0]) == (3, 3)

    def test_a_coloured_spell_does_not(self, builder):
        game = board(builder, hand=[BEAR], lands=("forest",) * 4)
        before = life(game)
        cast(game, BEAR)
        assert life(game) == before


class TestTheSelector:
    def test_it_destroys_only_the_colorless_creatures(self, builder):
        game = (
            builder(players=2)
            .hand(0, [PURGE])
            .battlefield(0, [CONSTRUCT, BEAR, "sol_ring"])
            .battlefield(0, ["swamp"] * 2)
            .build()
        )
        cast(game, PURGE)
        assert oids_of(game, CONSTRUCT) == []
        assert len(oids_of(game, BEAR)) == 1
        assert len(oids_of(game, "sol_ring")) == 1, "colorless, but not a creature"


def _load(card: dict) -> None:
    compile_card(CardModel.model_validate(card))


class TestTheLoader:
    def test_the_fixture_loads(self, registry):
        assert registry.get(MONUMENT).abilities

    @pytest.mark.parametrize("value", [False, "yes", 1])
    def test_a_static_refuses_anything_but_true(self, value):
        with pytest.raises(DslError, match="colorless"):
            _load(
                static_probe(
                    {
                        "effect": "buff",
                        "affects": {"types": ["Creature"], "colorless": value},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                    }
                )
            )

    def test_a_trigger_filter_refuses_false(self):
        with pytest.raises(DslError, match="colorless"):
            _load(
                {
                    "id": "probe",
                    "name": "Probe",
                    "oracle_text": "Probe.",
                    "mana_cost": "{W}",
                    "types": ["Enchantment"],
                    "abilities": [
                        {
                            "kind": "triggered",
                            "text": "Probe.",
                            "trigger": {
                                "event": "spell_cast",
                                "controller": "you",
                                "filter": {"colorless": False},
                            },
                            "effects": [
                                {"op": "gain_life", "player": "you", "amount": {"const": 1}}
                            ],
                        }
                    ],
                }
            )

    def test_a_cost_reduction_count_reads_it(self, builder):
        """The fourth reader: a reduction counted over colorless creatures --
        the Construct, not the Bear."""
        card = compile_card(
            cost_reduction_probe({"count": {"types": ["Creature"], "colorless": True}})
        )
        game = (
            builder(players=2)
            .battlefield(0, [CONSTRUCT, CONSTRUCT, BEAR])
            .build()
        )
        assert cost_reduction(game.state, 0, card) == 2

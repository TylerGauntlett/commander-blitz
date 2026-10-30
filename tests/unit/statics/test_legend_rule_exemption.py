"""The legend rule, switched off for some permanents.

    "The "legend rule" doesn't apply to creatures you control."
                                                  -- Council of Reeds

704.5j puts all but one of a player's same-named legendary permanents into the
graveyard. A ``legend_rule_exemption`` static takes the permanents its
``affects`` matches out of that grouping, read by
`player_statics.legend_rule_exempt` from `sba._legend_rule`. Without it Council
of Reeds' own token copy -- legendary, and named alike -- would kill one of the
two the moment it arrived, and the card's second line would do nothing.

The filter is the clause: an opponent's legendary creatures and your legendary
noncreatures are still bound by the rule, and the exemption ends with its source.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.sba import run as run_sba
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of, only_oid

REEDS = "t_lre_reeds"  # "The legend rule doesn't apply to creatures you control."
LEGEND = "t_legend"  # a legendary 2/2 creature
RELIC = "t_lre_relic"  # a legendary artifact


def board(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=False)
    )


class TestTheExemption:
    def test_two_legendary_creatures_named_alike_both_stay(self, builder):
        game = board(builder, mine=[REEDS, LEGEND, LEGEND])
        run_sba(game.state)
        assert len(oids_of(game, LEGEND, 0)) == 2

    def test_the_control(self, builder):
        game = board(builder, mine=[LEGEND, LEGEND])
        run_sba(game.state)
        assert len(oids_of(game, LEGEND, 0)) == 1


class TestTheFilter:
    def test_an_opponents_legends_are_still_bound(self, builder):
        game = board(builder, mine=[REEDS], theirs=[LEGEND, LEGEND])
        run_sba(game.state)
        assert len(oids_of(game, LEGEND, 1)) == 1

    def test_a_legendary_noncreature_is_still_bound(self, builder):
        game = board(builder, mine=[REEDS, RELIC, RELIC])
        run_sba(game.state)
        assert len(oids_of(game, RELIC, 0)) == 1

    def test_it_ends_with_its_source(self, builder):
        game = board(builder, mine=[REEDS, LEGEND, LEGEND])
        run_sba(game.state)
        move_object(game.state, only_oid(game, REEDS), Zone.GRAVEYARD)
        run_sba(game.state)
        assert len(oids_of(game, LEGEND, 0)) == 1


class TestTheLoader:
    def _compile(self, static: dict):
        model = CardModel.model_validate(
            {
                "id": "t_lre_bad",
                "name": "Bad Council",
                "types": ["Enchantment"],
                "abilities": [{"kind": "static", "text": "", **static}],
            }
        )
        return compile_card(model)

    def test_affects_is_required(self):
        with pytest.raises(DslError, match="needs 'affects'"):
            self._compile({"effect": "legend_rule_exemption"})

    def test_an_amount_is_refused(self):
        with pytest.raises(DslError, match="not a quantity"):
            self._compile(
                {
                    "effect": "legend_rule_exemption",
                    "affects": {"controller": "you", "types": ["Creature"]},
                    "amount": {"const": 1},
                }
            )

    def test_the_printed_shape_loads(self):
        card = self._compile(
            {
                "effect": "legend_rule_exemption",
                "affects": {"controller": "you", "types": ["Creature"]},
            }
        )
        assert card.abilities[0].static["effect"] == "legend_rule_exemption"

"""Thundermane Dragon — a filtered permission off the top of the library, with a rider.

    You may cast creature spells with power 4 or greater from the top of your
    library. If you cast a creature spell this way, it gains haste until end of
    turn.

Bolas's Citadel's permission with the other half changed. The Citadel swaps the
price to life and reaches every nonland card; this one keeps the printed price
and reaches only what its `affects_spells` filter names, so the top card is
offered every line it would have in hand -- and a board holding both offers both
prices, side by side, because 601.2b lets the caster pick which permission to
cast under.

**The filter reads the card where it is.** "Power 4 or greater" is asked of the
top card with its characteristic-defining abilities applied: 604.3 gives a CDA
its function in every zone, so a `*/*` counting your creatures is a number in a
library too. A filter that read only the printed face would see a 0 and refuse a
card the printed sentence admits.

**The rider is owed to the permanent.** "It gains haste until end of turn" is
said of the spell and kept by the creature it becomes, which is the staging
problem Arena of Glory's mana already solved: the keyword rides the spell, is
handed over as it enters, and is swept at cleanup. Without the rider the card is
a slower one -- the creature cast off the top sits a turn like any other.
"Cast this way" is the lane the cast took: a creature cast from hand, or off the
top through a Citadel standing beside it, gains nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import keywords, pass_until, settle

THUNDERMANE = "t_thundermane"
CITADEL = "t_citadel"
BRUTE = "t_spf_brute"  # {3}{G} 4/4
RUNT = "t_spf_runt"  # {2}{G} 3/3
STAR = "t_star_beast"  # {1}{G}, power = creatures you control
BEAR = "t_bear"  # {1}{G} 2/2


def board(builder, *, top: str = BRUTE, lands: int = 4, permanents=(THUNDERMANE,), extra=()):
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * lands + list(permanents) + list(extra))
        .hand(0, ["plains"])
        .life(0, 40)
        .library(0, [top] + ["forest"] * 10)
        .build()
    )


def top_lines(game):
    top = game.state.players[0].library[0]
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == top]


def cast_top(game, *, from_library_top: bool = False):
    top = game.state.players[0].library[0]
    lines = [a for a in top_lines(game) if a.from_library_top == from_library_top]
    assert lines, "the top card was not offered on that line"
    game.apply(lines[0])
    settle(game)
    return top


class TestTheFilter:
    def test_a_power_four_creature_on_top_is_castable(self, builder):
        assert top_lines(board(builder))

    def test_a_power_three_creature_is_not(self, builder):
        assert top_lines(board(builder, top=RUNT)) == []

    def test_without_the_permanent_nothing_is(self, builder):
        assert top_lines(board(builder, permanents=())) == []

    def test_a_characteristic_defining_power_is_read_in_the_library(self, builder):
        """604.3: four creatures on the board make the `*/*` a 4 where it sits."""
        assert top_lines(board(builder, top=STAR, extra=[BEAR] * 4))

    def test_and_three_make_it_a_three(self, builder):
        assert top_lines(board(builder, top=STAR, extra=[BEAR] * 3)) == []


class TestThePrintedPrice:
    def test_it_costs_its_mana_and_no_life(self, builder):
        game = board(builder)
        oid = cast_top(game)
        assert game.state.objects[oid].on_battlefield
        assert game.state.players[0].life == 40
        tapped = [
            o for o in game.state.battlefield_objects(0) if o.def_id == "forest" and o.tapped
        ]
        assert len(tapped) == 4

    def test_one_land_short_is_not_offered(self, builder):
        assert top_lines(board(builder, lands=3)) == []


class TestTheHasteRider:
    def test_the_creature_cast_this_way_has_haste(self, builder):
        game = board(builder)
        oid = cast_top(game)
        assert "haste" in keywords(game, oid)

    def test_it_wears_off_at_end_of_turn(self, builder):
        game = board(builder)
        oid = cast_top(game)
        pass_until(game, lambda g: g.state.turn > 1)
        assert "haste" not in keywords(game, oid)

    def test_the_same_creature_cast_from_hand_gains_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + [THUNDERMANE])
            .hand(0, [BRUTE])
            .library(0, ["forest"] * 10)
            .build()
        )
        oid = game.state.players[0].hand[0]
        line = next(
            a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid
        )
        game.apply(line)
        settle(game)
        assert game.state.objects[oid].on_battlefield
        assert "haste" not in keywords(game, oid)


class TestBesideTheCitadel:
    def test_both_prices_are_offered(self, builder):
        game = board(builder, permanents=(THUNDERMANE, CITADEL))
        lanes = {a.from_library_top for a in top_lines(game)}
        assert lanes == {True, False}

    def test_the_citadel_line_is_not_cast_this_way(self, builder):
        """Paid for in life under the Citadel, so Thundermane's rider is not owed."""
        game = board(builder, permanents=(THUNDERMANE, CITADEL))
        oid = cast_top(game, from_library_top=True)
        assert game.state.players[0].life == 36
        assert "haste" not in keywords(game, oid)

    def test_the_citadel_alone_still_reaches_what_the_filter_refuses(self, builder):
        game = board(builder, top=BEAR, permanents=(THUNDERMANE, CITADEL))
        assert {a.from_library_top for a in top_lines(game)} == {True}


def _permission(**extra):
    text = "You may cast creature spells from the top of your library."
    return CardModel.model_validate(
        {
            "id": "t_probe_top",
            "name": "Test Probe Top",
            "oracle_text": text,
            "mana_cost": "{3}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "static",
                    "text": text,
                    "effect": "cast_from_library_top",
                    "affects_player": "you",
                    **extra,
                }
            ],
        }
    )


class TestTheLoader:
    def test_a_filter_stands_in_for_the_price(self):
        card = compile_card(
            _permission(affects_spells={"types": ["Creature"]}, cast_gains_keywords=["haste"]),
            source="test",
        )
        static = card.abilities[0].static
        assert static["affects_spells"] == {"types": ["Creature"]}
        assert static["cast_gains_keywords"] == ["haste"]
        assert "pay_life_instead" not in static

    def test_an_empty_filter_is_refused(self):
        with pytest.raises(DslError, match="empty filter"):
            compile_card(_permission(affects_spells={}), source="test")

    def test_a_controller_key_is_refused(self):
        with pytest.raises(DslError, match="controller"):
            compile_card(
                _permission(affects_spells={"types": ["Creature"], "controller": "you"}),
                source="test",
            )

    def test_a_malformed_power_comparison_is_refused(self):
        with pytest.raises(DslError, match="power"):
            compile_card(
                _permission(affects_spells={"types": ["Creature"], "power": ">=4"}),
                source="test",
            )

    def test_an_unknown_rider_keyword_is_refused(self):
        with pytest.raises(DslError, match="unknown keyword"):
            compile_card(
                _permission(affects_spells={"types": ["Creature"]}, cast_gains_keywords=["zoom"]),
                source="test",
            )

    def test_the_rider_means_nothing_on_another_static(self):
        text = "Creatures you control have flying."
        model = CardModel.model_validate(
            {
                "id": "t_probe_rider",
                "name": "Test Probe Rider",
                "oracle_text": text,
                "mana_cost": "{3}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": text,
                        "effect": "grant_keyword",
                        "affects": {"types": ["Creature"]},
                        "keywords": ["flying"],
                        "cast_gains_keywords": ["haste"],
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="cast_gains_keywords"):
            compile_card(model, source="test")

"""Elder Brain: "you may spend mana as though it were mana of any color to cast it".

    …You may play lands and cast spells from among the exiled cards for as long
    as they remain exiled. If you cast a spell this way, you may spend mana as
    though it were mana of any color to cast it.

The cards Elder Brain takes are an *opponent's* hand, so without the waiver they
are mostly uncastable: a black deck stealing a green hand holds cards it has no
mana for, and the printed card is the theft plus the means to use it.

`grant_playable`'s `any_type` is the near miss, and it is strictly broader.
"Mana of any **type**" (Valigarmanda) names the colourless type too, so it lets
coloured mana pay ``{C}``; "as though it were mana of any **color**" does not --
mana spent as though it had a colour is still not colourless mana. What the
colour waiver *does* reach is colourless mana spent on a coloured symbol: the
Mycosynth Lattice ruling is that colourless mana may be spent as though it had a
colour, so a Sol Ring pays ``{B}{B}`` here. The gap record had that half
backwards, and `TestColourlessManaPaysColouredSymbols` pins the ruling.

609.4b: the waiver changes only how the cost may be paid. Mana value, colour and
the mana actually spent are what they were, which is why `ManaCost.as_any_color`
leaves ``text`` alone and nothing reads mana value off it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaCost
from tests.conftest import pass_until

THEFT = "t_mind_theft"
STRICT = "t_strict_theft"  # the same without the waiver
BLACK = "t_black_draw"  # {B}{B}
COLORLESS = "t_colorless_draw"  # {C}
HYBRID = "t_hybrid_draw"  # {2/W}{2/W}


def steal(builder, *, theft=THEFT, lands=("plains", "plains"), theirs=(BLACK,), mine=()):
    """Seat 0 casts the theft off whatever ``lands`` it has; seat 1's hand is ``theirs``."""
    game = (
        builder(players=2)
        .battlefield(0, list(lands))
        .hand(0, [theft, *mine])
        .hand(1, list(theirs))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .build()
    )
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == theft
        )
    )
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return game


def exiled(game, card_id: str) -> int:
    return next(
        oid for oid in game.state.players[1].exile if game.state.objects[oid].def_id == card_id
    )


def cast_lines(game, oid: int):
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


class TestTheCost:
    """`as_any_color`: every colour folds, ``{C}`` does not."""

    def test_coloured_pips_become_generic(self):
        cost = ManaCost.parse("{1}{R}{G}").as_any_color()
        assert cost.generic == 3
        assert not any(cost.colored)

    def test_the_colourless_pip_stays(self):
        # The one difference from `as_any_type`.
        cost = ManaCost.parse("{C}{R}").as_any_color()
        assert cost.colored[SYMBOL_INDEX["C"]] == 1
        assert cost.generic == 1
        assert ManaCost.parse("{C}{R}").as_any_type().colored[SYMBOL_INDEX["C"]] == 0

    def test_a_hybrid_pip_costs_one_mana_of_anything(self):
        # {2/W}'s white half is now payable with any single mana.
        cost = ManaCost.parse("{2/W}{W/U}").as_any_color()
        assert cost.generic == 2
        assert cost.hybrid == ()

    def test_x_and_the_printed_cost_survive(self):
        printed = ManaCost.parse("{X}{B}{B}")
        cost = printed.as_any_color()
        assert cost.x_count == 1
        assert cost.text == printed.text
        assert printed.mana_value() == 2


class TestTheWaiver:
    def test_the_stolen_black_spell_is_castable_off_plains(self, builder):
        game = steal(builder)
        assert cast_lines(game, exiled(game, BLACK))

    def test_without_the_waiver_it_is_not(self, builder):
        game = steal(builder, theft=STRICT)
        oid = exiled(game, BLACK)
        assert game.state.objects[oid].playable_by == 0, "the permission itself is there"
        assert cast_lines(game, oid) == []

    def test_it_is_actually_paid_and_resolves(self, builder):
        game = steal(builder, lands=("plains", "plains", "plains"))
        oid = exiled(game, BLACK)
        game.apply(cast_lines(game, oid)[0])
        assert sum(1 for o in game.state.battlefield_objects(0) if o.tapped) == 2
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert oid in game.state.players[1].graveyard

    def test_the_hybrid_pips_cost_one_each(self, builder):
        game = steal(builder, lands=("island", "island"), theirs=(HYBRID,))
        assert cast_lines(game, exiled(game, HYBRID))

    def test_it_does_not_reach_the_casters_own_spells(self, builder):
        """"…to cast **it**": the caster's other spells are paid for normally."""
        game = steal(builder, mine=(BLACK,))
        mine = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == BLACK)
        assert cast_lines(game, mine) == []

    def test_it_leaves_with_the_permission(self, builder):
        from commanderblitz.engine.zones import move_object

        game = steal(builder)
        oid = exiled(game, BLACK)
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert game.state.objects[oid].playable_any_color is False


class TestColourlessManaPaysColouredSymbols:
    def test_a_sol_ring_pays_black_black(self, builder):
        game = steal(builder, lands=("sol_ring",))
        assert cast_lines(game, exiled(game, BLACK))


class TestTheColourlessSymbolIsNotWaived:
    def test_plains_cannot_pay_c(self, builder):
        game = steal(builder, lands=("plains", "plains"), theirs=(COLORLESS,))
        assert cast_lines(game, exiled(game, COLORLESS)) == []

    def test_colourless_mana_still_can(self, builder):
        game = steal(builder, lands=("sol_ring",), theirs=(COLORLESS,))
        assert cast_lines(game, exiled(game, COLORLESS))


class TestTheLoader:
    def spell(self, effect):
        return {
            "id": "t_probe_any_color",
            "name": "Probe Any Color",
            "mana_cost": "{0}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
        }

    def compile(self, effect):
        return compile_card(CardModel.model_validate(self.spell(effect)))

    def test_on_a_permission_it_loads(self):
        self.compile({"op": "exile", "objects": {"zone": "hand", "controller": "opponent",
                      "count": "all"}, "playable": "while_exiled", "any_color": True})
        self.compile({"op": "grant_playable", "objects": {"zone": "exile", "count": "all"},
                      "any_color": True})

    def test_without_a_permission_it_is_refused(self):
        with pytest.raises(DslError, match="any_color"):
            self.compile({"op": "exile", "objects": {"zone": "hand", "controller": "opponent",
                          "count": "all"}, "any_color": True})

    def test_beside_any_type_it_is_refused(self):
        with pytest.raises(DslError, match="any_color"):
            self.compile({"op": "grant_playable", "objects": {"zone": "exile", "count": "all"},
                          "any_color": True, "any_type": True})

"""A triggered mana ability that adds "one mana of **any color**".

    Regal Behemoth -- "Whenever you tap a land for mana while you're the
    monarch, add an additional one mana of any color."

Crypt Ghast's `add_mana_on_tap` adds a literal, and Utopia Sprawl's
`{"chosen_color_of": "self"}` a colour fixed when the Aura entered. Neither says
this card: the colour is chosen each time, by the tapping player, as the
triggered mana ability resolves (605.1b, 605.4a). Writing a fixed `{G}` would be
a narrower card that never fixes a colour.

`{"any_color": 1}` keeps the rule that a mana ability never stops to ask inside a
payment: the solver is the one picking there, so `costs._sources_of` offers each
of the land's yields once per colour and `pay_mana` hands its pick back to
`activate_mana_ability`. A land tapped **by hand** (`Game._activate_mana`) asks
its player. The witness is that one Forest and one extra pays a spell whose
fifth pip only the extra can make.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability, mana_sources, pay_mana
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaCost
from tests.conftest import oids_of

BEHEMOTH = "t_any_color_behemoth"
RAINBOW = "t_any_color_rainbow"  # {W}{U}{B}{R}{G}
FILTER = "t_any_color_filter"  # {1}, {T}: Add {G}.

G = SYMBOL_INDEX["G"]
U = SYMBOL_INDEX["U"]


def position(builder, mine=(), *, hand=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .hand(0, list(hand))
        .library(0, ["forest"] * 10)
        .build()
    )


class TestTheSolverPicks:
    def test_each_colour_is_a_yield(self, builder):
        game = position(builder, [BEHEMOTH, "forest"])
        forest = oids_of(game, "forest", 0)[0]
        (source,) = [s for s in mana_sources(game.state, 0) if s.oid == forest]
        assert sorted(source.options) == sorted(
            tuple(2 if i == G == c else 1 if i in (G, c) else 0 for i in range(6))
            for c in range(5)
        )

    def test_it_pays_the_colour_the_land_cannot_make(self, builder):
        game = position(builder, [BEHEMOTH, "plains", "island", "swamp", "forest"])
        assert pay_mana(game.state, 0, ManaCost.parse("{W}{U}{B}{R}{G}").with_x(0))

    def test_without_the_behemoth_it_cannot(self, builder):
        game = position(builder, ["plains", "island", "swamp", "forest"])
        assert not pay_mana(game.state, 0, ManaCost.parse("{W}{U}{B}{R}{G}").with_x(0))

    def test_legality_offers_the_spell_the_extra_affords(self, builder):
        game = position(
            builder, [BEHEMOTH, "plains", "island", "swamp", "forest"], hand=[RAINBOW]
        )
        assert any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == RAINBOW
            for a in game.legal_actions()
        )

    def test_the_extra_pip_is_the_behemoths(self, builder):
        game = position(builder, [BEHEMOTH, "forest"])
        forest = oids_of(game, "forest", 0)[0]
        activate_mana_ability(game.state, forest, 0, 0, extra_colors=(U,))
        pool = game.state.players[0].mana_pool
        assert pool.amounts[G] == 1 and pool.amounts[U] == 1

    def test_with_no_pick_named_it_adds_nothing(self, builder):
        """`activate_mana_ability` never asks; the pick is its caller's."""
        game = position(builder, [BEHEMOTH, "forest"])
        activate_mana_ability(game.state, oids_of(game, "forest", 0)[0], 0, 0)
        assert sum(game.state.players[0].mana_pool.amounts) == 1


class TestByHandItAsks:
    def test_the_player_names_the_colour(self, builder):
        # A Bear in hand keeps the game at the main phase with priority; the
        # Forest pays the filter's {1}.
        game = position(builder, [BEHEMOTH, FILTER, "forest"], hand=["t_bear"])
        filt = oids_of(game, FILTER, 0)[0]
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == filt
            )
        )
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_MODE
        blue = next(
            a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == U
        )
        game.apply(blue)
        # The filter's {G} and the picked {U}. The Forest's own extra was the
        # solver's pick, spent with the Forest's {G} on the {1}.
        amounts = game.state.players[0].mana_pool.amounts
        assert amounts[U] >= 1 and amounts[G] >= 1


class TestTheLoader:
    def card(self, add_mana):
        return CardModel.model_validate(
            {
                "id": "t_bad_any_color",
                "name": "Test Bad Any Color",
                "oracle_text": "Whenever you tap a land for mana, add an additional one mana of any color.",
                "mana_cost": "{2}{G}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Whenever you tap a land for mana, add an additional one mana of any color.",
                        "effect": "add_mana_on_tap",
                        "affects_player": "you",
                        "tapped_permanent": {"types": ["Land"]},
                        "add_mana": add_mana,
                    }
                ],
            }
        )

    def test_the_shape_loads(self):
        compile_card(self.card({"any_color": 1}), source="t")

    @pytest.mark.parametrize("add_mana", [{"any_color": 2}, {"any_color": 1, "x": 1}])
    def test_another_count_is_refused(self, add_mana):
        with pytest.raises(DslError):
            compile_card(self.card(add_mana), source="t")

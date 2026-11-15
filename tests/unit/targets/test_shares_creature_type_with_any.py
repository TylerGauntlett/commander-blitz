""""…a creature card that shares a creature type with **a creature you control**."

    Descendants' Path -- "At the beginning of your upkeep, reveal the top card
    of your library. If it's a creature card that shares a creature type with a
    creature you control, you may cast it without paying its mana cost. If you
    don't cast it, put it on the bottom of your library."

`shares_a_creature_type_with` compared against exactly one object -- `"self"` or a
binding -- so "a creature you control" had no spelling: the printed test is
against the *union* of every such creature's types, and any one of them sharing
a type is enough. A nested selector says it: `{"types": ["Creature"],
"controller": "you"}` gathers the creature types of every matching object on
the battlefield, and the checked object is left out of its own pool, so a
creature never shares a type with itself.

Creature types only (205.3m), read through `creature_types_of` like the named
form, so a changeling on either side shares with everything.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import matches
from commanderblitz.engine.errors import DslError

RAPTOR = "t_reveal_raptor"  # a vanilla Dinosaur
BEAR = "t_bear"
YOURS = {"types": ["Creature"], "controller": "you"}


def library_match(builder, *, mine=(), theirs=(), top=RAPTOR, against=None) -> bool:
    game = (
        builder(players=2)
        .battlefield(0, ["forest", *mine])
        .battlefield(1, list(theirs))
        .library(0, [top, "forest"])
        .build(advance=False)
    )
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    oid = game.state.players[0].library[0]
    selector = {
        "zone": "library",
        "types": ["Creature"],
        "shares_a_creature_type_with": against or YOURS,
    }
    return matches(ctx, oid, selector)


class TestAgainstEveryCreatureYouControl:
    def test_a_dinosaur_card_shares_with_a_dinosaur_you_control(self, builder):
        assert library_match(builder, mine=[RAPTOR])

    def test_any_one_of_several_is_enough(self, builder):
        assert library_match(builder, mine=[BEAR, RAPTOR])

    def test_no_shared_type_does_not_match(self, builder):
        assert not library_match(builder, mine=[BEAR])

    def test_no_creatures_means_nothing_to_share_with(self, builder):
        assert not library_match(builder)

    def test_an_opponents_dinosaur_does_not_count(self, builder):
        assert not library_match(builder, theirs=[RAPTOR])

    def test_the_selector_decides_whose(self, builder):
        assert library_match(
            builder,
            theirs=[RAPTOR],
            against={"types": ["Creature"], "controller": "opponent"},
        )


class TestNotItself:
    def test_a_creature_does_not_share_a_type_with_itself(self, builder):
        """The checked object is left out of the pool it is compared against."""
        game = builder(players=2).battlefield(0, [RAPTOR]).build(advance=False)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        (oid,) = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == RAPTOR]
        assert not matches(ctx, oid, {"shares_a_creature_type_with": YOURS})

    def test_a_second_dinosaur_on_the_battlefield_does(self, builder):
        game = builder(players=2).battlefield(0, [RAPTOR, RAPTOR]).build(advance=False)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == RAPTOR)
        assert matches(ctx, oid, {"shares_a_creature_type_with": YOURS})


class TestTheLoaderRefuses:
    def card(self, shares):
        return CardModel.model_validate(
            {
                "id": "t_bad_shares",
                "name": "Test Bad Shares",
                "oracle_text": "Destroy target creature.",
                "mana_cost": "{1}{B}",
                "types": ["Sorcery"],
                "spell_effects": [
                    {
                        "op": "destroy",
                        "objects": {
                            "types": ["Creature"],
                            "count": "all",
                            "shares_a_creature_type_with": shares,
                        },
                    }
                ],
            }
        )

    @pytest.mark.parametrize("shares", [{}, {"no_such_key": 1}, 3, ""])
    def test_a_malformed_comparison(self, shares):
        with pytest.raises(DslError):
            compile_card(self.card(shares), source="t")

    def test_a_selector_loads(self):
        compile_card(self.card(YOURS), source="t")

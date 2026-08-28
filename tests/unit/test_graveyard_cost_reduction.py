"""Cyan, Vengeful Samurai — "costs {1} less for each creature card in your graveyard".

There was no third place a spell's own price could be lowered from. The
card-level `cost_reduction` (and the cost-node `mana_reduction` it shares a
language with) restricted its counting filter to `COST_REDUCTION_ZONES`, so a
graveyard filter was a load error rather than a silent zero -- correctly, since
`costs._reduction_matches` walked only those zones. And the battlefield
`spell_cost_reduction` static is the wrong shape twice over: it discounts a
*different* card, and its magnitude comes from `static_value_keys`, whose
`count` is filtered by `static_filter_keys` -- a set with no `zone` key at all.

So the graveyard joined the walked set, on the same test the command zone
passed: it is **public**, and it is **readable before anything is on the
stack**, which is the whole requirement for a zone a price can be computed from.
The hand is neither, and is what the two loader tests now use as the zone
nothing walks.

Cards are counted in their *owner's* graveyard (400.3), which is what
`controller: "you"` narrows to -- the same ownership keys that narrow the
command zone.
"""

from __future__ import annotations

import pytest

from automtg.engine.costs import cost_reduction
from automtg.engine.enums import ActionKind

CYAN = "t_cyan"
BEAR = "t_bear"


def board(builder, *, buried: int = 0, theirs: int = 0):
    return (
        builder(players=2)
        .hand(0, [CYAN])
        .battlefield(0, ["mountain"] * 6)
        .graveyard(0, [BEAR] * buried)
        .graveyard(1, [BEAR] * theirs)
        .build(advance=False)
    )


def discount(game, registry) -> int:
    return cost_reduction(game.state, 0, registry.get(CYAN))


class TestItCountsTheGraveyard:
    def test_an_empty_graveyard_is_no_discount(self, builder, registry):
        assert discount(board(builder), registry) == 0

    def test_one_creature_card_is_one_less(self, builder, registry):
        assert discount(board(builder, buried=1), registry) == 1

    def test_it_scales(self, builder, registry):
        assert discount(board(builder, buried=4), registry) == 4


class TestItIsYourGraveyardOnly:
    def test_an_opponents_graveyard_does_not_discount(self, builder, registry):
        """"in **your** graveyard" -- the ownership keys narrow it, as in the
        command zone."""
        assert discount(board(builder, theirs=3), registry) == 0

    def test_and_the_two_do_not_add_up(self, builder, registry):
        assert discount(board(builder, buried=2, theirs=3), registry) == 2


class TestThePriceActuallyMoves:
    """A discount nothing charges is not a discount."""

    def priced(self, builder, *, buried: int):
        """Four Mountains, and a spare land so the position keeps priority.

        `build(advance=False)` would leave no pending decision at all and
        `legal_actions()` empty, which passes the uncastable case for entirely
        the wrong reason.
        """
        return (
            builder(players=2)
            .hand(0, [CYAN, "forest"])
            .battlefield(0, ["mountain"] * 4)
            .graveyard(0, [BEAR] * buried)
            .library(0, ["forest"] * 10)
            .build()
        )

    def test_it_is_uncastable_off_four_lands_with_an_empty_graveyard(self, builder):
        assert not _cast_lines(self.priced(builder, buried=0))

    def test_two_creature_cards_make_it_castable(self, builder):
        """{4}{R} minus {2} is {2}{R}, which four Mountains can pay."""
        assert _cast_lines(self.priced(builder, buried=2))


def _cast_lines(game):
    state = game.state
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and state.objects[a.source].def_id == CYAN
    ]


class TestTheLoaderStillRefusesAHiddenZone:
    def test_the_hand_is_not_countable(self):
        """Hidden, and so not a thing a public price may be computed from."""
        from automtg.cards.loader import compile_card
        from automtg.cards.schema import CardModel
        from automtg.engine.errors import DslError

        card = CardModel.model_validate(
            {
                "id": "t_bad_reduction_zone",
                "name": "Test Bad Reduction Zone",
                "oracle_text": "This spell costs {1} less for each card in your hand.",
                "mana_cost": "{4}{R}",
                "types": ["Sorcery"],
                "cost_reduction": {"count": {"zone": "hand", "controller": "you"}},
                "spell_effects": [{"op": "draw", "player": "you"}],
            }
        )
        with pytest.raises(DslError, match="graveyard"):
            compile_card(card, source="test")

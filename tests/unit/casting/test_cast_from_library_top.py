"""Bolas's Citadel — casting off the top of your library, paying life.

    You may play lands and cast spells from the top of your library. If you cast
    a spell this way, pay life equal to its mana value rather than pay its mana
    cost.

Two halves, and they are one mechanic rather than two.

**The permission.** `play_lands_from_library_top` is the closest thing and is
documented as lands only -- "whether this player may play the top card of their
library, *if it is a land*" -- so it grants nothing for a nonland spell. This is
its casting twin, and the library is the only *hidden* zone a spell can be cast
from: the top card and nothing below it, which is what the card says and the
only part of a library anybody is entitled to see.

**The price.** "Pay life equal to its mana value **rather than** pay its mana
cost" is a whole substitution, and `spell_cost_reduction` -- the only static
that touches what other spells cost -- reduces a mana cost by an amount and
cannot swap the payment to a different resource. So the mana half is zeroed when
the line is priced and `Game._cast` charges the life.

The loader requires the price on the permission, because the permission without
it is every spell in the deck castable off the top at its printed cost: a
different and much stronger card, and one that would look entirely normal.

118.4 sets the boundary: a player may pay life down to exactly 0, so the test is
having that much rather than surviving it -- and a line that could not be paid
is withheld rather than offered and rewound.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind

CITADEL = "t_citadel"
BEAR = "t_bear"  # {1}{G}, mana value 2


def board(builder, *, citadel: bool = True, life: int = 40, top: str = BEAR):
    b = (
        builder(players=2)
        .battlefield(0, ["forest"] * 2)
        .hand(0, ["plains"])
        .life(0, life)
        .library(0, [top] + ["forest"] * 10)
    )
    if citadel:
        b = b.battlefield(0, [CITADEL])
    return b.build()


def cast_lines(game):
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST]


def resolve(game):
    lines = cast_lines(game)
    assert lines, "nothing was offered"
    game.apply(lines[0])
    state = game.state
    for _ in range(20):
        if not state.stack:
            break
        actions = game.legal_actions()
        if not actions:
            break
        game.apply(actions[0])
    return game


class TestThePermission:
    def test_the_top_card_is_castable(self, builder):
        assert cast_lines(board(builder))

    def test_without_the_permanent_it_is_not(self, builder):
        assert cast_lines(board(builder, citadel=False)) == []

    def test_it_actually_resolves_onto_the_battlefield(self, builder):
        game = resolve(board(builder))
        # two Forests, the Citadel, and the Bear
        assert len(game.state.battlefield_objects(0)) == 4


class TestThePrice:
    def test_it_costs_life_equal_to_mana_value(self, builder):
        """A {1}{G} creature is mana value 2, so two life."""
        game = resolve(board(builder))
        assert game.state.players[0].life == 38

    def test_it_costs_no_mana(self, builder):
        """"**rather than** pay its mana cost" -- measured with no mana at all.

        The board has no lands, so {1}{G} could never be paid. A card still
        offered there is a card paying no mana for it, which is a stronger claim
        than watching which permanents got tapped.
        """
        game = (
            builder(players=2)
            .battlefield(0, [CITADEL])
            .hand(0, ["plains"])
            .life(0, 40)
            .library(0, [BEAR] + ["forest"] * 10)
            .build()
        )
        assert cast_lines(game), "castable with no mana available at all"
        resolve(game)
        assert game.state.players[0].life == 38


class TestTheLifeBoundary:
    def test_exactly_enough_life_is_enough(self, builder):
        """118.4: a player may pay life down to exactly 0."""
        game = board(builder, life=2)
        assert cast_lines(game)

    def test_one_short_is_not_offered(self, builder):
        assert cast_lines(board(builder, life=1)) == []


class TestTheLoaderRequiresThePrice:
    def test_a_permission_with_no_price_is_refused(self):
        """It would be every spell in the deck, free, off the top."""
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.cards.schema import CardModel
        from commanderblitz.engine.errors import DslError

        card = CardModel.model_validate(
            {
                "id": "t_free_citadel",
                "name": "Test Free Citadel",
                "oracle_text": "You may cast spells from the top of your library.",
                "mana_cost": "{3}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "You may cast spells from the top of your library.",
                        "effect": "cast_from_library_top",
                        "affects_player": "you",
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="pay_life_instead"):
            compile_card(card, source="test")

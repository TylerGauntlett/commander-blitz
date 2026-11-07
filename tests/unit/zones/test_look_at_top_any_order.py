"""`rest_any_order` on `look_at_top`: the cards looked at go back in a chosen order.

    Halimar Depths — "When this land enters, look at the top three cards of
    your library, then put them back in any order."
    Portent — "Look at the top three cards of target player's library, then put
    them back in any order."
    Diabolic Vision — "Look at the top five cards of your library. Put one of
    them into your hand and the rest on top of your library in any order."

Without the key the rest stay on top in the order they were found, which is a
look and no more; `scry` is the near miss the other way, since it may also
bottom them. The claims: the resolving player chooses the order, even over
another player's library (Portent); a card the op took is not put back; nothing
leaves the top; and the loader refuses the key beside another instruction for
the rest.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError

LOOK_THREE = {
    "op": "look_at_top",
    "amount": 3,
    "objects": {"count": 0},
    "rest_any_order": True,
}


def a_board(builder, library_owner=0):
    game = (
        builder(players=2)
        .battlefield(0, ["t_bear"])
        .library(library_owner, ["t_bear", "island", "forest", "island", "island"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    source = game.state.battlefield[0]
    return game, source


def run(game, source, spec, answer):
    """Resolve `spec`; `answer(decision)` returns the chosen indices."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = execute(ctx, [spec])
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send(answer(decision))
    except StopIteration:
        pass
    return asked


def last_option(decision):
    return [len(decision.options) - 1]


class TestTheRestGoBackInTheChosenOrder:
    def test_choosing_the_last_each_time_keeps_the_order(self, builder):
        game, source = a_board(builder)
        library = game.state.players[0].library
        top, under = list(library[:3]), list(library[3:])
        run(game, source, LOOK_THREE, last_option)
        # Placed c, then b, then a; the last placed is the top, so a, b, c.
        assert library[:3] == top
        assert library[3:] == under

    def test_choosing_the_first_each_time_reverses_them(self, builder):
        game, source = a_board(builder)
        library = game.state.players[0].library
        a, b, c = library[:3]
        run(game, source, LOOK_THREE, lambda d: [0])
        # Placed a, then b, then c: c is the top.
        assert library[:3] == [c, b, a]

    def test_two_questions_for_three_cards(self, builder):
        game, source = a_board(builder)
        asked = run(game, source, LOOK_THREE, lambda d: [0])
        assert len(asked) == 2
        assert all(d.player == 0 for d in asked)

    def test_nothing_leaves_the_library(self, builder):
        game, source = a_board(builder)
        before = sorted(game.state.players[0].library)
        run(game, source, LOOK_THREE, lambda d: [0])
        assert sorted(game.state.players[0].library) == before


class TestPortentLooksAtAnotherLibrary:
    def test_the_caster_chooses_the_order_of_the_opponents_cards(self, builder):
        game, source = a_board(builder, library_owner=1)
        library = game.state.players[1].library
        a, b, c = library[:3]
        asked = run(game, source, {**LOOK_THREE, "player": "opponent"}, lambda d: [0])
        assert asked and all(d.player == 0 for d in asked)
        assert library[:3] == [c, b, a]


class TestDiabolicVisionTakesOneFirst:
    def test_the_taken_card_is_not_put_back(self, builder):
        game, source = a_board(builder)
        library = game.state.players[0].library
        taken, b, c = library[:3]
        spec = {**LOOK_THREE, "objects": {"count": 1}, "destination": "hand"}
        run(game, source, spec, lambda d: [0])
        assert taken in game.state.players[0].hand
        assert taken not in library
        # b, c remain; one ordering question, picking b first puts c on top.
        assert library[:2] == [c, b]


class TestWithoutTheKeyTheOrderStands:
    def test_a_plain_look_asks_nothing_and_moves_nothing(self, builder):
        game, source = a_board(builder)
        before = list(game.state.players[0].library)
        spec = {k: v for k, v in LOOK_THREE.items() if k != "rest_any_order"}
        asked = run(game, source, spec, lambda d: [0])
        assert asked == []
        assert game.state.players[0].library == before


class TestTheLoaderGuard:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_any_order_probe",
                "name": "Test Any Order Probe",
                "oracle_text": (
                    "Look at the top three cards of your library, then put them "
                    "back in any order."
                ),
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_the_key_loads(self):
        compile_card(self._card(LOOK_THREE))

    def test_it_is_a_flag(self):
        with pytest.raises(DslError, match="rest_any_order"):
            compile_card(self._card({**LOOK_THREE, "rest_any_order": "yes"}))

    @pytest.mark.parametrize(
        "other", [{"rest_to_bottom": True}, {"rest_to": "graveyard"}, {"shuffle": True}]
    )
    def test_another_instruction_for_the_rest_is_refused(self, other):
        with pytest.raises(DslError, match="rest_any_order"):
            compile_card(self._card({**LOOK_THREE, **other}))

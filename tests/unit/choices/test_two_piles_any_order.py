"""Two piles, the other on the bottom of the library in any order.

    "Reveal the top three cards of your library. An opponent separates those
    cards into two piles. Put one pile into your hand and the other on the
    bottom of your library **in any order**."
                                  -- Jace, Architect of Thought's -2

401.4: when cards are put into one position of a library together, their
owner arranges them. Without `any_order` the pile went to the bottom in the
order it was revealed, which nobody chose, and the next time the library
runs that deep the owner draws a card in a place they did not put it. The
arrangement is `put_on_top`'s (`_in_owners_order`): one pick at a time, each
card under the one before, so the last chosen is the bottom card.

The loader holds `any_order` to `other: "library_bottom"`, the one pile the
sentence arranges, and holds `to` and `other` to the places `two_piles`
moves a pile, so a misspelt destination fails at load rather than at
resolution.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

ARCHITECT = "t_tpao_architect"
TOP = ["plains", "island", "swamp"]


def board(builder, spell: str = ARCHITECT):
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * 4)
        .hand(0, [spell])
        .library(0, TOP + ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    return game


def def_ids(game, oids) -> list[str]:
    return [game.state.objects[o].def_id for o in oids]


def run(game, spell: str, order: list[str]) -> list[tuple[int, str]]:
    """Cast ``spell``; the opponent makes an empty first pile, the caster takes
    it, so all three go to the bottom, arranged by picking ``order``. Returns
    who was asked each library-order question, and for what."""
    cast = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == spell
    )
    game.apply(cast)
    asked: list[tuple[int, str]] = []
    wanted = list(order)
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            break
        purpose = decision.context.get("purpose") if decision.context else None
        if decision.kind is DecisionKind.CHOOSE_OBJECTS and purpose == "split_piles":
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
            )
            continue
        if decision.kind is DecisionKind.MAY:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
            continue
        if decision.kind is DecisionKind.CHOOSE_OBJECTS and purpose == "library_order":
            name = wanted.pop(0)
            index = next(
                i
                for i, option in enumerate(decision.options)
                if option.ref is not None
                and game.state.objects[option.ref.id].def_id == name
            )
            asked.append((decision.player, name))
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    return asked


class TestTheOwnerArrangesTheBottom:
    def test_the_last_card_chosen_is_the_bottom_card(self, builder):
        game = board(builder)
        run(game, ARCHITECT, ["swamp", "plains"])
        assert def_ids(game, game.state.players[0].library[-3:]) == [
            "swamp",
            "plains",
            "island",
        ]

    def test_another_order_is_another_library(self, builder):
        game = board(builder)
        run(game, ARCHITECT, ["island", "swamp"])
        assert def_ids(game, game.state.players[0].library[-3:]) == [
            "island",
            "swamp",
            "plains",
        ]

    def test_the_caster_is_asked_and_the_last_card_asks_nothing(self, builder):
        game = board(builder)
        asked = run(game, ARCHITECT, ["swamp", "plains"])
        assert asked == [(0, "swamp"), (0, "plains")]

    def test_nothing_else_leaves_the_library(self, builder):
        game = board(builder)
        before = len(game.state.players[0].library)
        run(game, ARCHITECT, ["swamp", "plains"])
        assert len(game.state.players[0].library) == before


def _card(**effect) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_piles", "name": "Bad Piles",
                "oracle_text": "Reveal the top three cards of your library.",
                "mana_cost": "{U}", "types": ["Sorcery"],
                "spell_effects": [{"op": "two_piles", "amount": {"const": 3}, **effect}],
            }
        )
    )


class TestTheLoader:
    def test_any_order_on_the_bottom_compiles(self):
        _card(to="hand", other="library_bottom", any_order=True)

    def test_any_order_on_a_graveyard_pile_is_refused(self):
        with pytest.raises(DslError, match="any_order"):
            _card(to="hand", other="graveyard", any_order=True)

    def test_a_misspelt_destination_is_refused(self):
        with pytest.raises(DslError, match="two_piles"):
            _card(to="hand", other="bottom")

    def test_fact_or_fiction_still_compiles(self):
        _card(to="hand", other="graveyard")

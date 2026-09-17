"""Several cards put into a library at once, in the order their owner chooses.

Teferi's Puzzle Box: "…that player puts the cards in their hand on the bottom of
their library **in any order**, then draws that many cards."

Rule 401.4: "If an effect puts two or more cards in a specific position in a
library at the same time, the owner of those cards may arrange them in any
order." `put_on_top` resolved its selector through `choose_objects`, which for
`count: "all"` hands back the pool in hand order and asks nothing -- so the
cards went under in whatever order they happened to be held, and nobody chose.
That is a different card whenever the order matters, which on the Box is every
turn: the bottom of the library is where the next Box activation, a scry, or a
shuffle-less tutor looks.

`any_order: true` asks the **owner** one card at a time, `ask_objects` with a
count of one over what is left, until a single card remains. No new decision
kind: "which card next" is a pick, and every seat that can already answer a pick
answers this. The reading of each answer is the physical one:

- **bottom** -- each card goes under the one before, so the last chosen is the
  very bottom card;
- **top** -- each card goes on top of the one before, so the last chosen is the
  top card, which is what Brainstorm's pick order already meant.

`TestTheOrderIsChosen` puts the same hand under in two different orders, which
is the only test that can tell "the player chose" from "the pool order happened
to match".
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from tests.conftest import _default_answer

BOTTOM = "t_tuck_hand_bottom_ordered"
TOP = "t_tuck_hand_top_ordered"
THEIRS = "t_tuck_opponents_hand_bottom_ordered"
HAND = ["island", "swamp", "mountain"]


def position(builder, spell: str, *, mine=HAND, theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, ["island"])
        .library(0, ["forest"] * 5)
        .library(1, ["plains"] * 5)
        .hand(0, [spell, *mine])
        .hand(1, list(theirs))
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def names(game, oids) -> list[str]:
    return [game.state.objects[oid].def_id for oid in oids]


def cast(game, spell: str, target: int | None = None) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == spell
        and (target is None or a.targets == (TargetRef.player(target),))
    )
    game.apply(action)


def resolve(game, order: list[str] | None = None) -> list[tuple[int, list[str]]]:
    """Resolve the spell, picking cards in ``order``; return each order prompt.

    Each prompt is recorded as ``(who was asked, the cards offered)``.
    """
    asked: list[tuple[int, list[str]]] = []
    wanted = list(order or [])
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            break
        if (
            decision.kind is DecisionKind.CHOOSE_OBJECTS
            and decision.context.get("purpose") == "library_order"
        ):
            offered = [game.state.objects[o.value].def_id for o in decision.options]
            asked.append((decision.player, offered))
            name = wanted.pop(0) if wanted else offered[0]
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE
                    and game.state.objects[decision.options[a.choice].value].def_id == name
                )
            )
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    return asked


class TestTheOrderIsChosen:
    def test_the_last_card_chosen_is_the_bottom_card(self, builder):
        game = position(builder, BOTTOM)
        cast(game, BOTTOM)
        resolve(game, ["swamp", "mountain", "island"])

        assert names(game, game.state.players[0].library[-3:]) == ["swamp", "mountain", "island"]

    def test_a_different_answer_is_a_different_library(self, builder):
        """The same hand, the other way round -- the pool order is not the answer."""
        game = position(builder, BOTTOM)
        cast(game, BOTTOM)
        resolve(game, ["island", "mountain", "swamp"])

        assert names(game, game.state.players[0].library[-3:]) == ["island", "mountain", "swamp"]

    def test_what_was_on_top_stays_on_top(self, builder):
        game = position(builder, BOTTOM)
        cast(game, BOTTOM)
        resolve(game, ["swamp", "mountain", "island"])

        assert names(game, game.state.players[0].library[:5]) == ["forest"] * 5

    def test_on_top_the_last_card_chosen_is_the_top_card(self, builder):
        game = position(builder, TOP)
        cast(game, TOP)
        resolve(game, ["swamp", "mountain", "island"])

        assert names(game, game.state.players[0].library[:3]) == ["island", "mountain", "swamp"]
        assert names(game, game.state.players[0].library[3:]) == ["forest"] * 5


class TestWhoIsAsked:
    def test_one_question_per_card_but_the_last(self, builder):
        """Three cards are two choices; the third has nowhere else to go."""
        game = position(builder, BOTTOM)
        cast(game, BOTTOM)
        asked = resolve(game, ["swamp", "mountain"])

        assert [len(offered) for _, offered in asked] == [3, 2]

    def test_the_owner_arranges_them(self, builder):
        """401.4 gives the order to the cards' owner, not the resolving player."""
        game = position(builder, THEIRS, mine=[], theirs=["island", "swamp"])
        cast(game, THEIRS, target=1)
        asked = resolve(game, ["swamp"])

        assert [who for who, _ in asked] == [1]
        assert names(game, game.state.players[1].library[-2:]) == ["swamp", "island"]

    def test_a_single_card_asks_nothing(self, builder):
        game = position(builder, BOTTOM, mine=["island"])
        cast(game, BOTTOM)

        assert resolve(game) == []
        assert names(game, game.state.players[0].library[-1:]) == ["island"]

    def test_an_empty_hand_asks_nothing(self, builder):
        game = position(builder, BOTTOM, mine=[])
        cast(game, BOTTOM)

        assert resolve(game) == []
        assert len(game.state.players[0].library) == 5


def compile_with(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_tuck",
                "name": "Bad Tuck",
                "oracle_text": "Put the cards in your hand on the bottom of your library in any order.",
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )
    )


class TestTheLoaderRefuses:
    HAND_POOL = {"zone": "hand", "player": "you", "count": "all"}

    def test_a_depth(self):
        """An ordinal names one position; "in any order" is several."""
        with pytest.raises(DslError, match="any_order"):
            compile_with(
                {"op": "put_on_top", "any_order": True, "from_top": 2, "objects": self.HAND_POOL}
            )

    def test_the_owners_choice_of_end(self):
        with pytest.raises(DslError, match="any_order"):
            compile_with(
                {
                    "op": "put_on_top",
                    "any_order": True,
                    "owner_chooses": True,
                    "objects": self.HAND_POOL,
                }
            )

    def test_a_non_boolean(self):
        with pytest.raises(DslError, match="any_order"):
            compile_with({"op": "put_on_top", "any_order": "yes", "objects": self.HAND_POOL})

    def test_another_op(self):
        with pytest.raises(DslError, match="any_order"):
            compile_with({"op": "exile", "any_order": True, "objects": self.HAND_POOL})

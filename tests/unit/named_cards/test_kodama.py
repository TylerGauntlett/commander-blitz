"""Kodama of the East Tree, and the loop guard it exists to demonstrate.

"Whenever another permanent you control enters, **if it wasn't put onto the
battlefield with this ability**, you may put a permanent card with equal or
lesser mana value from your hand onto the battlefield."

That clause is not flavour. Without it the ability triggers on the permanent it
just put down, and again on that one's, until the trigger loop guard kills the
game — so the card would be unplayable rather than subtly wrong, which is the
only reason this one fails loudly.

The guard lives on the *trigger*, not in a condition, because by the time the
ability resolves the cause is no longer anywhere to be read.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError
from tests.conftest import _default_answer


def board(builder, hand: list[str]):
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * 6 + ["kodama_of_the_east_tree"])
        .hand(0, hand)
        .library(0, ["island"] * 20)
        .build()
    )


def play_the_land(game) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.PLAY_LAND and game.state.objects[a.source].def_id == "forest"
    )
    game.apply(action)


def answer_mays(game, answers: list[bool]) -> int:
    """Answer each `may` in turn; unlisted ones are declined. Returns how many."""
    pending = iter(answers)
    asked = 0
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.MAY:
            asked += 1
            want = ActionKind.YES if next(pending, False) else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    return asked


class TestTheTrigger:
    def test_a_permanent_entering_offers_the_put(self, builder):
        """A 2-drop entering fetches a 2-drop: "equal or lesser" includes equal."""
        game = board(builder, ["grizzly_bears", "grizzly_bears"])
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "grizzly_bears"
        )
        game.apply(cast)
        assert answer_mays(game, [True]) == 1

        bears = [o for o in game.state.battlefield_objects(0) if o.def_id == "grizzly_bears"]
        assert len(bears) == 2, "the one cast, and the one it fetched"

    def test_it_does_not_trigger_on_its_own_output(self, builder):
        """The whole point. Two permanents entering, but only one question.

        A Forest enters (mana value 0 -- so nothing in hand qualifies... except
        another Forest), Kodama puts a Forest down, and that Forest entering must
        *not* ask again.
        """
        game = board(builder, ["forest", "forest"])
        play_the_land(game)
        asked = answer_mays(game, [True, True])

        forests = [o for o in game.state.battlefield_objects(0) if o.def_id == "forest"]
        assert len(forests) == 8, "the six it had, the one played, the one put down"
        assert asked == 1, "the put-down Forest must not ask again"

    def test_it_does_not_trigger_on_itself(self, builder):
        """'another permanent' -- Kodama arriving is not a trigger."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 6)
            .hand(0, ["kodama_of_the_east_tree", "grizzly_bears"])
            .library(0, ["island"] * 20)
            .build()
        )
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "kodama_of_the_east_tree"
        )
        game.apply(cast)
        assert answer_mays(game, [True]) == 0

    def test_a_bigger_card_is_not_offered(self, builder):
        """'equal or lesser mana value' -- a Forest's 0 does not fetch a 2-drop."""
        game = board(builder, ["forest", "terastodon"])
        play_the_land(game)
        answer_mays(game, [True])
        assert not [
            o for o in game.state.battlefield_objects(0) if o.def_id == "terastodon"
        ], "mana value 9 is not 'equal or lesser' than a Forest's 0"

    def test_declining_puts_nothing_down(self, builder):
        game = board(builder, ["forest", "grizzly_bears"])
        play_the_land(game)
        answer_mays(game, [False])
        assert not [
            o for o in game.state.battlefield_objects(0) if o.def_id == "grizzly_bears"
        ]


class TestPartnerIsInert:
    def test_it_loads_and_does_nothing(self, registry):
        """A deck-construction rule. Represented so the text is accounted for."""
        from automtg.engine.enums import INERT_KEYWORDS, Keyword

        card = registry.get("kodama_of_the_east_tree")
        assert "partner" in card.keywords
        assert Keyword.PARTNER in INERT_KEYWORDS

    def test_it_is_not_evasion_or_anything_else(self, builder):
        from automtg.engine.characteristics import chars

        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 6 + ["kodama_of_the_east_tree"])
            .build()
        )
        from tests.conftest import only_oid

        kodama = only_oid(game, "kodama_of_the_east_tree")
        got = chars(game.state, kodama)
        assert "partner" in got.keywords
        assert (got.power, got.toughness) == (6, 6), "a 6/6, unchanged by the word"


class TestNotCauseIsChecked:
    def test_it_is_rejected_on_a_trigger_with_no_cause_to_read(self):
        """Only zone changes carry a cause; elsewhere it would never fire."""
        model = CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "triggered",
                        "trigger": {"event": "upkeep", "not_cause": "probe"},
                        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="only means anything on an enters trigger"):
            compile_card(model)

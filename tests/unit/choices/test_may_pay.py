"""``may`` with a price — "you may pay {2}. **If you do**, draw a card."

    Seer's Sundial — "Landfall — Whenever a land you control enters, you may
    pay {2}. If you do, draw a card."

Every cost in the engine used to hang off the object being cast or activated,
read once at cast or activation time. A triggered ability fires on its own and
its effects run with no cost hook at all, so the only way to write this card was
to drop the {2} — turning a card that draws for two mana per land into one that
draws free. That is a strictly better card than the printed one, which is the
class of error the authoring gates exist to stop.

Three properties, and all three are the card:

1. **The effects are the "if you do" branch.** They run only when the payment
   completed. `may` already had a yes/no; what it lacked was anything at stake.
2. **The mana actually leaves the pool.** Not a flag — `pay` taps sources and
   spends, so a second trigger in the same turn can find the player broke.
3. **An unaffordable cost is not offered.** Asking a question the player cannot
   answer, then failing, would show a prompt that does nothing.

`unless_pays` (Rhystic Study) is the adjacent mechanic and is deliberately *not*
this one: it routes the payment to another player and inverts the outcome.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError

SUNDIAL = {
    "id": "t_sundial",
    "name": "Test Sundial",
    "oracle_text": "Landfall - Whenever a land you control enters, you may pay {2}. If you do, draw a card.",
    "mana_cost": "{4}",
    "types": ["Artifact"],
    "abilities": [
        {
            "kind": "triggered",
            "text": (
                "Landfall - Whenever a land you control enters, you may pay {2}. "
                "If you do, draw a card."
            ),
            "trigger": {"event": "land_played", "controller": "you"},
            "effects": [
                {
                    "op": "may",
                    "pay": {"mana": "{2}"},
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
    ],
}


def board(builder, *, lands: int):
    """``(game, hand_before)`` with the Sundial out and a land to play."""
    game = (
        builder(players=2)
        .battlefield(0, ["t_sundial"] + ["forest"] * lands)
        .hand(0, ["forest"])
        .library(0, ["island"] * 20)
        .build()
    )
    return game, len(game.state.players[0].hand)


def play_the_land(game) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.PLAY_LAND
    )
    game.apply(action)


def answer(game, *, yes: bool) -> bool:
    """Answer one pending MAY. Returns False when nothing was asked."""
    decision = game.pending()
    if decision is None or decision.kind is not DecisionKind.MAY:
        return False
    wanted = ActionKind.YES if yes else ActionKind.NO
    action = next(a for a in game.legal_actions() if a.kind is wanted)
    game.apply(action)
    return True


def settle(game) -> None:
    """Resolve the stack, answering nothing else."""
    for _ in range(50):
        if game.pending() is not None or not game.state.stack:
            return
        action = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
        )
        if action is None:
            return
        game.apply(action)


class TestTheEffectsAreTheIfYouDoBranch:
    def test_paying_draws(self, builder):
        game, before = board(builder, lands=6)
        play_the_land(game)
        settle(game)
        assert answer(game, yes=True), "the optional payment was never offered"
        settle(game)
        # -1 for the land played, +1 for the draw.
        assert len(game.state.players[0].hand) == before

    def test_declining_does_not_draw(self, builder):
        game, before = board(builder, lands=6)
        play_the_land(game)
        settle(game)
        assert answer(game, yes=False)
        settle(game)
        assert len(game.state.players[0].hand) == before - 1, "declining still drew"


class TestTheManaActuallyLeaves:
    def test_two_lands_are_tapped_for_it(self, builder):
        game, _ = board(builder, lands=6)
        play_the_land(game)
        settle(game)
        answer(game, yes=True)
        settle(game)
        tapped = sum(
            1
            for o in game.state.battlefield_objects(0)
            if o.tapped and o.def_id == "forest"
        )
        assert tapped == 2, f"expected {{2}} paid from two Forests, {tapped} tapped"


class TestAnUnaffordableCostIsNotOffered:
    def test_with_one_land_it_never_asks(self, builder):
        """One Forest cannot pay {2}, and the land just played enters untapped
        but is itself only one more source -- so the question must not appear."""
        game, _ = board(builder, lands=0)
        play_the_land(game)
        settle(game)
        decision = game.pending()
        assert decision is None or decision.kind is not DecisionKind.MAY, (
            "offered a payment the player cannot make"
        )


class TestLoadTimeGuards:
    def test_a_misspelled_cost_key_is_refused(self):
        """A dropped cost is the whole hazard: it makes a cheaper card than the
        printed one, and nothing on screen says so."""
        import copy

        card = copy.deepcopy(SUNDIAL)
        card["abilities"][0]["effects"][0]["pay"] = {"manna": "{2}"}
        with pytest.raises(DslError, match="bad 'pay' cost"):
            compile_card(CardModel.model_validate(card))

    def test_paying_for_nothing_is_refused(self):
        import copy

        card = copy.deepcopy(SUNDIAL)
        card["abilities"][0]["effects"][0].pop("effects")
        with pytest.raises(DslError, match="'pay' needs 'effects'"):
            compile_card(CardModel.model_validate(card))

    def test_the_card_itself_loads(self):
        compile_card(CardModel.model_validate(SUNDIAL))

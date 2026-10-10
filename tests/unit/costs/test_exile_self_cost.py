"""Phoenix Down — "{1}{W}, {T}, **Exile this artifact**:".

`cost_keys` carried `sacrifice`, which puts the source in the **graveyard**, and
`exile_from_graveyard`, which exiles a card already in one. Neither exiles the
source from the battlefield, and on this card the difference is the whole point:
Phoenix Down is meant to be one-shot and graveyard-proof, and paying with a
sacrifice would leave it recurrable *and* drop it into the very graveyard its
own first mode reanimates from.

Paying with the `exile` **op** is not a substitute either. 601.2h pays costs as
the ability goes on the stack; an op runs at resolution, so the ability could be
activated and responded to with the artifact still in play, and a removal spell
in response would leave the ability paid for and the card still around.

So `exile_self` is a boolean on the cost, the exile twin of `discard_self`, and
it asks nothing: which permanent goes is not a choice, it is *this* one.

`t_sac_down` is the counterfactual — the identical ability paying with a
sacrifice — and it is where the two cards visibly part company.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind, Zone

EXILER = "t_phoenix_down"
SACKER = "t_sac_down"


def board(builder, card_id: str):
    game = (
        builder(players=2)
        .battlefield(0, [card_id])
        .battlefield(0, ["plains"] * 3)
        .hand(0, ["forest"])
        .library(0, ["forest"] * 10)
        .build()
    )
    state = game.state
    oid = next(
        o.oid for o in state.battlefield_objects(0) if state.card_of(o).id == card_id
    )
    return game, oid


def activate(game, oid: int):
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
    )
    game.apply(action)
    state = game.state
    # Stop the moment the ability has resolved. Letting the loop run on hands
    # priority round and round and draws a card every turn, which would make
    # "did it draw one?" unanswerable.
    for _ in range(20):
        if not state.stack:
            break
        actions = game.legal_actions()
        if not actions:
            break
        game.apply(actions[0])
    return game


class TestTheSourceIsExiled:
    def test_it_ends_in_exile(self, builder):
        game, oid = board(builder, EXILER)
        activate(game, oid)
        assert game.state.objects[oid].zone is Zone.EXILE

    def test_not_in_the_graveyard(self, builder):
        """Where a sacrifice would have put it, and where this card must not be."""
        game, oid = board(builder, EXILER)
        activate(game, oid)
        assert oid not in game.state.players[0].graveyard

    def test_the_ability_still_happens(self, builder):
        """The cost is charged without breaking what the ability does."""
        game, oid = board(builder, EXILER)
        before = len(game.state.players[0].hand)
        activate(game, oid)
        assert len(game.state.players[0].hand) == before + 1


class TestTheSacrificeCounterfactual:
    def test_sacrificing_leaves_it_in_the_graveyard(self, builder):
        game, oid = board(builder, SACKER)
        activate(game, oid)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_the_two_end_in_different_zones(self, builder):
        exiled, oid_e = board(builder, EXILER)
        activate(exiled, oid_e)
        sacked, oid_s = board(builder, SACKER)
        activate(sacked, oid_s)
        assert exiled.state.objects[oid_e].zone is not sacked.state.objects[oid_s].zone


class TestThePaymentSolverKeepsItsHandsOff:
    def test_an_exile_self_cost_is_not_tap_only(self, builder):
        """Otherwise the solver could spend the artifact to pay for something else.

        The same trap `mill` records one field over: `costs.solver_taps` reads
        `is_tap_only` to decide which abilities it may activate unasked.
        """
        game, oid = board(builder, EXILER)
        cost = game.state.card_of(game.state.objects[oid]).abilities[0].cost
        assert not cost.is_tap_only()

    def test_it_describes_itself(self, builder):
        game, oid = board(builder, EXILER)
        cost = game.state.card_of(game.state.objects[oid]).abilities[0].cost
        assert "Exile this permanent" in cost.describe()


class TestItSatisfiesTheOutsideTheBattlefieldGuard:
    def test_an_ability_activated_from_a_graveyard_may_exile_itself(self):
        """The guard wants the source gone from the zone it was activated in.

        `discard_self` and `exile_from_graveyard` already satisfied it; exiling
        the source is the same promise made a third way.
        """
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.cards.schema import CardModel

        compile_card(
            CardModel.model_validate(
                {
                    "id": "t_exile_self_from_yard",
                    "name": "Test Exile Self From Yard",
                    "oracle_text": "{2}, Exile this card: Draw a card.",
                    "mana_cost": "{1}",
                    "types": ["Artifact"],
                    "abilities": [
                        {
                            "kind": "activated",
                            "text": "{2}, Exile this card: Draw a card.",
                            "active_zones": ["graveyard"],
                            "cost": {"mana": "{2}", "exile_self": True},
                            "effects": [{"op": "draw", "player": "you"}],
                        }
                    ],
                }
            ),
            source="test",
        )

    def test_mana_alone_is_still_refused(self):
        """The guard has not been weakened, only widened."""
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.cards.schema import CardModel
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="removes its source"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_free_yard_ability",
                        "name": "Test Free Yard Ability",
                        "oracle_text": "{2}: Draw a card.",
                        "mana_cost": "{1}",
                        "types": ["Artifact"],
                        "abilities": [
                            {
                                "kind": "activated",
                                "text": "{2}: Draw a card.",
                                "active_zones": ["graveyard"],
                                "cost": {"mana": "{2}"},
                                "effects": [{"op": "draw", "player": "you"}],
                            }
                        ],
                    }
                ),
                source="test",
            )

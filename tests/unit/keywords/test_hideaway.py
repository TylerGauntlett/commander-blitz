"""Hideaway — three shipped pieces in an order nothing had needed before.

    "Hideaway 4 (When this permanent enters, look at the top four cards of your
    library, exile one face down, then put the rest on the bottom in a random
    order.)
     {2}, Sacrifice this artifact: You may play the exiled card without paying
     its mana cost."

The census listed hideaway as waiting on *two* things — face-down exile and
play-from-exile — and it turned out to need one. "Face down in exile" is
`revealed_to`, which foretell shipped: a card nobody may interact with is hidden
by not being shown, and it needs none of the 2/2 characteristics shell that
morph does.

What was genuinely missing is the permission. The engine could exile a card and
could cast one for free, and had no way to say **"that one, from there"** —
which is `play_exiled`, reading back the O-Ring link the exile wrote.

The link direction is `exiled_by`, and it has to be: the *permanent* is what
later says "you may play the exiled card", so the permanent is what has to find
it. That is imprint's direction, not haunt's.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card, library_ids, only_oid, pass_until

WASTE = "island"
VAULT = "t_hideaway"
BEAR = "t_bear"
GIANT = "t_big"


def position(builder, library: list[str]):
    return (
        builder(players=2)
        .battlefield(0, [WASTE] * 6)
        .hand(0, [VAULT])
        .library(0, library + [WASTE] * 20)
        .library(1, [WASTE] * 20)
        .build()
    )


def play_the_vault(game):
    """Cast the Vault and answer its hideaway choice.

    Driven as a scan rather than a fixed sequence: the ETB trigger has to drain
    onto the stack and resolve before the choice is offered, and how many
    priority windows that takes is not the test's business.
    """
    game.apply(action_for_card(game, ActionKind.CAST, VAULT))
    for _ in range(120):
        if game.state.players[0].exile:
            return
        decision = game.pending()
        if decision is None:
            return
        if decision.context.get("purpose") == "hideaway":
            choose = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
            if choose:
                game.apply(choose[0])
                continue
        game.apply(_default_answer(game, decision))


class TestTheHideaway:
    def test_one_card_is_exiled(self, builder):
        game = position(builder, [GIANT, BEAR, BEAR, BEAR])
        play_the_vault(game)

        exiled = game.state.players[0].exile
        assert len(exiled) == 1

    def test_it_is_linked_to_the_permanent(self, builder):
        """`exiled_by` -- imprint's direction, because the permanent finds it."""
        game = position(builder, [GIANT, BEAR, BEAR, BEAR])
        play_the_vault(game)

        exiled = game.state.players[0].exile[0]
        assert game.state.objects[exiled].exiled_by == only_oid(game, VAULT)

    def test_only_its_controller_may_see_it(self, builder):
        """"Face down" here is `revealed_to`, not the morph shell."""
        game = position(builder, [GIANT, BEAR, BEAR, BEAR])
        play_the_vault(game)

        exiled = game.state.players[0].exile[0]
        assert game.state.objects[exiled].revealed_to == {0}

    def test_the_rest_go_to_the_bottom(self, builder):
        game = position(builder, [GIANT, BEAR, BEAR, BEAR])
        play_the_vault(game)

        assert library_ids(game)[0] == WASTE, "the looked-at four have gone"
        assert BEAR in library_ids(game)[-4:], "and are at the bottom"

    def test_the_depth_is_the_card(self, builder):
        game = position(builder, [GIANT, BEAR, BEAR, BEAR, GIANT])
        play_the_vault(game)

        # The fifth card was never looked at, so it is still on top.
        assert library_ids(game)[0] == GIANT


class TestPlayingIt:
    def test_the_ability_casts_the_exiled_card(self, builder):
        game = position(builder, [GIANT, BEAR, BEAR, BEAR])
        play_the_vault(game)
        exiled = game.state.players[0].exile[0]
        vault = only_oid(game, VAULT)

        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.player == 0, limit=200
        )
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == vault
        )
        game.apply(action)
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        assert game.state.objects[exiled].zone is Zone.BATTLEFIELD

    def test_it_costs_nothing(self, builder):
        """A Giant is {5}{G} and the board is six Islands: nothing could pay."""
        game = position(builder, [GIANT, BEAR, BEAR, BEAR])
        play_the_vault(game)
        exiled = game.state.players[0].exile[0]
        assert game.state.objects[exiled].def_id == GIANT
        vault = only_oid(game, VAULT)

        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.player == 0, limit=200
        )
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == vault
        )
        game.apply(action)
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        assert game.state.objects[exiled].zone is Zone.BATTLEFIELD


class TestTheLoaderGuard:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_hideaway_probe",
                "name": "Hideaway Probe",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "triggered",
                        "trigger": {"event": "self_enters", "source": "self"},
                        "effects": [effect],
                    }
                ],
            }
        )

    def test_a_depth_loads(self):
        compile_card(self._card({"op": "hideaway", "player": "you", "amount": {"const": 4}}))

    def test_without_one_it_is_refused(self):
        """Defaulted, it would look at one card and nothing downstream would care."""
        with pytest.raises(DslError, match="hideaway needs an 'amount'"):
            compile_card(self._card({"op": "hideaway", "player": "you"}))

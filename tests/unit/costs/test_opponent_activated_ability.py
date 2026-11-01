"""An ability somebody other than its controller may activate -- 602.1, 602.2.

Oft-Nabbed Goat is the witness: "{1}: Draw a card. Gain control of this creature
and put a -1/-1 counter on it. **Only your opponents may activate this ability**
and only as a sorcery." Activated abilities used to be offered to the source's
controller alone, so the Goat was a vanilla creature its owner could never give
away.

602.2: the player who activates an ability pays for it and controls it on the
stack. So "draw a card" and "gain control of this creature" are the
*activator's*, and the sorcery timing is the activator's main phase -- the
Goat's controller's turn is when nobody may activate it. And "your opponents" is
read against the controller *now*: once the Goat has changed hands, its old
owner is one of the players who may take it back.

"Any player may activate this ability" is the sibling wording and the same key.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import _activate_actions, _can_act_at_sorcery_speed
from commanderblitz.engine.objects import MINUS_ONE
from tests.conftest import activations, hand_ids, only_oid, pass_until, settle

GOAT = "t_oft_nabbed_goat"
WELL = "t_town_well"  # {2}: Draw a card. Any player may activate this ability.


def position(builder, mine=(GOAT,), *, active: int = 1):
    """Player 0 controls ``mine``; ``active`` is in their precombat main phase.

    Both players have Forests to pay with and a bear in hand, so the position
    stops at a real decision rather than auto-passing on.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + list(mine))
        .battlefield(1, ["forest"] * 3)
        .hand(0, ["t_bear"])
        .hand(1, ["t_bear"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
        .build()
    )
    return game, only_oid(game, mine[-1], 0)


def offered_to(game, oid: int) -> list:
    """The activations of ``oid`` the player with priority is offered."""
    return activations(game, oid)


class TestWhoIsOffered:
    def test_an_opponent_is_offered_it(self, builder):
        game, goat = position(builder, active=1)
        assert game.pending().player == 1
        assert offered_to(game, goat)

    def test_its_controller_is_not(self, builder):
        game, goat = position(builder, active=0)
        assert game.pending().player == 0
        assert not offered_to(game, goat)

    def test_only_as_a_sorcery_on_the_activators_turn(self, builder):
        """Player 1 asked on player 0's turn: it is not their main phase."""
        game, goat = position(builder, active=0)
        state = game.state
        offers = _activate_actions(state, 1, _can_act_at_sorcery_speed(state, 1))
        assert not [a for a in offers if a.source == goat]

    def test_any_player_may_activate_the_sibling(self, builder):
        for active in (0, 1):
            game, well = position(builder, mine=(WELL,), active=active)
            assert offered_to(game, well), f"player {active} is offered it"


class TestTheActivatorControlsIt:
    def test_the_activator_pays_draws_and_takes_the_goat(self, builder):
        game, goat = position(builder, active=1)
        before = len(hand_ids(game, 1))
        game.apply(offered_to(game, goat)[0])
        settle(game)
        state = game.state
        assert len(hand_ids(game, 1)) == before + 1, "the activator draws"
        assert len(hand_ids(game, 0)) == 1, "the Goat's old controller does not"
        assert state.objects[goat].controller == 1
        assert state.objects[goat].counter(MINUS_ONE) == 1
        tapped = [o for o in state.battlefield if state.objects[o].controller == 1 and state.objects[o].tapped]
        assert len(tapped) == 1, "the activator paid the {1}"

    def test_once_it_changes_hands_the_old_owner_may_take_it_back(self, builder):
        game, goat = position(builder, active=1)
        game.apply(offered_to(game, goat)[0])
        settle(game)
        assert not offered_to(game, goat), "its new controller is not an opponent"
        turn = game.state.turn
        pass_until(
            game,
            lambda g: g.state.turn > turn
            and g.state.active_player == 0
            and g.state.step is Step.PRECOMBAT_MAIN
            and g.pending() is not None
            and g.pending().player == 0,
        )
        assert offered_to(game, goat)


class TestTheDiesTrigger:
    def test_its_owner_draws_and_the_others_lose(self, builder):
        """The Goat's second sentence, to show the whole card can be written."""
        game, goat = position(builder, active=1)
        game.state.objects[goat].counters[MINUS_ONE] = 2
        game.state.bump_chars()
        game.apply(offered_to(game, goat)[0])  # the third counter kills a 3/3
        settle(game)
        assert goat not in game.state.battlefield
        assert len(hand_ids(game, 0)) == 1 + 3, "its owner draws that many"
        assert game.state.players[1].life == 40 - 3


def _probe(ability: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "Probe.",
            "mana_cost": "{1}",
            "types": ["Artifact"],
            "abilities": [{"text": "Probe.", **ability}],
        }
    )


DRAW = [{"op": "draw", "amount": {"const": 1}}]


class TestTheLoaderRefuses:
    def test_an_unknown_player(self):
        with pytest.raises(DslError, match="must be 'you', 'opponent' or 'any'"):
            compile_card(_probe({"kind": "activated", "cost": {"mana": "{1}"},
                                 "activated_by": "owner", "effects": DRAW}))

    def test_a_triggered_ability(self):
        with pytest.raises(DslError, match="only means anything on an activated ability"):
            compile_card(_probe({"kind": "triggered", "activated_by": "any",
                                 "trigger": {"event": "self_enters", "source": "self"},
                                 "effects": DRAW}))

    def test_an_ability_from_the_graveyard(self):
        with pytest.raises(DslError, match="from a hand or graveyard"):
            compile_card(_probe({"kind": "activated", "cost": {"mana": "{1}"},
                                 "activated_by": "any", "active_zones": ["graveyard"],
                                 "effects": [{"op": "return_to_hand",
                                              "objects": {"zone": "graveyard", "self_only": True}}]}))

    def test_a_mana_ability(self):
        with pytest.raises(DslError, match="mana ability"):
            compile_card(_probe({"kind": "activated", "cost": {"tap": True},
                                 "activated_by": "any", "is_mana_ability": True,
                                 "effects": [{"op": "add_mana", "mana": "{C}"}]}))

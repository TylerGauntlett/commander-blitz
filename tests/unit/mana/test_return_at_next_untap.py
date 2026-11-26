"""A mana ability whose drawback waits for its controller's next untap step.

    "{T}: Add one mana of any color. During your next untap step, as you untap
    your permanents, return this land to its owner's hand."
                                                    -- Undiscovered Paradise

Rules 502.3 and 502.4: the return is part of the untap step's untapping. It is
not a trigger, it uses no stack and no player gets priority for it, which is
what separates it from the two shapes an author would reach for first:

- **A `delay` to the next upkeep** is a delayed *trigger*. It would go on the
  stack after the land had untapped, and the controller could tap the land for
  mana once more in response -- a strictly better card than the printed one.
- **`return_to_hand` in the rider** returns the land at once, which is a
  different card again.

So `return_at_next_untap` marks the land (`GameObject.returns_at_untap_of`),
keyed to the activating seat -- the printed "your" -- and
`turn._untap_permanents` returns the marked permanents as that seat untaps. The
claims that would be wrong while looking right are about **whose** untap step
and **which** object: an opponent's untap step comes first and must not spend
the mark; an extra untap step of the controller's own is "your next untap
step" and must; and a land that left the battlefield and came back is a new
object (400.7), which owes nothing.

The witness is Undiscovered Paradise, whose generated proxy carries this rider
(`tests/cards/test_proxy.py`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.zones import move_object
from tests.conftest import hand_ids, only_oid, pass_until

PARADISE = "t_paradise"
SECOND_SUN = "t_second_sun"  # at each of your postcombat mains: +1 beginning phase
BOLT = "t_bolt"  # {R}: 3 damage to any target
COLOURS = ["W", "U", "B", "R", "G"]


def position(builder, mine=()):
    """Player 0's turn 1, in its precombat main, with a Paradise.

    The Bolt in hand is what stops the sandbox's auto-pass rolling straight past
    a main phase in which nobody has anything to spend mana on -- without it the
    game would already be on player 1's turn, and every claim below about
    *whose* untap step would be tested from the wrong seat.
    """
    game = (
        builder(players=2)
        .battlefield(0, [PARADISE, *mine])
        .hand(0, [BOLT])
        .library(0, ["island"] * 30)
        .library(1, ["island"] * 30)
        .build()
    )
    return game, only_oid(game, PARADISE, 0)


def tap(game, oid: int, colour: int = 0) -> None:
    """Tap the Paradise the way the payment solver taps it."""
    activate_mana_ability(game.state, oid, 0, 0, option_index=colour)


def returned(game, oid: int) -> list:
    """The moves that put this object into a hand, as the log recorded them."""
    return [
        e
        for e in game.state.events
        if e.type == EventType.ZONE_CHANGE and e.data.get("oid") == oid and e.data["to"] == "hand"
    ]


def at_main(turn: int):
    return lambda g: g.state.turn >= turn and g.state.step >= Step.PRECOMBAT_MAIN


class TestItIsAManaAbility:
    @pytest.mark.parametrize("colour", range(len(COLOURS)))
    def test_it_taps_for_any_colour(self, builder, colour):
        game, paradise = position(builder)
        tap(game, paradise, colour)
        assert game.state.players[0].mana_pool.to_dict() == {COLOURS[colour]: 1}

    def test_tapping_marks_it_for_its_controllers_untap_step(self, builder):
        game, paradise = position(builder)
        tap(game, paradise)
        obj = game.state.objects[paradise]
        assert obj.tapped and obj.zone is Zone.BATTLEFIELD, "nothing happens yet"
        assert obj.returns_at_untap_of == 0


class TestItGoesHomeAtTheRightUntapStep:
    def test_it_returns_at_its_controllers_next_untap_step(self, builder):
        game, paradise = position(builder)
        tap(game, paradise)
        pass_until(game, at_main(3))
        assert PARADISE in hand_ids(game, 0)
        (move,) = returned(game, paradise)
        assert (move.turn, move.step) == (3, int(Step.UNTAP)), "as the permanents untap"

    def test_not_at_an_opponents_untap_step(self, builder):
        """Player 1's untap step comes first, and it is not "your" untap step."""
        game, paradise = position(builder)
        assert game.state.active_player == 0
        tap(game, paradise)
        pass_until(game, at_main(3))
        opponents_untap = [
            e
            for e in game.state.events
            if e.type == EventType.STEP_ENDED and e.turn == 2 and str(e.data["step"]) == "UNTAP"
        ]
        assert opponents_untap, "player 1's untap step happened in between"
        assert [e.turn for e in returned(game, paradise)] == [3], "and spent nothing"

    def test_a_paradise_that_never_tapped_stays(self, builder):
        game, paradise = position(builder)
        pass_until(game, at_main(3))
        assert game.state.objects[paradise].zone is Zone.BATTLEFIELD
        assert returned(game, paradise) == []

    def test_an_extra_untap_step_is_your_next_untap_step(self, builder):
        """Sphinx of the Second Sun's added beginning phase untaps for real, so
        the land goes home in it -- the same turn it was tapped, not two turns
        later."""
        game, paradise = position(builder, [SECOND_SUN])
        tap(game, paradise)
        pass_until(game, at_main(2))
        (move,) = returned(game, paradise)
        assert (move.turn, move.step) == (1, int(Step.UNTAP))
        assert game.state.objects[paradise].returns_at_untap_of is None, "spent there"


class TestTheMarkBelongsToThatObject:
    def test_leaving_the_battlefield_clears_it(self, builder):
        """Blinked between the tap and the untap step, it is a new object
        (400.7) and owes the old one's drawback nothing."""
        game, paradise = position(builder)
        tap(game, paradise)
        move_object(game.state, paradise, Zone.EXILE)
        move_object(game.state, paradise, Zone.BATTLEFIELD)
        assert game.state.objects[paradise].returns_at_untap_of is None
        pass_until(game, at_main(3))
        assert game.state.objects[paradise].zone is Zone.BATTLEFIELD
        assert returned(game, paradise) == []

    def test_the_mark_is_spent_by_that_one_untap_step(self, builder):
        """Played again from hand, it untaps like any land afterwards."""
        game, paradise = position(builder)
        tap(game, paradise)
        pass_until(game, at_main(3))
        move_object(game.state, paradise, Zone.BATTLEFIELD)
        pass_until(game, at_main(5))
        assert game.state.objects[paradise].zone is Zone.BATTLEFIELD


class TestTheLoaderRefusesAMisreading:
    def test_it_names_no_other_object(self):
        """"Return **this land**": an `objects` beside the op would load and be
        ignored, returning the land when the card said something else."""
        model = CardModel.model_validate(
            {
                "id": "t_bad_paradise",
                "name": "Bad Paradise",
                "types": ["Land"],
                "abilities": [
                    {
                        "kind": "activated",
                        "is_mana_ability": True,
                        "cost": {"tap": True},
                        "effects": [
                            {"op": "add_mana", "mana": "{G}"},
                            {"op": "return_at_next_untap", "objects": {"self_only": True}},
                        ],
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="return_at_next_untap"):
            compile_card(model)

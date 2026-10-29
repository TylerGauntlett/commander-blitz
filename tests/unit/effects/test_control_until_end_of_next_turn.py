""""Gain control of target noncreature, nonland permanent that player controls
**until the end of your next turn**. It gains \"This permanent can't be
sacrificed\" until the end of your next turn." -- Stilt-Man, Towering Terror.

Rule 611.2b: an effect that lasts "until the end of your next turn" ends in the
cleanup step of the first turn of yours to *begin* after it was created. The
witness creates it from a combat-damage trigger, which is always during its
controller's own turn, so the turn it is made in is never "your next turn" --
ending the steal at that turn's cleanup is Act of Treason, a strictly weaker
card, and ending it at the opponent's turn's cleanup is the same mistake one
turn later. Created during an opponent's turn, the very next turn of yours is
the one. Both readings are pinned below, with the clock keyed by the seat and
compared against the turn it was made in, as `grant_playable`'s Light Up the
Stage permission already reads the same words.

Two more rules ride on the same clock:

* **800.4a.** When the player who gained control leaves the game, the effects
  giving them control end *before* what they still control is exiled -- so the
  stolen permanent goes back to the seat it was taken from rather than out of
  the game with the thief. The same holds for Act of Treason's shorter steal,
  which rides the same record. A seat whose next turn is the clock leaving the
  game ends the effect too, since that turn never comes.
* **701.17b, as a granted ability.** "This permanent can't be sacrificed" makes
  a sacrifice cost needing it unpayable and narrows an edict's pool, the two
  roads `cant_sacrifice` already closes. On this clock it is a
  `TempEffect(kind="cant_sacrifice")` on the permanent, not a row in
  `GameState.sacrifice_restrictions`: a granted ability ends with the object
  (400.7), and oids survive zone changes, so a table row would protect a
  flickered permanent for the rest of the duration.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import change_control, clear_until_eot
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.temp_effects import grant_cant_be_sacrificed, sacrifice_forbidden
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, only_oid, pass_until

STEAL = "t_long_steal"  # {U} instant: the witness's two sentences on a target creature
TREASON = "t_treason"  # gain control until end of turn
BEAR = "t_bear"
OUTLET = "t_sac_outlet"  # Sacrifice a creature: you gain 1 life.
EDICT = "t_edict"  # each opponent sacrifices a creature


def resolve(game) -> None:
    """Let the stack empty, answering every decision the most passive way."""
    for _ in range(40):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def cast(game, card_id: str, victim: int | None = None) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and (victim is None or TargetRef.obj(victim) in a.targets)
    )
    game.apply(action)
    resolve(game)


def pass_priority(game) -> None:
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))


def outlet_activations(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source is not None
        and game.state.objects[a.source].def_id == OUTLET
    ]


def handbacks(game, victim: int) -> list:
    """Every ``control_changed`` that moved ``victim`` away from player 0."""
    return [
        e
        for e in game.state.events
        if e.type == "control_changed" and e.source == victim and e.data["from"] == 0
    ]


def own_turn_steal(builder, players: int = 2):
    """Turn 1 is player 0's; they steal player 1's Bear in their main phase."""
    game = (
        builder(players=players)
        .hand(0, [STEAL])
        .battlefield(0, ["island"])
        .battlefield(1, [BEAR])
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    bear = only_oid(game, BEAR, 1)
    assert game.state.turn == 1
    cast(game, STEAL, bear)
    return game, bear


class TestTheClock:
    def test_the_thief_controls_it(self, builder):
        game, bear = own_turn_steal(builder)
        assert game.state.objects[bear].controller == 0

    def test_made_on_your_own_turn_it_outlasts_that_turns_cleanup(self, builder):
        """Turn 1 is the turn it was made in, not "your next turn"."""
        game, bear = own_turn_steal(builder)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.objects[bear].controller == 0

    def test_it_outlasts_the_opponents_turn(self, builder):
        game, bear = own_turn_steal(builder)
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.objects[bear].controller == 0

    def test_it_goes_back_in_the_cleanup_of_your_next_turn(self, builder):
        game, bear = own_turn_steal(builder)
        pass_until(game, lambda g: g.state.turn >= 4)
        assert game.state.objects[bear].controller == 1
        [back] = handbacks(game, bear)
        assert (back.turn, back.step) == (3, int(Step.CLEANUP))
        assert back.data["to"] == 1

    def test_made_on_an_opponents_turn_your_very_next_turn_ends_it(self, builder):
        """Turn 1 is player 1's; the steal resolves in it, so player 0's turn 2
        is "your next turn" and its cleanup hands the Bear back."""
        game = (
            builder(players=2)
            .hand(0, [STEAL])
            .battlefield(0, ["island"])
            .hand(1, [EDICT])
            .battlefield(1, [BEAR, "swamp"])
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        bear = only_oid(game, BEAR, 1)
        pass_priority(game)
        cast(game, STEAL, bear)
        assert game.state.objects[bear].controller == 0
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.objects[bear].controller == 1
        [back] = handbacks(game, bear)
        assert (back.turn, back.step) == (2, int(Step.CLEANUP))

    def test_the_clock_is_the_effects_controller_not_the_new_controller(self, builder):
        """`change_control`'s ``clock``: the cleanup that ends it is its seat's."""
        game = builder(players=3).battlefield(2, [BEAR]).build(advance=False)
        state = game.state
        bear = only_oid(game, BEAR, 2)
        change_control(state, bear, 1, duration="end_of_your_next_turn", clock=0)
        state.turn, state.active_idx = 2, 1
        clear_until_eot(state)
        assert state.objects[bear].controller == 1, "seat 1's turn is not seat 0's"
        state.turn, state.active_idx = 3, 0
        clear_until_eot(state)
        assert state.objects[bear].controller == 2


class TestTheControllerLeavingEndsIt:
    """800.4a: the control effect ends first, and only what the leaving player
    still controls afterwards is exiled."""

    def test_the_stolen_permanent_goes_home(self, builder):
        game, bear = own_turn_steal(builder, players=3)
        game.state.players[0].life = 0
        sba.run(game.state)
        assert game.state.players[0].has_lost
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].controller == 1
        assert game.state.objects[bear].until_eot == []

    def test_an_until_end_of_turn_steal_goes_home_too(self, builder):
        game = builder(players=3).battlefield(1, [BEAR]).build(advance=False)
        bear = only_oid(game, BEAR, 1)
        change_control(game.state, bear, 0, duration="until_end_of_turn")
        game.state.players[0].life = 0
        sba.run(game.state)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].controller == 1

    def test_a_permanent_steal_still_leaves_with_the_thief(self, builder):
        """No record of whom it came from, so nothing ends: still exiled."""
        game = builder(players=3).battlefield(1, [BEAR]).build(advance=False)
        bear = only_oid(game, BEAR, 1)
        change_control(game.state, bear, 0)
        game.state.players[0].life = 0
        sba.run(game.state)
        assert game.state.objects[bear].zone is Zone.EXILE

    def test_the_clock_seat_leaving_ends_it(self, builder):
        """Its next turn never comes, so the effect would otherwise stand for
        the rest of the game."""
        game = builder(players=3).battlefield(2, [BEAR]).build(advance=False)
        state = game.state
        bear = only_oid(game, BEAR, 2)
        change_control(state, bear, 1, duration="end_of_your_next_turn", clock=0)
        grant_cant_be_sacrificed(state, [bear], 0)
        state.players[0].life = 0
        sba.run(state)
        assert state.objects[bear].controller == 2
        assert not sacrifice_forbidden(state, bear)


class TestItCantBeSacrificed:
    def test_a_sacrifice_cost_needing_it_is_unpayable(self, builder):
        game = (
            builder(players=2)
            .hand(0, [STEAL])
            .battlefield(0, ["island", OUTLET])
            .battlefield(1, [BEAR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        bear = only_oid(game, BEAR, 1)
        cast(game, STEAL, bear)
        assert game.state.objects[bear].controller == 0
        assert outlet_activations(game) == [], "the only fodder can't be sacrificed"

    def test_an_edict_cannot_take_it(self, builder):
        """Granted during player 1's turn; player 1's edict then finds nothing
        player 0 may sacrifice."""
        game = (
            builder(players=2)
            .hand(0, [STEAL])
            .battlefield(0, ["island"])
            .hand(1, [EDICT])
            .battlefield(1, [BEAR, "swamp"])
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        bear = only_oid(game, BEAR, 1)
        pass_priority(game)
        cast(game, STEAL, bear)
        cast(game, EDICT)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].controller == 0

    def test_it_ends_with_the_clock(self, builder):
        """Player 0's own Bear, so control never moves and only the grant is
        under test: the outlet is first live in turn 4, after turn 3's cleanup."""
        game = (
            builder(players=2)
            .hand(0, [STEAL])
            .battlefield(0, ["island", OUTLET, BEAR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        cast(game, STEAL, bear)
        assert sacrifice_forbidden(game.state, bear)
        pass_until(game, lambda g: g.state.turn >= 3)
        assert sacrifice_forbidden(game.state, bear), "the opponent's turn is not the end"
        pass_until(game, lambda g: bool(outlet_activations(g)))
        assert game.state.turn == 4
        assert not sacrifice_forbidden(game.state, bear)

    def test_it_ends_with_the_object(self, builder):
        """400.7: the permanent that comes back is a new object without the
        granted ability, although it keeps its oid."""
        game = builder(players=2).battlefield(0, [BEAR]).build(advance=False)
        bear = only_oid(game, BEAR, 0)
        assert grant_cant_be_sacrificed(game.state, [bear], 0) == [bear]
        move_object(game.state, bear, Zone.EXILE)
        move_object(game.state, bear, Zone.BATTLEFIELD)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert not sacrifice_forbidden(game.state, bear)


STILT_MAN_TRIGGER = {
    "kind": "triggered",
    "text": "Whenever one or more Villains you control deal combat damage to a player, ...",
    "trigger": {
        "event": "creatures_deal_combat_damage",
        "controller": "you",
        "filter": {"subtypes": ["Villain"]},
        "per_player": True,
    },
    "targets": [
        {
            "id": "t1",
            "kind": "permanent",
            "count": 1,
            "selector": {
                "zone": "battlefield",
                "not_types": ["Creature", "Land"],
                "controller": {"binding": "defender"},
            },
        }
    ],
    "effects": [
        {"op": "gain_control", "objects": {"target": "t1"}, "duration": "end_of_your_next_turn"},
        {"op": "cant_sacrifice", "objects": {"target": "t1"}, "duration": "end_of_your_next_turn"},
    ],
}


def probe(effect: dict) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "x",
        "mana_cost": "{U}",
        "types": ["Sorcery"],
        "targets": [
            {
                "id": "t1",
                "kind": "permanent",
                "count": 1,
                "selector": {"types": ["Creature"], "zone": "battlefield"},
            }
        ],
        "spell_effects": [effect],
    }


class TestTheLoader:
    def test_the_witness_shape_compiles(self):
        compile_card(
            CardModel.model_validate(
                {
                    "id": "probe_stilt",
                    "name": "Probe Stilt",
                    "oracle_text": "x",
                    "mana_cost": "{4}{U}",
                    "types": ["Creature"],
                    "subtypes": ["Human", "Villain"],
                    "power": 3,
                    "toughness": 4,
                    "keywords": ["reach"],
                    "abilities": [STILT_MAN_TRIGGER],
                }
            )
        )

    def test_a_misspelt_control_duration_is_refused(self):
        with pytest.raises(DslError, match="unknown gain_control duration"):
            compile_card(
                CardModel.model_validate(
                    probe({"op": "gain_control", "objects": {"target": "t1"}, "duration": "until_your_next_turn"})
                )
            )

    def test_a_misspelt_sacrifice_duration_is_refused(self):
        with pytest.raises(DslError, match="unknown cant_sacrifice duration"):
            compile_card(
                CardModel.model_validate(
                    probe({"op": "cant_sacrifice", "objects": {"target": "t1"}, "duration": "until_your_next_turn"})
                )
            )

    def test_animate_does_not_borrow_the_new_control_word(self):
        """`animate` once built its list from `CONTROL_DURATIONS`; no animation
        implements this clock, so it must stay a load error there."""
        with pytest.raises(DslError, match="animate's 'duration'"):
            compile_card(
                CardModel.model_validate(
                    probe(
                        {
                            "op": "animate",
                            "objects": {"target": "t1"},
                            "power": 1,
                            "toughness": 1,
                            "duration": "end_of_your_next_turn",
                        }
                    )
                )
            )

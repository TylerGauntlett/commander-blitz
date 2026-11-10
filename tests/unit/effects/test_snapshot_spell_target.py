"""`snapshot` over a **spell** target: "that spell's mana value" after the
counter took it.

    "Counter target spell. At the beginning of your next first main phase, add
    X mana in any combination of colors, where X is that spell's mana value."
                                                         -- Plasm Capture

**The rules argument.** "That spell" is an object that has left the stack by
the time anybody asks about it, so its mana value is the one it had as it last
existed there (608.2h), and a spell's mana value counts the X it was cast with
(202.3e). The number is then carried into a delayed triggered ability, whose
values are fixed when it is created (603.7c). So the value is captured *before*
the counter moves anything, through the spell's stack item to its object, and
the delayed trigger reads the captured record.

The near miss is `counter`'s `as`, which binds the card the counter put into
the graveyard. Read from there the card has X = 0, a copy has nothing (it
ceased to exist, 707.10a) and a spell that can't be countered was never moved
-- and the rulings give the full mana in all three cases.
`TestTheGraveyardCardIsTheWrongAnswer` pins that spelling so the difference is
measured.

"Your next first main phase" is the `precombat_main` event (505.1a: the first
main phase is the precombat one; 505.1b makes every later one postcombat),
watched with `until_it_fires` and scoped to the caster. Cast during your own
precombat main phase, that phase has already begun, so it is the next turn's.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.ops_stack import put_copy_on_stack
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, find_action, pass_until, settle

CAPTURE = "t_pc_capture"
GRAVEYARD_CAPTURE = "t_pc_counted_capture"  # reads the countered card instead
DIVINATION = "t_draw_spell"  # {2}{U}: mana value 3
HYDRA = "t_x_spell"  # {X}{G}
UNSTOPPABLE = "t_cte_unstoppable"  # {2}{U}, can't be countered
FIREBALL = "t_fireball"  # {X}{R} instant
SPLIT = ["W", "U", "B", "R", "G"]


def opponents_turn(builder, spell: str, lands: list[str], capture: str = CAPTURE):
    """Seat 1 in their precombat main holding ``spell``; seat 0 holds the
    capture and one Island to cast it with. Seat 1's land in hand keeps the
    table from auto-passing out of the main phase once the stack is empty."""
    return (
        builder(players=2)
        .battlefield(0, ["island"])
        .battlefield(1, lands)
        .hand(0, [capture])
        .hand(1, [spell, "forest"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .active(1)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def cast_spell(game, pid: int, card_id: str, x: int | None = None) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    pending = game.pending()
    if pending is not None and pending.kind is DecisionKind.CHOOSE_X:
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
        )


def capture_top_of_stack(game, capture: str = CAPTURE) -> None:
    """Seat 0 casts the capture at the spell on top of the stack."""
    pass_until(game, lambda g: g.pending() is not None and g.pending().player == 0)
    sid = game.state.stack[-1].sid
    for action in game.legal_actions():
        if (
            action.kind is ActionKind.CAST
            and action.source is not None
            and game.state.objects[action.source].def_id == capture
            and TargetRef.stack(sid) in action.targets
        ):
            game.apply(action)
            return
    raise AssertionError("no cast of the capture at the top of the stack")


def to_main_phase_of(game, pid: int, *, after_turn: int) -> None:
    """Pass until the mana colour question, or failing one, until ``pid`` is
    active in the precombat main of a turn later than ``after_turn``."""
    pass_until(
        game,
        lambda g: (g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_MODE)
        or (
            g.state.active_player == pid
            and g.state.step is Step.PRECOMBAT_MAIN
            and g.state.turn > after_turn
            and not g.state.stack
            and not g.state.pending_triggers
            and not g.state.armed_delays
        ),
    )


def divide(game, colors: str) -> None:
    for color in colors:
        pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.CHOOSE_MODE)
        game.apply(find_action(game, ActionKind.CHOOSE, choice=SPLIT.index(color)))


def in_graveyard(game, card_id: str, pid: int) -> int:
    return next(
        oid for oid in game.state.players[pid].graveyard if game.state.objects[oid].def_id == card_id
    )


def pool(game, pid: int = 0) -> dict[str, int]:
    return game.state.players[pid].mana_pool.to_dict()


def mana_at_next_main(game, colors: str) -> dict[str, int]:
    """Walk from seat 1's turn 1 to seat 0's first main phase of turn 2, where
    the delayed trigger asks, and divide."""
    to_main_phase_of(game, 0, after_turn=1)
    assert game.state.active_player == 0 and game.state.step is Step.PRECOMBAT_MAIN
    assert game.state.turn == 2
    divide(game, colors)
    return pool(game)


class TestXIsThatSpellsManaValue:
    def test_a_plain_spell(self, builder):
        game = opponents_turn(builder, DIVINATION, ["island"] * 3)
        cast_spell(game, 1, DIVINATION)
        capture_top_of_stack(game)
        settle(game)
        assert in_graveyard(game, DIVINATION, 1)
        assert mana_at_next_main(game, "WUB") == {"W": 1, "U": 1, "B": 1}

    def test_the_x_it_was_cast_with_counts(self, builder):
        """202.3e: a Hydra cast for X = 2 is a mana value 3 spell."""
        game = opponents_turn(builder, HYDRA, ["forest"] * 3)
        cast_spell(game, 1, HYDRA, x=2)
        capture_top_of_stack(game)
        assert sum(mana_at_next_main(game, "GGG").values()) == 3

    def test_a_spell_that_cannot_be_countered_still_pays(self, builder):
        game = opponents_turn(builder, UNSTOPPABLE, ["island"] * 3)
        cast_spell(game, 1, UNSTOPPABLE)
        capture_top_of_stack(game)
        settle(game)
        assert any(
            e.type == "spell_resolved" and e.data.get("card") == UNSTOPPABLE
            for e in game.state.events
        )
        assert sum(mana_at_next_main(game, "RRR").values()) == 3

    def test_a_countered_copy_pays_its_mana_value(self, builder):
        game = opponents_turn(builder, DIVINATION, ["island"] * 3)
        cast_spell(game, 1, DIVINATION)
        put_copy_on_stack(game.state, 1, game.state.stack[-1])
        capture_top_of_stack(game)
        assert sum(mana_at_next_main(game, "UUU").values()) == 3

    def test_the_card_leaving_the_graveyard_changes_nothing(self, builder):
        game = opponents_turn(builder, DIVINATION, ["island"] * 3)
        cast_spell(game, 1, DIVINATION)
        capture_top_of_stack(game)
        settle(game)
        move_object(game.state, in_graveyard(game, DIVINATION, 1), Zone.EXILE, to_player=1)
        assert sum(mana_at_next_main(game, "GGG").values()) == 3


class TestTheGraveyardCardIsTheWrongAnswer:
    """`counter`'s `as` read afterwards: the card, not the spell."""

    def test_it_loses_the_x(self, builder):
        game = opponents_turn(builder, HYDRA, ["forest"] * 3, capture=GRAVEYARD_CAPTURE)
        cast_spell(game, 1, HYDRA, x=2)
        capture_top_of_stack(game, GRAVEYARD_CAPTURE)
        assert sum(mana_at_next_main(game, "G").values()) == 1

    def test_it_reads_nothing_for_a_copy(self, builder):
        game = opponents_turn(builder, DIVINATION, ["island"] * 3, capture=GRAVEYARD_CAPTURE)
        cast_spell(game, 1, DIVINATION)
        put_copy_on_stack(game.state, 1, game.state.stack[-1])
        capture_top_of_stack(game, GRAVEYARD_CAPTURE)
        to_main_phase_of(game, 0, after_turn=1)
        assert game.state.turn == 2
        assert game.pending().kind is not DecisionKind.CHOOSE_MODE
        assert pool(game) == {}


class TestYourNextFirstMainPhase:
    def test_cast_in_your_own_first_main_phase_it_waits_a_turn(self, builder):
        """That phase has already begun, so "next" is next turn's -- and the
        opponent's main phase in between is not yours."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 4)
            .hand(0, [DIVINATION, CAPTURE, "forest"])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        start_turn = game.state.turn
        cast_spell(game, 0, DIVINATION)
        capture_top_of_stack(game)
        settle(game)
        assert pool(game) == {}
        assert game.state.delayed_triggers
        pass_until(
            game,
            lambda g: g.state.active_player == 1 and g.state.step > Step.PRECOMBAT_MAIN,
        )
        assert game.state.delayed_triggers, "fired in the opponent's main phase"
        assert pool(game, 0) == {} and pool(game, 1) == {}
        to_main_phase_of(game, 0, after_turn=start_turn + 1)
        assert game.state.turn == start_turn + 2
        divide(game, "UUU")
        assert pool(game) == {"U": 3}
        assert not game.state.delayed_triggers

    def test_cast_in_your_upkeep_it_is_this_turns(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island", "t_bear"])
            .battlefield(1, ["mountain"] * 3)
            .hand(0, [CAPTURE, "forest"])
            .hand(1, [FIREBALL])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .active(0)
            .step(Step.UPKEEP)
            .build()
        )
        start_turn = game.state.turn
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 1)
        assert game.state.step is Step.UPKEEP
        cast_spell(game, 1, FIREBALL, x=2)
        capture_top_of_stack(game)
        to_main_phase_of(game, 0, after_turn=start_turn - 1)
        assert game.state.turn == start_turn
        divide(game, "RRR")
        assert pool(game) == {"R": 3}

    def test_it_fires_once(self, builder):
        game = opponents_turn(builder, DIVINATION, ["island"] * 3)
        cast_spell(game, 1, DIVINATION)
        capture_top_of_stack(game)
        mana_at_next_main(game, "UUU")
        assert not game.state.delayed_triggers


class TestTheLoaderGuard:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_pc_probe",
                "name": "Test Snapshot Probe",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "oracle_text": "Probe.",
                "targets": [{"id": "t1", "kind": "spell", "count": 1, "selector": {}}],
                "spell_effects": [effect],
            }
        )

    def test_a_spell_target_loads(self):
        compile_card(self._card({"op": "snapshot", "target": "t1", "as": "captured"}))

    def test_an_undeclared_target_is_refused(self):
        with pytest.raises(DslError):
            compile_card(self._card({"op": "snapshot", "target": "t2", "as": "captured"}))

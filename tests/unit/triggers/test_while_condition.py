"""`recheck: false` -- a trigger's "while" clause, checked only as it triggers.

    Pugnacious Hammerskull -- "Whenever this creature attacks **while** you
    don't control another Dinosaur, put a stun counter on it."

Rule 603.4 re-checks an intervening "**if**" on resolution; it says nothing of
"while", which qualifies the trigger event itself. So the Hammerskull's
ability triggers or not as it attacks, and once on the stack it resolves even
if a Dinosaur arrives in response. Written as a plain `condition` it would be
re-checked, and a Dinosaur flashed in would spare it the counter -- a strictly
better card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import attack_with, find_action, pass_until, plus_one_counters, settle

WHILE = "t_wc_while"
IF = "t_wc_if"
BEAR = "t_bear"
PUMP = "t_pump_spell"


def attacked(builder, card: str, *, bear_on_board: bool = False):
    """``card`` has attacked and its trigger is on the stack (if it triggered).

    The pump spell in hand, with a Forest open, is what makes the attacker's
    controller stop for priority with the trigger on the stack rather than
    auto-pass it through.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 2 + [card] + ([BEAR] if bear_on_board else []))
        .hand(0, [BEAR, PUMP])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .build()
    )
    oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == card)
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    attack_with(game, oid)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(game, lambda g: bool(g.state.stack) or g.state.combat is None)
    return game, oid


def bear_arrives(game) -> None:
    bear = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == BEAR)
    move_object(game.state, bear, Zone.BATTLEFIELD, to_player=0)


class TestWhileIsNotRechecked:
    def test_it_resolves_though_a_bear_arrived(self, builder):
        game, oid = attacked(builder, WHILE)
        assert game.state.stack, "it triggered: no Bear as it attacked"
        bear_arrives(game)

        settle(game)

        assert plus_one_counters(game, oid) == 1

    def test_an_if_is_rechecked_and_does_nothing(self, builder):
        """The same line as an intervening "if" (603.4), for contrast."""
        game, oid = attacked(builder, IF)
        assert game.state.stack
        bear_arrives(game)

        settle(game)

        assert plus_one_counters(game, oid) == 0

    def test_it_still_does_not_trigger_when_false(self, builder):
        game, oid = attacked(builder, WHILE, bear_on_board=True)

        settle(game)

        assert plus_one_counters(game, oid) == 0


class TestTheLoader:
    def test_recheck_without_a_condition_is_refused(self):
        with pytest.raises(DslError, match="recheck"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_wc_probe",
                        "name": "While Probe",
                        "mana_cost": "{1}",
                        "types": ["Creature"],
                        "power": 1,
                        "toughness": 1,
                        "abilities": [
                            {
                                "kind": "triggered",
                                "trigger": {"event": "attacks", "source": "self",
                                            "recheck": False},
                                "effects": [{"op": "draw", "amount": {"const": 1},
                                             "player": "you"}],
                            }
                        ],
                    }
                )
            )

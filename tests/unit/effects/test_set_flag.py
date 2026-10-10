"""Renown (702.112), and the one-way words a permanent can become.

The census routes renown as "`deals_combat_damage_to_player` trigger plus a
one-way flag, exactly like `monstrous`" -- and the trigger was already there.
What was missing is the flag, and the whole content of the keyword is that it
happens **once**: "if it isn't renowned, put two +1/+1 counters on it and it
becomes renowned."

Without somewhere to write the word the trigger fires on every combat damage
and the creature grows for ever. The counters cannot stand in for it either:
gating on "has no +1/+1 counters" would make a creature renewably renowned the
moment anything removed them, and would refuse to renown a creature that got a
counter from somewhere else.

`flags` is a set rather than a `renowned` boolean beside `monstrous`, because
the shape repeats and each new printed adjective would otherwise be three
edits -- a field, a condition leaf and an op -- to say one word. `monstrous` is
deliberately left alone: it carries its own event and an op that reads it, and
rewriting a shipped mechanic for tidiness is not worth the risk.

The flag clears with the rest of the battlefield state, so a renowned creature
that leaves and returns is a new object and may be renowned again. That is the
rule (400.7) and it is also the interesting half in play.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, find_action, only_oid, pass_until, plus_one_counters

RENOWNED = "t_renowned"  # 2/2, renown 2


def settle(game, limit: int = 40) -> None:
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("nothing resolved")


def swing(game, oid: int) -> None:
    """Attack an empty board and run combat out, so the damage lands.

    `settle` alone is not enough here: at the moment attackers are declared
    nothing is on the stack and no trigger is pending, so it returns before any
    damage has been dealt. The renown trigger only exists after the combat
    damage step. This is `test_combat.resolve_combat`'s exit condition -- past
    the damage step, or into another turn.
    """
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),))
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    start = game.state.turn
    for _ in range(60):
        if game.over:
            return
        if game.state.turn != start or int(game.state.step) > int(Step.COMBAT_DAMAGE):
            break
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    settle(game)


class TestRenown:
    def test_connecting_makes_it_renowned(self, builder):
        game = builder(players=2).battlefield(0, [RENOWNED]).build()
        oid = only_oid(game, RENOWNED, 0)
        swing(game, oid)
        assert plus_one_counters(game, oid) == 2
        assert "renowned" in game.state.objects[oid].flags

    def test_it_only_happens_once(self, builder):
        """The whole keyword. Without the flag the creature grows every combat."""
        game = builder(players=2).battlefield(0, [RENOWNED]).build()
        oid = only_oid(game, RENOWNED, 0)
        swing(game, oid)
        assert plus_one_counters(game, oid) == 2
        # A second combat, several turns later.
        pass_until(game, lambda g: g.state.turn >= 3)
        swing(game, oid)
        assert plus_one_counters(game, oid) == 2, "already renowned, so nothing more"

    def test_not_connecting_does_not_renown_it(self, builder):
        game = builder(players=2).battlefield(0, [RENOWNED]).build()
        oid = only_oid(game, RENOWNED, 0)
        settle(game)
        assert "renowned" not in game.state.objects[oid].flags
        assert plus_one_counters(game, oid) == 0

    def test_leaving_and_returning_clears_it(self, builder):
        """Rule 400.7: it is a new object, and may be renowned again."""
        game = builder(players=2).battlefield(0, [RENOWNED]).build()
        oid = only_oid(game, RENOWNED, 0)
        swing(game, oid)
        assert "renowned" in game.state.objects[oid].flags
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert game.state.objects[oid].flags == set()


class TestTheFlagItself:
    def test_it_starts_empty(self, builder):
        game = builder(players=2).battlefield(0, ["t_bear"]).build()
        assert game.state.objects[only_oid(game, "t_bear", 0)].flags == set()

    def test_the_condition_reads_the_source(self, builder):
        from commanderblitz.engine.effects.conditions import evaluate_condition

        game = builder(players=2).battlefield(0, [RENOWNED]).build()
        oid = only_oid(game, RENOWNED, 0)
        cond = {"has_flag": "renowned"}
        assert not evaluate_condition(game.state, cond, controller=0, source=oid)
        game.state.objects[oid].flags.add("renowned")
        assert evaluate_condition(game.state, cond, controller=0, source=oid)

    def test_it_is_serialized(self, builder):
        game = builder(players=2).battlefield(0, [RENOWNED]).build()
        oid = only_oid(game, RENOWNED, 0)
        game.state.objects[oid].flags.add("renowned")
        assert game.state.objects[oid].to_dict()["flags"] == ["renowned"]


class TestTheLoaderGuardsIt:
    def test_a_flagless_set_flag_is_refused(self):
        with pytest.raises(DslError, match="needs a 'flag'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "x",
                        "mana_cost": "{W}",
                        "types": ["Creature"],
                        "power": 1,
                        "toughness": 1,
                        "abilities": [
                            {
                                "kind": "triggered",
                                "text": "x",
                                "trigger": {
                                    "event": "deals_combat_damage_to_player",
                                    "source": "self",
                                },
                                "effects": [{"op": "set_flag"}],
                            }
                        ],
                    }
                )
            )

    def test_the_renown_card_compiles(self, registry):
        card = registry.get(RENOWNED)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert [e["op"] for e in ability.effects] == ["add_counters", "set_flag"]

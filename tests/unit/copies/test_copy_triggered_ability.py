"""Targeting a **triggered** ability on the stack, and not an activated one.

    Mister Fantastic -- "{R}{G}{W}{U}, {T}: Copy target triggered ability you
    control twice. You may choose new targets for the copies."

113.7a makes activated and triggered abilities on the stack the same kind of
object, but the printed word "triggered" narrows the target to one of them
(Strionic Resonator, Mister Fantastic). Without a record of which an ability
was, the only spelling was Peter Parker's Camera's "activated or triggered" --
a strictly wider card, able to copy a mana-hungry activation for free.

`StackItem.ability_kind` is that record, written as the ability goes on the
stack (`push_activated_ability`, `push_triggered_ability`) and kept by a copy.
The `ability_on_stack` selector's `ability_kind` clause reads it, in both
`candidates` and `still_legal`, so a target that is offered is one the
re-check on resolution accepts. The loader refuses the clause anywhere else.

"Twice" needs nothing new: two `copy_ability` effects on the one target.

Witness: Mister Fantastic (`mister_fantastic` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.stack import push_activated_ability, push_triggered_ability
from commanderblitz.engine.structs import TargetRef, TriggerInstance
from commanderblitz.engine.targeting import candidates, still_legal
from tests.conftest import only_oid

RESONATOR = "t_resonator"
TRIGGERER = "t_upkeep_gainer"  # at the beginning of your upkeep, gain 2
ACTIVATED = "t_gainer"  # {T}: you gain 2 life


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 4 + [RESONATOR, TRIGGERER, ACTIVATED])
        .build(advance=False)
    )


def trigger(game):
    trig = TriggerInstance(
        source_oid=only_oid(game, TRIGGERER, 0), ability_index=0, controller=0
    )
    for _ in push_triggered_ability(game.state, trig):
        raise AssertionError("this trigger chooses nothing")
    return game.state.stack[-1]


def activate(game):
    return push_activated_ability(game.state, only_oid(game, ACTIVATED, 0), 0, 0)


def spec(game):
    return game.state.registry.get(RESONATOR).abilities[0].targets[0]


def offered(game) -> list[int]:
    return [
        ref.id for ref in candidates(game.state, 0, spec(game), only_oid(game, RESONATOR, 0))
    ]


class TestTheStackRecordsTheKind:
    def test_an_activation_is_activated(self, builder):
        game = board(builder)
        assert activate(game).ability_kind == "activated"

    def test_a_trigger_is_triggered(self, builder):
        game = board(builder)
        assert trigger(game).ability_kind == "triggered"

    def test_a_copy_keeps_it(self, builder):
        """706.10: the copy is the same kind of ability as its original."""
        game = board(builder)
        item = trigger(game)
        ctx = EffectContext(
            state=game.state, controller=0, targets={"t1": [TargetRef.stack(item.sid)]}
        )
        for _ in OPS["copy_ability"](ctx, {"target": "t1"}):
            raise AssertionError("a targetless copy asks nothing")

        assert game.state.stack[-1].sid != item.sid
        assert game.state.stack[-1].ability_kind == "triggered"


class TestOnlyATriggerIsOffered:
    def test_the_trigger_is_offered(self, builder):
        game = board(builder)
        item = trigger(game)
        assert offered(game) == [item.sid]

    def test_an_activation_is_not(self, builder):
        game = board(builder)
        activate(game)
        assert offered(game) == []

    def test_with_both_on_the_stack_only_the_trigger(self, builder):
        game = board(builder)
        triggered = trigger(game)
        activate(game)
        assert offered(game) == [triggered.sid]

    def test_still_legal_agrees(self, builder):
        game = board(builder)
        triggered, activated = trigger(game), activate(game)
        source = only_oid(game, RESONATOR, 0)

        assert still_legal(game.state, 0, spec(game), TargetRef.stack(triggered.sid), source)
        assert not still_legal(
            game.state, 0, spec(game), TargetRef.stack(activated.sid), source
        )


class TestTheLoader:
    def _card(self, target) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_resonator_probe",
                "name": "Resonator Probe",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "{T}: Copy target triggered ability you control.",
                        "cost": {"tap": True},
                        "targets": [target],
                        "effects": [{"op": "copy_ability", "target": "t1"}],
                    }
                ],
            }
        )

    def test_it_loads(self):
        compile_card(
            self._card(
                {
                    "id": "t1",
                    "kind": "ability_on_stack",
                    "selector": {"controller": "you", "ability_kind": "triggered"},
                }
            )
        )

    def test_an_unknown_kind_is_refused(self):
        with pytest.raises(DslError, match="ability_kind"):
            compile_card(
                self._card(
                    {"id": "t1", "kind": "ability_on_stack", "selector": {"ability_kind": "static"}}
                )
            )

    def test_a_face_clause_is_refused(self):
        with pytest.raises(DslError, match="ability_on_stack"):
            compile_card(
                self._card(
                    {"id": "t1", "kind": "ability_on_stack", "selector": {"types": ["Creature"]}}
                )
            )

    def test_it_means_nothing_on_a_permanent(self):
        with pytest.raises(DslError, match="ability_kind"):
            compile_card(
                self._card(
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "selector": {"zone": "battlefield", "ability_kind": "triggered"},
                    }
                )
            )

"""What a permanent sacrificed as a cost had: its counters and its Equipment.

    Zack Fair: "{1}, Sacrifice Zack Fair: Target creature you control gains
    indestructible until end of turn. Put Zack Fair's counters on that creature
    and attach an Equipment that was attached to Zack Fair to that creature."

Zack is sacrificed while the cost is paid (601.2h, via 602.2b), so by the time
the ability resolves he is in the graveyard: his counters are gone (400.7) and
every Equipment that hung on him has fallen off (704.5n). Both halves of the
sentence are therefore last-known information (608.2h), and the only moment the
answer exists is between choosing him and moving him. The `sacrifice` cost's
`as` records it there (`costs.sacrificed_snapshot`): `zones.snapshot`'s counters,
plus each permanent attached to him with the zone timestamp it had.

What would be wrong without each claim below:

- **Every kind of counter.** `move_counters` with `all_kinds` and
  `from_had_counters: <name>` puts each kind he had, in its amount. Reading the
  live source (`from`) finds an empty graveyard card; `counters_had` reads a
  leave trigger's binding, which an activated ability never has.
- **Only what was attached to him.** `was_attached_to` names exactly the
  Equipment recorded on him; an Equipment that was sitting unattached is not
  one of them, and with none recorded the attach does nothing.
- **An Equipment, chosen.** With two attached, one moves and the controller
  picks it; the other stays where it fell.
- **The same object.** An Equipment that left the battlefield and came back
  before resolution is a new object (400.7) and does not match; one merely
  moved to another creature in the meantime still does.
- **The loader refuses** a `was_attached_to` or `from_had_counters` name that
  is not this ability's sacrifice `as`, `from_had_counters` without
  `all_kinds`, and `was_attached_to` in a target, chosen before costs are paid.

The witness is Zack Fair (`zack_fair` in `data/cards/auto/`); `t_zack_outlet` is
his ability on a test creature.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Keyword, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, attach
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, oids_of, only_oid, pass_until

ZACK = "t_zack_outlet"
GEAR = "t_zack_gear"
GEAR_TWO = "t_zack_gear_two"
BEAR = "t_bear"  # 2/2, the creature that inherits
GIANT = "t_big"  # 6/6, somewhere else to hang the gear


def position(builder, *gear: str, attached: int | None = None, counters=None):
    """Zack, a Bear, Plains to pay {1}, and ``gear`` on the battlefield.

    The first ``attached`` pieces of gear (all of them by default) are attached
    to Zack. The opponent holds a Bolt so the ability waits on the stack.
    """
    game = (
        builder(players=2)
        .battlefield(0, [ZACK, BEAR, "plains", "plains"])
        .battlefield(0, list(gear))
        .hand(1, ["t_bolt"])
        .battlefield(1, ["mountain"])
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    zack = only_oid(game, ZACK)
    gear_oids = [o for gid in dict.fromkeys(gear) for o in oids_of(game, gid)]
    for oid in gear_oids[: len(gear_oids) if attached is None else attached]:
        assert attach(game.state, oid, zack)
    for kind, n in (counters or {}).items():
        add_counters(game.state, zack, kind, n)
    return game, zack, only_oid(game, BEAR)


def activate(game, zack: int, target: int) -> None:
    action = next(
        a for a in activations(game, zack) if [t.id for t in a.targets] == [target]
    )
    game.apply(action)
    assert game.state.stack, "the ability should be waiting on the stack"


def resolve(game, pick: int | None = None) -> None:
    def done(g):
        decision = g.pending()
        if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS and pick:
            g.apply(
                next(
                    a
                    for a in g.legal_actions()
                    if a.kind is ActionKind.CHOOSE and [t.id for t in a.targets] == [pick]
                )
            )
        return not g.state.stack

    pass_until(game, done)


class TestTheCounters:
    def test_every_kind_moves_in_its_amount(self, builder):
        game, zack, bear = position(builder, counters={"+1/+1": 2, "charge": 1})
        activate(game, zack, bear)
        assert not game.state.objects[zack].on_battlefield
        resolve(game)
        obj = game.state.objects[bear]
        assert obj.counter("+1/+1") == 2
        assert obj.counter("charge") == 1
        assert Keyword.INDESTRUCTIBLE in chars(game.state, bear).keywords

    def test_no_counters_puts_none(self, builder):
        game, zack, bear = position(builder)
        activate(game, zack, bear)
        resolve(game)
        assert not any(game.state.objects[bear].counters.values())
        assert Keyword.INDESTRUCTIBLE in chars(game.state, bear).keywords


class TestTheEquipment:
    def test_the_equipment_moves_to_the_target(self, builder):
        game, zack, bear = position(builder, GEAR)
        gear = only_oid(game, GEAR)
        activate(game, zack, bear)
        assert game.state.objects[gear].attached_to is None, "it fell off with Zack"
        resolve(game)
        assert game.state.objects[gear].attached_to == bear

    def test_an_unattached_equipment_is_not_his(self, builder):
        game, zack, bear = position(builder, GEAR, attached=0)
        gear = only_oid(game, GEAR)
        activate(game, zack, bear)
        resolve(game)
        assert game.state.objects[gear].attached_to is None

    def test_with_two_one_moves_and_the_controller_picks(self, builder):
        game, zack, bear = position(builder, GEAR, GEAR_TWO)
        first, second = only_oid(game, GEAR), only_oid(game, GEAR_TWO)
        activate(game, zack, bear)
        resolve(game, pick=second)
        assert game.state.objects[second].attached_to == bear
        assert game.state.objects[first].attached_to is None

    def test_one_moved_elsewhere_meanwhile_is_still_his(self, builder):
        """Attached to the Giant in response, it is still the Equipment that
        was attached to Zack, and it moves to the target."""
        game, zack, bear = position(builder, GEAR, GIANT, attached=1)
        gear = only_oid(game, GEAR)
        activate(game, zack, bear)
        giant = only_oid(game, GIANT)
        assert attach(game.state, gear, giant)
        resolve(game)
        assert game.state.objects[gear].attached_to == bear

    def test_one_that_left_and_came_back_is_a_new_object(self, builder):
        game, zack, bear = position(builder, GEAR)
        gear = only_oid(game, GEAR)
        activate(game, zack, bear)
        move_object(game.state, gear, Zone.EXILE)
        move_object(game.state, gear, Zone.BATTLEFIELD)
        assert game.state.objects[gear].on_battlefield
        resolve(game)
        assert game.state.objects[gear].attached_to is None

    def test_one_that_is_gone_moves_nothing_and_the_counters_still_go(self, builder):
        game, zack, bear = position(builder, GEAR, counters={"+1/+1": 1})
        gear = only_oid(game, GEAR)
        activate(game, zack, bear)
        move_object(game.state, gear, Zone.GRAVEYARD)
        resolve(game)
        assert game.state.objects[bear].counter("+1/+1") == 1
        assert not game.state.objects[gear].on_battlefield


class TestTheLoaderRefuses:
    @pytest.fixture
    def raw(self):
        return {
            "id": "t_zack_probe",
            "name": "Zack Probe",
            "oracle_text": "",
            "mana_cost": "{1}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "activated",
                    "text": "probe",
                    "cost": {"mana": "{1}", "sacrifice": {"self_only": True, "as": "zack"}},
                    "targets": [
                        {
                            "id": "t1",
                            "kind": "permanent",
                            "selector": {"zone": "battlefield", "types": ["Creature"]},
                        }
                    ],
                    "effects": [
                        {
                            "op": "move_counters",
                            "all_kinds": True,
                            "from_had_counters": "zack",
                            "objects": {"target": "t1"},
                        },
                        {
                            "op": "attach",
                            "attachment": {
                                "zone": "battlefield",
                                "subtypes": ["Equipment"],
                                "was_attached_to": "zack",
                                "count": 1,
                            },
                            "objects": {"target": "t1"},
                        },
                    ],
                }
            ],
        }

    def compile(self, raw):
        return compile_card(CardModel.model_validate(raw))

    def test_the_well_formed_shape_loads(self, raw):
        self.compile(raw)

    def test_a_name_the_cost_does_not_bind(self, raw):
        raw["abilities"][0]["effects"][1]["attachment"]["was_attached_to"] = "other"
        with pytest.raises(DslError, match="sacrifice cost binds"):
            self.compile(raw)

    def test_a_name_with_no_sacrifice_as(self, raw):
        del raw["abilities"][0]["cost"]["sacrifice"]["as"]
        with pytest.raises(DslError, match="sacrifice cost binds"):
            self.compile(raw)

    def test_from_had_counters_without_all_kinds(self, raw):
        del raw["abilities"][0]["effects"][0]["all_kinds"]
        with pytest.raises(DslError, match="all_kinds"):
            self.compile(raw)

    def test_from_had_counters_beside_from(self, raw):
        raw["abilities"][0]["effects"][0]["from"] = {"self_only": True}
        with pytest.raises(DslError, match="'from' would"):
            self.compile(raw)

    def test_was_attached_to_in_a_target(self, raw):
        raw["abilities"][0]["targets"][0]["selector"]["was_attached_to"] = "zack"
        with pytest.raises(DslError, match="targets are chosen before costs"):
            self.compile(raw)

    def test_an_empty_name(self, raw):
        raw["abilities"][0]["effects"][1]["attachment"]["was_attached_to"] = ""
        with pytest.raises(DslError, match="was_attached_to"):
            self.compile(raw)

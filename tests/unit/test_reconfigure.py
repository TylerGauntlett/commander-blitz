"""Reconfigure — the first thing that takes an Equipment *off*.

    "Reconfigure {1} ({1}: Attach to target creature you control. {1}: Unattach
    this permanent. Reconfigure only as a sorcery.)"

Two halves, and only one of them existed. The attach half is the equip ability
already in the pool: an ordinary `sorcery_speed_only` activated ability whose
effect is `attach`. The other half had **no route at all** — the attach model
only ever *moved* an Equipment, and moving it onto a creature you do not want it
on is a different game action from taking it off.

The half that is easy to forget is the type line. Rule 702.151d: an attached
permanent with reconfigure is not a creature. These cards are printed "Artifact
Creature — Equipment", so without it a reconfigured blade both pumps the
creature it is on and attacks alongside it, which is a strictly better card and
looks completely normal on a board.

That is a `set_types` static gated on `{"is_attached": true}` — a new leaf in
the *static* condition language, and legal there for the reason counters are:
``attached_to`` is a field the attach primitive writes, so no layer can change
it and no static comes to depend on another static's output.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, _validate_effect, _validate_static_condition
from automtg.engine.characteristics import chars
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, Zone

BLADE = "t_reconfigurer"
BEAR = "t_bear"
FOREST = "forest"


def position(builder, lands: int = 4):
    game = (
        builder(players=2)
        .battlefield(0, [FOREST] * lands)
        .battlefield(0, [BLADE, BEAR])
        .build()
    )
    blade = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BLADE)
    bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
    return game, blade, bear


def run_unattach(game, oid: int, spec=None):
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    gen = OPS["unattach"](ctx, spec or {"op": "unattach", "objects": {"self_only": True}})
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return
        send = list(range(len(decision.options)))


def attach(game, blade: int, bear: int) -> None:
    from automtg.engine.primitives import attach as attach_primitive

    attach_primitive(game.state, blade, bear)


class TestTheOp:
    def test_it_takes_the_equipment_off(self, builder):
        game, blade, bear = position(builder)
        attach(game, blade, bear)
        assert game.state.objects[blade].attached_to == bear

        run_unattach(game, blade)

        assert game.state.objects[blade].attached_to is None

    def test_the_equipment_stays_on_the_battlefield(self, builder):
        """Unattaching is not sacrificing. It sits there, ready to go back on."""
        game, blade, bear = position(builder)
        attach(game, blade, bear)
        run_unattach(game, blade)
        assert game.state.objects[blade].zone is Zone.BATTLEFIELD

    def test_the_buff_stops(self, builder):
        game, blade, bear = position(builder)
        attach(game, blade, bear)
        assert chars(game.state, bear).power == 4, "2/2 plus the blade"

        run_unattach(game, blade)

        assert chars(game.state, bear).power == 2, "the static reads a live field"

    def test_unattaching_an_unattached_permanent_does_nothing(self, builder):
        """A legal activation that changes nothing — what the printed card says."""
        game, blade, _ = position(builder)
        run_unattach(game, blade)
        assert game.state.objects[blade].attached_to is None
        assert game.state.objects[blade].zone is Zone.BATTLEFIELD


class TestTheTypeLine:
    def test_it_is_a_creature_while_unattached(self, builder):
        game, blade, _ = position(builder)
        assert "Creature" in chars(game.state, blade).types

    def test_attaching_stops_it_being_a_creature(self, builder):
        """702.151d. Without it the blade pumps the bear *and* attacks."""
        game, blade, bear = position(builder)
        attach(game, blade, bear)
        assert "Creature" not in chars(game.state, blade).types
        assert "Artifact" in chars(game.state, blade).types

    def test_unattaching_makes_it_a_creature_again(self, builder):
        game, blade, bear = position(builder)
        attach(game, blade, bear)
        run_unattach(game, blade)
        assert "Creature" in chars(game.state, blade).types
        assert chars(game.state, blade).power == 1


class TestThroughTheCardsOwnAbilities:
    def test_both_halves_are_offered_at_sorcery_speed(self, builder):
        game, blade, _ = position(builder)
        activations = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == blade
        ]
        assert len(activations) == 2, "attach, and unattach"

    def test_activating_the_unattach_half_takes_it_off(self, builder):
        game, blade, bear = position(builder)
        attach(game, blade, bear)
        # The attach half needs a target; the unattach half does not, which is
        # what tells them apart without reading a label.
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == blade and not a.targets
        )
        game.apply(action)
        for _ in range(40):
            if game.state.objects[blade].attached_to is None:
                break
            decision = game.pending()
            if decision is None:
                break
            game.apply(game.legal_actions()[0])

        assert game.state.objects[blade].attached_to is None
        assert chars(game.state, bear).power == 2


class TestItCannotEquipItself:
    """Rule 301.5c, unreachable until now.

    Reconfigure prints the first Equipment that is also a creature, so it is the
    first one whose own "target creature you control" can find it. An Equipment
    attached to itself is a permanent nothing can ever detach — the buff reads
    `attached`, so it would pump itself for ever.
    """

    def test_the_target_list_does_not_offer_it(self, builder):
        game, blade, bear = position(builder)
        offered = {
            t.id
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == blade
            for t in a.targets
        }
        assert offered == {bear}

    def test_the_primitive_refuses_it_anyway(self, builder):
        game, blade, _ = position(builder)
        attach(game, blade, blade)
        assert game.state.objects[blade].attached_to is None


class TestTheGuards:
    def test_a_well_formed_unattach_loads(self):
        _validate_effect({"op": "unattach", "objects": {"self_only": True}}, "test", set())

    def test_omitting_objects_is_refused(self):
        with pytest.raises(DslError, match="unattach needs 'objects'"):
            _validate_effect({"op": "unattach"}, "test", set())

    def test_is_attached_takes_a_boolean(self):
        _validate_static_condition({"is_attached": True}, "test")
        _validate_static_condition({"is_attached": False}, "test")

    def test_a_non_boolean_is_attached_is_refused(self):
        """`false` is the other half of the keyword, so truthiness will not do."""
        with pytest.raises(DslError, match="is_attached"):
            _validate_static_condition({"is_attached": "yes"}, "test")

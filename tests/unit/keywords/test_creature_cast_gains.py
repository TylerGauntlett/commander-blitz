"""`creature_cast_gains` — what a creature cast free by an effect gains.

Strago and Relm: "Target opponent exiles cards from the top of their library
until they exile an instant, sorcery, or creature card. You may cast that card
without paying its mana cost. **If you cast a creature spell this way, it gains
haste and "At the beginning of the end step, sacrifice this creature."**"

The rider is owed by the *cast*, not by the card the walk found, and it is owed
to the *permanent* the spell becomes. Written as a `grant_keyword` and a
`grant_ability` after the walk, it would reach a hit left uncast in exile, or a
spell still on the stack whose battlefield arrival (400.7) sweeps both grants
away -- a creature that cannot attack and is never sacrificed, which is a far
stronger card than the printed one. So the rider rides `cast_for_free`: staged
on the spell only once it is on the stack and only for a creature spell, and
cashed by `zones._enter_battlefield` for as long as the permanent lasts (the
sentence prints no duration). The sacrifice is a *granted triggered ability*,
not a delayed trigger, so it belongs to the creature and is gone with it.

Suspend's haste is the near miss and stays suspend's alone; `cast_gains_keywords`
is Thundermane Dragon's until-end-of-turn rider on a cast off the library top.
"""

from __future__ import annotations

import inspect

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_cards import cast_rider
from commanderblitz.engine.enums import ActionKind, DecisionKind, Keyword, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import (
    activations,
    find_action,
    keywords,
    oids_of,
    pass_until,
    settle,
)

STRAGO = "strago_and_relm"
MOUNTAIN = "mountain"
FOREST = "forest"
BEAR = "t_bear"            # a creature card: the rider's one recipient
DIVINATION = "divination"  # a sorcery: cast this way, it gains nothing
SOL_RING = "sol_ring"      # a noncreature permanent, for the op-level boundary
SOURCE = "t_cascader"      # only somewhere for a bare effect to come from

HASTE = Keyword.HASTE.value


def board(builder, theirs: list[str]):
    """Strago and Relm with three Mountains, facing a library of ``theirs``."""
    game = (
        builder(players=2)
        .battlefield(0, [STRAGO, MOUNTAIN, MOUNTAIN, MOUNTAIN])
        .library(1, theirs)
        .build()
    )
    (strago,) = oids_of(game, STRAGO, 0)
    return game, strago


def sketch_and_lore(game, strago: int, *, cast: bool) -> None:
    """Activate, let it resolve, answer the free-cast offer, and resolve the spell."""
    game.apply(activations(game, strago)[0])
    pass_until(game, lambda g: g.pending() is not None and g.pending().kind is DecisionKind.MAY)
    game.apply(find_action(game, ActionKind.YES if cast else ActionKind.NO))
    settle(game)


def the_bear(game) -> int:
    (oid,) = oids_of(game, BEAR)
    return oid


def free_cast(builder, card_id: str, card_type: str) -> tuple:
    """Walk to ``card_id`` and say yes, stopping with the spell on the stack."""
    game = builder(players=2).battlefield(0, [SOURCE]).library(0, [FOREST, card_id]).build()
    (src,) = oids_of(game, SOURCE, 0)
    spec = {
        "op": "exile_until",
        "objects": {"types": [card_type]},
        "cast_free": True,
        "creature_cast_gains": {"keywords": ["haste"], "abilities": [0]},
    }
    ctx = EffectContext(state=game.state, controller=0, source_oid=src)
    gen = OPS["exile_until"](ctx, spec)
    assert inspect.isgenerator(gen)
    gen.send(None)
    with pytest.raises(StopIteration):
        gen.send([0])
    return game, the_one(game, card_id)


def the_one(game, card_id: str) -> int:
    """The one object of ``card_id``, in whatever zone it is."""
    (oid,) = [o.oid for o in game.state.objects.values() if o.def_id == card_id]
    return oid


class TestACreatureCastThisWay:
    def test_enters_with_haste_and_may_attack_this_turn(self, builder):
        game, strago = board(builder, [FOREST, BEAR])

        sketch_and_lore(game, strago, cast=True)

        bear = the_bear(game)
        assert game.state.objects[bear].controller == 0
        assert game.state.objects[bear].entered_turn == game.state.turn
        assert HASTE in keywords(game, bear)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        assert any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == bear for a in game.legal_actions()
        ), "summoning sick despite the haste it gained"

    def test_is_sacrificed_at_the_end_step_once(self, builder):
        game, strago = board(builder, [FOREST, BEAR, FOREST, FOREST])
        sketch_and_lore(game, strago, cast=True)
        bear = the_bear(game)
        mark = len(game.state.events)

        pass_until(game, lambda g: g.state.turn > 1)

        assert bear in game.state.players[1].graveyard, "its owner's graveyard (400.3)"
        since = game.state.events[mark:]
        fired = [e for e in since if e.type == EventType.ABILITY_TRIGGERED and e.source == bear]
        sacrificed = [e for e in since if e.type == EventType.SACRIFICED and e.source == bear]
        assert len(fired) == len(sacrificed) == 1
        assert (sacrificed[0].turn, sacrificed[0].step) == (1, Step.END_STEP), (
            "this turn's end step -- not combat, not cleanup"
        )

    def test_the_rider_is_the_permanents_and_not_the_cards(self, builder):
        """400.7: the object that comes back is new, and owes nothing."""
        game, strago = board(builder, [FOREST, BEAR])
        sketch_and_lore(game, strago, cast=True)
        bear = the_bear(game)
        obj = game.state.objects[bear]
        assert obj.cast_rider is None, "cashed as it entered, not kept for the next arrival"

        move_object(game.state, bear, Zone.HAND)
        move_object(game.state, bear, Zone.BATTLEFIELD)

        assert HASTE not in keywords(game, bear)
        assert not obj.granted_abilities_permanent


class TestNothingIsGained:
    def test_a_declined_cast_leaves_the_hit_in_exile_owing_nothing(self, builder):
        game, strago = board(builder, [FOREST, BEAR])

        sketch_and_lore(game, strago, cast=False)

        bear = the_one(game, BEAR)
        obj = game.state.objects[bear]
        assert obj.zone is Zone.EXILE
        assert obj.cast_rider is None
        assert not obj.granted_keywords

    def test_a_sorcery_cast_this_way_carries_no_rider(self, builder):
        game, spell = free_cast(builder, DIVINATION, "Sorcery")

        assert game.state.objects[spell].zone is Zone.STACK
        assert game.state.objects[spell].cast_rider is None

    def test_a_noncreature_permanent_spell_gains_nothing(self, builder):
        """"If you cast a **creature** spell this way" -- an artifact is not one."""
        game, ring = free_cast(builder, SOL_RING, "Artifact")
        assert game.state.objects[ring].cast_rider is None

        settle(game)

        assert game.state.objects[ring].zone is Zone.BATTLEFIELD
        assert HASTE not in keywords(game, ring)
        assert not game.state.objects[ring].granted_abilities_permanent

    def test_a_creature_spell_carries_it_on_the_stack(self, builder):
        """The contrast: the same walk, the same yes, a creature."""
        game, bear = free_cast(builder, BEAR, "Creature")

        assert game.state.objects[bear].zone is Zone.STACK
        assert game.state.objects[bear].cast_rider is not None


class TestTheLoader:
    @staticmethod
    def probe(spec_extra: dict, grantable: int = 1) -> None:
        spec = {
            "op": "exile_until",
            "objects": {"types": ["Creature"]},
            "player": {"target": "t1"},
            **spec_extra,
        }
        compile_card(
            CardModel.model_validate(
                {
                    "id": "t_creature_cast_gains_probe",
                    "name": "Creature Cast Gains Probe",
                    "mana_cost": "{2}",
                    "types": ["Sorcery"],
                    "targets": [
                        {"id": "t1", "kind": "player", "count": 1,
                         "selector": {"controller": "opponent"}}
                    ],
                    "spell_effects": [spec],
                    "grantable_abilities": [
                        {
                            "kind": "triggered",
                            "text": "At the beginning of the end step, sacrifice this creature.",
                            "trigger": {"event": "end_step", "controller": "any"},
                            "effects": [{"op": "sacrifice", "objects": {"self_only": True}}],
                        }
                    ][:grantable],
                }
            )
        )

    def test_strago_and_relms_rider_loads(self):
        self.probe(
            {"cast_free": True, "creature_cast_gains": {"keywords": ["haste"], "abilities": [0]}}
        )

    @pytest.mark.parametrize(
        ("extra", "grantable", "message"),
        [
            ({"creature_cast_gains": {"keywords": ["haste"]}}, 1, "needs 'cast_free'"),
            ({"cast_free": True, "creature_cast_gains": {}}, 1, "grants nothing"),
            ({"cast_free": True, "creature_cast_gains": {"keywords": ["hasty"]}}, 1,
             "unknown keyword"),
            ({"cast_free": True, "creature_cast_gains": {"haste": True}}, 1, "unknown keys"),
            ({"cast_free": True, "creature_cast_gains": {"abilities": [0]}}, 0,
             "grantable_abilities[0]"),
        ],
    )
    def test_a_rider_that_could_not_work_is_refused(self, extra, grantable, message):
        with pytest.raises(DslError, match=message.replace("[", r"\[").replace("]", r"\]")):
            self.probe(extra, grantable)


def test_the_granter_is_the_card_whose_ability_cast_it(builder):
    """``abilities`` index the *source's* ``grantable_abilities``, as `grant_ability` does."""
    game, strago = board(builder, [FOREST, BEAR])
    ctx = EffectContext(
        state=game.state,
        controller=0,
        source_oid=strago,
        targets={"t1": (TargetRef("player", 1),)},
    )

    assert cast_rider(ctx, None) is None
    rider = cast_rider(ctx, {"keywords": ["haste"], "abilities": [0]})
    assert rider is not None
    assert (rider.source, rider.keywords, rider.abilities) == (strago, ("haste",), (0,))

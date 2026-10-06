"""Classes (rule 716): a level the permanent has, and abilities that come with it.

Caretaker's Talent is the witness -- "(Gain the next level as a sorcery to add
its ability.) Whenever one or more tokens you control enter, draw a card. This
ability triggers only once each turn. / {W}: Level 2 / When this Class becomes
level 2, create a token that's a copy of target token you control. / {3}{W}:
Level 3 / Creature tokens you control get +2/+2." -- and behind it the whole
cycle: thirty-four Classes in the catalog, every one the same three-band shape.

`docs/rules-coverage.md` recorded no decision about Classes. The nearest one it
did record is **level up**, which it answered with an ordinary counter and a
conditional static -- and that answer is the wrong one here, for reasons the gap
record checked in full and each class below pins:

`TestTheLadder`
    716.2a: "[Cost]: Level N" means "[Cost]: This Class's level becomes N.
    Activate only if this Class is level N-1 and only as a sorcery." A counter
    added by an ordinary ability can be bought twice and bought out of order;
    the restriction is what makes a level a ladder, and it is a *legality*
    question.

`TestAbilitiesComeWithTheLevel`
    716.2b-c: the ability printed under a level is **there** only at that level
    or higher. Not refused, not inert -- absent -- and that has to hold for
    every reader of a permanent's abilities: legality (an activated ability),
    trigger collection (a triggered one), the characteristics pipeline (an
    anthem), the printed-face walks for player-wide statics and for "loses all
    abilities". A static condition could say "as long as level >= 3" for the
    anthem and nothing else could say it for the other four.

`TestSeatsAreKept`
    The gate cannot simply drop a missing ability, because an ability's
    position is its address: actions, stack items, the per-turn trigger cap and
    the once-each-turn ledger all name one by index. A level-3 ability is held
    by a `latent` stand-in at its printed seat.

`TestTheLevelIsNotACounter`
    716.3: the level is a property, entering at 1. Proliferate cannot reach it,
    and a copy -- which does not copy it (707.2) -- is a fresh level-1 Class.

`TestTheLevelIsSerialized`, `TestTheLoaderRefuses` and
`TestTheActivationSweepReachesEveryRung` cover the wire, the card format and the
per-card gate.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.costs import land_drops_available
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import AbilityKind, ActionKind, Keyword, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import create_token
from automtg.engine.serialize import card_view
from automtg.engine.zones import move_object
from tests.conftest import only_oid, pass_until

CLASS = "t_class"
BEAR = "t_bear"
FLYER = "t_flyer"

#: Printed positions on `t_class`, which the seat tests depend on.
ANTHEM_1, LEVEL_2, ENTERS_2, LAND_2, STRIP_2, LEVEL_3, ANTHEM_3, LIFE_3 = range(8)


def position(builder, *, level: int = 1, lands: int = 6, hand=()):
    """Player 0's main phase with ``t_class`` at ``level``, a Bear beside it.

    The opponent has a Flyer, which is what "creatures your opponents control
    lose all abilities" is visible on, and a Lightning Bolt they never cast
    beside a Mountain: an instant they could answer with is what stops the
    engine auto-passing a level line straight through to resolution, so a test
    can look at the stack in between.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * lands)
        .battlefield(0, [BEAR])
        .battlefield(0, [CLASS], level=level)
        .battlefield(1, [FLYER, "mountain"])
        .hand(1, ["lightning_bolt"])
        .hand(0, list(hand))
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .build()
    )
    return game, only_oid(game, CLASS)


def activation(game, oid: int, index: int):
    """The legal activation of ability ``index`` of ``oid``, or ``None``."""
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid and a.ability_index == index
        ),
        None,
    )


def activate(game, oid: int, index: int) -> None:
    action = activation(game, oid, index)
    assert action is not None, [a.label for a in game.legal_actions()]
    game.apply(action)


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def pt(game, oid: int) -> tuple[int | None, int | None]:
    derived = chars(game.state, oid)
    return derived.power, derived.toughness


def run(game, effects, controller: int = 0, source: int | None = None) -> None:
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    gen = execute(ctx, effects)
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


class TestTheLadder:
    def test_level_one_offers_level_two_and_not_level_three(self, builder):
        game, cls = position(builder)
        assert activation(game, cls, LEVEL_2) is not None
        assert activation(game, cls, LEVEL_3) is None

    def test_the_level_rises_when_the_ability_resolves_not_when_it_is_activated(self, builder):
        """716.2a's level line is an activated ability and uses the stack: an
        opponent can answer it, and until it resolves the Class is level 1."""
        game, cls = position(builder)
        activate(game, cls, LEVEL_2)
        assert game.state.stack
        assert game.state.objects[cls].class_level == 1
        resolve(game)
        assert game.state.objects[cls].class_level == 2

    def test_level_two_cannot_be_bought_twice(self, builder):
        game, cls = position(builder)
        activate(game, cls, LEVEL_2)
        resolve(game)
        assert activation(game, cls, LEVEL_2) is None
        assert activation(game, cls, LEVEL_3) is not None

    def test_the_top_of_the_ladder_offers_nothing(self, builder):
        game, cls = position(builder, level=3)
        assert activation(game, cls, LEVEL_2) is None
        assert activation(game, cls, LEVEL_3) is None

    def test_two_rungs_in_one_turn(self, builder):
        """Nothing limits levels per turn -- only the order."""
        game, cls = position(builder)
        activate(game, cls, LEVEL_2)
        resolve(game)
        activate(game, cls, LEVEL_3)
        resolve(game)
        assert game.state.objects[cls].class_level == 3

    def test_only_as_a_sorcery(self, builder):
        """Not during combat, and not with anything on the stack."""
        game, cls = position(builder)
        assert activation(game, cls, LEVEL_2) is not None
        game.state.step = Step.BEGIN_COMBAT
        assert activation(game, cls, LEVEL_2) is None

    def test_not_while_the_level_ability_is_on_the_stack(self, builder):
        """The stack is not empty, so the level-3 line waits even though the
        answer to "is this Class level 2" is about to be yes."""
        game, cls = position(builder)
        activate(game, cls, LEVEL_2)
        assert activation(game, cls, LEVEL_3) is None

    def test_a_level_line_is_paid_for(self, builder):
        game, cls = position(builder, lands=0)
        assert activation(game, cls, LEVEL_2) is None

    def test_the_effect_does_nothing_to_a_class_that_has_left(self, builder):
        """113.7a: the ability resolves without its source, and there is no
        level to set on a card in a graveyard."""
        game, cls = position(builder)
        activate(game, cls, LEVEL_2)
        move_object(game.state, cls, Zone.GRAVEYARD)
        resolve(game)
        assert game.state.objects[cls].class_level == 1

    def test_becomes_is_a_set_not_an_increment(self, builder):
        """A copy of the level-2 line resolving on a level-2 Class leaves it at 2."""
        game, cls = position(builder, level=2)
        run(game, [{"op": "become_level", "level": 2}], source=cls)
        assert game.state.objects[cls].class_level == 2


class TestAbilitiesComeWithTheLevel:
    def test_a_level_one_ability_is_always_there(self, builder):
        game, _ = position(builder)
        bear = only_oid(game, BEAR, 0)
        assert pt(game, bear) == (3, 2)

    def test_a_level_three_anthem_is_absent_below_three(self, builder):
        game, _ = position(builder, level=2)
        assert pt(game, only_oid(game, BEAR, 0)) == (3, 2)

    def test_a_level_three_anthem_switches_on_as_the_level_is_gained(self, builder):
        game, cls = position(builder, level=2)
        bear = only_oid(game, BEAR, 0)
        activate(game, cls, LEVEL_3)
        resolve(game)
        assert pt(game, bear) == (3, 4)

    def test_every_lower_level_stays_on(self, builder):
        """716.2b: "the abilities of its level and of each level below it"."""
        game, _ = position(builder, level=3)
        assert pt(game, only_oid(game, BEAR, 0)) == (3, 4)
        assert land_drops_available(game.state, 0) == 2

    def test_a_level_gated_activated_ability_is_not_offered_below_its_level(self, builder):
        game, cls = position(builder, level=2)
        assert activation(game, cls, LIFE_3) is None

    def test_a_level_gated_activated_ability_is_offered_at_its_level(self, builder):
        game, cls = position(builder, level=3)
        life = game.state.players[0].life
        activate(game, cls, LIFE_3)
        resolve(game)
        assert game.state.players[0].life == life + 2

    def test_a_level_gated_trigger_does_not_fire_below_its_level(self, builder):
        game, _ = position(builder, level=1)
        life = game.state.players[0].life
        create_token(game.state, BEAR, 0)
        resolve(game)
        assert game.state.players[0].life == life

    def test_a_level_gated_trigger_fires_at_its_level(self, builder):
        game, _ = position(builder, level=2)
        life = game.state.players[0].life
        create_token(game.state, BEAR, 0)
        resolve(game)
        assert game.state.players[0].life == life + 1

    def test_a_level_gated_player_wide_static(self, builder):
        """`player_statics` walks the printed face, so it needs the gate too."""
        low, _ = position(builder, level=1)
        high, _ = position(builder, level=2)
        assert land_drops_available(low.state, 0) == 1
        assert land_drops_available(high.state, 0) == 2

    def test_a_level_gated_lose_all_abilities(self, builder):
        """`_ability_statics` walks the printed face too, for its own reason."""
        low, _ = position(builder, level=1)
        high, _ = position(builder, level=2)
        assert Keyword.FLYING.value in chars(low.state, only_oid(low, FLYER, 1)).keywords
        assert Keyword.FLYING.value not in chars(high.state, only_oid(high, FLYER, 1)).keywords


class TestSeatsAreKept:
    def test_the_list_is_as_long_as_the_printed_one(self, builder):
        game, cls = position(builder)
        have = abilities_of(game.state, cls)
        assert len(have) == len(game.state.card(cls).abilities)
        assert [a.index for a in have] == list(range(len(have)))

    def test_a_missing_ability_holds_its_seat_with_a_latent_stand_in(self, builder):
        game, cls = position(builder)
        have = abilities_of(game.state, cls)
        latent = {a.index for a in have if a.kind is AbilityKind.LATENT}
        assert latent == {ENTERS_2, LAND_2, STRIP_2, ANTHEM_3, LIFE_3}
        stand_in = have[ANTHEM_3]
        assert not (stand_in.is_activated or stand_in.is_triggered or stand_in.is_static)
        assert not stand_in.is_mana_ability
        assert stand_in.text == "Creatures you control get +0/+2."

    def test_the_level_three_line_keeps_its_number_at_every_level(self, builder):
        """Were seats dropped, "{1}{W}: Level 3" would be ability 2 at level 1
        and 5 at level 3, and a stack item would resolve the wrong line."""
        game, cls = position(builder, level=2)
        action = activation(game, cls, LEVEL_3)
        assert action is not None and action.ability_index == LEVEL_3
        game.apply(action)
        assert game.state.stack[-1].ability_index == LEVEL_3

    def test_a_card_that_is_not_a_class_gets_its_printed_tuple_back(self, builder):
        game, _ = position(builder)
        bear = only_oid(game, BEAR, 0)
        assert abilities_of(game.state, bear) is game.state.card(bear).abilities


class TestTheLevelIsNotACounter:
    def test_a_class_enters_at_level_one(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"])
            .hand(0, [CLASS])
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .build()
        )
        pass_until(game, lambda g: (d := g.pending()) is not None and d.player == 0)
        cast = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST)
        game.apply(cast)
        resolve(game)
        cls = only_oid(game, CLASS, 0)
        assert game.state.objects[cls].class_level == 1
        assert game.state.objects[cls].counters == {}

    def test_proliferate_does_not_touch_it(self, builder):
        game, cls = position(builder, level=2)
        run(game, [{"op": "proliferate"}])
        assert game.state.objects[cls].class_level == 2
        assert game.state.objects[cls].counters == {}

    def test_a_copy_is_a_fresh_level_one_class(self, builder):
        """707.2: the level is not a copiable value."""
        game, _ = position(builder, level=3)
        (copy,) = create_token(game.state, CLASS, 0)
        assert game.state.objects[copy].class_level == 1

    def test_it_comes_back_at_level_one(self, builder):
        """A permanent that left and returned is a new object (400.7), and a
        new Class enters at level 1 (716.3)."""
        game, cls = position(builder, level=3)
        move_object(game.state, cls, Zone.HAND)
        move_object(game.state, cls, Zone.BATTLEFIELD)
        assert game.state.objects[cls].class_level == 1
        assert pt(game, only_oid(game, BEAR, 0)) == (3, 2)

    def test_it_leaves_with_the_level_it_had(self, builder):
        """603.10a looks back: a leaves-the-battlefield trigger is collected off
        the object after it has left, and must see the level it left at."""
        game, cls = position(builder, level=3)
        move_object(game.state, cls, Zone.GRAVEYARD)
        assert game.state.objects[cls].class_level == 3
        have = abilities_of(game.state, cls)
        assert have[ANTHEM_3].kind is AbilityKind.STATIC


class TestTheLevelIsSerialized:
    def test_a_class_carries_its_level(self, builder):
        game, cls = position(builder, level=2)
        assert card_view(game.state, cls)["level"] == 2

    def test_a_card_with_no_levels_carries_none(self, builder):
        game, _ = position(builder)
        assert "level" not in card_view(game.state, only_oid(game, BEAR, 0))

    def test_the_full_view_has_it(self, builder):
        game, cls = position(builder, level=3)
        assert game.state.objects[cls].to_dict()["class_level"] == 3


def _class(**over):
    card = {
        "id": "t_x",
        "name": "X",
        "mana_cost": "{W}",
        "types": ["Enchantment"],
        "subtypes": ["Class"],
        "abilities": [
            {"kind": "level", "text": "{W}: Level 2", "level": 2, "cost": {"mana": "{W}"}},
            {
                "kind": "static",
                "text": "Creatures you control get +1/+1.",
                "level": 2,
                "effect": "buff",
                "affects": {"controller": "you", "types": ["Creature"]},
                "power": {"const": 1},
                "toughness": {"const": 1},
            },
        ],
    }
    card.update(over)
    return card


def compile_(card):
    return compile_card(CardModel.model_validate(card))


def _line(level: int, **over):
    line = {"kind": "level", "text": f"{{W}}: Level {level}", "level": level, "cost": {"mana": "{W}"}}
    line.update(over)
    return line


class TestTheLoaderRefuses:
    def test_the_well_formed_class_loads(self):
        card = compile_(_class())
        assert card.top_level == 2
        line = card.abilities[0]
        assert line.is_activated and line.sorcery_speed_only and line.becomes_level == 2
        assert line.effects == ({"op": "become_level", "level": 2},)
        assert card.abilities[1].level == 2

    def test_levels_on_a_card_that_is_not_a_class(self):
        with pytest.raises(DslError, match="Class"):
            compile_(_class(subtypes=[]))

    def test_a_gap_in_the_ladder(self):
        with pytest.raises(DslError, match="no gap"):
            compile_(_class(abilities=[_line(2), _line(4)]))

    def test_two_lines_for_one_level(self):
        with pytest.raises(DslError, match="no gap"):
            compile_(_class(abilities=[_line(2), _line(2)]))

    def test_an_ability_under_a_level_no_line_reaches(self):
        card = _class()
        card["abilities"][1]["level"] = 3
        with pytest.raises(DslError, match="could never be present"):
            compile_(card)

    def test_level_one_written_out(self):
        card = _class()
        card["abilities"][1]["level"] = 1
        with pytest.raises(DslError, match="omits the key"):
            compile_(card)

    def test_a_level_line_that_writes_its_own_effect(self):
        line = _line(2, effects=[{"op": "draw", "amount": {"const": 1}}])
        with pytest.raises(DslError, match="rule 716"):
            compile_(_class(abilities=[line]))

    def test_a_level_line_that_is_not_a_sorcery(self):
        with pytest.raises(DslError, match="rule 716"):
            compile_(_class(abilities=[_line(2, sorcery_speed_only=False)]))

    def test_a_level_line_without_a_level(self):
        line = _line(2)
        del line["level"]
        with pytest.raises(DslError, match="needs the 'level'"):
            compile_(_class(abilities=[line]))

    def test_a_level_line_without_a_cost(self):
        line = _line(2)
        del line["cost"]
        with pytest.raises(DslError, match="needs the 'cost'"):
            compile_(_class(abilities=[line]))

    def test_become_level_written_by_hand(self):
        ability = {
            "kind": "activated",
            "text": "{W}: Level 2",
            "cost": {"mana": "{W}"},
            "effects": [{"op": "become_level", "level": 2}],
        }
        with pytest.raises(DslError, match="written by the loader"):
            compile_(_class(abilities=[ability]))

    def test_a_level_gate_outside_the_battlefield(self):
        card = _class()
        card["abilities"][1]["active_zones"] = ["graveyard"]
        with pytest.raises(DslError, match="only exists on the battlefield"):
            compile_(card)

    def test_a_granted_ability_with_a_level(self):
        card = _class(
            grantable_abilities=[
                {
                    "kind": "static",
                    "text": "gets +1/+1",
                    "level": 2,
                    "effect": "buff",
                    "affects": {"self_only": True},
                    "power": {"const": 1},
                    "toughness": {"const": 1},
                }
            ]
        )
        with pytest.raises(DslError, match="granted ability"):
            compile_(card)

    def test_a_class_with_no_levels_is_accepted_and_inert(self):
        """The Saga rule: this is what an unimplemented Class looks like."""
        card = compile_(_class(abilities=[]))
        assert card.top_level == 0


class TestTheActivationSweepReachesEveryRung:
    """`tests/cards/test_every_card_works.py` activates every activated ability
    of every shipped card. A level-3 line and a level-3 ability are not
    activatable on a fresh level-1 Class, so the sweep stands the Class on the
    rung each one needs -- the way it stocks counters for a counter cost --
    rather than reporting a working card as broken or skipping the ability."""

    def test_the_sweep_activates_every_level_line_and_gated_ability(self, registry):
        from tests.cards.test_every_card_works import TestActivatedAbilities

        TestActivatedAbilities().test_every_activated_ability_can_be_used(registry, CLASS)

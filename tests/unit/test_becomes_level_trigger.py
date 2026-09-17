"""`becomes_level` — "When this Class becomes level N" (716.4).

The second commit of the Class subsystem. Caretaker's Talent is the witness:
"{W}: Level 2 / When this Class becomes level 2, create a token that's a copy of
target token you control." A Class printed in the catalog carries this line on
eleven of its thirty-four cards, and it is the payoff for buying the level.

The two near misses the gap record named, each a class below:

`TestItFiresOnTheLevelNotTheActivation`
    `ability_activated` fires as the level line is *activated*. The level line
    uses the stack, so that is a whole round of priority before the Class is
    level 2 -- the opponent could destroy the Class in response and the token
    would still be made.

`TestItFiresOnceOnItsOwnRung`
    `counter_placed` on an invented level counter fires on every level, so the
    level-3 purchase would make a second token. The trigger carries the level it
    waits for and the event carries the level reached, compared exactly as a
    Saga's chapter is.

`TestCaretakersTalent` plays the whole witness: its level-1 batched,
once-a-turn token draw (already sayable), the level-2 copy of a token, and the
level-3 token anthem. `TestTheLoaderRefuses` covers the card format.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.primitives import create_token
from automtg.engine.zones import move_object
from tests.conftest import oids_of, only_oid, pass_until

CARETAKER = "t_caretakers_talent"
WATCHER = "t_level_watcher"
SOLDIER = "human_soldier_1_1_w"

#: Printed positions.
C_DRAW, C_LEVEL_2, C_COPY, C_LEVEL_3, C_ANTHEM = range(5)
W_LEVEL_2, W_GAIN_2, W_LEVEL_3, W_GAIN_3 = range(4)


def position(builder, card: str, *, level: int = 1, tokens: int = 0):
    """Player 0's main phase, ``card`` at ``level``, ``tokens`` Soldiers beside it.

    The opponent holds a Lightning Bolt beside a Mountain so the engine stops for
    a response rather than auto-passing a level line straight to resolution.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 8)
        .battlefield(0, [card], level=level)
        .battlefield(0, [SOLDIER] * tokens)
        .battlefield(1, ["mountain"])
        .hand(1, ["lightning_bolt"])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .build()
    )
    for oid in oids_of(game, SOLDIER, 0):
        game.state.objects[oid].is_token = True
    game.state.bump_chars()
    return game, only_oid(game, card)


def activate(game, oid: int, index: int) -> None:
    action = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid and a.ability_index == index
        ),
        None,
    )
    assert action is not None, [a.label for a in game.legal_actions()]
    game.apply(action)


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def level_events(game) -> list[int]:
    return [e.data["level"] for e in game.state.events if e.type == EventType.BECAME_LEVEL]


class TestTheEvent:
    def test_the_level_line_resolving_fires_it_with_the_level(self, builder):
        game, cls = position(builder, WATCHER)
        activate(game, cls, W_LEVEL_2)
        resolve(game)
        (event,) = [e for e in game.state.events if e.type == EventType.BECAME_LEVEL]
        assert event.source == cls and event.data["oid"] == cls and event.data["level"] == 2

    def test_a_level_that_does_not_change_fires_nothing(self, builder):
        """"Becomes" is a change. A copied level line on a Class already at that
        level sets nothing and announces nothing."""
        from tests.unit.test_class_levels import run

        game, cls = position(builder, WATCHER, level=2)
        run(game, [{"op": "become_level", "level": 2}], source=cls)
        assert level_events(game) == []


class TestItFiresOnTheLevelNotTheActivation:
    def test_nothing_triggers_while_the_level_line_is_on_the_stack(self, builder):
        game, cls = position(builder, WATCHER)
        life = game.state.players[0].life
        activate(game, cls, W_LEVEL_2)
        assert game.state.stack
        assert not game.state.pending_triggers
        assert game.state.players[0].life == life

    def test_a_class_destroyed_in_response_never_becomes_level_two(self, builder):
        game, cls = position(builder, WATCHER)
        life = game.state.players[0].life
        activate(game, cls, W_LEVEL_2)
        move_object(game.state, cls, Zone.GRAVEYARD)
        resolve(game)
        assert level_events(game) == []
        assert game.state.players[0].life == life


class TestItFiresOnceOnItsOwnRung:
    def test_level_two_fires_the_level_two_ability_only(self, builder):
        game, cls = position(builder, WATCHER)
        life = game.state.players[0].life
        activate(game, cls, W_LEVEL_2)
        resolve(game)
        assert game.state.players[0].life == life + 2

    def test_level_three_does_not_fire_level_two_again(self, builder):
        game, cls = position(builder, WATCHER)
        life = game.state.players[0].life
        activate(game, cls, W_LEVEL_2)
        resolve(game)
        activate(game, cls, W_LEVEL_3)
        resolve(game)
        assert game.state.players[0].life == life + 2 + 3
        assert level_events(game) == [2, 3]

    def test_it_is_this_class_and_not_another(self, builder):
        """The loader supplies `source: "self"`: a second Class going up a level
        does not fire the first one's ability."""
        game, cls = position(builder, WATCHER)
        (other,) = create_token(game.state, WATCHER, 0)
        life = game.state.players[0].life
        from tests.unit.test_class_levels import run

        run(game, [{"op": "become_level", "level": 2}], source=other)
        resolve(game)
        assert game.state.players[0].life == life + 2
        assert game.state.objects[cls].class_level == 1


class TestCaretakersTalent:
    def test_becoming_level_two_copies_a_token(self, builder):
        game, cls = position(builder, CARETAKER, tokens=1)
        activate(game, cls, C_LEVEL_2)
        resolve(game)
        assert len(oids_of(game, SOLDIER, 0)) == 2

    def test_the_copy_entering_draws_through_the_level_one_ability(self, builder):
        game, cls = position(builder, CARETAKER, tokens=1)
        hand = len(game.state.players[0].hand)
        activate(game, cls, C_LEVEL_2)
        resolve(game)
        assert len(game.state.players[0].hand) == hand + 1

    def test_the_draw_triggers_only_once_each_turn(self, builder):
        game, _ = position(builder, CARETAKER)
        hand = len(game.state.players[0].hand)
        create_token(game.state, SOLDIER, 0, count=2)
        resolve(game)
        create_token(game.state, SOLDIER, 0)
        resolve(game)
        assert len(game.state.players[0].hand) == hand + 1

    def test_level_three_does_not_copy_again(self, builder):
        game, cls = position(builder, CARETAKER, tokens=1)
        activate(game, cls, C_LEVEL_2)
        resolve(game)
        activate(game, cls, C_LEVEL_3)
        resolve(game)
        assert len(oids_of(game, SOLDIER, 0)) == 2

    def test_level_three_pumps_creature_tokens(self, builder):
        game, _ = position(builder, CARETAKER, level=3, tokens=1)
        soldier = only_oid(game, SOLDIER, 0)
        derived = chars(game.state, soldier)
        assert (derived.power, derived.toughness) == (3, 3)

    def test_the_anthem_is_absent_at_level_two(self, builder):
        game, _ = position(builder, CARETAKER, level=2, tokens=1)
        derived = chars(game.state, only_oid(game, SOLDIER, 0))
        assert (derived.power, derived.toughness) == (1, 1)


def _watcher(**trigger):
    return {
        "id": "t_x",
        "name": "X",
        "mana_cost": "{W}",
        "types": ["Enchantment"],
        "subtypes": ["Class"],
        "abilities": [
            {"kind": "level", "text": "{W}: Level 2", "level": 2, "cost": {"mana": "{W}"}},
            {
                "kind": "triggered",
                "text": "When this Class becomes level 2, draw a card.",
                "trigger": {"event": "becomes_level", **trigger},
                "effects": [{"op": "draw", "amount": {"const": 1}}],
            },
        ],
    }


def compile_(card):
    return compile_card(CardModel.model_validate(card))


class TestTheLoaderRefuses:
    def test_the_well_formed_trigger_is_scoped_to_itself(self):
        card = compile_(_watcher(level=2))
        spec = card.abilities[1].trigger
        assert spec.source == "self" and spec.level == 2

    def test_a_becomes_level_trigger_without_a_level(self):
        with pytest.raises(DslError, match="needs the 'level'"):
            compile_(_watcher())

    def test_level_one(self):
        with pytest.raises(DslError, match="needs the 'level'"):
            compile_(_watcher(level=1))

    def test_a_level_no_line_reaches(self):
        with pytest.raises(DslError, match="only reach 2"):
            compile_(_watcher(level=3))

    def test_a_level_on_another_event(self):
        card = _watcher(level=2)
        card["abilities"][1]["trigger"] = {"event": "self_enters", "level": 2}
        with pytest.raises(DslError, match="only means anything on becomes_level"):
            compile_(card)

    def test_printed_under_a_higher_level_than_it_waits_for(self):
        card = _watcher(level=2)
        card["abilities"].append(
            {"kind": "level", "text": "{W}: Level 3", "level": 3, "cost": {"mana": "{W}"}}
        )
        card["abilities"][1]["level"] = 3
        with pytest.raises(DslError, match="not there when"):
            compile_(card)

    def test_on_a_card_that_is_not_a_class(self):
        card = _watcher(level=2)
        card["subtypes"] = []
        card["abilities"] = card["abilities"][1:]
        with pytest.raises(DslError, match="Class"):
            compile_(card)

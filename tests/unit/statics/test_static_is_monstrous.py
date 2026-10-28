"""A static's "as long as" can ask whether its own source is monstrous.

    Fleecemane Lion -- "{3}{G}{W}: Monstrosity 1. As long as this creature is
    monstrous, it has hexproof and indestructible."

701.37b: once a permanent has become monstrous it stays monstrous until it
leaves the battlefield, and nothing else about it -- least of all its counters
-- changes that. The `monstrosity` op already writes `GameObject.monstrous`;
without a static condition that reads it, the Lion's second sentence has no
exact form. Both stand-ins make a different card:

* ``{"counters": {"counter": "+1/+1"}}`` is on for a Lion that was merely
  pumped by something else, and off again for a monstrous Lion whose counter
  was removed;
* a `becomes_monstrous` trigger writing a flag uses the stack, so between the
  ability resolving and the trigger resolving the Lion is monstrous and can be
  killed or targeted -- a window the printed static does not have.

`is_monstrous` reads the field directly. The field is written only by the op
(which bumps `char_version`) and cleared only by a zone change (400.7), so it is
a pipeline input as a counter is and ADR 0001's fixed order stays acyclic.

The claims, each of which is one of those wrong cards if it breaks:

* the Lion has neither keyword until monstrosity resolves, and both the moment
  it does, with no trigger in between;
* a +1/+1 counter from elsewhere does not switch the static on, and removing
  the monstrosity counter does not switch it off;
* a zone change forgets it (400.7);
* ``{"is_monstrous": false}`` is the other half, and the loader refuses a
  non-boolean.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import _condition_met
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, remove_counters
from commanderblitz.engine.zones import move_object
from tests.conftest import keywords, only_oid, pass_until, static_probe

LION = "t_monstrous_lion"
GRANTED = {"hexproof", "indestructible"}


def lion_board(builder):
    """``(game, oid)``: the Lion with five lands to pay for Monstrosity 1."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest", "plains", "forest", "plains", "forest", LION])
        .battlefield(1, ["plains"])
        .build()
    )
    return game, only_oid(game, LION)


def activate_monstrosity(game, oid):
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
    )
    game.apply(action)


def go_monstrous(game, oid):
    activate_monstrosity(game, oid)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


class TestTheStaticFollowsMonstrosity:
    def test_not_monstrous_means_no_keywords(self, builder):
        game, oid = lion_board(builder)
        assert not keywords(game, oid) & GRANTED

    def test_monstrosity_switches_both_keywords_on(self, builder):
        game, oid = lion_board(builder)
        go_monstrous(game, oid)
        assert game.state.objects[oid].monstrous
        assert keywords(game, oid) >= GRANTED

    def test_there_is_no_trigger_in_between(self, builder):
        """The grant is on as the ability resolves; nothing else is queued."""
        game, oid = lion_board(builder)
        activate_monstrosity(game, oid)
        pass_until(game, lambda g: not g.state.stack)
        assert not game.state.pending_triggers
        assert keywords(game, oid) >= GRANTED


class TestCountersAreNotTheQuestion:
    def test_a_counter_from_elsewhere_does_not_make_it_monstrous(self, builder):
        game, oid = lion_board(builder)
        keywords(game, oid)  # warms the cache
        add_counters(game.state, oid, "+1/+1", 1, source=oid)
        game.state.bump_chars()
        assert game.state.objects[oid].counter("+1/+1") == 1
        assert not keywords(game, oid) & GRANTED

    def test_losing_the_counter_does_not_stop_it_being_monstrous(self, builder):
        """701.37b: monstrous until it leaves, whatever happens to the counter."""
        game, oid = lion_board(builder)
        go_monstrous(game, oid)
        remove_counters(game.state, oid, "+1/+1", 1)
        game.state.bump_chars()
        assert game.state.objects[oid].counter("+1/+1") == 0
        assert keywords(game, oid) >= GRANTED


class TestAZoneChangeForgetsIt:
    def test_the_new_object_is_not_monstrous(self, builder):
        """400.7: the Lion that comes back is a new object."""
        game, oid = lion_board(builder)
        go_monstrous(game, oid)
        move_object(game.state, oid, Zone.HAND)
        new = game.state.players[0].hand[-1]
        assert not game.state.objects[new].monstrous
        move_object(game.state, new, Zone.BATTLEFIELD)
        back = only_oid(game, LION)
        assert not keywords(game, back) & GRANTED


class TestTheLeaf:
    def test_false_is_the_other_half(self, builder):
        game, oid = lion_board(builder)
        source = game.state.objects[oid]
        assert _condition_met(game.state, source, {"is_monstrous": False}) is True
        assert _condition_met(game.state, source, {"is_monstrous": True}) is False
        source.monstrous = True
        assert _condition_met(game.state, source, {"is_monstrous": True}) is True
        assert _condition_met(game.state, source, {"is_monstrous": False}) is False

    @pytest.mark.parametrize("value", ["yes", 1, None, {}])
    def test_the_loader_refuses_a_non_boolean(self, value):
        card = static_probe(
            {
                "effect": "grant_keyword",
                "affects": {"self_only": True},
                "keywords": ["hexproof"],
                "condition": {"is_monstrous": value},
            }
        )
        with pytest.raises(DslError, match="is_monstrous"):
            compile_card(CardModel.model_validate(card))

    def test_a_boolean_loads(self):
        card = static_probe(
            {
                "effect": "grant_keyword",
                "affects": {"self_only": True},
                "keywords": ["hexproof"],
                "condition": {"not": {"is_monstrous": True}},
            }
        )
        compile_card(CardModel.model_validate(card))

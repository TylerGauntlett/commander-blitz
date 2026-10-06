"""Distributing counters among targets, divided on activation.

    "-3: Distribute three +1/+1 counters among up to three target creatures.
    They gain vigilance until end of turn."          -- Ajani, Sleeper Agent

601.2d (applied to abilities by 602.2b): the player announces how a
distributed number is divided **as the targets are declared**, and each target
gets at least one. `add_counters` takes one amount for every object it names,
so the only near miss was "one counter on each", which is a different card at
every target count but three.

The division is asked in `game.Game._activate`, straight after the targets and
before the cost, one extra counter at a time ("which target gets another?") --
composed from `ask_objects`, so no new decision kind, and nothing is asked when
the split is forced. It rides on the stack item as ``bindings["distribution"]``
and `distribute_counters` honours it at resolution. A target that became
illegal in response takes its share with it (608.2b); the survivors are **not**
given more, because asking again at resolution would let the split follow the
response.

The loader keeps the op to top-level effects of activated abilities (where the
announcement exists) and refuses a target spec that could name more objects
than there are counters.
"""

from __future__ import annotations

import pytest

from automtg.ai.agents import HeuristicAgent
from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.zones import destroy
from tests.conftest import oids_of, only_oid, pass_until

WALKER = "t_dc_walker"
BEAR = "t_rc_bear"
ROCK = "t_rc_rock"


def position(builder, mine=(), theirs=()):
    """The walker and ``mine`` for player 0, ``theirs`` for player 1.

    The Bolt and its Mountain are an anchor, not a card under test: holding an
    instant keeps the engine from auto-passing the stack and the phase away.
    """
    game = (
        builder(players=2)
        .battlefield(0, [WALKER, "mountain", *mine])
        .hand(0, ["lightning_bolt"])
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def activate_at(game, targets: list[int]) -> None:
    """Activate the minus line aimed at exactly ``targets`` (in any order)."""
    walker = only_oid(game, WALKER, 0)
    wanted = sorted(targets)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and a.source == walker
            and sorted(t.id for t in a.targets) == wanted
        )
    )


def give_extra_to(game, oid: int) -> None:
    pending = game.pending()
    assert pending.kind is DecisionKind.CHOOSE_OBJECTS
    assert pending.context["purpose"] == "distribute"
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and any(t.id == oid for t in a.targets)
        )
    )


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack)


def plus_ones(game, oid: int) -> int:
    return game.state.objects[oid].counter("+1/+1")


class TestTheDivision:
    def test_one_target_takes_all_three(self, builder):
        game = position(builder, mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        activate_at(game, [bear])
        assert game.pending().kind is not DecisionKind.CHOOSE_OBJECTS, "a forced split asks nothing"
        resolve(game)
        assert plus_ones(game, bear) == 3

    def test_three_targets_take_one_each(self, builder):
        game = position(builder, mine=[BEAR, BEAR, BEAR])
        bears = oids_of(game, BEAR, 0)
        activate_at(game, bears)
        assert game.pending().kind is not DecisionKind.CHOOSE_OBJECTS
        resolve(game)
        assert [plus_ones(game, b) for b in bears] == [1, 1, 1]

    @pytest.mark.parametrize("favoured", [0, 1])
    def test_two_targets_split_two_and_one_as_chosen(self, builder, favoured):
        game = position(builder, mine=[BEAR, BEAR])
        bears = oids_of(game, BEAR, 0)
        activate_at(game, bears)
        give_extra_to(game, bears[favoured])
        resolve(game)
        assert plus_ones(game, bears[favoured]) == 2
        assert plus_ones(game, bears[1 - favoured]) == 1

    def test_it_is_announced_before_the_ability_resolves(self, builder):
        """601.2d: the split is on the stack item while it waits there."""
        game = position(builder, mine=[BEAR, BEAR])
        bears = oids_of(game, BEAR, 0)
        activate_at(game, bears)
        give_extra_to(game, bears[1])
        item = game.state.stack[-1]
        assert sorted(map(tuple, item.bindings["distribution"]["t1"])) == sorted(
            [(bears[0], 1), (bears[1], 2)]
        )

    def test_they_gain_vigilance(self, builder):
        game = position(builder, mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        activate_at(game, [bear])
        resolve(game)
        from automtg.engine.characteristics import chars

        assert "vigilance" in chars(game.state, bear).keywords


class TestAnIllegalTargetTakesItsShare:
    def test_the_survivor_is_not_given_more(self, builder):
        game = position(builder, mine=[BEAR, BEAR])
        bears = oids_of(game, BEAR, 0)
        activate_at(game, bears)
        give_extra_to(game, bears[0])
        destroy(game.state, bears[0])
        resolve(game)
        assert plus_ones(game, bears[1]) == 1


class TestTheHeuristicAgent:
    def test_it_favours_its_own_creature(self, builder):
        game = position(builder, mine=[BEAR], theirs=[BEAR])
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        activate_at(game, [mine, theirs])
        chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
        assert any(t.id == mine for t in chosen.targets)


class TestTheLoader:
    def _card(self, ability=None, spell_effects=None, types=("Artifact",)):
        data = {
            "id": "x",
            "name": "X",
            "oracle_text": "Distribute three +1/+1 counters among up to three target creatures.",
            "mana_cost": "{1}",
            "types": list(types),
        }
        if ability is not None:
            data["abilities"] = [ability]
        if spell_effects is not None:
            data["spell_effects"] = spell_effects
            data["targets"] = [_target(3)]
        return CardModel.model_validate(data)

    def _activated(self, count=3, amount=3, objects=None):
        return {
            "kind": "activated",
            "text": "Distribute three +1/+1 counters among up to three target creatures.",
            "cost": {"mana": "{1}"},
            "targets": [_target(count)],
            "effects": [
                {
                    "op": "distribute_counters",
                    "amount": amount,
                    "objects": objects or {"target": "t1"},
                }
            ],
        }

    def test_an_activated_ability_loads(self):
        compile_card(self._card(self._activated()))

    def test_a_spell_is_refused(self):
        effects = [{"op": "distribute_counters", "amount": 3, "objects": {"target": "t1"}}]
        with pytest.raises(DslError, match="activated ability"):
            compile_card(self._card(spell_effects=effects, types=("Sorcery",)))

    def test_a_trigger_is_refused(self):
        ability = dict(self._activated(), kind="triggered", trigger={"event": "self_enters"})
        ability.pop("cost")
        with pytest.raises(DslError, match="activated ability"):
            compile_card(self._card(ability))

    def test_more_targets_than_counters_is_refused(self):
        with pytest.raises(DslError, match="at most 2"):
            compile_card(self._card(self._activated(count=3, amount=2)))

    def test_a_computed_amount_is_refused(self):
        with pytest.raises(DslError, match="printed 'amount'"):
            compile_card(self._card(self._activated(amount={"x": True})))

    def test_objects_must_name_a_target(self):
        with pytest.raises(DslError, match="target"):
            compile_card(self._card(self._activated(objects={"controller": "you"})))


def _target(count: int) -> dict:
    return {
        "id": "t1",
        "kind": "permanent",
        "count": count,
        "up_to": True,
        "selector": {"types": ["Creature"], "controller": "any"},
    }

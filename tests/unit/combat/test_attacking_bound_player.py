""""Other creatures you control attacking **that player**" -- `attacking_player`
naming the seat a binding holds.

Namor, Atlantean King is the witness: "Whenever Namor attacks a player who has
more life than you, other creatures you control attacking that player get
+2/+0 until end of turn." The player is the `defender` of Namor's own `attacks`
event. `attacking_player` took only words relative to the controller -- `you`,
`opponent`, `any`, `most_life` -- and `opponent` would also pump creatures sent
at a *different* opponent in a pod; `attacking` has no notion of whom at all.

So the key also takes `{"binding": name}`: the creature is attacking the seat
that binding holds, and attacking it as a player (506.2) -- not a planeswalker
or battle that player controls. What is pinned:

1. At a pod, only creatures attacking the bound seat match.
2. A creature attacking that player's planeswalker does not.
3. An empty binding matches nobody, and out of combat nothing matches.
4. The loader takes a binding and nothing else, and refuses it in a trigger
   filter, where nothing is bound yet.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import CombatState
from tests.conftest import oids_of, only_oid

BEAR = "t_bear"
WALKER = "t_walker"

THAT_PLAYER = {"controller": "you", "types": ["Creature"], "attacking_player": {"binding": "defender"}}


def board(builder):
    """Player 0's three Bears: one at player 1, one at player 2, one at player
    1's planeswalker."""
    game = (
        builder(players=3)
        .battlefield(0, [BEAR, BEAR, BEAR])
        .battlefield(1, [WALKER])
        .active(0)
        .step(Step.DECLARE_ATTACKERS)
        .build()
    )
    at_one, at_two, at_walker = oids_of(game, BEAR, 0)
    combat = CombatState(declaring_player=0)
    combat.attackers = {at_one: 1, at_two: 2, at_walker: 1}
    combat.attacking_permanent = {at_walker: only_oid(game, WALKER, 1)}
    game.state.combat = combat
    return game, (at_one, at_two, at_walker)


def pool(game, defender) -> list[int]:
    ctx = EffectContext(state=game.state, controller=0)
    if defender is not None:
        ctx.bindings["defender"] = defender
    return sorted(resolve_pool(ctx, {**THAT_PLAYER, "zone": "battlefield"}))


class TestTheBoundSeat:
    def test_only_creatures_attacking_that_player_match(self, builder):
        game, (at_one, at_two, _) = board(builder)
        assert pool(game, 1) == [at_one]
        assert pool(game, 2) == [at_two]

    def test_attacking_that_players_walker_is_not_attacking_them(self, builder):
        game, (_, _, at_walker) = board(builder)
        assert at_walker not in pool(game, 1)

    def test_an_empty_binding_matches_nobody(self, builder):
        game, _ = board(builder)
        assert pool(game, None) == []

    def test_out_of_combat_nothing_matches(self, builder):
        game, _ = board(builder)
        game.state.combat = None
        assert pool(game, 1) == []


def _creature(abilities: list) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Probe.",
        "mana_cost": "{W}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": abilities,
    }


def _pump(selector: dict) -> dict:
    return {
        "kind": "triggered",
        "text": "Probe.",
        "trigger": {"event": "attacks", "source": "self"},
        "effects": [{"op": "pump", "power": {"const": 2}, "toughness": {"const": 0},
                     "objects": selector}],
    }


class TestTheLoader:
    def test_a_binding_loads(self):
        compile_card(CardModel.model_validate(_creature([_pump(THAT_PLAYER)])))

    @pytest.mark.parametrize(
        "who", [{"target": "t1"}, {"binding": 1}, {"binding": "defender", "x": 1}, True]
    )
    def test_anything_else_is_refused(self, who):
        selector = {**THAT_PLAYER, "attacking_player": who}
        with pytest.raises(DslError, match="attacking_player"):
            compile_card(CardModel.model_validate(_creature([_pump(selector)])))

    def test_a_trigger_filter_refuses_a_binding(self):
        ability = {
            "kind": "triggered",
            "text": "Probe.",
            "trigger": {"event": "attacks", "filter": {"attacking_player": {"binding": "defender"}}},
            "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
        }
        with pytest.raises(DslError, match="nothing is bound yet"):
            compile_card(CardModel.model_validate(_creature([ability])))

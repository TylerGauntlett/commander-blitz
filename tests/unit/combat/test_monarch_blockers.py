""""Creatures **the monarch** controls" -- the crown as a seat a filter can name.

Azure Fleet Admiral: "This creature can't be blocked by creatures the monarch
controls." Rule 721 makes the monarch one player at a time, and the sentence
names whoever that is *as blockers are declared* (509.1a): the crown can change
hands earlier the same turn, and the restriction follows it.

`block_restriction`'s `blockers` filter could only say you/opponent/any, and the
near miss -- `condition: {"is_monarch": "opponent"}` on an unfiltered
restriction -- switches the whole static on while *any* opponent wears the
crown, so at a pod it refuses blocks from every opponent rather than the one who
holds it. That counterfactual is the three-seat class below: seat 2 is an
opponent who is not the monarch, and their creature still blocks.

So `"monarch"` is a player spec (`select_players`) and a `controller` word in
both filter languages -- the static one (`characteristics._matches`) and the
effect one (`selectors.matches`) -- naming nobody while the crown is unclaimed.
The witness is `t_crown_evader`, the Admiral's line alone on a 2/2.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.combat import can_block
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import select_players, validate_selector
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import become_monarch
from tests.conftest import attack_with, find_action, only_oid, pass_until, static_probe

EVADER = "t_crown_evader"
BEAR = "t_bear"
COUNT_MONARCHS = {"count": {"zone": "battlefield", "types": ["Creature"], "controller": "monarch"}}


def blocking(builder, *, monarch: int | None, players: int = 2, defender: int = 1):
    """``(game, evader)`` at declare blockers, each other seat holding one Bear."""
    b = builder(players=players).battlefield(0, ["forest"] * 4 + [EVADER])
    for pid in range(1, players):
        b.battlefield(pid, [BEAR])
    game = b.build()
    if monarch is not None:
        become_monarch(game.state, monarch)
    evader = only_oid(game, EVADER, 0)
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    attack_with(game, evader, defender)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    return game, evader


class TestTheMonarchsCreaturesCannotBlock:
    def test_the_monarchs_creature_is_refused(self, builder):
        game, evader = blocking(builder, monarch=1)
        bear = only_oid(game, BEAR, 1)
        assert not can_block(game.state, bear, evader, 1)

    def test_legality_does_not_offer_the_refused_block(self, builder):
        game, _ = blocking(builder, monarch=1)
        bear = only_oid(game, BEAR, 1)
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_BLOCKER and a.source == bear
        ]

    def test_a_defender_who_is_not_the_monarch_blocks(self, builder):
        """The attacker holds the crown: nobody blocking is the monarch."""
        game, evader = blocking(builder, monarch=0)
        bear = only_oid(game, BEAR, 1)
        assert can_block(game.state, bear, evader, 1)

    def test_with_no_monarch_nothing_is_refused(self, builder):
        """721.2: until somebody becomes the monarch, the phrase names nobody."""
        game, evader = blocking(builder, monarch=None)
        bear = only_oid(game, BEAR, 1)
        assert can_block(game.state, bear, evader, 1)

    def test_the_crown_is_read_at_declaration(self, builder):
        """Moved after the attack was declared, the restriction follows it."""
        game, evader = blocking(builder, monarch=0)
        bear = only_oid(game, BEAR, 1)
        become_monarch(game.state, 1)
        assert not can_block(game.state, bear, evader, 1)


class TestAtAPod:
    """The near miss: "an opponent is the monarch" would wall off every seat."""

    def test_only_the_monarch_is_named(self, builder):
        game, evader = blocking(builder, monarch=1, players=3, defender=2)
        bear = only_oid(game, BEAR, 2)
        assert can_block(game.state, bear, evader, 2)

    def test_the_monarch_defending_is_refused(self, builder):
        game, evader = blocking(builder, monarch=2, players=3, defender=2)
        bear = only_oid(game, BEAR, 2)
        assert not can_block(game.state, bear, evader, 2)


class TestThePlayerSpec:
    def _ctx(self, game):
        return EffectContext(state=game.state, controller=0, source_oid=None)

    def test_it_names_the_crowns_holder(self, builder):
        game = builder(players=3).build()
        become_monarch(game.state, 2)
        assert select_players(self._ctx(game), "monarch") == [2]

    def test_it_names_nobody_while_unclaimed(self, builder):
        game = builder(players=3).build()
        assert select_players(self._ctx(game), "monarch") == []

    def test_an_effect_selector_counts_the_monarchs_creatures(self, builder):
        game = (
            builder(players=3).battlefield(1, [BEAR]).battlefield(2, [BEAR, BEAR]).build()
        )
        become_monarch(game.state, 2)
        assert evaluate_value(self._ctx(game), COUNT_MONARCHS) == 2
        become_monarch(game.state, 1)
        assert evaluate_value(self._ctx(game), COUNT_MONARCHS) == 1

    def test_an_effect_selector_with_no_monarch_counts_nothing(self, builder):
        game = builder(players=2).battlefield(1, [BEAR]).build()
        assert evaluate_value(self._ctx(game), COUNT_MONARCHS) == 0


class TestLoading:
    def test_the_selector_word_loads(self):
        validate_selector({"zone": "battlefield", "controller": "monarch"}, "probe")
        validate_selector({"zone": "battlefield", "owner": "monarch"}, "probe")

    def test_a_misspelling_is_still_refused(self):
        with pytest.raises(DslError, match="unknown controller clause"):
            validate_selector({"zone": "battlefield", "controller": "the_monarch"}, "probe")

    def test_the_static_loads(self):
        probe = static_probe(
            {
                "effect": "block_restriction",
                "affects": {"self_only": True},
                "blockers": {"types": ["Creature"], "controller": "monarch"},
            }
        )
        compile_card(CardModel.model_validate(probe))

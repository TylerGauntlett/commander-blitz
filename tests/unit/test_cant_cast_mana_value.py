"""A cast prohibition by mana value: "can't cast spells with mana value 3 or less."

Brisela, Voice of Nightmares is the witness: "Your opponents can't cast spells
with mana value 3 or less." `cant_cast_spells` already took a printed-face
filter (Narset's "noncreature"), and mana value is as printed as a type line --
except on an X spell. 202.3e counts the X a spell on the stack was cast with,
and the official ruling on Brisela says so in as many words: an opponent may
cast a `{X}{R}` spell with X = 3 or more. So the lock is a question about the
*cast*, not about the card in hand, and the X in hand is 0 (107.3).

Without the X half, a Fireball would be uncastable under Brisela at any size --
a strictly stronger card than the printed one. Without the filter at all, the
only spelling was Voice of Victory's total lock, stronger still.

So the answer is a floor: `cast_lock_min_x` is the least X that lifts the lock,
legality offers the cast only when the board can pay that X, and `ask_x` starts
its options there. A price with no X to announce -- "without paying its mana
cost" makes X 0 (107.3b) -- keeps the locked mana value and is not offered.

Cards: `t_mv_lock` (Brisela's line on an enchantment), `t_mv3`, `t_mv4` in
tests/data/cant_cast_mana_value.cards.json; `t_x_spell` ({X}{G}) and `t_bear`
from testing.cards.json.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import legality
from automtg.engine.characteristics import cast_lock_min_x, player_cant_cast_spells
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.zones import destroy
from tests.conftest import oids_of, only_oid, pass_until

LOCK = "t_mv_lock"
MV3 = "t_mv3"  # {2}{G}
MV4 = "t_mv4"  # {3}{G}
BEAR = "t_bear"  # {1}{G}
HYDRA = "t_x_spell"  # {X}{G}, enters with X +1/+1 counters

PLUS_ONE = "+1/+1"


def position(
    builder,
    *,
    lock: bool = True,
    forests: int = 8,
    hand1: tuple[str, ...] = (BEAR, MV3, MV4),
    hand0: tuple[str, ...] = (),
    advance: bool = False,
):
    """Player 0 holds the lock; player 1, whose main phase it is, is named by it."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + ([LOCK] if lock else []))
        .battlefield(1, ["forest"] * forests)
        .hand(0, list(hand0))
        .hand(1, list(hand1))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(1)
        .build(advance=advance)
    )
    return game


def casts(game, pid: int) -> list:
    return [a for a in legality._priority_actions(game.state, pid) if a.kind is ActionKind.CAST]


def cast_ids(game, pid: int) -> set[str]:
    return {game.state.objects[a.source].def_id for a in casts(game, pid)}


class TestTheThreshold:
    def test_three_or_less_is_withheld_and_four_is_not(self, builder):
        game = position(builder)
        assert cast_ids(game, 1) == {MV4}

    def test_without_the_lock_everything_is_offered(self, builder):
        """Pins that the refusal above is the lock's, not the position's."""
        game = position(builder, lock=False)
        assert cast_ids(game, 1) == {BEAR, MV3, MV4}

    def test_its_controller_is_unaffected(self, builder):
        """"Your *opponents*"."""
        game = position(builder, hand0=(BEAR,))
        game.state.active_idx = 0
        assert BEAR in cast_ids(game, 0)

    def test_the_seat_alone_is_not_locked(self, builder):
        game = position(builder)
        registry = game.state.registry
        assert not player_cant_cast_spells(game.state, 1)
        assert player_cant_cast_spells(game.state, 1, registry.get(MV3))
        assert not player_cant_cast_spells(game.state, 1, registry.get(MV4))

    def test_it_lifts_when_the_source_leaves(self, builder):
        game = position(builder)
        destroy(game.state, only_oid(game, LOCK, 0))
        assert cast_ids(game, 1) == {BEAR, MV3, MV4}


class TestAnXSpell:
    """202.3e: the X it is cast with counts, so X is floored rather than refused."""

    def test_the_floor_is_the_least_x_that_escapes(self, builder):
        # {X}{G}: mana value X + 1, so X = 3 is mana value 4.
        game = position(builder)
        assert cast_lock_min_x(game.state, 1, game.state.registry.get(HYDRA)) == 3

    def test_it_is_offered_when_the_floor_is_payable(self, builder):
        game = position(builder, forests=4, hand1=(HYDRA,))
        assert cast_ids(game, 1) == {HYDRA}

    def test_it_is_withheld_when_only_a_smaller_x_is_payable(self, builder):
        # Three Forests: {G} and X = 2 at most -- mana value 3, locked.
        game = position(builder, forests=3, hand1=(HYDRA,))
        assert cast_ids(game, 1) == set()

    def test_without_the_lock_the_same_board_casts_it(self, builder):
        game = position(builder, lock=False, forests=3, hand1=(HYDRA,))
        assert cast_ids(game, 1) == {HYDRA}

    def test_the_question_starts_at_the_floor(self, builder):
        game = position(builder, forests=6, hand1=(HYDRA,), advance=True)
        game.apply(casts(game, 1)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        assert [o.value for o in decision.options] == [3, 4, 5]
        assert decision.context["min_x"] == 3
        assert decision.context["max_x"] == 5

    def test_the_answer_is_the_option_not_the_ordinal(self, builder):
        game = position(builder, forests=6, hand1=(HYDRA,), advance=True)
        game.apply(casts(game, 1)[0])
        # Ordinal 1 is X = 4.
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 1)
        )
        pass_until(game, lambda g: oids_of(g, HYDRA, 1))
        assert game.state.objects[only_oid(game, HYDRA, 1)].counter(PLUS_ONE) == 4

    def test_a_floor_equal_to_the_ceiling_is_not_asked(self, builder):
        """`ask_x` declines a question with one answer -- and that answer is 3, not 0."""
        game = position(builder, forests=4, hand1=(HYDRA,), advance=True)
        game.apply(casts(game, 1)[0])
        pass_until(game, lambda g: oids_of(g, HYDRA, 1))
        assert game.state.objects[only_oid(game, HYDRA, 1)].counter(PLUS_ONE) == 3

    def test_an_unlocked_question_still_starts_at_zero(self, builder):
        game = position(builder, lock=False, forests=4, hand1=(HYDRA,), advance=True)
        game.apply(casts(game, 1)[0])
        decision = game.pending()
        assert [o.value for o in decision.options] == [0, 1, 2, 3]
        assert "min_x" not in decision.context


class TestTheLoader:
    def _lock(self, filt) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_mv_probe",
                "name": "MV Probe",
                "mana_cost": "{W}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "x",
                        "effect": "cant_cast_spells",
                        "affects_player": "opponent",
                        "affects_spells": filt,
                    }
                ],
            }
        )

    def test_the_comparison_loads(self):
        compile_card(self._lock({"mana_value": {"op": "<=", "value": 3}}))

    def test_a_bare_number_loads(self):
        compile_card(self._lock({"mana_value": 3}))

    @pytest.mark.parametrize(
        "bad",
        [
            {"op": "<=", "value": {"const": 3}},
            {"op": "about", "value": 3},
            {"op": "<=", "value": 3, "or_less": True},
            "3",
        ],
    )
    def test_anything_else_is_refused(self, bad):
        with pytest.raises(DslError, match="mana_value"):
            compile_card(self._lock({"mana_value": bad}))

    def test_no_other_spell_filter_takes_it(self):
        """Only the cast lock knows the X a spell is cast for."""
        model = CardModel.model_validate(
            {
                "id": "t_mv_probe2",
                "name": "MV Probe Two",
                "mana_cost": "{W}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "x",
                        "effect": "spell_cost_increase",
                        "affects_spells": {"controller": "opponent", "mana_value": 3},
                        "cost": {"mana": "{1}"},
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="mana_value"):
            compile_card(model)

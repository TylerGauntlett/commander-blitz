"""Entering with one additional counter per death this turn: Gorma (614.1c).

    Gorma, the Gullet: "Nontoken creatures you control enter with an
    additional +1/+1 counter on them for each creature that died under your
    control this turn."

Oath of Gideon's static (`enters_with_additional_counters`) with an amount that
is the turn ledger's death tally, `{"creatures_died_this_turn": "you"}`, rather
than a number or a board count. Still a replacement on the arrival (614.1c,
614.12): the creature is never on the battlefield at its printed size, and the
number is read as it enters -- so a creature already standing there does not
grow when something dies later.

What was wrong without this: the amount was a whole number or a battlefield
`count` only, and the board is the wrong place to look in both directions. A
creature that died is no longer on it, and a fixed amount adds counters on a
turn when nothing died. Zero deaths is zero counters.

The tally is keyed by the dead creature's controller (`GameState._tally`), so
"under your control" is the static controller's dead, not an opponent's. Tokens
that die count, since a token creature is a creature that died; tokens that
*enter* do not get counters, which is the `is_token: false` in the affects
filter and not anything in the amount.

The same leaf is now in `STATIC_VALUE_KEYS`, so an anthem's magnitude can read
it too: the ledger is written once per death by `_tally` and emptied only at
cleanup, never by a layer, so it is a pipeline input and the statics-may-not-
read-statics rule holds.

Witness: Gorma, the Gullet. `t_gorma` is its third line alone.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.zones import destroy, move_object
from tests.conftest import only_oid

GORMA = "t_gorma"
ANTHEM = "t_died_anthem"
BEAR = "t_bear"  # vanilla 2/2
SOLDIER = "soldier_1_1_w"


def position(builder, *, mine=(GORMA,), theirs=(), hand=(BEAR,)):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .library(0, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def kill(game, controller: int, n: int = 1) -> None:
    """``n`` creatures die under ``controller``: tokens, destroyed."""
    for oid in create_token(game.state, SOLDIER, controller, n):
        assert destroy(game.state, oid)


def enter_from_hand(game, card_id: str = BEAR) -> int:
    oid = next(
        o.oid
        for o in game.state.objects.values()
        if o.def_id == card_id and o.zone is Zone.HAND
    )
    move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0)
    return oid


def plus(game, oid: int) -> int:
    return game.state.objects[oid].counter("+1/+1")


class TestOnePerDeath:
    def test_no_deaths_no_counter(self, builder):
        """The boundary: a turn with nothing dead adds nothing at all."""
        game = position(builder)
        assert plus(game, enter_from_hand(game)) == 0

    def test_one_death_one_counter(self, builder):
        game = position(builder)
        kill(game, 0)
        assert plus(game, enter_from_hand(game)) == 1

    def test_two_deaths_two_counters(self, builder):
        game = position(builder)
        kill(game, 0, 2)
        bear = enter_from_hand(game)
        assert plus(game, bear) == 2
        assert chars(game.state, bear).power == 4

    def test_a_nontoken_death_counts_too(self, builder):
        game = position(builder, mine=(GORMA, BEAR))
        assert destroy(game.state, only_oid(game, BEAR, 0))
        assert plus(game, enter_from_hand(game)) == 1


class TestUnderYourControl:
    def test_an_opponents_death_does_not_count(self, builder):
        game = position(builder)
        kill(game, 1, 2)
        assert plus(game, enter_from_hand(game)) == 0

    def test_only_yours_are_counted_in_a_mix(self, builder):
        game = position(builder)
        kill(game, 0)
        kill(game, 1, 3)
        assert plus(game, enter_from_hand(game)) == 1


class TestWhoGetsThem:
    def test_a_token_creature_gets_nothing(self, builder):
        game = position(builder)
        kill(game, 0, 2)
        (token,) = create_token(game.state, SOLDIER, 0, 1)
        assert plus(game, token) == 0

    def test_an_opponents_creature_gets_nothing(self, builder):
        game = position(builder, hand=())
        kill(game, 0, 2)
        (token,) = create_token(game.state, SOLDIER, 1, 1)
        assert plus(game, token) == 0


class TestReadAsItEnters:
    def test_a_later_death_does_not_grow_what_is_there(self, builder):
        """A replacement on the entering, not a continuous effect."""
        game = position(builder)
        kill(game, 0)
        bear = enter_from_hand(game)
        kill(game, 0, 2)
        assert plus(game, bear) == 1

    def test_without_gorma_nothing_is_added(self, builder):
        game = position(builder, mine=())
        kill(game, 0, 2)
        assert plus(game, enter_from_hand(game)) == 0

    def test_the_tally_is_the_turns(self, builder):
        """The cleanup step empties the ledger: yesterday's dead are not counted."""
        game = position(builder)
        kill(game, 0, 2)
        game.state.turn_ledger.clear()
        assert plus(game, enter_from_hand(game)) == 0


class TestAsAnAnthem:
    """The leaf is a static value in general, not only this static's amount."""

    def test_the_anthem_grows_with_each_death(self, builder):
        game = position(builder, mine=(ANTHEM, BEAR), hand=())
        bear = only_oid(game, BEAR, 0)
        assert chars(game.state, bear).power == 2
        kill(game, 0)
        assert chars(game.state, bear).power == 3
        kill(game, 1)
        assert chars(game.state, bear).power == 3
        kill(game, 0)
        assert chars(game.state, bear).power == 4


class TestTheLoaderChecksIt:
    def _card(self, amount, effect="enters_with_additional_counters") -> CardModel:
        ability = {
            "kind": "static",
            "text": "Nontoken creatures you control enter with an additional +1/+1 counter on them for each creature that died under your control this turn.",
            "effect": effect,
            "affects": {"controller": "you", "types": ["Creature"], "is_token": False},
            "counter": "+1/+1",
            "amount": amount,
        }
        return CardModel.model_validate(
            {
                "id": "t_bad_gorma",
                "name": "Test Bad Gorma",
                "mana_cost": "{3}{B}{G}",
                "types": ["Creature"],
                "power": 3,
                "toughness": 3,
                "oracle_text": ability["text"],
                "abilities": [ability],
            }
        )

    @pytest.mark.parametrize("who", ["you", "opponent", "all"])
    def test_a_death_tally_loads(self, who):
        compile_card(self._card({"creatures_died_this_turn": who}))

    def test_the_player_spec_is_checked(self):
        with pytest.raises(DslError, match="creatures_died_this_turn"):
            compile_card(self._card({"creatures_died_this_turn": "nobody"}))

    @pytest.mark.parametrize(
        "amount",
        [
            # Each of these would count the arrival itself.
            {"spells_cast_this_turn": "you"},
            {"permanents_entered_this_turn": {"controller": "you", "types": ["Creature"]}},
            # One tally alone, not combined.
            {"creatures_died_this_turn": "you", "const": 1},
            {"times": [{"creatures_died_this_turn": "you"}, {"const": 2}]},
        ],
    )
    def test_nothing_but_the_death_tally(self, amount):
        with pytest.raises(DslError, match="amount"):
            compile_card(self._card(amount))

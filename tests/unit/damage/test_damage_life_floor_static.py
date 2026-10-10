""""If you control a creature, damage that would reduce your life total to less
than 1 reduces it to 1 instead." -- the `damage_life_floor` static. Rule 614.

Serra the Benevolent's -6 emblem is the witness (an emblem is in the command zone
for the rest of the game, 114.1/114.4), and Worship prints the same sentence on an
enchantment. The engine already had the sentence's *one-shot* form: Angel's
Grace's `damage_life_floor` op records a `LifeFloor` whose only duration is
"this turn". That cannot be Serra's emblem twice over -- it would wear off at
cleanup, and as a record written once it cannot re-ask "if you control a
creature", which is the whole drawback of Worship: the floor holds only while a
creature does. So the static form reads its ``condition`` **at each damage
event**, through `player_statics._active_player_statics`, and
`temp_effects.life_floor` -- the one reader `primitives.damage_player` asks --
takes the highest of the timed records and the statics.

What is pinned below:

1. With a creature, a lethal hit lands you on 1; a small hit is untouched (a
   floor, not a Fog), and you are still in the game after state-based actions.
2. Without a creature the floor is not there: lethal damage kills.
3. The condition is read at the moment of damage, both ways round -- a creature
   that dies between two hits drops the floor, one that arrives raises it.
4. It floors **damage** only: paying or losing life walks past it (the near
   miss), exactly as it does past Angel's Grace.
5. It names its seat: the opponent is not protected, and an opponent's creature
   does not satisfy "you control a creature".
6. Worship on the battlefield is the same static, and it lifts when Worship leaves.
7. The loader refuses a floor with no number, a floor of 0, and a permanent filter.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import (
    create_token,
    damage_player,
    give_emblem,
    lose_life,
)
from commanderblitz.engine.temp_effects import life_floor
from commanderblitz.engine.zones import destroy, move_object
from tests.conftest import only_oid, static_probe

EMBLEM = "t_life_floor_emblem"  # sorcery carrying Serra the Benevolent's emblem
WORSHIP = "t_worship"  # the same static printed on an enchantment
BEAR = "t_bear"
ANGEL = "angel_4_4_w_flying_vigilance"


def position(builder, *, creature: bool = True, emblem: bool = True, worship: bool = False):
    """Player 0 at 40 with (optionally) a bear and the emblem or Worship; player 1
    has a bear, so an opponent's creature is always on the table."""
    mine = ["plains"] + ([BEAR] if creature else []) + ([WORSHIP] if worship else [])
    game = (
        builder(players=2)
        .battlefield(0, mine)
        .battlefield(1, [BEAR])
        .library(0, ["plains"] * 10)
        .library(1, ["plains"] * 10)
        .active(0)
        .step(Step.UNTAP)
        .build()
    )
    if emblem:
        give_emblem(game.state, EMBLEM, 0, 0)
    return game


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


class TestWithACreatureYouStopAtOne:
    def test_a_lethal_hit_lands_on_one(self, builder):
        game = position(builder)
        damage_player(game.state, 0, 100, only_oid(game, BEAR, 1))
        assert life(game) == 1

    def test_a_small_hit_is_unchanged(self, builder):
        """A floor, not a Fog: damage above it lands in full."""
        game = position(builder)
        before = life(game)
        damage_player(game.state, 0, 5, only_oid(game, BEAR, 1))
        assert life(game) == before - 5

    def test_each_later_hit_is_floored_too(self, builder):
        """Unlike Angel's Grace's record, nothing is used up or wears off."""
        game = position(builder)
        attacker = only_oid(game, BEAR, 1)
        damage_player(game.state, 0, 100, attacker)
        damage_player(game.state, 0, 100, attacker)
        assert life(game) == 1

    def test_you_are_still_in_the_game(self, builder):
        game = position(builder)
        damage_player(game.state, 0, 100, only_oid(game, BEAR, 1))
        sba._player_losses(game.state)
        assert game.state.players[0].has_lost is False

    def test_the_damage_was_still_dealt(self, builder):
        """The floor sits on the *loss*: `DAMAGE_DEALT` carries the whole hit,
        and `LIFE_LOST` only what actually left the total."""
        game = position(builder)
        mark = len(game.state.events)
        damage_player(game.state, 0, 100, only_oid(game, BEAR, 1))
        events = game.state.events[mark:]
        assert [e.data["amount"] for e in events if e.type == "damage_dealt"] == [100]
        assert [e.data["amount"] for e in events if e.type == "life_lost"] == [39]


class TestWithoutACreatureThereIsNoFloor:
    def test_lethal_damage_kills(self, builder):
        game = position(builder, creature=False)
        damage_player(game.state, 0, 100, only_oid(game, BEAR, 1))
        assert life(game) == -60
        sba._player_losses(game.state)
        assert game.state.players[0].has_lost is True

    def test_the_floor_reads_none(self, builder):
        assert life_floor(position(builder, creature=False).state, 0) is None

    def test_an_opponents_creature_does_not_count(self, builder):
        """"If **you** control a creature" -- the emblem's owner's board."""
        game = position(builder, creature=False)
        assert only_oid(game, BEAR, 1)
        damage_player(game.state, 0, 100, None)
        assert life(game) == -60


class TestTheConditionIsReadAtEachDamageEvent:
    def test_a_creature_that_dies_takes_the_floor_with_it(self, builder):
        game = position(builder)
        attacker = only_oid(game, BEAR, 1)
        damage_player(game.state, 0, 30, attacker)
        assert life(game) == 10
        destroy(game.state, only_oid(game, BEAR, 0))
        damage_player(game.state, 0, 30, attacker)
        assert life(game) == -20

    def test_a_creature_that_arrives_brings_it(self, builder):
        game = position(builder, creature=False)
        assert life_floor(game.state, 0) is None
        create_token(game.state, ANGEL, 0)
        damage_player(game.state, 0, 100, only_oid(game, BEAR, 1))
        assert life(game) == 1


class TestItFloorsDamageAndNotLifeLoss:
    """"**Damage** that would reduce your life total" -- the printed word, and
    the near miss. Paying life or losing life is not damage."""

    def test_losing_life_walks_past_it(self, builder):
        game = position(builder)
        lose_life(game.state, 0, 100)
        assert life(game) == -60

    def test_and_damage_on_the_same_board_is_still_floored(self, builder):
        game = position(builder)
        damage_player(game.state, 0, 100, only_oid(game, BEAR, 1))
        assert life(game) == 1
        lose_life(game.state, 0, 3)
        assert life(game) == -2


class TestItNamesItsSeat:
    def test_the_opponent_is_not_protected(self, builder):
        """Player 1 controls a creature too, but the emblem is player 0's."""
        game = position(builder)
        damage_player(game.state, 1, 100, only_oid(game, BEAR, 0))
        assert life(game, 1) == -60

    def test_an_emblem_given_to_the_opponent_protects_them(self, builder):
        game = position(builder, emblem=False)
        give_emblem(game.state, EMBLEM, 0, 1)
        damage_player(game.state, 1, 100, only_oid(game, BEAR, 0))
        damage_player(game.state, 0, 100, only_oid(game, BEAR, 1))
        assert (life(game, 1), life(game, 0)) == (1, -60)


class TestWorshipOnTheBattlefield:
    def test_worship_floors_the_hit(self, builder):
        game = position(builder, emblem=False, worship=True)
        damage_player(game.state, 0, 100, only_oid(game, BEAR, 1))
        assert life(game) == 1

    def test_it_lifts_when_worship_leaves(self, builder):
        game = position(builder, emblem=False, worship=True)
        move_object(game.state, only_oid(game, WORSHIP, 0), Zone.GRAVEYARD)
        damage_player(game.state, 0, 100, only_oid(game, BEAR, 1))
        assert life(game) == -60


class TestTheLoaderRefusesAGuess:
    def _compile(self, static: dict):
        return compile_card(CardModel.model_validate(static_probe(static)))

    def test_worships_line_loads(self):
        self._compile(
            {
                "effect": "damage_life_floor",
                "amount": 1,
                "affects_player": "you",
                "condition": {"exists": {"controller": "you", "types": ["Creature"]}},
            }
        )

    def test_a_floor_is_required(self):
        with pytest.raises(DslError, match="needs an 'amount'"):
            self._compile({"effect": "damage_life_floor", "affects_player": "you"})

    def test_a_floor_of_zero_is_refused(self):
        with pytest.raises(DslError, match="must be 1 or more"):
            self._compile({"effect": "damage_life_floor", "amount": 0, "affects_player": "you"})

    def test_a_seat_is_required(self):
        with pytest.raises(DslError, match="needs 'affects_player'"):
            self._compile({"effect": "damage_life_floor", "amount": 1})

    def test_a_permanent_filter_is_refused(self):
        with pytest.raises(DslError, match="no 'affects'"):
            self._compile(
                {
                    "effect": "damage_life_floor",
                    "amount": 1,
                    "affects_player": "you",
                    "affects": {"types": ["Creature"]},
                }
            )

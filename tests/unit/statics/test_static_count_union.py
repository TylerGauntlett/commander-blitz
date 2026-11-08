"""A static magnitude that counts a union of filters.

    "Equipped creature gets +1/+1 for each creature you control with base
     power or toughness 1."                          -- Sword of the Squeak

Rule 611.3a sizes a static's effect off the objects its count describes, and an
object either is described or is not: a 1/1 is one creature with base power or
toughness 1, not two. Every other key in a counting filter is ANDed, so one
filter could say only "base power **and** toughness 1", and the near misses are
both wrong cards:

* two `count`s summed in a `sum` count every 1/1 twice -- in a Squirrel or
  Mouse deck, which is every creature the card is printed for;
* `power: 1, toughness: 1` misses the 1/3 and the 3/1 entirely.

``any_of`` in a static's `count` is matched by
`characteristics._matches_wherever`, each branch as the outer filter plus the
branch's keys, the same recursion a static's `affects` already uses. And
``power``/``toughness`` in a static filter already read **base** P/T
(`characteristics._base_pt`), so nothing a layer writes -- not this very
anthem, not a +1/+1 counter, not a pump -- moves a 1/1 out of the count. That is
"base power" by construction, and the reason the union is the only missing
piece: no base-P/T key was needed, and `STATIC_FILTER_KEYS` is untouched, so no
static gains a way to read another static's output.

`t_scu_banner` is the card's magnitude on an anthem, so the creatures it pumps
are the ones it counts: the witness, on every board here, that being pumped does
not stop a 1/1 counting.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import (
    STATIC_FILTER_KEYS,
    STATIC_VALUE_COUNT_FILTER_KEYS,
    compile_card,
)
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.primitives import add_counters, pump
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pt, static_probe, two_seat_board

BANNER = "t_scu_banner"  # artifact: creatures you control +1/+1 per base power or toughness 1
MOUSE = "t_scu_mouse"  # 1/3 -- base power 1
RAT = "t_scu_rat"  # 3/1 -- base toughness 1
SQUIRREL = "t_scu_squirrel"  # 1/1 -- both, counted once
BEAR = "t_scu_bear"  # 2/2 -- neither

UNION = {"controller": "you", "types": ["Creature"], "any_of": [{"power": 1}, {"toughness": 1}]}


def board(builder, mine=(), theirs=()):
    """``(game, oid)`` -- the board, and the id of the banner on it."""
    game = two_seat_board(builder, [BANNER, *mine], theirs)
    return game, only_oid(game, BANNER, 0)


def bonus(game, card_id: str = BEAR, pid: int = 0) -> int:
    """How much the banner adds to ``card_id`` -- the count, read off a creature."""
    oid = only_oid(game, card_id, pid)
    power, _ = pt(game, oid)
    return power - game.state.card_of(game.state.objects[oid]).power


class TestEachBranchCounts:
    def test_base_power_one_counts(self, builder):
        game, _ = board(builder, [MOUSE, BEAR])
        assert bonus(game) == 1

    def test_base_toughness_one_counts(self, builder):
        game, _ = board(builder, [RAT, BEAR])
        assert bonus(game) == 1

    def test_a_creature_in_neither_branch_does_not(self, builder):
        game, _ = board(builder, [BEAR])
        assert bonus(game) == 0
        assert pt(game, only_oid(game, BEAR, 0)) == (2, 2)

    def test_every_branch_together(self, builder):
        game, _ = board(builder, [MOUSE, RAT, SQUIRREL, BEAR])
        assert bonus(game) == 3


class TestTheUnionIsNotATally:
    def test_a_one_one_counts_once(self, builder):
        """Both branches describe it; two summed counts would make this +2."""
        game, _ = board(builder, [SQUIRREL, BEAR])
        assert bonus(game) == 1

    def test_the_outer_controller_applies_to_every_branch(self, builder):
        """"…you control", on both halves: an opponent's 1/3 and 3/1 are
        described by neither branch."""
        game, _ = board(builder, [BEAR], [MOUSE, RAT, SQUIRREL])
        assert bonus(game) == 0


class TestBasePowerIgnoresWhatWasDoneToIt:
    def test_the_anthem_does_not_uncount_what_it_pumps(self, builder):
        """The 1/1 is a 2/2 under the banner and still has base power 1."""
        game, _ = board(builder, [SQUIRREL])
        assert pt(game, only_oid(game, SQUIRREL, 0)) == (2, 2)

    def test_a_counter_pumped_one_one_still_counts(self, builder):
        game, _ = board(builder, [SQUIRREL, BEAR])
        add_counters(game.state, only_oid(game, SQUIRREL, 0), PLUS_ONE, 2)
        assert bonus(game) == 1
        assert pt(game, only_oid(game, SQUIRREL, 0)) == (4, 4)

    def test_an_until_end_of_turn_pump_does_not_uncount_it(self, builder):
        game, _ = board(builder, [MOUSE, BEAR])
        pump(game.state, only_oid(game, MOUSE, 0), 3, 0)
        assert bonus(game) == 1

    def test_a_two_two_is_not_counted_by_shrinking_it(self, builder):
        """The other direction: a 2/2 pumped -1/-1 is a 1/1 on the board and
        not one with base power or toughness 1."""
        game, _ = board(builder, [BEAR])
        pump(game.state, only_oid(game, BEAR, 0), -1, -1)
        assert pt(game, only_oid(game, BEAR, 0)) == (1, 1)


class TestItWearsOff:
    def test_the_count_drops_when_a_counted_creature_leaves(self, builder):
        game, _ = board(builder, [SQUIRREL, MOUSE, BEAR])
        assert bonus(game) == 2
        move_object(game.state, only_oid(game, SQUIRREL, 0), Zone.GRAVEYARD)
        assert bonus(game) == 1


class TestTheLoaderRefuses:
    @staticmethod
    def _compile(count):
        return compile_card(
            CardModel.model_validate(
                static_probe(
                    {
                        "effect": "buff",
                        "affects": {"controller": "you", "types": ["Creature"]},
                        "power": {"count": count},
                        "toughness": {"count": count},
                    }
                )
            )
        )

    def test_the_union_loads(self):
        self._compile(UNION)

    def test_the_static_filter_language_itself_is_unchanged(self):
        """The word is the `count` leaf's alone; no static filter gains it."""
        assert "any_of" in STATIC_VALUE_COUNT_FILTER_KEYS
        assert "any_of" not in STATIC_FILTER_KEYS

    def test_a_union_of_one(self):
        with pytest.raises(DslError, match="at least two"):
            self._compile({"any_of": [{"power": 1}]})

    def test_an_empty_branch(self):
        """`{}` would describe every creature you control."""
        with pytest.raises(DslError, match="non-empty"):
            self._compile({"types": ["Creature"], "any_of": [{"power": 1}, {}]})

    def test_a_branch_that_repeats_an_outer_key(self):
        with pytest.raises(DslError, match="already appear on the outer filter"):
            self._compile({"types": ["Creature"], "any_of": [{"types": ["Artifact"]}, {"power": 1}]})

    def test_a_malformed_comparison_inside_a_branch(self):
        """`"1"` would load and blow up at match time."""
        with pytest.raises(DslError, match="power"):
            self._compile({"types": ["Creature"], "any_of": [{"power": "1"}, {"toughness": 1}]})

    def test_a_key_the_static_language_does_not_have_inside_a_branch(self):
        with pytest.raises(DslError, match="unsupported filter keys"):
            self._compile({"types": ["Creature"], "any_of": [{"power": 1}, {"base_power": 1}]})

    def test_a_zone_inside_a_branch(self):
        with pytest.raises(DslError, match="may not name"):
            self._compile({"types": ["Creature"], "any_of": [{"power": 1}, {"zone": "graveyard"}]})

    def test_a_union_off_the_battlefield(self):
        with pytest.raises(DslError, match="battlefield"):
            self._compile(
                {"zone": "graveyard", "types": ["Creature"], "any_of": [{"power": 1}, {"toughness": 1}]}
            )

    def test_a_nested_union(self):
        with pytest.raises(DslError, match="may not name"):
            self._compile(
                {
                    "types": ["Creature"],
                    "any_of": [{"power": 1}, {"any_of": [{"toughness": 1}, {"colors": ["G"]}]}],
                }
            )

    def test_any_of_is_the_count_leafs_only(self):
        """An `exists` condition is read by its own callers; the word stays out."""
        with pytest.raises(DslError, match="unsupported filter keys"):
            compile_card(
                CardModel.model_validate(
                    static_probe(
                        {
                            "effect": "buff",
                            "affects": {"self_only": True},
                            "power": 1,
                            "toughness": 1,
                            "condition": {"exists": UNION},
                        }
                    )
                )
            )

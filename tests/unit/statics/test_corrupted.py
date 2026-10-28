"""Corrupted -- "as long as an opponent has three or more poison counters".

    "Corrupted — As long as an opponent has three or more poison counters,
    creatures you control with toxic have lifelink."   -- Skrelv's Hive

A static with a condition exists exactly while the condition holds (604.3), and
this condition reads a player's poison counters (`PlayerState.poison`), which
nothing in the value vocabulary reached: `counters_on` counts counters on
*objects*, and a player is not one. So the leaf is `{"max_poison_of": spec}`,
modelled on `max_life_of` -- the most poison on any ONE of the spec's players.

Three things the tests below pin, each invisible on screen:

- **One player, not the table.** "An opponent has three or more" is an
  existential. A summing read opens it at a pod with two counters on each of
  two opponents, a game the printed card is not yet live in.
- **It follows the poison.** `chars` is cached per `char_version`, and the
  poison funnel (`primitives.add_poison`) did not bump it -- a Hive read at two
  poison stayed off after a Mite's hit took the opponent to three until
  something unrelated invalidated the cache. `_move_life` bumps for the same
  reason on the life side.
- **It stays acyclic** (ADR 0001). A poison count is a pipeline input: only
  `add_poison` writes one, and no layer of `characteristics` can. So the
  condition cannot come to depend on another static's output.

Skrelv's Hive is the shipped witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.values import validate_value
from commanderblitz.engine.enums import Keyword, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_poison, damage_player
from tests.conftest import keywords, oids_of, only_oid, static_probe

HIVE = "skrelv_s_hive"
MITE = "phyrexian_mite_1_1_c_toxic"     # 1/1, toxic 1, can't block
BEAR = "t_bear"                         # 2/2, no toxic

LIFELINK = Keyword.LIFELINK.value


def hive(builder, poison: list[int], *, mine=(MITE,), theirs=()):
    """The Hive and ``mine`` for player 0, with the table at these poison counts.

    The counts are written straight onto the seats and the cache bumped by hand,
    so these tests are about the condition; `TestItFollowsThePoison` is the one
    that leaves the bumping to the engine.
    """
    b = builder(players=len(poison)).battlefield(0, [HIVE, *mine])
    if theirs:
        b = b.battlefield(1, list(theirs))
    game = b.build(advance=False)
    for pid, n in enumerate(poison):
        game.state.players[pid].poison = n
    game.state.bump_chars()
    return game


def has_lifelink(game, card: str = MITE, pid: int = 0) -> bool:
    return LIFELINK in keywords(game, only_oid(game, card, pid))


class TestTheThreshold:
    def test_two_poison_is_not_corrupted(self, builder):
        assert not has_lifelink(hive(builder, [0, 2]))

    def test_three_poison_is(self, builder):
        assert has_lifelink(hive(builder, [0, 3]))

    def test_more_than_three_still_is(self, builder):
        assert has_lifelink(hive(builder, [0, 9]))

    def test_no_poison_anywhere_is_not(self, builder):
        assert not has_lifelink(hive(builder, [0, 0]))


class TestWhoseCounters:
    def test_it_asks_about_one_opponent_not_the_table(self, builder):
        # Two each on two opponents: a sum reads 4 and opens the threshold no
        # single opponent has reached.
        assert not has_lifelink(hive(builder, [0, 2, 2, 0]))

    def test_one_corrupted_opponent_among_clean_ones_is_enough(self, builder):
        assert has_lifelink(hive(builder, [0, 0, 0, 3]))

    def test_your_own_poison_does_not_count(self, builder):
        """"An opponent has…" -- the controller at three is not corrupted."""
        assert not has_lifelink(hive(builder, [3, 0]))

    def test_an_opponent_who_has_left_the_game_does_not_count(self, builder):
        game = hive(builder, [0, 3, 0])
        assert has_lifelink(game)
        game.state.players[1].has_lost = True
        game.state.bump_chars()
        assert not has_lifelink(game), "over nobody it is 0, so the condition is off"


class TestWhatItGrants:
    def test_a_creature_without_toxic_gets_nothing(self, builder):
        game = hive(builder, [0, 3], mine=(MITE, BEAR))
        assert has_lifelink(game)
        assert not has_lifelink(game, BEAR)

    def test_an_opponents_toxic_creature_gets_nothing(self, builder):
        game = hive(builder, [0, 3], mine=(), theirs=(MITE,))
        assert not has_lifelink(game, MITE, 1), "creatures *you* control"

    def test_each_of_your_toxic_creatures_gets_it(self, builder):
        game = hive(builder, [0, 3], mine=(MITE, MITE))
        assert all(LIFELINK in keywords(game, oid) for oid in oids_of(game, MITE, 0))


class TestItFollowsThePoison:
    """No hand bump here: the funnel has to do it, or the cache keeps the old answer."""

    def test_the_funnel_switches_it_on(self, builder):
        game = hive(builder, [0, 2])
        assert not has_lifelink(game)

        add_poison(game.state, 1, 1)

        assert has_lifelink(game)

    def test_a_toxic_hit_switches_it_on(self, builder):
        """The Mite's own combat hit is the third counter, and the next read sees it."""
        game = hive(builder, [0, 2])
        mite = only_oid(game, MITE, 0)
        assert not has_lifelink(game)

        damage_player(game.state, 1, 1, mite, is_combat=True)

        assert game.state.players[1].poison == 3
        assert has_lifelink(game)


class TestTheUpkeepTrigger:
    def test_each_of_your_upkeeps_costs_a_life_and_makes_a_mite(self, builder):
        """Measured per resolution: with nothing to decide the engine auto-passes
        through as many turns as it likes, so the claim is the ratio -- one life
        and one Mite for each of *your* upkeeps, none for the opponent's."""
        game = (
            builder(players=2)
            .battlefield(0, [HIVE])
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .active(0)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        before = game.state.players[0].life
        game._advance()

        events = game.state.events
        upkeeps = sum(1 for e in events if e.type == "upkeep" and e.player == 0)
        resolved = sum(
            1
            for e in events
            if e.type == "ability_resolved" and e.data.get("card") == HIVE
        )
        assert upkeeps >= 1
        assert resolved == upkeeps, "your upkeep only"
        assert game.state.players[0].life == before - resolved
        assert len(oids_of(game, MITE, 0)) == resolved


class TestTheLoader:
    def corrupted(self, who) -> CardModel:
        return CardModel.model_validate(
            static_probe(
                {
                    "effect": "grant_keyword",
                    "keywords": ["lifelink"],
                    "affects": {"types": ["Creature"], "controller": "you"},
                    "condition": {
                        "cmp": ">=",
                        "left": {"max_poison_of": who},
                        "right": {"const": 3},
                    },
                }
            )
        )

    def test_a_static_may_ask_about_each_opponent(self):
        compile_card(self.corrupted("each_opponent"))

    @pytest.mark.parametrize("who", ["active_player", {"target": "t1"}, 3])
    def test_a_static_takes_only_the_life_leaves_player_specs(self, who):
        with pytest.raises(DslError, match="max_poison_of"):
            compile_card(self.corrupted(who))

    def test_the_effect_language_has_it_too(self):
        validate_value({"max_poison_of": "each_opponent"}, "probe")

    def test_the_effect_language_refuses_a_misspelled_player(self):
        with pytest.raises(DslError, match="max_poison_of"):
            validate_value({"max_poison_of": "opponents"}, "probe")

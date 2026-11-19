"""Poison read across a table: the total, and the headcount at a floor.

    "This creature gets +1/+1 for each poison counter your opponents have."
                                                        -- Mycosynth Fiend
    "…return up to X target cards from your graveyard to your hand, where X is
    the number of opponents who have three or more poison counters."
                                                        -- Glissa's Retriever

Corrupted's `max_poison_of` is the most poison on ONE player, the existential
"an opponent has three or more". These cards ask two other questions of the
same `PlayerState.poison`, and at a pod each gets a different number from it:

- **The total.** `{"total_poison_of": spec}` sums the spec's players. Two and
  three counters on two opponents is +5/+5; the most on one would say +3/+3.
- **The headcount.** `{"players_with_poison": {"player": spec, "at_least": n}}`
  counts the spec's players who EACH have at least ``n``. Two opponents on
  three is two; the sum (six) and the extreme (three) are both wrong, and two
  opponents on two each is none, though their sum passes three.

Both are pipeline inputs on `max_poison_of`'s terms: only `primitives.add_poison`
writes poison, and it bumps `char_version`, so a static re-reads at once. Both
work in the effect language and in a static. A seat that has left the game is
nobody's opponent for the headcount (800.4a).

Mycosynth Fiend, Vishgraz, the Doomhive, Phyrexian Swarmlord, Glissa's
Retriever and Wurmquake are the shipped witnesses.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_poison
from tests.conftest import only_oid, pt, static_probe

GROWER = "t_poison_grower"  # 1/1, +1/+1 per poison counter your opponents have
COUNTER = "t_corrupted_counter"  # 1/1, +1/+1 per opponent on three or more


def table(builder, poison: list[int], card: str = GROWER):
    """``card`` for player 0, with the seats at these poison counts."""
    game = builder(players=len(poison)).battlefield(0, [card]).build(advance=False)
    for pid, n in enumerate(poison):
        game.state.players[pid].poison = n
    game.state.bump_chars()
    return game


def size(game, card: str = GROWER) -> tuple[int, int]:
    return pt(game, only_oid(game, card, 0))


def value(game, expr, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


TOTAL = {"total_poison_of": "each_opponent"}
CORRUPTED = {"players_with_poison": {"player": "each_opponent", "at_least": 3}}


class TestTheTotal:
    def test_no_poison_is_the_printed_size(self, builder):
        assert size(table(builder, [0, 0])) == (1, 1)

    def test_it_sums_every_opponent(self, builder):
        """Two and three: +5/+5, where the most on one opponent is +3/+3."""
        assert size(table(builder, [0, 2, 3, 0])) == (6, 6)

    def test_your_own_poison_is_not_your_opponents(self, builder):
        assert size(table(builder, [4, 1])) == (2, 2)

    def test_it_follows_the_funnel(self, builder):
        """No hand bump: `add_poison` has to invalidate the cache itself."""
        game = table(builder, [0, 1])
        assert size(game) == (2, 2)
        add_poison(game.state, 1, 2)
        assert size(game) == (4, 4)

    def test_the_effect_language_reads_the_same_sum(self, builder):
        game = table(builder, [5, 2, 3])
        assert value(game, TOTAL) == 5
        assert value(game, {"total_poison_of": "each_player"}) == 10


class TestTheHeadcount:
    def test_one_opponent_at_the_floor_counts_one(self, builder):
        assert size(table(builder, [0, 3, 0], COUNTER), COUNTER) == (2, 2)

    def test_each_is_measured_alone(self, builder):
        """Two each on two opponents is four between them and nobody at three."""
        assert size(table(builder, [0, 2, 2], COUNTER), COUNTER) == (1, 1)

    def test_every_corrupted_opponent_counts_once(self, builder):
        """Three and nine is two opponents, not twelve counters or nine."""
        assert size(table(builder, [0, 3, 9, 1], COUNTER), COUNTER) == (3, 3)

    def test_you_are_not_your_opponent(self, builder):
        assert size(table(builder, [3, 0], COUNTER), COUNTER) == (1, 1)

    def test_a_seat_that_has_left_does_not_count(self, builder):
        game = table(builder, [0, 3, 3])
        assert value(game, CORRUPTED) == 2
        game.state.players[2].has_lost = True
        assert value(game, CORRUPTED) == 1

    def test_the_floor_is_the_cards(self, builder):
        game = table(builder, [0, 1, 2])
        at_one = {"players_with_poison": {"player": "each_opponent", "at_least": 1}}
        assert value(game, at_one) == 2
        assert value(game, CORRUPTED) == 0

    def test_it_follows_the_funnel(self, builder):
        game = table(builder, [0, 2], COUNTER)
        assert size(game, COUNTER) == (1, 1)
        add_poison(game.state, 1, 1)
        assert size(game, COUNTER) == (2, 2)


class TestTheLoader:
    def anthem(self, amount) -> CardModel:
        return CardModel.model_validate(
            static_probe(
                {
                    "effect": "buff",
                    "affects": {"types": ["Creature"], "controller": "you"},
                    "power": amount,
                    "toughness": amount,
                }
            )
        )

    @pytest.mark.parametrize("expr", [TOTAL, CORRUPTED])
    def test_both_languages_take_both(self, expr):
        compile_card(self.anthem(expr))
        validate_value(expr, "probe")

    @pytest.mark.parametrize("who", ["opponents", 3])
    def test_the_total_refuses_a_misspelled_player(self, who):
        with pytest.raises(DslError, match="total_poison_of"):
            validate_value({"total_poison_of": who}, "probe")
        with pytest.raises(DslError, match="total_poison_of"):
            compile_card(self.anthem({"total_poison_of": who}))

    @pytest.mark.parametrize(
        "spec",
        [
            {"player": "each_opponent"},  # no floor: the card's, never defaulted
            {"player": "each_opponent", "at_least": 0},
            {"player": "each_opponent", "at_least": True},
            {"at_least": 3},  # no player: whose counters is the card
            {"player": "each_opponent", "at_least": 3, "cmp": ">"},
        ],
    )
    def test_the_headcount_refuses_a_loose_spec(self, spec):
        with pytest.raises(DslError, match="players_with_poison"):
            validate_value({"players_with_poison": spec}, "probe")
        with pytest.raises(DslError, match="players_with_poison"):
            compile_card(self.anthem({"players_with_poison": spec}))


class TestTheSeatsThemselves:
    """Geth's Summons: "for each opponent who has three or more poison counters
    ..., put up to one target creature card from **that player's** graveyard".
    The same spec as a player spec names the seats the headcount counts, so a
    target's ``owner`` can be restricted to them."""

    SEATS = {"players_with_poison": {"player": "each_opponent", "at_least": 3}}

    def test_it_names_each_opponent_at_the_floor(self, builder):
        from commanderblitz.engine.effects.selectors import select_players

        game = table(builder, [5, 3, 2, 4])
        ctx = EffectContext(state=game.state, controller=0)
        assert select_players(ctx, self.SEATS) == [1, 3]

    def test_a_graveyard_selector_takes_it_as_owner(self, builder):
        from commanderblitz.engine.effects.selectors import resolve_pool, validate_selector

        game = (
            builder(players=3)
            .graveyard(1, ["t_bear"])
            .graveyard(2, ["t_bear"])
            .build(advance=False)
        )
        game.state.players[1].poison = 3
        selector = {"zone": "graveyard", "types": ["Creature"], "owner": self.SEATS}
        validate_selector(selector, "probe")
        ctx = EffectContext(state=game.state, controller=0)
        owners = {game.state.objects[oid].owner for oid in resolve_pool(ctx, selector)}
        assert owners == {1}

    def test_a_loose_owner_spec_is_refused(self):
        from commanderblitz.engine.effects.selectors import validate_selector

        with pytest.raises(DslError, match="players_with_poison"):
            validate_selector(
                {"zone": "graveyard", "owner": {"players_with_poison": {"player": "each_opponent"}}},
                "probe",
            )

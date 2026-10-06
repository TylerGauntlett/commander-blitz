"""Strive — a spell that costs more for every target past the first.

    "Strive — This spell costs {1}{W} more to cast for each target beyond the
    first." (Call the Coppercoats; the Journey into Nyx cycle.)

Strive is an ability word, so the rules say nothing about it by name; what they
say is where the price comes from. 601.2c announces the targets, and 601.2f then
totals the cost: "the mana cost or alternative cost, plus all additional costs
and cost increases, and minus all cost reductions." The increase is therefore
fixed by the target count before anything is paid, and a cast with three targets
is a different price from a cast with one.

Nothing already in the DSL could say it. `cost_reduction` only subtracts and
reads the battlefield, never the spell's own targets. `multikicker` repeats a
price, but the caster chooses how many times independently of the targets, so a
three-target cast paying no kicks would be the printed card with its drawback
deleted.

Legality is where it can go wrong quietly. Cast lines are one action per target
tuple, and before this every tuple shared one payment solved at the printed
cost, so a three-target line on four lands would have been offered and then
failed at `pay`. Each target count is now priced on its own and a count the
caster cannot afford is not offered. There is a second, subtler trap in the
enumeration: "any number" subsets come largest first and are cut at
`MAX_TARGET_OPTIONS`, so on a crowded board every kept tuple is too expensive,
and filtering them would leave only the zero-target line. The tuples are
re-enumerated one affordable size at a time instead, which `TestACrowdedBoard`
pins.

There is no shipped witness yet: Call the Coppercoats is blocked on this and is
authored separately, so `t_strive_tap` stands in for it. Tapping is the smallest
effect that shows every chosen target was bound.
"""

from __future__ import annotations

import pytest

from automtg.cards.authoring.fidelity import unimplemented_mechanics
from automtg.cards.authoring.verify import _covered
from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import suspend
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError

PLAINS = "plains"
ISLAND = "island"
BEAR = "grizzly_bears"
STRIVE = "t_strive_tap"  # {2}{W} sorcery, strive {1}{W}: tap any number of target creatures

STRIVE_LINE = "Strive — This spell costs {1}{W} more to cast for each target beyond the first."


def board(builder, lands, bears: int = 3):
    """Player 0 holds the strive spell; player 1 has ``bears`` creatures to aim at."""
    if isinstance(lands, int):
        lands = [PLAINS] * lands
    return (
        builder(players=2)
        .battlefield(0, lands)
        .battlefield(1, [BEAR] * bears)
        .hand(0, [STRIVE])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build()
    )


def lines(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == STRIVE
    ]


def counts(game) -> list[int]:
    return sorted({len(a.targets) for a in lines(game)})


def tapped_lands(game) -> int:
    return sum(
        1
        for o in game.state.battlefield_objects(0)
        if o.tapped and o.def_id in (PLAINS, ISLAND)
    )


def cast_with(game, n: int):
    game.apply(next(a for a in lines(game) if len(a.targets) == n))
    return tapped_lands(game)


def resolve(game, limit: int = 20):
    for _ in range(limit):
        if not game.state.stack:
            return
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    raise AssertionError("the stack never emptied")


class TestWhatEachTargetCountCosts:
    """The price is the printed cost plus {1}{W} per target past the first."""

    def test_one_target_costs_the_printed_cost(self, builder):
        game = board(builder, lands=10)
        assert cast_with(game, 1) == 3

    def test_three_targets_cost_two_surcharges_more(self, builder):
        """{2}{W} + 2 x {1}{W} is seven mana."""
        game = board(builder, lands=10)
        assert cast_with(game, 3) == 7

    def test_two_targets_cost_one_surcharge_more(self, builder):
        game = board(builder, lands=10)
        assert cast_with(game, 2) == 5

    def test_zero_targets_cost_the_printed_cost(self, builder):
        """"Any number" includes none, and none is not a target beyond the first."""
        game = board(builder, lands=10)
        assert cast_with(game, 0) == 3

    def test_every_chosen_target_is_bound(self, builder):
        """Read off the events: the game runs on into the bears' own untap step."""
        game = board(builder, lands=10)
        bears = {o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEAR}
        cast_with(game, 3)
        resolve(game)
        tapped = {e.source for e in game.state.events if e.type == "tapped"}
        assert bears <= tapped


class TestACountThatCannotBePaidIsNotOffered:
    """An action on offer is an action the engine can honour."""

    def test_every_count_is_offered_when_the_mana_is_there(self, builder):
        game = board(builder, lands=7)
        assert counts(game) == [0, 1, 2, 3]

    def test_the_boundary_is_the_mana(self, builder):
        """Six lands pays for two targets with one to spare, not three."""
        game = board(builder, lands=6)
        assert counts(game) == [0, 1, 2]

    def test_the_printed_cost_alone_still_offers_one_target(self, builder):
        game = board(builder, lands=3)
        assert counts(game) == [0, 1]

    def test_nothing_is_offered_below_the_printed_cost(self, builder):
        game = board(builder, lands=2)
        assert lines(game) == []

    def test_the_surcharge_has_a_colour(self, builder):
        """{1}{W} is not {2}: five lands with one Plains cast one target, not two."""
        game = board(builder, lands=[PLAINS] + [ISLAND] * 4)
        assert counts(game) == [0, 1]

    def test_the_first_line_is_the_largest_affordable_one(self, builder):
        """Whatever casts without asking takes the first line -- it must be payable."""
        game = board(builder, lands=5)
        assert len(lines(game)[0].targets) == 2

    def test_each_line_shows_the_lands_it_would_tap(self, builder):
        game = board(builder, lands=7)
        by_count = {len(a.targets): len(a.pays) for a in lines(game)}
        assert by_count == {0: 3, 1: 3, 2: 5, 3: 7}


class TestACrowdedBoard:
    """The enumeration cap must not swallow the affordable sizes.

    Six creatures give 63 non-empty subsets, and `MAX_TARGET_OPTIONS` keeps the
    largest. Filtered after the fact, a caster with five lands would be offered
    nothing but the zero-target line.
    """

    def test_affordable_sizes_survive_the_cap(self, builder):
        game = board(builder, lands=5, bears=6)
        assert counts(game) == [0, 1, 2]

    def test_and_are_really_charged(self, builder):
        game = board(builder, lands=5, bears=6)
        assert cast_with(game, 2) == 5


class TestAFreeCastTakesOneTarget:
    """Casting without paying the mana cost charges no surcharge on this path.

    `suspend.cast_for_free` pays nothing at all, so the most targets it may
    choose is the count that owes nothing. Taking the largest tuple, as it does
    for any other "any number" spell, would be the card with its cost increase
    deleted.
    """

    def test_at_most_one_target(self, builder):
        game = board(builder, lands=0)
        oid = game.state.players[0].hand[0]
        assert suspend.cast_for_free(game.state, 0, oid)
        (item,) = game.state.stack
        assert len(item.targets) == 1


def _model(**extra) -> CardModel:
    base = {
        "id": "t_strive_probe",
        "name": "Strive Probe",
        "mana_cost": "{2}{W}",
        "types": ["Sorcery"],
        "strive": "{1}{W}",
        "targets": [{"id": "t1", "kind": "permanent", "count": "any"}],
        "spell_effects": [{"op": "tap", "objects": {"target": "t1"}}],
    }
    base.update(extra)
    return CardModel.model_validate(base)


class TestTheLoader:
    """Strive prices one "any number of target" spec, and nothing else."""

    def test_the_whole_thing_loads(self):
        card = compile_card(_model())
        assert card.strive is not None and card.strive.mana_value() == 2

    def test_it_is_not_part_of_mana_value(self):
        assert compile_card(_model()).mana_value == 3

    def test_no_targets_is_refused(self):
        with pytest.raises(DslError, match="exactly one target spec"):
            compile_card(_model(targets=[], spell_effects=[{"op": "draw", "player": "you"}]))

    def test_a_fixed_count_is_refused(self):
        """With a fixed count the surcharge is a constant, and belongs in the mana cost."""
        with pytest.raises(DslError, match="exactly one target spec"):
            compile_card(_model(targets=[{"id": "t1", "kind": "permanent", "count": 2}]))

    def test_a_free_strive_is_refused(self):
        with pytest.raises(DslError, match="costs nothing"):
            compile_card(_model(strive="{0}"))

    def test_x_is_refused(self):
        with pytest.raises(DslError, match="strive cost with X"):
            compile_card(_model(strive="{X}"))


class TestTheMechanicLine:
    """The fidelity audit reads "Strive —" as a mechanic the card must have."""

    def test_a_card_with_strive_has_it(self):
        card = compile_card(_model(oracle_text=f"{STRIVE_LINE}\nTap any number of target creatures."))
        assert unimplemented_mechanics(card, card.oracle_text) == []

    def test_a_card_without_it_is_reported(self):
        card = compile_card(
            _model(
                strive=None,
                oracle_text=f"{STRIVE_LINE}\nTap any number of target creatures.",
            )
        )
        assert unimplemented_mechanics(card, card.oracle_text) == [STRIVE_LINE]

    def test_the_line_is_claimed_when_the_symbols_match(self):
        assert _covered(compile_card(_model()), STRIVE_LINE)

    def test_a_different_printed_price_is_not_claimed(self):
        """Declaring {1}{W} does not launder a printed "{2}{R} more"."""
        line = STRIVE_LINE.replace("{1}{W}", "{2}{R}")
        assert not _covered(compile_card(_model()), line)

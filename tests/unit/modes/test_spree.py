"""Spree (702.166a): "Choose **one or more** additional costs."

Smuggler's Surprise. Three priced modes printed on one card, and what makes the
mechanic is the word *subset*: the caster takes any non-empty combination of
them as the spell is cast, pays **every** chosen price on top of the printed
cost, and on resolution runs **every** chosen mode's effect.

Without it the nearest thing in the DSL is `additional_cost_options`, which is
exclusive by construction -- `chosen_additional` returns one indexed branch, the
paid branch is stored as one `int | None`, and `{"cost_option": n}` can only
ever report a single index. Spelling Smuggler's Surprise that way loads clean
and plays a strictly weaker card: the player may buy exactly one of three modes
and never two, however much mana is on the table. That is the failure these
tests exist to make visible, and it is invisible to any test that only ever
picks one mode -- which is why every claim below is made about *two*.

The other half of 702.166a is the floor. "One or more" means the unmodified
spell is not a legal cast at all, so the plain cast line is withdrawn: a spree
card castable for its printed cost is a card with none of its text.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import pass_until

CAPER = "t_spree_caper"  # {G}; +{1} draw, +{2} gain 3, +{4} 2 damage to each opponent

#: Every non-empty subset of three modes, which is what legality must offer.
ALL_SUBSETS = {(0,), (1,), (2,), (0, 1), (0, 2), (1, 2), (0, 1, 2)}


def position(builder, forests: int = 1, wastes: int = 12):
    """One Forest for the {G}, plus ``wastes`` colourless lands for the modes."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * forests + ["wastes"] * wastes)
        .battlefield(1, ["plains"])
        .library(0, ["island"] * 10)
        .hand(0, [CAPER])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def casts(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == CAPER
    ]


def offered(game) -> set[tuple[int, ...]]:
    return {a.spree_modes for a in casts(game)}


def cast_modes(game, modes: tuple[int, ...]) -> None:
    """Cast the line that buys exactly ``modes`` and let it finish resolving."""
    action = next(a for a in casts(game) if a.spree_modes == modes)
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


class TestEveryNonEmptySubsetIsACastLine:
    def test_all_seven_combinations_are_offered(self, builder):
        """Three modes are seven ways to cast the spell, not three."""
        assert offered(position(builder)) == ALL_SUBSETS

    def test_the_combinations_are_the_heart_of_it(self, builder):
        """The claim an exclusive cost cannot make: two modes on one cast.

        `additional_cost_options` would offer three lines here -- one per price
        -- and the player could never buy the mill and the hexproof together.
        """
        assert {s for s in offered(position(builder)) if len(s) > 1} == {
            (0, 1),
            (0, 2),
            (1, 2),
            (0, 1, 2),
        }


class TestChoosingNoneIsIllegal:
    def test_the_unmodified_spell_is_never_offered(self, builder):
        """702.166a: "one or more". A spree card has no plain cast line."""
        assert () not in offered(position(builder))

    def test_every_line_buys_at_least_one_mode(self, builder):
        assert all(a.spree_modes for a in casts(position(builder)))

    def test_a_card_that_cannot_afford_one_mode_is_not_castable(self, builder):
        """The floor with no line under it: {G} alone buys nothing.

        One Forest pays the printed cost and leaves nothing for the cheapest
        mode, and because the plain line is withdrawn the spell is simply not
        castable -- rather than castable for {G} and empty.
        """
        assert casts(position(builder, wastes=0)) == []


class TestThePriceIsEveryChosenMode:
    def test_a_budget_admits_only_the_subsets_it_can_pay_for(self, builder):
        """{G} plus three generic. The modes cost 1, 2 and 4.

        So {0}, {1} and {0,1} fit in three and nothing else does. The line that
        pins the summation is **{0,2}**: priced at 1 + 4 it is unaffordable, and
        a version charging only the first chosen mode would price it at 1 and
        offer it -- a card that buys its most expensive mode for its cheapest.
        """
        assert offered(position(builder, wastes=3)) == {(0,), (1,), (0, 1)}

    def test_every_mode_is_added_not_picked(self, builder):
        """Six generic buys any two modes but never all three (1+2+4 = 7)."""
        assert offered(position(builder, wastes=6)) == {
            (0,),
            (1,),
            (2,),
            (0, 1),
            (0, 2),
            (1, 2),
        }


class TestEveryChosenModeResolves:
    def test_one_mode_runs_only_its_own_effect(self, builder):
        game = position(builder)
        hand, life, theirs = (
            len(game.state.players[0].hand),
            game.state.players[0].life,
            game.state.players[1].life,
        )
        cast_modes(game, (0,))
        # The card left hand and a card was drawn: net zero, and the spell is
        # the one that left.
        assert len(game.state.players[0].hand) == hand
        assert game.state.players[0].life == life
        assert game.state.players[1].life == theirs

    def test_two_modes_run_both_effects(self, builder):
        """The whole mechanic, in one assertion.

        A single-mode implementation passes every test above that asks about one
        mode. It fails here: whichever mode it kept, one of these two axes does
        not move.
        """
        game = position(builder)
        hand, life = len(game.state.players[0].hand), game.state.players[0].life
        cast_modes(game, (0, 1))
        assert len(game.state.players[0].hand) == hand  # drew one, cast one
        assert game.state.players[0].life == life + 3

    def test_all_three_modes_run(self, builder):
        game = position(builder)
        hand, life = len(game.state.players[0].hand), game.state.players[0].life
        theirs = game.state.players[1].life
        cast_modes(game, (0, 1, 2))
        assert len(game.state.players[0].hand) == hand
        assert game.state.players[0].life == life + 3
        assert game.state.players[1].life == theirs - 2

    def test_a_mode_that_was_not_bought_does_not_run(self, builder):
        """The counterfactual. Buying the draw must not hand out the life."""
        game = position(builder)
        life = game.state.players[0].life
        theirs = game.state.players[1].life
        cast_modes(game, (0,))
        assert game.state.players[0].life == life
        assert game.state.players[1].life == theirs

    def test_the_two_modes_that_skip_the_first_still_run(self, builder):
        """Neither mode is the one the engine happens to read first."""
        game = position(builder)
        hand, life = len(game.state.players[0].hand), game.state.players[0].life
        theirs = game.state.players[1].life
        cast_modes(game, (1, 2))
        assert len(game.state.players[0].hand) == hand - 1  # nothing drawn
        assert game.state.players[0].life == life + 3
        assert game.state.players[1].life == theirs - 2


class TestTheSubsetIsPartOfTheAction:
    def test_two_lines_for_one_card_are_two_different_actions(self, builder):
        game = position(builder)
        one = next(a for a in casts(game) if a.spree_modes == (0,))
        both = next(a for a in casts(game) if a.spree_modes == (0, 1))
        assert one != both
        assert one.key() != both.key()

    def test_the_seven_lines_have_seven_labels(self, builder):
        """The client groups its rows by `base_label`.

        Seven lines sharing one label would collapse into a single row, and the
        player would pick blind between "draw a card" and all three modes at
        once.
        """
        labels = {a.base_label for a in casts(position(builder))}
        assert len(labels) == len(ALL_SUBSETS)


class TestTheLoaderRefusesWhatSpreeCannotMean:
    def _card(self, **extra):
        from commanderblitz.cards.schema import CardModel

        return CardModel.model_validate(
            {
                "id": "t_bad_spree",
                "name": "Test Bad Spree",
                "oracle_text": "Draw a card.",
                "mana_cost": "{G}",
                "types": ["Instant"],
                "spell_effects": [{"op": "draw", "player": "you"}],
                **extra,
            }
        )

    def _refuses(self, match: str, **extra):
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match=match):
            compile_card(self._card(**extra), source="t")

    def test_one_mode_is_not_a_choice(self):
        self._refuses("at least two", spree=[{"mana": "{1}"}])

    def test_it_does_not_combine_with_an_additional_cost(self):
        """Two slots that both answer "what else does this cast owe"."""
        self._refuses(
            "does not compose",
            spree=[{"mana": "{1}"}, {"mana": "{2}"}],
            additional_cost={"discard": 1},
        )

    def test_it_does_not_combine_with_a_modal_additional_cost(self):
        """One line per subset and one line per branch disagree."""
        self._refuses(
            "does not compose",
            spree=[{"mana": "{1}"}, {"mana": "{2}"}],
            additional_cost_options=[{"discard": 1}, {"pay_life": 3}],
        )

    def test_the_whole_spree_may_not_be_made_optional(self):
        """`additional_optional` is exactly what 702.166a forbids."""
        self._refuses(
            "702.166a",
            spree=[{"mana": "{1}"}, {"mana": "{2}"}],
            additional_optional=True,
        )

    def test_a_free_mode_is_not_a_choice(self):
        self._refuses(
            "no cost", spree=[{"mana": "{0}"}, {"mana": "{2}"}]
        )

    def test_a_non_mana_mode_is_refused(self):
        """Subsets are priced by the mana solver, which sees only mana.

        A "sacrifice a creature" mode would be checked once per mode and never
        per combination, so two such modes would be offered together to a player
        with one creature.
        """
        self._refuses(
            "mana price", spree=[{"discard": 1}, {"mana": "{2}"}]
        )

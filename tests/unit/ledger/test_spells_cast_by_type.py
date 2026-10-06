""""…only if you've cast three or more **instant and/or sorcery** spells this turn."

Urabrask // The Great Work. `spells_cast_this_turn` sums `TurnLedger.spells_cast`,
a flat per-player integer bumped once per `SPELL_CAST` with no record of what was
cast — so there is nothing to filter on, and the bare count turns Urabrask's
transform on after three **creature** spells. That is a strictly better card than
the printed one, and silent.

Two workers disagreed about this. The first filed the front face as expressible
and only chapter III as blocked; the second read `values.py` and `structs.py` and
reported that the count carries no types. The second was right, and this file is
that argument in code: `TestTheBareCountCannotSeeTypes` casts three creature
spells and shows the unfiltered value reaching 3 while the filtered one stays 0.

The ledger therefore keeps `spells_cast_ids` beside the count rather than instead
of it. Storm asks only "how many", and it asks per copy, so paying a list's
length for every storm trigger to serve a rarer question would be the wrong
trade. Cards matched with `_matches_printed`, the same matcher
`graveyard_cast_allows` uses and for its reason: a spell that has finished
resolving has a printed face and no board state left to ask about.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value, validate_value
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from tests.conftest import pass_until

INSTANT = "t_plain_instant"  # {W} instant
BEAR = "t_bear"  # a creature spell


def position(builder, hand):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 6 + ["forest"] * 6)
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 20)
        .hand(0, list(hand))
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_all(game, card_id: str, times: int) -> None:
    for _ in range(times):
        game._advance()
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        )
        game.apply(action)
        pass_until(
            game,
            lambda g: not g.state.stack
            and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
        )


def value(game, expr):
    ctx = EffectContext(state=game.state, controller=0, source_name="test")
    return evaluate_value(ctx, expr)


BARE = {"spells_cast_this_turn": "you"}
TYPED = {
    "spells_cast_this_turn": {
        "player": "you",
        "filter": {"any_types": ["Instant", "Sorcery"]},
    }
}


class TestNothingCastYet:
    def test_both_forms_are_zero(self, builder):
        game = position(builder, [])
        game._advance()

        assert value(game, BARE) == 0
        assert value(game, TYPED) == 0


class TestTheBareCountCannotSeeTypes:
    """The claim the whole capability rests on, and the two workers' dispute."""

    def test_three_creature_spells_reach_three(self, builder):
        game = position(builder, [BEAR] * 3)
        cast_all(game, BEAR, 3)

        assert value(game, BARE) == 3, "the count is a count"

    def test_but_none_of_them_is_an_instant(self, builder):
        game = position(builder, [BEAR] * 3)
        cast_all(game, BEAR, 3)

        assert value(game, TYPED) == 0, (
            "Urabrask would have transformed off three creature spells"
        )


class TestTheFilteredCountSeesTheRightSpells:
    def test_instants_are_counted(self, builder):
        game = position(builder, [INSTANT] * 3)
        cast_all(game, INSTANT, 3)

        assert value(game, TYPED) == 3

    def test_a_mixed_turn_counts_only_the_matching_half(self, builder):
        game = position(builder, [INSTANT, INSTANT, BEAR])
        cast_all(game, INSTANT, 2)
        cast_all(game, BEAR, 1)

        assert value(game, BARE) == 3
        assert value(game, TYPED) == 2


class TestItIsPerPlayer:
    def test_an_opponents_spells_are_not_yours(self, builder):
        """The seat is asked the same way the bare form asks it."""
        game = position(builder, [INSTANT])
        cast_all(game, INSTANT, 1)

        assert value(game, TYPED) == 1
        assert (
            value(game, {"spells_cast_this_turn": {"player": "each_opponent",
                                                   "filter": {"any_types": ["Instant"]}}})
            == 0
        )


class TestItResetsWithTheTurn:
    def test_last_turns_spells_do_not_count(self, builder):
        game = position(builder, [INSTANT] * 2)
        cast_all(game, INSTANT, 2)
        assert value(game, TYPED) == 2
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        assert value(game, TYPED) == 0


class TestTheLoaderChecksTheFilter:
    def test_a_misspelled_type_is_refused(self):
        """Unmatched it would count zero for ever, turning the card off silently."""
        with pytest.raises(DslError):
            validate_value(
                {"spells_cast_this_turn": {"player": "you", "filter": {"nonsense": ["Instant"]}}},
                "probe",
            )

    def test_unknown_keys_are_refused(self):
        with pytest.raises(DslError, match="unknown keys"):
            validate_value(
                {"spells_cast_this_turn": {"player": "you", "filter": {}, "types": ["Instant"]}},
                "probe",
            )

    def test_the_bare_player_spec_still_validates(self):
        validate_value({"spells_cast_this_turn": "you"}, "probe")
        validate_value({"spells_cast_this_turn": "all"}, "probe")


class TestTheStormPathIsUnchanged:
    def test_a_card_reading_the_bare_count_still_compiles(self):
        compile_card(
            CardModel.model_validate(
                {
                    "id": "t_probe_storm",
                    "name": "Probe Storm",
                    "mana_cost": "{R}",
                    "types": ["Instant"],
                    "spell_effects": [
                        {"op": "copy_spell", "amount": {"spells_cast_this_turn": "all"}}
                    ],
                }
            )
        )

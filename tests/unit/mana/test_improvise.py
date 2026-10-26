"""Improvise: untapped artifacts you control pay for the generic cost.

Rule 702.126a: "Improvise is a static ability that functions while the spell
with improvise is on the stack. 'Improvise' means 'For each generic mana in
this spell's total cost, you may tap an untapped artifact you control rather
than pay that mana.'" And 702.126b: improvise is not an additional or
alternative cost and applies only after the total cost is determined.

It is convoke's shape (`pay_generic_with`) with a different currency, so it
inherits ADR 0020: one cast line, carrying the fewest artifacts the mana cannot
cover, and a `CHOOSE_OBJECTS` tagged ``improvise`` asked as the spell is paid
for. Without it Kappa Cannoneer is a {5}{U} creature that a board of
Treasures and Thopters cannot help cast -- or, written as convoke, one that
taps creatures and ignores the Mind Stone.

What would be wrong without each claim below:

- **Artifacts, not creatures.** A non-artifact creature cannot improvise and a
  non-creature artifact can.
- **Generic only.** Improvise never pays a coloured pip -- unlike convoke, that
  is the printed rule, not a simplification.
- **Tapped before the mana** ("after you're done activating mana abilities"):
  a Sol Ring tapped to improvise cannot also make {C}{C}, so a pick that taps
  the Sol Ring the rest of the cost needed is asked again.
- **The template reads the bare keyword** into the card-level field, and a line
  that adds anything to it is not claimed.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.authoring.templates import _translate_line
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from tests.unit.mana.test_pay_generic_with import (
    cast_lines,
    oids_of,
    pick,
    settle,
    spends,
    tapped_count,
)

IMPROVISER = "t_improviser"  # {3}{U} sorcery, improvise, draw two
TRINKET = "t_trinket"  # a vanilla artifact
CONSTRUCT = "t_construct"  # a 1/1 artifact creature
BEAR = "t_bear"  # a creature that is not an artifact

REMINDER = (
    "Improvise (Your artifacts can help cast this spell. Each artifact you tap "
    "after you're done activating mana abilities pays for {1}.)"
)


def position(builder, *, islands=2, trinkets=2, constructs=0, bears=0, sol_rings=0):
    return (
        builder(players=2)
        .hand(0, [IMPROVISER])
        .battlefield(0, ["island"] * islands)
        .battlefield(0, [TRINKET] * trinkets)
        .battlefield(0, [CONSTRUCT] * constructs)
        .battlefield(0, [BEAR] * bears)
        .battlefield(0, ["sol_ring"] * sol_rings)
        .build()
    )


class TestTheCurrencyIsArtifacts:
    def test_the_cast_asks_which_artifacts_tap(self, builder):
        game = position(builder, islands=4, trinkets=2)
        assert spends(game) == {0}, "the mana alone pays, so the printed line is the line"
        game.apply(cast_lines(game)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.context["purpose"] == "improvise"
        assert "improvise" in decision.prompt
        assert (decision.min_count, decision.max_count) == (0, 2)

    def test_it_makes_an_unaffordable_spell_castable(self, builder):
        """Two Islands cannot pay {3}{U}; two artifacts make up the difference."""
        game = position(builder, islands=2, trinkets=2)
        assert spends(game) == {2}
        before = len(game.state.players[0].hand)
        game.apply(cast_lines(game)[0])
        settle(game)
        assert tapped_count(game, TRINKET) == 2
        assert tapped_count(game, "island") == 2
        assert len(game.state.players[0].hand) == before - 1 + 2, "cast one, drew two"

    def test_improvising_saves_the_mana(self, builder):
        game = position(builder, islands=4, trinkets=2)
        game.apply(cast_lines(game)[0])
        pick(game, "improvise", oids_of(game, TRINKET)[:1])
        settle(game)
        assert tapped_count(game, TRINKET) == 1
        assert tapped_count(game, "island") == 3

    def test_an_artifact_creature_improvises(self, builder):
        game = position(builder, islands=3, trinkets=0, constructs=1)
        assert spends(game) == {1}
        game.apply(cast_lines(game)[0])
        settle(game)
        assert tapped_count(game, CONSTRUCT) == 1

    def test_a_creature_that_is_not_an_artifact_cannot(self, builder):
        """The near miss: this is improvise, not convoke."""
        game = position(builder, islands=2, trinkets=0, bears=2)
        assert cast_lines(game) == []

    def test_a_tapped_artifact_cannot(self, builder):
        game = position(builder, islands=2, trinkets=2)
        for obj in game.state.battlefield_objects(0):
            if obj.def_id == TRINKET:
                obj.tapped = True
        assert cast_lines(game) == []

    def test_an_opponents_artifact_cannot(self, builder):
        game = (
            builder(players=2)
            .hand(0, [IMPROVISER])
            .battlefield(0, ["island"] * 2)
            .battlefield(1, [TRINKET] * 2)
            .build()
        )
        assert cast_lines(game) == []


class TestGenericOnly:
    def test_it_never_pays_the_coloured_pip(self, builder):
        game = position(builder, islands=0, trinkets=4)
        assert cast_lines(game) == [], "no blue source, so no line at any count"

    def test_the_ceiling_is_the_generic_cost(self, builder):
        game = position(builder, islands=4, trinkets=6)
        game.apply(cast_lines(game)[0])
        assert game.pending().max_count == 3


class TestTappedBeforeTheMana:
    def test_a_pick_that_strands_the_mana_is_asked_again(self, builder):
        """Island plus Sol Ring is three mana; {3}{U} needs one artifact more.
        Improvising with the Sol Ring leaves {2}{U} for one Island -- so the
        pick is refused, and the Trinket goes instead."""
        game = position(builder, islands=1, trinkets=1, sol_rings=1)
        assert spends(game) == {1}
        game.apply(cast_lines(game)[0])
        first = game.pending()
        pick(game, "improvise", oids_of(game, "sol_ring"))
        again = game.pending()
        assert again is not first and again.context["purpose"] == "improvise"
        assert "Not enough mana" in again.prompt
        assert tapped_count(game, "sol_ring") == 0
        pick(game, "improvise", oids_of(game, TRINKET))
        settle(game)
        assert tapped_count(game, TRINKET) == 1
        assert tapped_count(game, "sol_ring") == 1, "the Sol Ring tapped for mana instead"
        assert not game.state.stack


class TestTheLoaderAndTheTemplate:
    def test_the_card_compiles(self, registry):
        assert registry.get(IMPROVISER).pay_generic_with == "tap_artifacts"

    def test_the_keyword_line_is_the_card_level_field(self):
        produced = _translate_line(REMINDER, is_spell=True)
        assert produced is not None
        kind, payload, _translation, name = produced
        assert (kind, payload, name) == ("card", {"pay_generic_with": "tap_artifacts"}, "improvise")

    @pytest.mark.parametrize("line", ["Improvise 2", "Improvise, then draw a card."])
    def test_a_line_that_says_more_is_not_claimed(self, line):
        produced = _translate_line(line, is_spell=True)
        assert produced is None or produced[3] != "improvise"

    def test_the_templated_card_loads(self):
        compile_card(
            CardModel.model_validate(
                {
                    "id": "probe",
                    "name": "Probe",
                    "oracle_text": REMINDER,
                    "mana_cost": "{3}{U}",
                    "types": ["Sorcery"],
                    "pay_generic_with": "tap_artifacts",
                    "spell_effects": [{"op": "noop"}],
                }
            )
        )

    def test_the_cast_line_is_one_row(self, builder):
        game = position(builder, islands=4, trinkets=3)
        lines = cast_lines(game)
        assert len(lines) == 1
        assert lines[0].kind is ActionKind.CAST

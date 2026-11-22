"""Offering (702.48): sacrifice a matching permanent, pay the difference.

"You may cast this card any time you could cast an instant by sacrificing a
[quality] permanent. If you do, the total cost to cast this spell is reduced by
the sacrificed permanent's mana cost" (702.48a). Three things emerge does not
do, and each is a different card if it is missed:

- **The quality is a permanent filter**, not "a creature". Blast-Furnace
  Hellkite's is *Artifact offering*: a Sol Ring is fodder and a bear is not.
  Read off derived characteristics, so a permanent granted the type qualifies.
- **The reduction is the mana cost, colour included.** ``{7}{R}{R}`` less a
  ``{1}{R}`` artifact is ``{6}{R}``, not emerge's ``{5}{R}{R}``: the red symbol
  takes a red pip off (118.7b). A colour the spell does not demand reduces the
  generic part instead (118.7c), so a ``{2}{G}{G}`` artifact still takes four.
- **Instant timing belongs to the offering line.** At sorcery timing the
  printed line is offered beside it; at instant timing only the sacrifice
  makes the cast legal, so the printed line is not offered at all. A version
  that gave the card flash would cast an unsacrificed Hellkite in the end step.

The witness is Blast-Furnace Hellkite; Goblin offering (`t_offering`) keeps the
subtype half of the filter honest.
"""

from __future__ import annotations

import dataclasses

import pytest

from commanderblitz.cards.authoring.verify import residual_text
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import ManaCost
from commanderblitz.engine.primitives import add_subtypes
from tests.conftest import only_oid, settle

OFFERING = "t_offering"  # {4}{R} 4/4 Goblin, Goblin offering
GOBLIN = "t_goblin"  # {1}{R} 1/1 Goblin
BEAR = "t_bear"  # {1}{G} 2/2, not a Goblin
HELLKITE = "t_artifact_offering"  # {7}{R}{R} 6/6 flier, Artifact offering
RED_RELIC = "t_red_relic"  # {1}{R} artifact
GREEN_RELIC = "t_green_relic"  # {2}{G}{G} artifact


def position(builder, card=OFFERING, board=(GOBLIN,), lands=5, step=Step.PRECOMBAT_MAIN):
    return (
        builder(players=2)
        .hand(0, [card])
        .battlefield(0, list(board))
        .battlefield(0, ["mountain"] * lands)
        .step(step)
        .build()
    )


def casts(game) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST]


def offering_lines(game) -> list:
    return [a for a in casts(game) if a.emerge_oid is not None]


def untapped_lands(game) -> int:
    return sum(
        1
        for o in game.state.battlefield_objects(0)
        if not o.tapped and "Land" in game.state.card_of(o).types
    )


def mana_spent_casting(game, line) -> int:
    before = untapped_lands(game)
    game.apply(line)
    settle(game)
    return before - untapped_lands(game)


class TestTheFodderIsFiltered:
    def test_a_matching_subtype_is_offered(self, builder):
        game = position(builder)
        (line,) = offering_lines(game)
        assert line.emerge_oid == only_oid(game, GOBLIN, 0)

    def test_a_creature_of_another_type_is_not(self, builder):
        game = position(builder, board=(BEAR,))
        assert offering_lines(game) == []

    def test_an_artifact_is_fodder_for_artifact_offering(self, builder):
        game = position(builder, card=HELLKITE, board=(RED_RELIC, BEAR), lands=7)
        (line,) = offering_lines(game)
        assert line.emerge_oid == only_oid(game, RED_RELIC, 0)
        assert "offering, sacrificing Test Red Relic" in line.label

    def test_the_printed_cost_is_still_offered(self, builder):
        game = position(builder, board=(BEAR,), lands=6)
        assert [a for a in casts(game) if a.emerge_oid is None]


class TestItReadsDerivedTypes:
    def test_a_creature_given_the_type_becomes_legal_fodder(self, builder):
        game = position(builder, board=(BEAR,))
        assert offering_lines(game) == []
        add_subtypes(game.state, only_oid(game, BEAR, 0), ["Goblin"])
        game.state.bump_chars()
        (line,) = offering_lines(game)
        assert line.emerge_oid == only_oid(game, BEAR, 0)


class TestTheReductionIsTheManaCost:
    def test_a_coloured_symbol_takes_a_coloured_pip(self):
        cost, generic_less = ManaCost.parse("{7}{R}{R}").reduced_by_mana_cost(
            ManaCost.parse("{1}{R}")
        )
        assert (cost.generic - generic_less, cost.symbols_of("R")) == (6, 1)

    def test_an_undemanded_colour_reduces_generic(self):
        """118.7c: the excess of a colour the cost lacks comes off generic."""
        cost, generic_less = ManaCost.parse("{7}{R}{R}").reduced_by_mana_cost(
            ManaCost.parse("{2}{G}{G}")
        )
        assert (cost.generic - generic_less, cost.symbols_of("R")) == (3, 2)

    def test_a_hybrid_symbol_takes_the_half_the_cost_demands(self):
        cost, generic_less = ManaCost.parse("{3}{R}").reduced_by_mana_cost(
            ManaCost.parse("{R/G}")
        )
        assert (cost.generic - generic_less, cost.symbols_of("R")) == (3, 0)

    def test_the_red_artifact_pays_red(self, builder):
        """{7}{R}{R} less {1}{R} is {6}{R}: seven mana. Emerge's mana-value
        arithmetic would have charged {5}{R}{R}, the same seven but two red."""
        game = position(builder, card=HELLKITE, board=(RED_RELIC,), lands=7)
        assert mana_spent_casting(game, offering_lines(game)[0]) == 7

    def test_a_green_artifact_comes_off_generic(self, builder):
        """{7}{R}{R} less {2}{G}{G} is {3}{R}{R}, five mana: offered on five."""
        game = position(builder, card=HELLKITE, board=(GREEN_RELIC,), lands=5)
        assert mana_spent_casting(game, offering_lines(game)[0]) == 5

    def test_too_little_mana_is_no_line(self, builder):
        game = position(builder, card=HELLKITE, board=(RED_RELIC,), lands=6)
        assert offering_lines(game) == []

    def test_the_fodder_is_sacrificed_and_the_spell_resolves(self, builder):
        game = position(builder, card=HELLKITE, board=(RED_RELIC,), lands=7)
        relic = only_oid(game, RED_RELIC, 0)
        game.apply(offering_lines(game)[0])
        settle(game)
        assert not game.state.objects[relic].on_battlefield
        assert only_oid(game, HELLKITE, 0) in game.state.battlefield


class TestInstantTimingIsTheOfferingLines:
    def test_at_instant_timing_only_the_sacrifice_is_offered(self, builder):
        game = position(builder, board=(GOBLIN,), lands=6, step=Step.UPKEEP)
        assert game.state.step is Step.UPKEEP
        lines = casts(game)
        assert lines
        assert all(a.emerge_oid is not None for a in lines)

    def test_without_fodder_it_waits_for_sorcery_timing(self, builder):
        """The card has no flash of its own: a bear is no Goblin, so nothing
        makes an upkeep cast legal."""
        game = (
            builder(players=2)
            .hand(0, [OFFERING, "lightning_bolt"])
            .battlefield(0, [BEAR])
            .battlefield(0, ["mountain"] * 6)
            .step(Step.UPKEEP)
            .build()
        )
        # The bolt is what holds the upkeep open for the question.
        assert game.state.step is Step.UPKEEP
        (offering,) = (
            oid for oid in game.state.players[0].hand if game.state.card(oid).id == OFFERING
        )
        assert [a for a in casts(game) if a.source == offering] == []


class TestTheLoaderGuardsIt:
    @staticmethod
    def _probe(**fields):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "probe",
                    "name": "Probe",
                    "oracle_text": "x",
                    "mana_cost": "{4}{R}",
                    "types": ["Creature"],
                    "power": 1,
                    "toughness": 1,
                    **fields,
                }
            )
        )

    def test_an_empty_selector_is_refused(self):
        with pytest.raises(DslError, match="needs a selector"):
            self._probe(offering={})

    def test_an_unknown_selector_key_is_refused(self):
        with pytest.raises(DslError, match="unknown selector keys"):
            self._probe(offering={"kind": "Artifact"})

    def test_emerge_beside_offering_is_refused(self):
        with pytest.raises(DslError, match="both 'emerge' and 'offering'"):
            self._probe(emerge="{3}{R}", offering={"types": ["Artifact"]})

    def test_the_offering_cards_compile(self, registry):
        assert registry.get(OFFERING).offering == {"subtypes": ["Goblin"]}
        assert registry.get(HELLKITE).offering == {"types": ["Artifact"]}
        assert registry.get(HELLKITE).emerge is None

    def test_plain_emerge_has_no_offering(self, registry):
        assert registry.get("t_emerger").offering is None


class TestTheResidualGateReadsTheQuality:
    """The printed "<quality> offering" line is claimed only by a selector of
    exactly that quality -- a card eating creatures cannot wear "Artifact
    offering"."""

    LINE = (
        "Artifact offering (You may cast this spell as though it had flash by "
        "sacrificing an artifact and paying the difference in mana costs between "
        "this and the sacrificed artifact. Mana cost includes color.)"
    )

    def test_the_matching_selector_claims_the_line(self, registry):
        card = registry.get(HELLKITE)
        assert "offering" not in residual_text(card, self.LINE).lower()

    def test_another_quality_does_not(self, registry):
        card = dataclasses.replace(registry.get(HELLKITE), offering={"types": ["Creature"]})
        assert "Artifact offering" in residual_text(card, self.LINE)

"""Improvise: artifacts you tap while casting pay for generic mana (702.126).

702.126a: "Each artifact you tap after you're done activating mana abilities
pays for {1}" -- convoke's shape (702.51) over artifacts, so it is the third
value of `pay_generic_with`, ``"tap_artifacts"``, and rides the same one cast
line and mid-payment pick ADR 0020 gives convoke and delve. Without it Kappa
Cannoneer, a {5}{U} creature its own deck casts off a board of artifacts,
could only be paid for in mana.

Two differences from convoke are the rule, not a simplification:

- **Generic only.** Convoke may also pay a coloured pip of the tapped
  creature's colour; improvise never pays anything but {1}, so tapping every
  artifact on the board still leaves {U} to find.
- **Artifacts, not creatures.** A creature that is not an artifact cannot
  improvise, and an artifact creature can (it is an artifact).

The tap comes before the mana, as convoke's does, so a pick that improvises
the Sol Ring the rest of the cost needed is refused and asked again.
"""

from __future__ import annotations

from commanderblitz.engine.enums import DecisionKind
from tests.unit.mana.test_pay_generic_with import (
    cast_lines,
    oids_of,
    pick,
    settle,
    spends,
    tapped_count,
)

IMPROVISER = "t_improviser"  # {3}{U} sorcery, improvise, draw two
RELIC = "t_glory_relic"  # a vanilla {2} artifact
BEAR = "t_bear"
ARTIFACT_CREATURE = "t_artifact_blocker"


def position(builder, *, lands=2, relics=2, others=()):
    return (
        builder(players=2)
        .hand(0, [IMPROVISER])
        .battlefield(0, ["island"] * lands)
        .battlefield(0, [RELIC] * relics)
        .battlefield(0, list(others))
        .build()
    )


class TestTheCast:
    def test_one_line_and_the_printed_one_when_mana_pays(self, builder):
        game = position(builder, lands=4, relics=3)
        assert len(cast_lines(game)) == 1
        assert spends(game) == {0}

    def test_the_cast_asks_which_artifacts_tap(self, builder):
        game = position(builder, lands=4, relics=2)
        game.apply(cast_lines(game)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.context["purpose"] == "improvise"
        assert (decision.min_count, decision.max_count) == (0, 2)
        assert "improvise" in decision.prompt

    def test_improvising_saves_the_mana(self, builder):
        game = position(builder, lands=4, relics=2)
        game.apply(cast_lines(game)[0])
        pick(game, "improvise", oids_of(game, RELIC)[:1])
        settle(game)
        assert tapped_count(game, RELIC) == 1
        assert tapped_count(game, "island") == 3

    def test_it_makes_an_unaffordable_spell_castable(self, builder):
        """The whole keyword: two Islands cannot pay {3}{U} alone."""
        game = position(builder, lands=2, relics=2)
        assert spends(game) == {2}
        before = len(game.state.players[0].hand)
        game.apply(cast_lines(game)[0])
        settle(game)
        assert tapped_count(game, RELIC) == 2
        assert len(game.state.players[0].hand) == before - 1 + 2, "cast one, drew two"


class TestWhatMayBeTapped:
    def test_a_creature_cannot_improvise(self, builder):
        game = position(builder, lands=2, relics=0, others=[BEAR, BEAR])
        assert cast_lines(game) == []

    def test_an_artifact_creature_can(self, builder):
        game = position(builder, lands=2, relics=1, others=[ARTIFACT_CREATURE])
        assert spends(game) == {2}
        game.apply(cast_lines(game)[0])
        settle(game)
        assert tapped_count(game, ARTIFACT_CREATURE) == 1
        assert tapped_count(game, RELIC) == 1

    def test_a_tapped_artifact_cannot(self, builder):
        game = position(builder, lands=2, relics=2)
        for obj in game.state.battlefield_objects(0):
            if obj.def_id == RELIC:
                obj.tapped = True
        assert cast_lines(game) == []

    def test_it_never_pays_the_coloured_pip(self, builder):
        """Improvise pays {1} and nothing else: four artifacts and no Island
        leave the {U} unpaid at every count."""
        game = position(builder, lands=0, relics=4)
        assert cast_lines(game) == []

    def test_the_ceiling_is_the_generic_cost(self, builder):
        game = position(builder, lands=4, relics=6)
        game.apply(cast_lines(game)[0])
        assert game.pending().max_count == 3


class TestTheTapComesBeforeTheMana:
    def test_a_pick_that_strands_the_mana_is_asked_again(self, builder):
        """Island + Sol Ring make three of the four; improvising the Sol Ring
        with the relic would leave {1}{U} to pay off one Island."""
        game = position(builder, lands=1, relics=1, others=["sol_ring"])
        assert spends(game) == {1}
        game.apply(cast_lines(game)[0])
        first = game.pending()
        pick(game, "improvise", [oids_of(game, "sol_ring")[0], oids_of(game, RELIC)[0]])
        again = game.pending()
        assert again is not first and again.context["purpose"] == "improvise"
        assert "Not enough mana" in again.prompt
        assert tapped_count(game, RELIC) == 0 and tapped_count(game, "sol_ring") == 0
        pick(game, "improvise", oids_of(game, RELIC))
        settle(game)
        assert tapped_count(game, RELIC) == 1
        assert tapped_count(game, "sol_ring") == 1, "the Sol Ring tapped for mana instead"


class TestTheLoaderKnowsIt:
    def test_the_card_compiles(self, registry):
        assert registry.get(IMPROVISER).pay_generic_with == "tap_artifacts"


class TestThePrintedLineIsClaimed:
    """Gate 3's bookkeeping. `pay_generic_with` is card-level, so no ability
    can carry the printed "Improvise" -- a spell's line was always claimed by
    its `spell_effects`, but a permanent like Kappa Cannoneer has none. The
    claimant is the field, and the field must be the currency the word names.
    """

    def _card(self, pay_generic_with):
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.cards.schema import CardModel

        return compile_card(
            CardModel.model_validate(
                {
                    "id": "t_improvise_residual",
                    "name": "Improvise Residual",
                    "mana_cost": "{5}{U}",
                    "oracle_text": (
                        "Improvise (Your artifacts can help cast this spell. Each artifact"
                        " you tap after you're done activating mana abilities pays for {1}.)"
                        "\nFlying"
                    ),
                    "types": ["Artifact", "Creature"],
                    "power": 4,
                    "toughness": 4,
                    "keywords": ["flying"],
                    "pay_generic_with": pay_generic_with,
                }
            )
        )

    def test_the_line_is_claimed(self):
        from commanderblitz.cards.authoring.verify import residual_text

        card = self._card("tap_artifacts")
        assert residual_text(card, card.oracle_text) == ""

    def test_no_field_no_claim(self):
        from commanderblitz.cards.authoring.verify import residual_text

        card = self._card(None)
        assert "Improvise" in residual_text(card, card.oracle_text)

    def test_convoke_cannot_claim_improvise(self):
        from commanderblitz.cards.authoring.verify import residual_text

        card = self._card("tap_creatures")
        assert "Improvise" in residual_text(card, card.oracle_text)

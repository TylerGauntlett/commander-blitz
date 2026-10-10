""""Spend this mana only to cast a **non**creature spell."

The Emperor of Palamecia. `mana_restriction` was already the right home for the
line and was purely positive: `_restriction_groups` compiled each group to a
frozenset of literal names and `ManaSource.permits` answered
`group <= purpose.names` against the spell's flat set of types and subtypes.
Nothing in that chain could ask about a name being **absent**.

Both spellings available before this are wrong, in opposite directions, and both
are kept here as live cards because a negation is only worth having if the near
misses are worse:

- `["noncreature"]` loads -- the loader's guard only asks that an entry look like
  a word -- and then matches nothing ever, because no spell has a type called
  "noncreature". The mana is permanently unspendable, a strictly *worse* card,
  and silent. `TestTheLiteralSpellingIsDead` is that claim.
- `["artifact", "enchantment", "instant", "sorcery"]` enumerates the noncreature
  types and over-permits every artifact creature, because `permits` sees
  "artifact" among the names and never learns "creature" is there too. A strictly
  *better* card. `TestTheEnumeratedSpellingLeaks` is that claim, and the
  artifact creature is the witness that separates it from the real thing.

`RestrictionGroup` therefore carries `forbidden` beside `required`, and a group
is satisfied when every required name is present and no forbidden one is. This
is the same one-word idea trigger filters have had all along as `not_types`,
arriving in the one place that lacked it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import spell_purpose
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import (
    ACTIVATE,
    CAST,
    ManaRestriction,
    RestrictionGroup,
    SpendPurpose,
)
from tests.conftest import pass_until

NEGATED = "t_emperor_mana"  # [[{"not": "creature"}]]
ENUMERATED = "t_enumerated_font"  # the four noncreature types, spelled out
LITERAL = "t_literal_noncreature_font"  # the word "noncreature", which is not a type

ARTIFACT_CREATURE = "t_artifact_creature_spell"  # {U} 1/1 Artifact Creature
ARTIFACT = "t_plain_artifact_spell"  # {U} Artifact
CREATURE = "t_plain_creature_spell"  # {U} Creature


def position(builder, font: str, spell: str):
    """One font, and one {U} spell in hand -- no other blue source on the board.

    The board is deliberately starved: with a single Island available the test
    could never tell a permitted payment from an unrestricted one.
    """
    return (
        builder(players=2)
        .battlefield(0, [font, "wastes"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 10)
        .hand(0, [spell])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def can_cast(game, card_id: str) -> bool:
    game._advance()
    pass_until(game, lambda g: g.pending() is not None)
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


class TestTheNegationItself:
    """`permits` asks both questions."""

    def group(self):
        return ManaRestriction(cast=(RestrictionGroup(frozenset(), frozenset({"creature"})),))

    def permits(self, names: set[str]) -> bool:
        from commanderblitz.engine.mana import ManaSource

        source = ManaSource(oid=1, ability_index=0, options=((0, 1, 0, 0, 0, 0),), restriction=self.group())
        return source.permits(SpendPurpose(CAST, frozenset(names)))

    def test_a_noncreature_spell_is_permitted(self):
        assert self.permits({"instant"})

    def test_a_creature_spell_is_not(self):
        assert not self.permits({"creature", "bear"})

    def test_an_artifact_creature_is_not(self):
        """The whole reason a negation and an enumeration are different cards."""
        assert not self.permits({"artifact", "creature", "construct"})


class TestARequiredNameAndAForbiddenOneTogether:
    """"a noncreature **artifact** spell" -- both halves in one group."""

    def permits(self, names: set[str]) -> bool:
        from commanderblitz.engine.mana import ManaSource

        restriction = ManaRestriction(
            cast=(RestrictionGroup(frozenset({"artifact"}), frozenset({"creature"})),)
        )
        source = ManaSource(
            oid=1, ability_index=0, options=((0, 1, 0, 0, 0, 0),), restriction=restriction
        )
        return source.permits(SpendPurpose(CAST, frozenset(names)))

    def test_a_plain_artifact_is_permitted(self):
        assert self.permits({"artifact"})

    def test_an_artifact_creature_is_not(self):
        assert not self.permits({"artifact", "creature"})

    def test_a_noncreature_nonartifact_is_not(self):
        """The required half still has to be met; "not a creature" is not enough."""
        assert not self.permits({"instant"})


class TestTheKindStillMatters:
    def test_a_cast_restriction_does_not_fund_an_activation(self):
        """The negation changes nothing about which half is being asked."""
        from commanderblitz.engine.mana import ManaSource

        restriction = ManaRestriction(cast=(RestrictionGroup(frozenset(), frozenset({"creature"})),))
        source = ManaSource(
            oid=1, ability_index=0, options=((0, 1, 0, 0, 0, 0),), restriction=restriction
        )
        assert not source.permits(SpendPurpose(ACTIVATE, frozenset({"instant"})))


class TestInAGame:
    def test_the_noncreature_spell_can_be_cast(self, builder):
        game = position(builder, NEGATED, ARTIFACT)
        assert can_cast(game, ARTIFACT)

    def test_the_creature_spell_cannot(self, builder):
        game = position(builder, NEGATED, CREATURE)
        assert not can_cast(game, CREATURE)

    def test_and_neither_can_an_artifact_creature(self, builder):
        """The card the enumerated spelling would have paid for."""
        game = position(builder, NEGATED, ARTIFACT_CREATURE)
        assert not can_cast(game, ARTIFACT_CREATURE)


class TestTheEnumeratedSpellingLeaks:
    """Kept as a live card: this is the strictly-better card the negation avoids."""

    def test_it_pays_for_an_artifact_creature(self, builder):
        game = position(builder, ENUMERATED, ARTIFACT_CREATURE)
        assert can_cast(game, ARTIFACT_CREATURE), (
            "the enumeration sees 'artifact' and never learns 'creature' is there too"
        )


class TestTheLiteralSpellingIsDead:
    """The other near miss, and the quieter one: mana that can never be spent."""

    def test_it_pays_for_nothing_at_all(self, builder):
        game = position(builder, LITERAL, ARTIFACT)
        assert not can_cast(game, ARTIFACT), "no spell has a type called 'noncreature'"


class TestTheLoaderRefusesWhatCannotBeSatisfied:
    def card(self, restriction):
        return {
            "id": "t_probe",
            "name": "Probe",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "activated",
                    "text": "{T}: Add {U}.",
                    "cost": {"tap": True},
                    "is_mana_ability": True,
                    "mana_restriction": restriction,
                    "effects": [{"op": "add_mana", "mana": "{U}", "player": "you"}],
                }
            ],
        }

    def test_a_name_both_required_and_forbidden(self):
        """Nothing can satisfy it -- the same dead mana a typo makes."""
        with pytest.raises(DslError, match="both required and forbidden"):
            compile_card(CardModel.model_validate(self.card([["creature", {"not": "creature"}]])))

    def test_a_negated_chosen_type(self):
        """Refused rather than accepted and half-honoured: no card prints it."""
        with pytest.raises(DslError, match="literal type or subtype"):
            compile_card(
                CardModel.model_validate(
                    self.card([[{"not": {"chosen_type_of": "self"}}]])
                )
            )

    def test_a_negation_with_extra_keys(self):
        with pytest.raises(DslError, match="takes only 'not'"):
            compile_card(
                CardModel.model_validate(self.card([[{"not": "creature", "and": "artifact"}]]))
            )


class TestTheOldSpellingIsUnchanged:
    def test_a_bare_positive_group_still_compiles(self):
        """The coercion path: a plain list is every name required, none forbidden."""
        card = compile_card(
            CardModel.model_validate(
                {
                    "id": "t_probe2",
                    "name": "Probe Two",
                    "mana_cost": "{2}",
                    "types": ["Artifact"],
                    "abilities": [
                        {
                            "kind": "activated",
                            "text": "{T}: Add {U}.",
                            "cost": {"tap": True},
                            "is_mana_ability": True,
                            "mana_restriction": "creature",
                            "effects": [{"op": "add_mana", "mana": "{U}", "player": "you"}],
                        }
                    ],
                }
            )
        )
        assert card.abilities[0].mana_restriction.cast == (
            RestrictionGroup(frozenset({"creature"}), frozenset()),
        )


class TestSpellPurposeIsUnchanged:
    def test_it_still_reports_the_flat_name_set(self, registry):
        """The negation reads the same `names` the positive form always did."""
        card = registry.get(ARTIFACT_CREATURE)
        purpose = spell_purpose(card)
        assert "artifact" in purpose.names and "creature" in purpose.names

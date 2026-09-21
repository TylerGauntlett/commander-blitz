"""Mana spendable only on a *legendary* spell -- a supertype, not a type.

    "{T}: Add one mana of any color. Spend this mana only to cast a legendary
    spell, and that spell can't be countered."      -- Delighted Halfling

`mana_restriction` was the right field and had the wrong vocabulary.
`costs.spell_purpose` built the set of names a restricted source is matched
against from ``card.types`` and ``card.subtypes`` and never `supertypes`, while
`loader.mana._restriction_name` accepts any alphabetic word -- so "legendary"
**loaded clean and matched nothing on any card in the game**.

That is the worst shape a bug can take here. It is not a crash and not a refusal:
it is mana that can never be spent, which reads on the board as a permanent that
taps for nothing, and the card looks implemented the whole time.

Supertypes are added at both purposes. `ability_purpose` too, and off the
permanent's *current* characteristics where it has them, because "a legendary
source" is a question about what the permanent is now -- the same reading
`ability_purpose` already takes for types and subtypes.

The board below is starved on purpose: one restricted source and no other, so a
permitted payment and an unrestricted one cannot be confused.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step
from tests.conftest import pass_until

HALFLING = "t_halfling_mana"  # "spend this mana only to cast a legendary spell"

LEGEND = "t_legend_spell"  # {G} Legendary Creature
PLAIN = "t_plain_spell"  # {G} Creature -- the same card without the supertype
RELIC = "t_legend_artifact"  # {G} Legendary Artifact -- legendary, not a creature


def position(builder, spell: str):
    """The Halfling and one {G} spell in hand, with no other green source."""
    return (
        builder(players=2)
        .battlefield(0, [HALFLING, "wastes"])
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


class TestTheSupertypeIsRead:
    def test_a_legendary_creature_can_be_cast(self, builder):
        """The whole point. Before supertypes were read this was False, and the
        Halfling's second ability made mana nothing in the game could spend."""
        assert can_cast(position(builder, LEGEND), LEGEND)

    def test_a_legendary_noncreature_can_be_cast_too(self, builder):
        """"Legendary spell" names the supertype and nothing else, so the
        artifact qualifies exactly as the creature does."""
        assert can_cast(position(builder, RELIC), RELIC)


class TestItIsStillARestriction:
    def test_an_ordinary_creature_cannot(self, builder):
        """The same card at the same cost without the supertype.

        This is what stops the fix from being "match everything": the two spells
        differ in one word, and only one of them may be paid for.
        """
        assert not can_cast(position(builder, PLAIN), PLAIN)

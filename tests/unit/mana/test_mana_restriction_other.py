""""This mana can't be spent to cast a nonartifact spell." -- the Vibranium token.

Every restriction before it was worded "spend this mana **only** to …": it
permits one thing and refuses the rest. The Vibranium token's is a
**prohibition**: it refuses one thing, casting a nonartifact spell, and permits
the rest. Mana is spent on more than spells and abilities (rule 106.6 and the
payments of 118): a ward price, an attack tax (508.1g), a resolving ability's
"you may pay", an enters price, and the special actions of 116.2 -- suspend,
foretell, turning a face-down creature up. A `mana_restriction` had only
`cast` and `activate` halves, and every one of those other payments passed no
purpose at all, which withholds restricted mana. So the nearest spelling,
Automated Artificer's ``{"cast": [["artifact"]], "activate": "any"}``, ships a
Vibranium whose mana pays no Propaganda and no ward: a weaker card than the
printed one.

The `other` half answers those payments, which pass `mana.OTHER_PAYMENT`. It
takes only ``"any"``: no spell or source stands behind a tax, so there is
nothing to name. Omitted, as on every "spend this mana only to …" card, it is
"never", and that is still right for them -- Cryptic Trilobite's mana pays no
ward.

The witnesses are the five Wakanda Forever cards that make Vibranium tokens
(T'Challa, the Black Panther; Dora Milaje Elite; The Great Mound; Vibranium
Mining Mech; Shuri's Fabricator). `t_artificer_shape_mana` is the near miss,
kept as a live card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.carddef import Cost
from commanderblitz.engine.costs import can_pay, mana_sources
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import (
    ACTIVATE,
    CAST,
    OTHER,
    OTHER_PAYMENT,
    ManaCost,
    ManaRestriction,
    ManaSource,
    RestrictionGroup,
    SpendPurpose,
)
from tests.conftest import action_for_card, advance_to_step, oids_of

VIBRANIUM = "vibranium_token"
NEAR_MISS = "t_artificer_shape_mana"  # {"cast": [["artifact"]], "activate": "any"}

ARTIFACT_SPELL = "arcane_signet"  # {2} Artifact
SORCERY = "t_generic_spell"  # {2} Sorcery
SINK = "t_sink_enchantment"  # "{2}: You gain 1 life."
BEAR = "grizzly_bears"
PROPAGANDA = "t_propaganda"  # attacks cost {2} each


def position(builder, font: str, *, board=(), hand=(), theirs=("plains",)):
    """Two of ``font`` and nothing else that makes mana.

    Starved deliberately, as `test_mana_restriction_activate_any` is: with any
    other source on the table a permitted payment and one the font never funded
    look the same.
    """
    return (
        builder(players=2)
        .battlefield(0, [font, font, *board])
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 10)
        .hand(0, list(hand))
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def offered(game, font: str, purpose) -> bool:
    fonts = set(oids_of(game, font, 0))
    return any(s.oid in fonts for s in mana_sources(game.state, 0, purpose=purpose))


def can(game, kind: ActionKind, card_id: str) -> bool:
    try:
        action_for_card(game, kind, card_id)
    except AssertionError:
        return False
    return True


class TestTheToken:
    """The printed token, pinned where its restriction is the claim."""

    def test_it_is_an_indestructible_colorless_vibranium_artifact(self, registry):
        token = registry.get(VIBRANIUM)
        assert token.is_token and token.name == "Vibranium"
        assert list(token.types) == ["Artifact"]
        assert list(token.subtypes) == ["Vibranium"]
        assert not token.colors
        assert set(token.keywords) == {"indestructible"}

    def test_its_mana_ability_carries_all_three_halves(self, registry):
        [ability] = registry.get(VIBRANIUM).abilities
        assert ability.is_mana_ability
        restriction = ability.mana_restriction
        [cast] = restriction.cast
        assert cast.required == frozenset({"artifact"}) and not cast.forbidden
        [activate] = restriction.activate
        [other] = restriction.other
        assert not activate.required and not other.required


class TestWhatTheMayPayFor:
    """The restriction as `mana_sources` sees it, one purpose at a time."""

    @pytest.mark.parametrize(
        ("purpose", "allowed"),
        [
            (SpendPurpose(CAST, frozenset({"artifact"})), True),
            (SpendPurpose(CAST, frozenset({"artifact", "creature", "construct"})), True),
            (SpendPurpose(CAST, frozenset({"sorcery"})), False),
            (SpendPurpose(CAST, frozenset({"creature", "bear"})), False),
            (SpendPurpose(ACTIVATE, frozenset({"enchantment"})), True),
            (SpendPurpose(ACTIVATE, frozenset()), True),
            (OTHER_PAYMENT, True),
            (None, False),
        ],
        ids=[
            "artifact-spell",
            "artifact-creature-spell",
            "sorcery",
            "creature-spell",
            "ability",
            "ability-of-a-typeless-source",
            "other-payment",
            "no-purpose",
        ],
    )
    def test_vibranium(self, builder, purpose, allowed):
        game = position(builder, VIBRANIUM)
        assert offered(game, VIBRANIUM, purpose) is allowed

    def test_no_purpose_still_withholds_it(self, builder):
        """`None` stays "no payment in mind" -- an AI count -- and under-counts.

        Reading `None` as "other" instead would have handed the yes to every
        count with no spell in mind, and to the cast-time payments that pass
        none (splice, madness).
        """
        game = position(builder, VIBRANIUM)
        assert not offered(game, VIBRANIUM, None)

    def test_the_near_miss_refuses_the_other_payment(self, builder):
        """The whole difference, and the reason `other` exists."""
        game = position(builder, NEAR_MISS)
        assert offered(game, NEAR_MISS, SpendPurpose(CAST, frozenset({"artifact"})))
        assert offered(game, NEAR_MISS, SpendPurpose(ACTIVATE, frozenset()))
        assert not offered(game, NEAR_MISS, OTHER_PAYMENT)

    def test_a_spend_only_restriction_refuses_it_too(self, builder):
        """Every card that omits `other` -- Ancient Ziggurat's "only to cast a
        creature spell" -- pays no tax, exactly as before."""
        assert OTHER_PAYMENT.kind == OTHER
        source = ManaSource(
            oid=1,
            ability_index=0,
            options=((0, 0, 0, 0, 0, 1),),
            restriction=ManaRestriction(cast=(RestrictionGroup(frozenset({"creature"})),)),
        )
        assert not source.permits(OTHER_PAYMENT)


class TestInAGame:
    def test_it_casts_an_artifact_spell(self, builder):
        game = position(builder, VIBRANIUM, hand=[ARTIFACT_SPELL])
        assert can(game, ActionKind.CAST, ARTIFACT_SPELL)

    def test_it_does_not_cast_a_nonartifact_spell(self, builder):
        """The printed prohibition."""
        game = position(builder, VIBRANIUM, hand=[SORCERY])
        assert not can(game, ActionKind.CAST, SORCERY)

    def test_it_activates_an_ability(self, builder):
        game = position(builder, VIBRANIUM, board=[SINK])
        assert can(game, ActionKind.ACTIVATE, SINK)

    def test_it_pays_a_resolving_abilitys_price(self, builder):
        """`op_may`'s `can_pay` and `pay` -- ward, Rhystic Study -- pass `OTHER_PAYMENT`."""
        game = position(builder, VIBRANIUM)
        price = Cost(mana=ManaCost.parse("{2}"))
        assert can_pay(game.state, 0, price, None, purpose=OTHER_PAYMENT)
        assert not can_pay(game.state, 0, price, None)

    def test_the_near_miss_cannot_pay_it(self, builder):
        game = position(builder, NEAR_MISS)
        price = Cost(mana=ManaCost.parse("{2}"))
        assert not can_pay(game.state, 0, price, None, purpose=OTHER_PAYMENT)


class TestAnAttackTax:
    """Propaganda's {2}: 508.1g, paid as the attack is declared."""

    def attacks(self, game):
        return [a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER]

    def board(self, builder, font: str):
        game = position(builder, font, board=[BEAR], theirs=[PROPAGANDA])
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        return game

    def test_vibranium_pays_it(self, builder):
        game = self.board(builder, VIBRANIUM)
        [attack, *_] = self.attacks(game)
        game.apply(attack)
        assert all(game.state.objects[oid].tapped for oid in oids_of(game, VIBRANIUM, 0)), (
            "both tokens really paid the tax"
        )
        assert game.state.combat is not None and game.state.combat.attackers

    def test_the_near_miss_does_not(self, builder):
        """The weaker card `other` exists to avoid: the attack is unaffordable."""
        game = self.board(builder, NEAR_MISS)
        assert self.attacks(game) == []


class TestTheLoader:
    def card(self, restriction):
        return {
            "id": "t_probe_other",
            "name": "Probe Other",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "activated",
                    "text": "{T}: Add {C}.",
                    "cost": {"tap": True},
                    "is_mana_ability": True,
                    "mana_restriction": restriction,
                    "effects": [{"op": "add_mana", "mana": "{C}", "player": "you"}],
                }
            ],
        }

    def compile(self, restriction):
        return compile_card(CardModel.model_validate(self.card(restriction)))

    def test_other_takes_the_wildcard(self):
        card = self.compile({"cast": [["artifact"]], "activate": "any", "other": "any"})
        assert len(card.abilities[0].mana_restriction.other) == 1

    def test_other_omitted_is_never(self):
        card = self.compile({"cast": [["artifact"]], "activate": "any"})
        assert card.abilities[0].mana_restriction.other == ()

    @pytest.mark.parametrize("value", [["artifact"], [["creature"]], []], ids=str)
    def test_other_refuses_names(self, value):
        """No spell or source stands behind a tax: a name would never match,
        and the mana would silently never pay one."""
        with pytest.raises(DslError, match="takes only 'any'"):
            self.compile({"cast": [["artifact"]], "other": value})

    def test_all_three_wildcarded_is_still_ordinary_mana(self):
        with pytest.raises(DslError, match="restricts nothing"):
            self.compile({"cast": "any", "activate": "any", "other": "any"})

    def test_other_alone_permits_no_spell_or_ability(self):
        """Mana for taxes only is printed nowhere, and reads as a blank."""
        with pytest.raises(DslError, match="permits nothing"):
            self.compile({"other": "any"})

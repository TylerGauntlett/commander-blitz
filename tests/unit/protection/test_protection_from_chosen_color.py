""""Enchanted creature has protection from the chosen color. This effect doesn't
remove this Aura." -- 702.16a, 303.4d

    "Enchant creature. As this Aura enters, choose a color. Enchanted creature
    has protection from the chosen color. This effect doesn't remove this
    Aura. {W}: Return this Aura to its owner's hand."  -- Flickering Ward

Two halves were missing. The `protection` static's `from_colors` took literal
colour letters only, while the colour `choose_color` writes to `chosen_color`
was read by `add_mana`, the static filters and the one-shot `grant_protection`
-- so "protection from the chosen color" had no static to live on. It is
``{"chosen_color_of": "self"}`` in `from_colors`, substituted by
`characteristics.resolve_chosen_color_list` inside `protection_from` at the
moment a rule asks, so damage, enchant/equip, block and target all see it.

And protection from a colour stops the host being enchanted by anything of that
colour (702.16c), the Ward itself included: a white Ward that chose white would
be a white Aura its own host is protected from. "This effect doesn't remove this
Aura" is ``spares: "self"``, read only by the enchant/equip rule
(`protected_from(..., attaching=True)`) and only for the static's own source.
Without it a Ward put back onto its host -- or offered it as a host -- would be
refused by its own protection. A second white Aura is still refused, and the
Ward's own damage, blocks and targets still meet the protection: the sentence
is about removal and nothing else.

The boundaries: before a choice the static protects from **nothing**, a colour
other than the chosen one walks through, a near-miss leaf and a granted copy are
refused, and `spares` loads only on a `protection` static an attachment grants
its host.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import protected_from, protection_from
from commanderblitz.engine.combat import can_block
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach, damage_permanent
from commanderblitz.engine.structs import CombatState
from tests.conftest import only_oid, settle, static_probe

WARD = "t_pcc_ward"  # white Aura: protection from the chosen colour, spares itself
UNSPARED = "t_pcc_unspared"  # the same Aura without "doesn't remove this Aura"
RAY = "t_pcc_ray"  # {W} instant, 2 damage to target creature
BOLT = "t_bolt"  # {R} instant, 3 damage to any target
BEAR = "t_bear"  # {1}{G} Bear -- green

CHOSEN = {"chosen_color_of": "self"}


def position(builder, chosen: str | None, auras=(WARD,)):
    """Our Bear wearing each of ``auras`` (all with ``chosen`` written on them),
    beside our bare Bear; their Bear, and a Bolt and a Ray in their hand.

    Attached before the position advances, so the state-based action that bins
    an unattached Aura never sees one. Returns ``(game, bear, aura_oids)``.
    """
    game = (
        builder(players=2)
        .battlefield(0, [BEAR, *auras])
        .battlefield(1, [BEAR, "mountain", "plains"])
        .hand(1, [BOLT, RAY])
        .library(0, ["plains"] * 20)
        .library(1, ["mountain"] * 20)
        .active(1)
        .step(Step.UNTAP)
        .build(advance=False)
    )
    bear = only_oid(game, BEAR, 0)
    worn = [o for o in game.state.battlefield if game.state.objects[o].def_id in auras]
    for oid in worn:
        assert attach(game.state, oid, bear)
    for oid in worn:
        game.state.objects[oid].chosen_color = chosen
    game.state.bump_chars()
    game._advance()
    return game, bear, worn


def targets_of(game, def_id: str) -> set[int]:
    return {
        ref.id
        for action in game.legal_actions()
        if action.kind is ActionKind.CAST
        and game.state.objects[action.source].def_id == def_id
        for ref in action.targets
        if ref.kind != "player"
    }


class TestTheChosenColorIsTheQuality:
    def test_it_reads_the_choice(self, builder):
        game, bear, _ = position(builder, "R")
        assert protection_from(game.state, bear) == frozenset({"R"})

    def test_before_a_choice_it_protects_from_nothing(self, builder):
        """Not from everything: the window before the choice grants nothing."""
        game, bear, _ = position(builder, None)
        assert protection_from(game.state, bear) == frozenset()

    def test_a_later_choice_is_followed(self, builder):
        game, bear, (ward,) = position(builder, "R")
        game.state.objects[ward].chosen_color = "U"
        game.state.bump_chars()
        assert protection_from(game.state, bear) == frozenset({"U"})

    def test_only_the_host_has_it(self, builder):
        game, _, (ward,) = position(builder, "R")
        theirs = only_oid(game, BEAR, 1)
        assert protection_from(game.state, theirs) == frozenset()
        assert protection_from(game.state, ward) == frozenset()


class TestTheFourRulesSeeIt:
    def test_a_spell_of_the_chosen_color_cannot_target_the_host(self, builder):
        game, bear, _ = position(builder, "R")
        assert bear not in targets_of(game, BOLT)
        assert bear in targets_of(game, RAY)

    def test_another_choice_lets_that_spell_through(self, builder):
        game, bear, _ = position(builder, "W")
        assert bear in targets_of(game, BOLT)
        assert bear not in targets_of(game, RAY)

    def test_damage_from_the_chosen_color_is_prevented(self, builder):
        game, bear, _ = position(builder, "G")
        theirs = only_oid(game, BEAR, 1)
        assert damage_permanent(game.state, bear, 2, theirs) == 0

    def test_damage_from_another_color_is_dealt(self, builder):
        game, bear, _ = position(builder, "R")
        theirs = only_oid(game, BEAR, 1)
        assert damage_permanent(game.state, bear, 1, theirs) == 1

    def test_a_creature_of_the_chosen_color_cannot_block_the_host(self, builder):
        game, bear, _ = position(builder, "G")
        theirs = only_oid(game, BEAR, 1)
        game.state.combat = CombatState(attackers={bear: 1})
        game.state.bump_chars()
        assert not can_block(game.state, theirs, bear, 1)


class TestThisEffectDoesNotRemoveThisAura:
    def test_the_ward_goes_back_onto_a_host_it_protects_from_its_own_color(self, builder):
        """The Ward is white and chose white: its host is protected from white
        Auras, and the Ward is spared."""
        game, bear, (ward,) = position(builder, "W")
        assert "W" in protection_from(game.state, bear)
        assert not protected_from(game.state, bear, ward, attaching=True)
        assert attach(game.state, ward, bear)
        assert game.state.objects[ward].attached_to == bear

    def test_the_control_without_the_sentence_it_is_refused(self, builder):
        game, bear, (aura,) = position(builder, "W", auras=(UNSPARED,))
        assert protected_from(game.state, bear, aura, attaching=True)
        assert not attach(game.state, aura, bear)

    def test_it_spares_only_itself(self, builder):
        """Two Wards on one host, the second chose blue: the first's
        protection from white still refuses the second, a white Aura."""
        game, bear, (first, second) = position(builder, "W", auras=(WARD, WARD))
        game.state.objects[second].chosen_color = "U"
        game.state.bump_chars()
        assert protected_from(game.state, bear, second, attaching=True)
        assert not protected_from(game.state, bear, first, attaching=True)

    def test_it_is_about_removal_and_nothing_else(self, builder):
        """Asked as damage, block or target, the Ward meets the protection."""
        game, bear, (ward,) = position(builder, "W")
        assert protected_from(game.state, bear, ward)

    def test_cast_and_chosen_its_own_color_it_stays_on(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, "plains"])
            .hand(0, [WARD])
            .library(0, ["plains"] * 20)
            .library(1, ["mountain"] * 20)
            .active(0)
            .max_turns(1)
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == WARD
            )
        )
        while (decision := game.pending()) is not None and decision.kind is not DecisionKind.CHOOSE_MODE:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
        index = [o.label for o in decision.options].index("White")
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
        )
        settle(game)
        ward = only_oid(game, WARD, 0)
        assert game.state.objects[ward].attached_to == bear
        assert protection_from(game.state, bear) == frozenset({"W"})


def _aura(**static) -> CardModel:
    return CardModel.model_validate(
        static_probe(
            {"effect": "protection", "affects": {"attached": True}, **static}
        )
    )


class TestTheLoader:
    def test_the_chosen_entry_loads(self):
        compile_card(_aura(from_colors=[CHOSEN], spares="self"))

    def test_it_loads_beside_a_literal(self):
        compile_card(_aura(from_colors=["B", CHOSEN]))

    def test_a_near_miss_is_refused(self):
        with pytest.raises(DslError, match="chosen_color_of"):
            compile_card(_aura(from_colors=[{"chosen_color_of": "other"}]))

    def test_the_type_leaf_is_not_a_colour(self):
        with pytest.raises(DslError, match="chosen_color_of"):
            compile_card(_aura(from_colors=[{"chosen_card_type_of": "self"}]))

    def test_spares_names_only_self(self):
        with pytest.raises(DslError, match="spares"):
            compile_card(_aura(from_colors=["W"], spares="auras"))

    def test_spares_needs_an_attached_host(self):
        with pytest.raises(DslError, match="spares"):
            compile_card(
                CardModel.model_validate(
                    static_probe(
                        {
                            "effect": "protection",
                            "affects": {"self_only": True},
                            "from_colors": ["W"],
                            "spares": "self",
                        }
                    )
                )
            )

    def test_spares_is_refused_off_protection(self):
        with pytest.raises(DslError, match="spares"):
            compile_card(
                CardModel.model_validate(
                    static_probe(
                        {
                            "effect": "buff",
                            "affects": {"attached": True},
                            "power": {"const": 1},
                            "toughness": {"const": 1},
                            "spares": "self",
                        }
                    )
                )
            )

    def test_a_granted_copy_is_refused(self):
        """A granted static's source is its recipient, which has chosen
        nothing -- the author's "the chosen color" would read the wrong
        permanent and protect from nothing."""
        spec = {
            "id": "t_pcc_granter",
            "name": "Granter",
            "mana_cost": "{2}{W}",
            "types": ["Enchantment"],
            "grantable_abilities": [
                {
                    "kind": "static",
                    "text": "This creature has protection from the chosen color.",
                    "effect": "protection",
                    "affects": {"self_only": True},
                    "from_colors": [CHOSEN],
                }
            ],
            "abilities": [
                {
                    "kind": "static",
                    "text": 'Creatures you control have "..."',
                    "effect": "grant_ability",
                    "affects": {"types": ["Creature"], "controller": "you"},
                    "ability": 0,
                }
            ],
        }
        with pytest.raises(DslError, match="chosen_color_of"):
            compile_card(CardModel.model_validate(spec))

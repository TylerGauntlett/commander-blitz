"""Protection, which is four rules wearing one name.

Damage, Enchant/equip, Block, Target — and a card that implements one of the
four looks exactly like a card that implements all of them right up until the
moment it matters. So each of the four gets its own assertion here, and each is
paired with the negative case: a source *without* the quality must still get
through, or "protection from Wizards" has quietly become "protection".

The other trap is hexproof-shaped thinking. Hexproof stops opponents; protection
stops **everyone**, including the controller. A card that reuses the hexproof
check would let you target your own protected creature, which is wrong.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import protected_from, protection_from
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid


def a_wizard(registry) -> str:
    """Any non-token Wizard in the pool, so the fixture is not a fixed id."""
    return next(
        (
            c.id
            for c in sorted(registry, key=lambda c: c.id)
            if c.is_creature and not c.is_token and "Wizard" in c.subtypes
        ),
        "",
    )


class TestWhatItProtectsFrom:
    def test_it_reads_both_halves_of_the_printed_line(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + ["greensleeves_maro_sorcerer"])
            .build()
        )
        greensleeves = only_oid(game, "greensleeves_maro_sorcerer")
        assert protection_from(game.state, greensleeves) == frozenset(
            {"Planeswalker", "Wizard"}
        )

    def test_a_wizard_is_a_source_it_is_protected_from(self, registry, builder):
        wizard_id = a_wizard(registry)
        if not wizard_id:
            pytest.skip("no Wizard in the pool")
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + ["greensleeves_maro_sorcerer"])
            .battlefield(1, [wizard_id, "grizzly_bears"])
            .build()
        )
        greensleeves = only_oid(game, "greensleeves_maro_sorcerer")
        wizard = only_oid(game, wizard_id, 1)
        bear = only_oid(game, "grizzly_bears", 1)

        assert protected_from(game.state, greensleeves, wizard)
        assert not protected_from(game.state, greensleeves, bear), "a Bear is not a Wizard"

    def test_no_source_is_never_protection(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + ["greensleeves_maro_sorcerer"])
            .build()
        )
        greensleeves = only_oid(game, "greensleeves_maro_sorcerer")
        assert not protected_from(game.state, greensleeves, None)


class TestGreensleevesIsAlsoStarStar:
    def test_with_no_lands_it_is_a_zero_over_zero_and_dies(self, builder):
        """Not a bug to work around in the other tests -- it is the card.

        Every board here has to carry lands for the same reason a real one does.
        """
        from tests.conftest import pass_until

        game = builder(players=2).battlefield(0, ["greensleeves_maro_sorcerer"]).build()
        pass_until(game, lambda g: not g.state.stack)
        assert not [
            o
            for o in game.state.battlefield_objects(0)
            if o.def_id == "greensleeves_maro_sorcerer"
        ]


class TestTheFourRules:
    """One assertion per rule, each with its negative case."""

    def board(self, builder, registry):
        wizard_id = a_wizard(registry)
        if not wizard_id:
            pytest.skip("no Wizard in the pool")
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + ["greensleeves_maro_sorcerer"])
            .battlefield(1, [wizard_id, "grizzly_bears"])
            .build()
        )
        return (
            game,
            only_oid(game, "greensleeves_maro_sorcerer"),
            only_oid(game, wizard_id, 1),
            only_oid(game, "grizzly_bears", 1),
        )

    def test_damage_from_it_is_prevented(self, registry, builder):
        from commanderblitz.engine.primitives import damage_permanent

        game, greensleeves, wizard, bear = self.board(builder, registry)
        assert damage_permanent(game.state, greensleeves, 3, wizard) == 0
        assert game.state.objects[greensleeves].damage == 0

        assert damage_permanent(game.state, greensleeves, 3, bear) == 3
        assert game.state.objects[greensleeves].damage == 3

    def test_it_cannot_be_targeted_by_it(self, registry, builder):
        from commanderblitz.engine.targeting import can_be_targeted

        game, greensleeves, wizard, bear = self.board(builder, registry)
        assert not can_be_targeted(game.state, 1, greensleeves, source_oid=wizard)
        assert can_be_targeted(game.state, 1, greensleeves, source_oid=bear)

    def test_protection_stops_its_own_controller_too(self, registry, builder):
        """The half a hexproof-shaped implementation would get wrong."""
        from commanderblitz.engine.targeting import can_be_targeted

        game, greensleeves, wizard, _ = self.board(builder, registry)
        assert not can_be_targeted(game.state, 0, greensleeves, source_oid=wizard)

    def test_it_cannot_be_blocked_by_it(self, registry, builder):
        from commanderblitz.engine.combat import can_block
        from commanderblitz.engine.structs import CombatState

        game, greensleeves, wizard, bear = self.board(builder, registry)
        game.state.combat = CombatState()
        game.state.combat.attackers[greensleeves] = 1
        for oid in (wizard, bear):
            game.state.objects[oid].tapped = False
        game.state.bump_chars()

        assert not can_block(game.state, wizard, greensleeves, 1)
        assert can_block(game.state, bear, greensleeves, 1)

    def test_it_cannot_be_enchanted_by_it(self, registry, builder):
        from commanderblitz.engine.primitives import attach

        game, greensleeves, wizard, bear = self.board(builder, registry)
        assert not attach(game.state, wizard, greensleeves)
        assert game.state.objects[wizard].attached_to is None

        assert attach(game.state, bear, greensleeves)


class TestTheStaticIsChecked:
    base = {
        "id": "probe",
        "name": "Probe",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
    }

    def _with(self, static: dict):
        return CardModel.model_validate({**self.base, "abilities": [static]})

    def test_protection_from_nothing_is_rejected(self):
        """It would load, look implemented, and protect from nothing."""
        model = self._with(
            {"kind": "static", "effect": "protection", "affects": {"self_only": True}}
        )
        with pytest.raises(DslError, match="protection needs"):
            compile_card(model)

    def test_an_unknown_type_is_rejected(self):
        model = self._with(
            {
                "kind": "static",
                "effect": "protection",
                "affects": {"self_only": True},
                "from_types": ["Spaceship"],
            }
        )
        with pytest.raises(DslError, match="unknown type"):
            compile_card(model)

    def test_the_qualities_need_the_protection_effect(self):
        model = self._with(
            {
                "kind": "static",
                "effect": "grant_keyword",
                "affects": {"self_only": True},
                "keywords": ["flying"],
                "from_subtypes": ["Wizard"],
            }
        )
        with pytest.raises(DslError, match="need effect 'protection'"):
            compile_card(model)

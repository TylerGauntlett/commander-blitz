"""Mana that may only pay for some things, and abilities lent to other cards.

Both halves of Herd Heirloom.

**Restricted mana** is enforced by *filtering sources* before the solver ever
sees them, not by tagging the pool. That works only because mana here is tapped
at the moment it is spent — so the question "may this source pay for this
spell?" has an answer at exactly the point it is asked, and the solver's inner
loop never learns restrictions exist. The risk is that legality and payment ask
that question differently; both go through `spell_purpose`, and the last test in
the first class is what would catch them drifting.

**A granted ability** lives on the card that grants it and is pointed at by the
permanent that received it, so there is one definition rather than a copy. The
trap is whose ability it becomes: "whenever **this creature** deals combat
damage" has to mean the creature, not the artifact.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.costs import available_mana, mana_sources, spell_purpose
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from tests.conftest import only_oid, pass_until


class TestRestrictedMana:
    def board(self, builder, hand: list[str], forests: int = 1):
        return (
            builder(players=2)
            .battlefield(0, ["forest"] * forests + ["herd_heirloom"])
            .hand(0, hand)
            .library(0, ["island"] * 20)
            .build()
        )

    def test_it_is_offered_for_a_creature(self, registry, builder):
        game = self.board(builder, [])
        card = registry.get("grizzly_bears")
        sources = mana_sources(game.state, 0, purpose=spell_purpose(card))
        assert any(s.oid == only_oid(game, "herd_heirloom") for s in sources)

    def test_it_is_withheld_from_anything_else(self, registry, builder):
        game = self.board(builder, [])
        card = registry.get("counterspell")
        sources = mana_sources(game.state, 0, purpose=spell_purpose(card))
        assert not any(s.oid == only_oid(game, "herd_heirloom") for s in sources)

    def test_with_no_spell_in_mind_it_is_not_counted(self, builder):
        """An under-count, which is the safe direction for a number the AI reads."""
        game = self.board(builder, [], forests=1)
        assert available_mana(game.state, 0) == 1, "the Forest only"

    def test_a_creature_can_be_cast_off_it(self, builder):
        """One Forest and the Heirloom: two mana, and Bears costs {1}{G}."""
        game = self.board(builder, ["grizzly_bears"])
        cast = next(
            (
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == "grizzly_bears"
            ),
            None,
        )
        assert cast is not None

    def test_a_noncreature_cannot(self, registry, builder):
        """Divination is {2}{U} -- but the point is it is not offered at all."""
        if "divination" not in registry:
            pytest.skip("no cheap noncreature spell in the pool")
        game = (
            builder(players=2)
            .battlefield(0, ["island", "island", "herd_heirloom"])
            .hand(0, ["divination"])
            .build()
        )
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "divination"
        ], "{2}{U} off two Islands and restricted mana is not payable"

    def test_legality_and_payment_agree(self, builder):
        """The drift test: what was offered must go through.

        A cast that legality allowed on restricted mana and payment then refused
        would strand the spell halfway, so this one actually applies the action.
        """
        game = self.board(builder, ["grizzly_bears"])
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "grizzly_bears"
        )
        game.apply(cast)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert [o for o in game.state.battlefield_objects(0) if o.def_id == "grizzly_bears"]


class TestGrantedAbilities:
    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["forest", "herd_heirloom", "terastodon"])
            .library(0, ["island"] * 20)
            .build()
        )

    def grant(self, game):
        heirloom = only_oid(game, "herd_heirloom")
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == heirloom
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        return only_oid(game, "terastodon")

    def test_the_keyword_half_lands(self, builder):
        from automtg.engine.characteristics import chars

        game = self.board(builder)
        beast = self.grant(game)
        assert "trample" in chars(game.state, beast).keywords

    def test_the_ability_half_is_recorded_against_the_creature(self, builder):
        from automtg.engine.primitives import granted_abilities

        game = self.board(builder)
        beast = self.grant(game)
        granted = list(granted_abilities(game.state, beast))
        assert len(granted) == 1
        granter, ability = granted[0]
        assert granter.def_id == "herd_heirloom", "the definition stays on the granter"
        assert ability.is_triggered

    def test_the_granted_trigger_fires_for_the_creature(self, builder):
        """'Whenever *this creature* deals combat damage' -- the creature's.

        Nothing about the artifact deals combat damage, so a version that kept
        the artifact as the trigger's source would simply never fire.
        """
        from automtg.engine.events import EventType
        from automtg.engine.triggers import fire

        game = self.board(builder)
        beast = self.grant(game)
        before = len(game.state.players[0].hand)

        fire(
            game.state,
            EventType.COMBAT_DAMAGE_TO_PLAYER,
            player=0,
            source=beast,
            oid=beast,
            amount=9,
        )
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert len(game.state.players[0].hand) == before + 1

    def test_it_wears_off_at_end_of_turn(self, builder):
        from automtg.engine.primitives import granted_abilities

        game = self.board(builder)
        beast = self.grant(game)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        assert not list(granted_abilities(game.state, beast))

    def test_a_weak_creature_is_not_a_legal_target(self, builder):
        """'target creature you control with power 4 or greater'."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest", "herd_heirloom", "grizzly_bears"])
            .build()
        )
        heirloom = only_oid(game, "herd_heirloom")
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == heirloom
        ], "a 2/2 is not power 4 or greater"


class TestWhatCanBeGranted:
    base = {"id": "probe", "name": "Probe", "types": ["Artifact"]}

    @pytest.mark.parametrize(
        "ability",
        [
            {
                "kind": "static",
                "effect": "grant_keyword",
                "affects": {"self_only": True},
                "keywords": ["flying"],
            },
            {
                "kind": "activated",
                "cost": {"tap": True},
                "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            },
        ],
    )
    def test_only_triggered_abilities_may_be_granted(self, ability):
        """The others would be accepted and then never appear.

        A granted static has no place in the fixed-order characteristics
        pipeline, and a granted activated ability would need `Action` to carry
        where it came from before legality could offer it.
        """
        model = CardModel.model_validate({**self.base, "grantable_abilities": [ability]})
        with pytest.raises(DslError, match="only triggered abilities can be granted"):
            compile_card(model)

class TestASubtypeRestriction:
    """Master of Dark Rites — "…only to cast Vampire, Cleric, and/or Demon spells".

    The restriction was one lowercased *card type*, checked against the eight
    known ones, and the purpose a spell presented was built from `card.types`
    alone — so a subtype had no representation at either end. Leaving the clause
    off would have produced unrestricted {B}{B}{B}, which is a strictly better
    card than the printed one.

    Both ends widened to the same flat set of lowercased names, intersected. The
    printed "and/or" is an any-of, so one matching subtype is enough.
    """

    def card(self, restriction):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "t_tribal_mana",
                    "name": "Tribal Mana",
                    "mana_cost": "{2}",
                    "types": ["Artifact"],
                    "oracle_text": "{T}: Add {B}. Spend this mana only to cast Vampire spells.",
                    "abilities": [
                        {
                            "kind": "activated",
                            "text": "{T}: Add {B}. Spend this mana only to cast Vampire spells.",
                            "is_mana_ability": True,
                            "mana_restriction": restriction,
                            "cost": {"tap": True},
                            "effects": [{"op": "add_mana", "mana": "{B}"}],
                        }
                    ],
                }
            )
        )

    def test_a_list_of_subtypes_compiles(self):
        """Three one-name groups: "and/or" is an any-of, so any group matching wins."""
        card = self.card(["Vampire", "Cleric", "Demon"])
        assert set(card.abilities[0].mana_restriction.cast) == {
            frozenset({"vampire"}),
            frozenset({"cleric"}),
            frozenset({"demon"}),
        }

    def test_a_bare_string_still_works(self):
        """The old single-type form is unchanged."""
        card = self.card("creature")
        assert card.abilities[0].mana_restriction.cast == (frozenset({"creature"}),)

    def test_the_bare_form_permits_no_activation(self):
        """"Spend this mana only to **cast** a Vampire spell" -- and nothing else.

        The half that would otherwise be handed out for free the moment
        restricted mana learned to pay for abilities at all.
        """
        card = self.card(["Vampire"])
        assert card.abilities[0].mana_restriction.activate == ()

    def test_an_empty_list_is_refused(self):
        with pytest.raises(DslError, match="empty"):
            self.card([])

    def test_a_purpose_reads_subtypes(self, registry):
        """Grizzly Bears is a Bear, and the set says so."""
        assert "bear" in spell_purpose(registry.get("grizzly_bears")).names
        assert "creature" in spell_purpose(registry.get("grizzly_bears")).names

    def test_one_matching_subtype_is_enough(self, registry, builder):
        """"and/or" is an any-of: a Vampire that is not a Cleric still qualifies."""
        card = registry.get("vampire_of_the_dire_moon")
        restriction = frozenset({"vampire", "cleric", "demon"})
        assert restriction & spell_purpose(card).names

    def test_an_unrelated_creature_does_not_qualify(self, registry):
        restriction = frozenset({"vampire", "cleric", "demon"})
        assert not (restriction & spell_purpose(registry.get("grizzly_bears")).names)


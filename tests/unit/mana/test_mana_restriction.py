"""Mana whose spend restriction names the type its source chose, and reaches abilities.

Secluded Courtyard — "As this land enters, choose a creature type. … {T}: Add one
mana of any color. Spend this mana only to cast a creature spell of the chosen
type **or activate an ability of a creature source of the chosen type**." Cavern
of Souls and Unclaimed Territory are the same line.

Two things were missing, and each one alone makes a different card:

**The restriction could not name the chosen type.** `mana_restriction` was a list
of literal words frozen at load time, so every value that would load is a card
nobody printed: `"creature"` casts *any* creature, which is strictly better than
Secluded Courtyard, and a hardcoded subtype ignores the choice the land makes on
entry. The type is now the same `{"chosen_type_of": "self"}` leaf `subtypes`
filters already take (Vanquisher's Banner, Door of Destinies), substituted per
permanent by `costs.resolve_mana_restriction` at the moment the mana is offered.

**Restricted mana could only ever pay for spells.** `purpose` was
`spell_purpose(card)` and was passed at the four cast sites only, so every
`mana_sources` call funding an activation dropped restricted sources outright
(rule 602.1b: activating an ability is not casting a spell, and the printed line
names both). `costs.ability_purpose` is the second half, threaded through
`legality._ability_aims` and `game._activate`.

The trap the two halves make together is what most of this file is about: an
`ACTIVATE` permission handed out by *name* alone would have silently upgraded
Herd Heirloom, Ancient Ziggurat and Master of Dark Rites, all three of which
print "only to **cast**". `SpendPurpose` carries the kind for exactly that
reason, and `TestCastOnlyRestrictionsStayCastOnly` is the witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.costs import ability_purpose, mana_sources, spell_purpose
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import ACTIVATE, CAST, ManaRestriction, ManaSource, SpendPurpose
from tests.conftest import only_oid, pass_until

COURTYARD = "secluded_courtyard"
#: "{B}: This creature gains deathtouch until end of turn." A **Human Warrior**,
#: so it is a creature source of a type the Courtyard can choose and of two it
#: cannot -- and the cost is a coloured pip, which the land's *other* mana
#: ability ("{T}: Add {C}") can never pay. That is what keeps every assertion
#: below about the restriction rather than about the colourless line.
BLADE = "mardu_hateblade"
#: {B}, and a Vampire: the cast half's witness.
VAMPIRE = "vampire_of_the_dire_moon"


class _Board:
    """A board with ``lands`` restricted lands, the Hateblade, and a chosen type.

    The type is written **before** ``build()``, not after: ``build`` runs the
    engine's auto-pass, and a Courtyard that has chosen nothing offers nothing,
    so the position would roll past the main phase before a test could look at
    it.
    """

    def __init__(self, builder):
        self.builder = builder

    def make(self, chosen: str | None, *, land: str = COURTYARD, lands: int = 1, hand=()):
        b = (
            self.builder(players=2)
            .battlefield(0, [land] * lands + [BLADE])
            .hand(0, list(hand))
            .library(0, ["island"] * 20)
        )
        for oid in list(b.state.battlefield):
            if b.state.objects[oid].def_id == land:
                b.state.objects[oid].chosen_type = chosen
        b.state.bump_chars()
        game = b.build()
        return game, only_oid(game, BLADE)


@pytest.fixture
def board(builder):
    return _Board(builder)


def activation(game, oid: int):
    return next(
        (a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid),
        None,
    )


def cast_of(game, card_id: str):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        ),
        None,
    )


class TestTheRestrictionIsTheTypeThatWasChosen:
    """The whole point: one land, and which spell it pays for is a board fact."""

    def test_it_casts_a_creature_spell_of_the_chosen_type(self, board):
        game, _ = board.make("Vampire", hand=[VAMPIRE])
        assert cast_of(game, VAMPIRE) is not None

    def test_it_refuses_a_creature_of_another_type(self, board):
        """The same land, the same spell, one different word on the permanent."""
        game, _ = board.make("Bear", hand=[VAMPIRE])
        assert cast_of(game, VAMPIRE) is None, "{B} off a Bear-restricted land"

    def test_before_a_type_is_chosen_it_pays_for_nothing(self, board):
        """A group naming the chosen type is dropped, not widened.

        The alternative -- treating "no choice yet" as "no restriction" -- is a
        five-colour land that casts anything, which is the one direction this
        must never fail in. Reachable in a real game: the choice is a
        `self_enters` trigger, so the land is on the battlefield for a moment
        before it resolves.
        """
        game, _ = board.make(None, hand=[VAMPIRE])
        assert cast_of(game, VAMPIRE) is None

    def test_the_colourless_line_is_still_unrestricted(self, board, registry):
        """"{T}: Add {C}" carries no restriction and must keep offering itself."""
        game, _ = board.make(None)
        courtyard = only_oid(game, COURTYARD)
        offered = [s for s in mana_sources(game.state, 0) if s.oid == courtyard]
        assert len(offered) == 1, "the {C} ability, and only it, with no purpose in mind"
        assert offered[0].restriction is None


class TestRestrictedManaReachesAbilityCosts:
    """"…or activate an ability of a creature source of the chosen type."

    Unreachable before this: every `mana_sources` call funding an activation
    passed no purpose, and a source with a restriction is dropped when the
    purpose is `None`.
    """

    def test_it_pays_for_an_ability_of_a_source_of_the_chosen_type(self, board):
        game, blade = board.make("Warrior")
        assert activation(game, blade) is not None

    def test_it_refuses_an_ability_of_a_source_of_another_type(self, board):
        game, blade = board.make("Vampire")
        assert activation(game, blade) is None, "a Human Warrior is not a Vampire source"

    def test_before_a_type_is_chosen_no_ability_is_funded(self, board):
        game, blade = board.make(None)
        assert activation(game, blade) is None

    def test_legality_and_payment_agree(self, board):
        """The drift test, on the new path.

        An activation legality allowed on restricted mana and payment then
        refused would strand the ability halfway, so this one actually applies
        the action and reads the board afterwards.
        """
        game, blade = board.make("Warrior")
        game.apply(activation(game, blade))
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert "deathtouch" in chars(game.state, blade).keywords
        assert game.state.objects[only_oid(game, COURTYARD)].tapped, "the land really paid"


class TestCastOnlyRestrictionsStayCastOnly:
    """Herd Heirloom, Ancient Ziggurat, Master of Dark Rites — "only to **cast**".

    Three shipped cards that say nothing about activating abilities. Handing the
    activate permission out by name alone would have rewritten all three without
    a line of their JSON changing, which is the failure this whole distinction
    exists to prevent.
    """

    def test_a_cast_only_source_does_not_fund_an_ability(self, board):
        game, blade = board.make("Warrior", land="herd_heirloom")
        assert activation(game, blade) is None

    def test_it_still_casts_what_it_always_did(self, board):
        game, _ = board.make("Warrior", land="herd_heirloom", hand=[VAMPIRE])
        assert cast_of(game, VAMPIRE) is not None

    @pytest.mark.parametrize("card_id", ["herd_heirloom", "master_of_dark_rites"])
    def test_the_compiled_form_permits_nothing_to_activate(self, registry, card_id):
        restricted = [
            a for a in registry.get(card_id).abilities if a.mana_restriction is not None
        ]
        assert restricted, f"{card_id} is a restricted-mana card"
        assert all(a.mana_restriction.activate == () for a in restricted)
        assert all(a.mana_restriction.cast for a in restricted)


class TestTheGroupIsAnAllOf:
    """"a **creature** spell **of the chosen type**" is a conjunction.

    Read as one flat any-of -- which is what the printed "Vampire, Cleric,
    and/or Demon" means and what the old representation could only express --
    the `creature` half alone would offer the mana for every creature ever
    printed.
    """

    def source(self, **groups):
        return ManaSource(oid=1, ability_index=0, options=((0, 0, 0, 0, 0, 1),), **groups)

    def test_both_names_together_are_permitted(self):
        s = self.source(restriction=ManaRestriction(cast=(frozenset({"creature", "bear"}),)))
        assert s.permits(SpendPurpose(CAST, frozenset({"creature", "bear"})))

    def test_the_type_alone_is_not_enough(self):
        """A hypothetical Bear that is not a creature -- a Kindred instant."""
        s = self.source(restriction=ManaRestriction(cast=(frozenset({"creature", "bear"}),)))
        assert not s.permits(SpendPurpose(CAST, frozenset({"instant", "bear"})))

    def test_creature_alone_is_not_enough(self):
        s = self.source(restriction=ManaRestriction(cast=(frozenset({"creature", "bear"}),)))
        assert not s.permits(SpendPurpose(CAST, frozenset({"creature", "vampire"})))

    def test_separate_groups_are_still_an_any_of(self):
        """Master of Dark Rites' "and/or" is unchanged: one group matching wins."""
        s = self.source(
            restriction=ManaRestriction(
                cast=(frozenset({"vampire"}), frozenset({"cleric"}), frozenset({"demon"}))
            )
        )
        assert s.permits(SpendPurpose(CAST, frozenset({"creature", "cleric"})))

    def test_a_kind_it_does_not_permit_is_refused(self):
        s = self.source(restriction=ManaRestriction(cast=(frozenset({"creature"}),)))
        assert not s.permits(SpendPurpose(ACTIVATE, frozenset({"creature"})))

    def test_no_purpose_at_all_withholds_it(self):
        """An under-count, which is the safe direction for a number the AI reads."""
        s = self.source(restriction=ManaRestriction(cast=(frozenset({"creature"}),)))
        assert not s.permits(None)


class TestThePurposesSayWhichAction:
    def test_a_spell_purpose_is_a_cast(self, registry):
        assert spell_purpose(registry.get(VAMPIRE)).kind == CAST

    def test_an_ability_purpose_is_an_activation(self, board):
        game, blade = board.make("Warrior")
        assert ability_purpose(game.state, blade).kind == ACTIVATE

    def test_an_ability_purpose_reads_current_characteristics(self, board):
        """`chars`, not the printed face: an animated land really is a creature."""
        game, blade = board.make("Warrior")
        assert ability_purpose(game.state, blade).names >= {"creature", "human", "warrior"}


class TestWhatTheLoaderAccepts:
    base = {
        "id": "t_chosen_mana",
        "name": "Chosen Mana",
        "mana_cost": "{2}",
        "types": ["Artifact"],
    }

    def card(self, restriction):
        return compile_card(
            CardModel.model_validate(
                {
                    **self.base,
                    "abilities": [
                        {
                            "kind": "activated",
                            "text": "{T}: Add {B}.",
                            "is_mana_ability": True,
                            "mana_restriction": restriction,
                            "cost": {"tap": True},
                            "effects": [{"op": "add_mana", "mana": "{B}"}],
                        }
                    ],
                }
            )
        )

    def test_the_two_halves_compile_apart(self):
        card = self.card(
            {
                "cast": [["creature", {"chosen_type_of": "self"}]],
                "activate": [["creature", {"chosen_type_of": "self"}]],
            }
        )
        restriction = card.abilities[0].mana_restriction
        assert restriction.dynamic
        assert len(restriction.cast) == 1 and len(restriction.activate) == 1

    def test_a_half_may_be_omitted(self):
        card = self.card({"cast": ["creature"]})
        assert card.abilities[0].mana_restriction.activate == ()

    def test_an_unknown_half_is_refused(self):
        """Mana is spent to cast or to activate, and there is no third thing."""
        with pytest.raises(DslError, match="cast"):
            self.card({"play": ["land"]})

    def test_an_object_permitting_nothing_is_refused(self):
        with pytest.raises(DslError, match="permits nothing"):
            self.card({})

    def test_a_near_miss_dynamic_leaf_is_refused(self):
        """It would otherwise freeze into a literal name no card has.

        Mana that can never be spent is the safe direction but a silent one, and
        this is the one leaf whose spelling cannot be checked against the board.
        """
        with pytest.raises(DslError, match="chosen_type_of"):
            self.card([[{"chosen_type_of": "that_creature"}]])

    def test_the_shipped_card_names_both_halves(self, registry):
        restriction = registry.get(COURTYARD).abilities[2].mana_restriction
        assert restriction.cast and restriction.activate
        assert restriction.dynamic, "the chosen type is substituted per permanent"

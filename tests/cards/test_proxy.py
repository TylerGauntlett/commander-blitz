"""Generating a card definition for something nobody hand-wrote.

Every case here asserts three things, and the third is the one that matters:
the coverage verdict, the notes, and that ``compile_card`` **accepts the result**.
A generated card that does not compile is not a degraded card, it is a
``DslError`` propagating out of ``CardRegistry.from_paths`` and taking the whole
registry down at boot -- so "it compiles" is the property this file exists to
defend.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.proxy import (
    CardFacts,
    build_proxy,
    lift_keywords,
    simplify_mana_cost,
    slug_for,
    split_type_line,
)


def facts(**kwargs) -> CardFacts:
    base = {"name": "Test Card", "scryfall_id": "abcdef01-2345-6789-abcd-ef0123456789"}
    return CardFacts(**{**base, **kwargs})


def built(**kwargs):
    """``(result, compiled)`` -- compiling is not optional, so it happens here."""
    result = build_proxy(facts(**kwargs))
    assert result.error is None, result.error
    return result, compile_card(result.model)


# ----------------------------------------------------------------------
# ids
# ----------------------------------------------------------------------


class TestTheId:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Sol Ring", "sol_ring"),
            ("Aesi, Tyrant of Gyre Strait", "aesi_tyrant_of_gyre_strait"),
            # Diacritics fold rather than being dropped as punctuation, or
            # "Lim-Dul's Vault" and "Lim-Dûl's Vault" become different cards.
            ("Lim-Dûl's Vault", "lim_dul_s_vault"),
            ("Æther Vial", "aether_vial"),
            ("Ratchet, Field Medic", "ratchet_field_medic"),
            ("Fire // Ice", "fire_ice"),
            ("+2 Mace", "2_mace"),
        ],
    )
    def test_folds_a_name_to_the_art_path_charset(self, name, expected):
        # `server/art.py`'s CARD_ID is the tighter of the two guards *and* the
        # path-traversal guard, because the id becomes a filename.
        slug = slug_for(name)
        assert slug == expected
        assert all(c.islower() or c.isdigit() or c == "_" for c in slug)

    def test_a_name_that_is_all_punctuation_still_gets_an_id(self):
        assert slug_for("!?!", "deadbeef-0000-0000-0000-000000000000") == "card_deadbeef"

    def test_a_collision_resolves_on_the_scryfall_id_not_a_counter(self):
        # A counter would make the id depend on the order cards happened to be
        # imported in.  These ids are art filenames and deck-list keys; they
        # have to survive a re-import unchanged.
        first = slug_for("Forest", "11111111-0000-0000-0000-000000000000", taken=set())
        second = slug_for("Forest", "22222222-0000-0000-0000-000000000000", taken={"forest"})
        assert first == "forest"
        assert second == "forest_222222"
        # Stable: asking again gives the same answer.
        assert slug_for("Forest", "22222222-0000-0000-0000-000000000000", taken={"forest"}) == second

    def test_a_very_long_name_truncates_on_a_word_boundary(self):
        slug = slug_for("Rem Karolus Stalwart Slayer " * 6)
        assert len(slug) <= 72
        assert not slug.endswith("_")


# ----------------------------------------------------------------------
# type line
# ----------------------------------------------------------------------


class TestTheTypeLine:
    @pytest.mark.parametrize("dash", ["—", "–", " - "])  # noqa: RUF001
    def test_accepts_every_dash_a_type_line_is_printed_with(self, dash):
        # Scryfall prints an em-dash, `build_type_line` emits ASCII, older data
        # uses an en-dash.  Get this wrong and every subtype becomes a type.
        supertypes, types, subtypes, _ = split_type_line(f"Legendary Creature{dash}Human Wizard")
        assert supertypes == ["Legendary"]
        assert types == ["Creature"]
        assert subtypes == ["Human", "Wizard"]

    def test_subtypes_need_no_whitelist(self):
        # `compile_card` validates types, supertypes and keywords only, so there
        # is deliberately no list of subtypes to keep up to date.
        _, _, subtypes, _ = split_type_line("Creature — Praetor Phyrexian Horror")
        assert subtypes == ["Praetor", "Phyrexian", "Horror"]

    def test_a_split_card_takes_its_front_half(self):
        _, types, _, _ = split_type_line("Instant // Sorcery")
        assert types == ["Instant"]


# ----------------------------------------------------------------------
# the cards that come out whole
# ----------------------------------------------------------------------


class TestCardsThatSurviveIntact:
    """`full` is a promise that nothing was lost, so it has to be earned."""

    def test_a_vanilla_creature(self):
        result, card = built(
            name="Grizzly Bears",
            type_line="Creature — Bear",
            mana_cost="{1}{G}",
            power="2",
            toughness="2",
            colors="G",
            color_identity="G",
        )
        assert result.coverage == "full"
        assert result.notes == ()
        assert (card.power, card.toughness) == (2, 2)
        assert card.mana_value == 2

    def test_a_french_vanilla_creature_keeps_its_keywords(self):
        result, card = built(
            name="Serra Angel",
            type_line="Creature — Angel",
            mana_cost="{3}{W}{W}",
            oracle_text="Flying, vigilance",
            keywords=("Flying", "Vigilance"),
            power="4",
            toughness="4",
            colors="W",
            color_identity="W",
        )
        assert result.coverage == "full"
        assert sorted(card.keywords) == ["flying", "vigilance"]

    def test_a_basic_land_taps_for_its_colour(self):
        result, card = built(
            name="Forest",
            type_line="Basic Land — Forest",
            oracle_text="({T}: Add {G}.)",
            produced_mana=("G",),
            color_identity="G",
        )
        assert result.coverage == "full"
        assert card.is_basic
        # The whole point: a land with no mana ability makes the deck unplayable.
        assert any(a.is_mana_ability for a in card.abilities)

    def test_a_dual_land_offers_both_colours_without_asking(self):
        _, card = built(
            name="Temple Garden",
            type_line="Land — Forest Plains",
            oracle_text="({T}: Add {G} or {W}.)\nAs this land enters, you may pay 2 life. "
            "If you don't, it enters tapped.",
            produced_mana=("G", "W"),
            color_identity="GW",
        )
        ability = next(a for a in card.abilities if a.is_mana_ability)
        # Flattened into solver options, so the payment solver picks the colour
        # rather than stopping the game to ask.
        assert len(ability.mana_options) == 2

    def test_a_simple_mana_rock(self):
        result, card = built(
            name="Chromatic Lantern Test",
            type_line="Artifact",
            mana_cost="{3}",
            oracle_text="{T}: Add one mana of any color.",
            produced_mana=("W", "U", "B", "R", "G"),
            color_identity="",
        )
        assert result.coverage == "full"
        assert card.color_identity == frozenset()

    def test_a_rock_whose_any_colour_clause_has_a_condition_is_partial(self):
        """Arcane Signet makes a colour *in your commander's identity*.

        The generated version makes any of five regardless, which is more
        permissive than the printed card -- so it is reported as simplified
        rather than claimed as complete.
        """
        result, _ = built(
            name="Arcane Signet",
            type_line="Artifact",
            mana_cost="{2}",
            oracle_text="{T}: Add one mana of any color in your commander's color identity.",
            produced_mana=("W", "U", "B", "R", "G"),
            color_identity="",
        )
        assert result.coverage == "partial"


class TestTheReflectedColourClause:
    """"…any color that a land an opponent controls could produce."

    Read exactly or not at all. The any-colour fallback below this in
    `_mana_effects` would turn the sentence into five fixed modes, and a Fellwar
    Stone that taps for colours no opponent has a land for is a strictly better
    card than the printed one.
    """

    def stone(self, oracle_text: str, **kwargs):
        return built(
            name="Fellwar Stone",
            type_line="Artifact",
            mana_cost="{2}",
            oracle_text=oracle_text,
            produced_mana=("W", "U", "B", "R", "G"),
            color_identity="",
            **kwargs,
        )

    def reflecting_of(self, card):
        ability = next(a for a in card.abilities if a.is_mana_ability)
        return ability.mana_reflects

    def test_an_opponents_lands_become_a_selector(self):
        result, card = self.stone(
            "{T}: Add one mana of any color that a land an opponent controls could produce."
        )
        assert result.coverage == "full"
        assert result.notes == ()
        assert self.reflecting_of(card) == {
            "zone": "battlefield",
            "controller": "opponent",
            "types": ["Land"],
        }

    def test_it_is_not_five_fixed_modes(self):
        """The trap. Five modes is a different, better card."""
        _, card = self.stone(
            "{T}: Add one mana of any color that a land an opponent controls could produce."
        )
        ability = next(a for a in card.abilities if a.is_mana_ability)
        assert ability.mana_reflects is not None

    def test_the_you_control_half_of_the_family(self):
        """Harvester Druid — the same sentence pointed the other way."""
        result, card = built(
            name="Harvester Druid",
            type_line="Creature — Human Druid",
            mana_cost="{1}{G}",
            oracle_text="{T}: Add one mana of any color that a land you control could produce.",
            produced_mana=("W", "U", "B", "R", "G"),
            power="1",
            toughness="1",
            colors="G",
            color_identity="G",
        )
        assert result.coverage == "full"
        assert self.reflecting_of(card)["controller"] == "you"

    def test_any_type_is_refused(self):
        """Reflecting Pool prints "any **type**", which includes {C} -- and
        `reflecting` narrows a five-*colour* superset. Claiming this would ship
        a Reflecting Pool that cannot tap off a Wastes."""
        result, _ = built(
            name="Reflecting Pool",
            type_line="Land",
            oracle_text="{T}: Add one mana of any type that a land you control could produce.",
            produced_mana=("W", "U", "B", "R", "G"),
            color_identity="",
        )
        assert result.coverage == "partial"

    def test_a_qualified_noun_is_refused(self):
        """Star Compass reads "a **basic** land you control", and reading past
        the qualifier would let it tap off lands the printed card ignores."""
        result, _ = built(
            name="Star Compass",
            type_line="Artifact",
            mana_cost="{2}",
            oracle_text="This artifact enters tapped.\n{T}: Add one mana of any color "
            "that a basic land you control could produce.",
            produced_mana=("W", "U", "B", "R", "G"),
            color_identity="",
        )
        assert result.coverage == "partial"


# ----------------------------------------------------------------------
# colour identity
# ----------------------------------------------------------------------


class TestColourIdentityComesFromTheCatalog:
    def test_a_five_colour_mana_ability_does_not_widen_the_identity(self):
        """The trap that would break every import.

        `_derive_color_identity` widens identity to every colour a mana ability
        can produce.  Derived, a generated Command Tower has a WUBRG identity,
        and `validate_deck`'s subset check then throws it out of every deck in
        the game.  The catalog already knows the printed answer.
        """
        _, card = built(
            name="Command Tower",
            type_line="Land",
            oracle_text="{T}: Add one mana of any color in your commander's color identity.",
            produced_mana=("W", "U", "B", "R", "G"),
            color_identity="",
        )
        assert card.color_identity == frozenset()

    def test_an_off_colour_utility_land_keeps_its_printed_identity(self):
        _, card = built(
            name="Bloodstained Mire",
            type_line="Land",
            oracle_text="{T}, Pay 1 life, Sacrifice this land: Search your library for a Swamp "
            "or Mountain card, put it onto the battlefield, then shuffle.",
            color_identity="",
        )
        assert card.color_identity == frozenset()


# ----------------------------------------------------------------------
# keywords
# ----------------------------------------------------------------------


class TestKeywords:
    def test_a_granted_keyword_is_not_lifted(self):
        """Scryfall's `keywords` lists what a card grants, not only what it has.

        Lifting it blindly gives every lord the keyword it hands out -- a
        Serra's Blessing that itself has vigilance, an anthem that flies.
        """
        found, consumed = lift_keywords(
            "Creatures you control have vigilance.", ("Vigilance",)
        )
        assert found == []
        assert consumed == set()

    def test_a_bare_keyword_line_is_lifted(self):
        found, consumed = lift_keywords("Flying\nWhenever this creature attacks, draw a card.", ("Flying",))
        assert found == ["flying"]
        assert consumed == {"Flying"}

    def test_a_comma_separated_keyword_line_is_lifted_whole(self):
        found, _ = lift_keywords("Flying, first strike, lifelink", ("Flying", "First strike", "Lifelink"))
        assert found == ["flying", "first_strike", "lifelink"]

    def test_reminder_text_does_not_stop_a_keyword_line_being_recognised(self):
        found, _ = lift_keywords(
            "Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)",
            ("Deathtouch",),
        )
        assert found == ["deathtouch"]

    @pytest.mark.parametrize(
        "text", ["Ward {2}", "Protection from red", "Annihilator 2", "Cumulative upkeep {1}"]
    )
    def test_a_parameterised_keyword_falls_through_to_the_residual(self, text):
        # No special case needed: these are not in `Keyword`, so they simply do
        # not match, and the residual reports them as unimplemented.
        found, consumed = lift_keywords(text, ())
        assert found == []
        assert consumed == set()

    def test_an_unimplemented_keyword_is_reported_rather_than_dropped(self):
        result, card = built(
            name="Sword Coast Serpent",
            type_line="Creature — Serpent",
            mana_cost="{5}{U}",
            oracle_text="Flying\nWard {2}",
            keywords=("Flying", "Ward"),
            power="5",
            toughness="5",
            colors="U",
            color_identity="U",
        )
        assert "flying" in card.keywords
        assert result.coverage == "partial"
        assert any("Ward {2}" in n for n in result.notes)


# ----------------------------------------------------------------------
# mana costs the engine cannot parse
# ----------------------------------------------------------------------


class TestManaCostSimplification:
    """`ManaCost.parse` raises on some symbols, and the raise is not local.

    It travels out through `compile_card` and `CardRegistry.from_paths`, so one
    unparsable card in the generated pool would stop the whole registry loading
    at boot.  Rewriting here is what keeps the DSL's "unknown vocabulary is a
    load-time error" rule exactly as strict as it was.

    Ordinary hybrid is no longer among them: `{W/U}` and `{2/W}` are parsed and
    paid properly, so they are left exactly as printed.  Narrowing them to one
    half was always a loss of the card's real flexibility.
    """

    @pytest.mark.parametrize(
        ("printed", "identity", "expected"),
        [
            ("{W/U}", "WU", "{W/U}"),  # hybrid is kept
            ("{W/U}", "U", "{W/U}"),
            ("{2/W}", "W", "{2/W}"),
            # Phyrexian used to be narrowed to "{W}" here, on the argument that
            # life is not a mana payment. It is now parsed and paid properly, and
            # the narrowing was worse than a simplification: it deleted the "or 2
            # life" clause the card is played for.
            ("{W/P}", "W", "{W/P}"),
            ("{W/U/P}", "WU", "{W/U/P}"),
            ("{S}", "", "{1}"),
            ("{1}{G}", "G", "{1}{G}"),  # untouched
        ],
    )
    def test_rewrites_preserve_the_mana_value(self, printed, identity, expected):
        out, notes = simplify_mana_cost(printed, identity)
        assert out == expected
        assert bool(notes) is (out != printed)

    def test_a_hybrid_card_keeps_the_cost_it_was_printed_with(self):
        result, card = built(
            name="Boros Charm",
            type_line="Instant",
            mana_cost="{R/W}{R/W}",
            oracle_text="Choose one —",
            colors="RW",
            color_identity="RW",
        )
        assert card.mana_value == 2
        assert result.coverage == "partial"
        assert not [n for n in result.notes if "mana cost simplified" in n]
        assert {c for c in card.colors} == {"R", "W"}

    def test_a_phyrexian_card_compiles(self):
        _, card = built(
            name="Gitaxian Probe",
            type_line="Sorcery",
            mana_cost="{U/P}",
            oracle_text="Look at target player's hand.\nDraw a card.",
            colors="U",
            color_identity="U",
        )
        assert card.mana_value == 1


# ----------------------------------------------------------------------
# lands
# ----------------------------------------------------------------------


class TestLands:
    def test_a_tapland_enters_tapped(self):
        result, card = built(
            name="Jungle Hollow",
            type_line="Land",
            oracle_text="This land enters tapped.\n{T}: Add {B} or {G}.\n"
            "When this land enters, you gain 1 life.",
            produced_mana=("B", "G"),
            color_identity="BG",
        )
        assert any(r["event"] == "self_enters_tapped" for r in card.replacements)
        # The lifegain is not implemented and the card says so.
        assert any("gain 1 life" in n for n in result.notes)

    def test_a_conditional_tapland_carries_its_printed_condition(self):
        """The condition is read, so the card is the one in the deck list.

        A checkland generated as always-tapped is the worst dual in the format
        wearing the right name; the whole reason it is played is that it is
        usually untapped. `ReplacementModel.condition` is the negation of the
        printed sentence -- when it holds, the land enters tapped.
        """
        result, card = built(
            name="Sunpetal Grove",
            type_line="Land",
            oracle_text="This land enters tapped unless you control a Forest or a Plains.\n"
            "{T}: Add {G} or {W}.",
            produced_mana=("G", "W"),
            color_identity="GW",
        )
        replacement = next(r for r in card.replacements if r["event"] == "self_enters_tapped")
        assert replacement["condition"] == {
            "not": {
                "exists": {
                    "zone": "battlefield",
                    "controller": "you",
                    "any_of": [{"subtypes": ["Forest"]}, {"subtypes": ["Plains"]}],
                }
            }
        }
        assert not any("printed condition is not modelled" in n for n in result.notes)

    def test_one_basic_type_is_not_wrapped_in_any_of(self):
        """The Castle cycle names one type, and `any_of` takes two or more.

        The single-type case is the common one -- the five Eldraine Castles,
        Arena of Glory, Shifting Woodland and four more -- and it used to build
        a one-branch `any_of`, which `validate_selector` raises on.  The raise
        travelled out of `build_proxy` as "could not be generated", and
        `import_deck` turns any card it could not generate into `unknown_cards`
        -- so one Castle failed the **whole deck**, not just itself.
        """
        result, card = built(
            name="Castle Ardenvale",
            type_line="Land",
            oracle_text="This land enters tapped unless you control a Plains.\n"
            "{T}: Add {W}.\n"
            "{2}{W}{W}, {T}: Create a 1/1 white Human creature token.",
            produced_mana=("W",),
            color_identity="W",
        )
        replacement = next(r for r in card.replacements if r["event"] == "self_enters_tapped")
        assert replacement["condition"] == {
            "not": {
                "exists": {
                    "zone": "battlefield",
                    "controller": "you",
                    "subtypes": ["Plains"],
                }
            }
        }
        assert not any("printed condition is not modelled" in n for n in result.notes)

    def test_an_unreadable_condition_still_enters_tapped_and_says_so(self):
        """A free untapped dual distorts a game far more than a slow one.

        Generating the *upgrade* -- always untapped -- would quietly hand every
        imported deck a better mana base than the one it was built with. So a
        printed shape the reader does not recognise falls back to entering
        tapped unconditionally, never to entering untapped.
        """
        result, card = built(
            name="Sea of Clouds",
            type_line="Land",
            oracle_text="This land enters tapped unless you have two or more opponents.\n"
            "{T}: Add {W} or {U}.",
            produced_mana=("W", "U"),
            color_identity="WU",
        )
        replacement = next(r for r in card.replacements if r["event"] == "self_enters_tapped")
        assert "condition" not in replacement or replacement["condition"] is None
        assert any("printed condition is not modelled" in n for n in result.notes)

    def test_a_fetchland_produces_nothing_and_is_reported(self):
        # The biggest playability risk in an import: a mana base that looks like
        # 37 lands and behaves like 34.  The import report has a line for it.
        result, card = built(
            name="Windswept Heath",
            type_line="Land",
            oracle_text="{T}, Pay 1 life, Sacrifice this land: Search your library for a Forest "
            "or Plains card, put it onto the battlefield, then shuffle.",
            color_identity="",
        )
        assert not any(a.is_mana_ability for a in card.abilities)
        assert result.coverage == "partial"

    def test_an_instant_that_makes_mana_does_not_become_a_mana_permanent(self):
        # Dark Ritual carries produced_mana and is an Instant.  Without the
        # permanence check it would generate a tap ability on a spell.
        _, card = built(
            name="Dark Ritual",
            type_line="Instant",
            mana_cost="{B}",
            oracle_text="Add {B}{B}{B}.",
            produced_mana=("B",),
            colors="B",
            color_identity="B",
        )
        assert card.abilities == ()

    def test_a_signet_keeps_the_mana_half_of_its_cost(self):
        """`{1}, {T}: Add {G}{U}` is not `{T}: Add`.

        Dropping the `{1}` generates a rock strictly cheaper than the printed
        card -- the same "quietly hand the deck an upgrade" failure the
        conditional taplands are guarded against.
        """
        result, card = built(
            name="Simic Signet",
            type_line="Artifact",
            mana_cost="{2}",
            oracle_text="{1}, {T}: Add {G}{U}.",
            produced_mana=("G", "U"),
            color_identity="GU",
        )
        ability = next(a for a in card.abilities if a.is_mana_ability)
        assert ability.cost.tap is True
        assert str(ability.cost.mana) == "{1}"
        # And the payout is the printed {G}{U}, not one of either.
        assert ability.mana_options == ((0, 1, 0, 0, 1, 0),)
        assert result.coverage == "full"

    def test_a_mana_ability_with_a_cost_the_dsl_cannot_express_is_not_generated(self):
        # A bounce land's "return an Island you control to its owner's hand" has
        # no expression here. Generating the tap half alone would be a dual land
        # with no drawback at all.
        result, card = built(
            name="Coral Atoll",
            type_line="Land",
            oracle_text="This land enters tapped.\nWhen this land enters, sacrifice it "
            "unless you return an untapped Island you control to its owner's hand.\n"
            "{T}: Add {G}{U}.",
            produced_mana=("G", "U"),
            color_identity="GU",
        )
        # The tap-for-mana line itself is plain, so it is still generated -- what
        # is dropped is the separate sacrifice trigger, which the residual names.
        assert any(a.is_mana_ability for a in card.abilities)
        assert result.coverage == "partial"

    def test_a_fetchland_whose_whole_cost_is_unexpressible_makes_no_mana(self):
        result, card = built(
            name="Windswept Heath",
            type_line="Land",
            oracle_text="{T}, Pay 1 life, Sacrifice this land: Search your library for a "
            "Forest or Plains card, put it onto the battlefield, then shuffle.",
            color_identity="",
            produced_mana=(),
        )
        assert not any(a.is_mana_ability for a in card.abilities)
        assert result.coverage == "partial"

    def test_an_aura_does_not_take_the_mana_ability_it_grants(self):
        """The same trap as Scryfall's `keywords` listing what a card grants.

        Abundant Growth reads `Enchanted land has "{T}: Add one mana of any
        color."` and carries `produced_mana` for all five. Lifting that gives
        the *Aura* a five-colour mana ability it does not have.
        """
        result, card = built(
            name="Abundant Growth",
            type_line="Enchantment — Aura",
            mana_cost="{G}",
            oracle_text='Enchant land\nWhen Abundant Growth enters, draw a card.\n'
            'Enchanted land has "{T}: Add one mana of any color."',
            produced_mana=("W", "U", "B", "R", "G"),
            colors="G",
            color_identity="G",
        )
        assert not any(a.is_mana_ability for a in card.abilities)
        assert result.coverage == "partial"

    def test_a_basic_lands_reminder_text_still_counts_as_its_ability(self):
        # A basic land's *entire* rules text is the parenthesised reminder, so
        # code that strips reminders before looking for `{T}: Add` leaves Forest
        # unable to make mana.
        _, card = built(
            name="Forest",
            type_line="Basic Land — Forest",
            oracle_text="({T}: Add {G}.)",
            produced_mana=("G",),
            color_identity="G",
        )
        assert any(a.is_mana_ability for a in card.abilities)

    def test_a_rock_taps_for_the_amount_it_prints(self):
        """`{T}: Add {C}{C}` is two mana, and the amount is in the *text*.

        `produced_mana` lists which symbols a card can make and never how many,
        so reading it alone turns every Signet and Sol Ring into a one-mana rock
        -- the difference between a fast deck and a slow one, applied silently to
        every imported deck.
        """
        result, card = built(
            name="Sol Ring",
            type_line="Artifact",
            mana_cost="{1}",
            oracle_text="{T}: Add {C}{C}.",
            produced_mana=("C",),
            color_identity="",
        )
        ability = next(a for a in card.abilities if a.is_mana_ability)
        assert ability.mana_options == ((0, 0, 0, 0, 0, 2),)
        assert result.coverage == "full"


# ----------------------------------------------------------------------
# things the engine only half-models
# ----------------------------------------------------------------------


class TestPartiallyModelledCards:
    def test_a_planeswalker_enters_play_but_says_it_does_nothing(self):
        result, card = built(
            name="Jace, the Mind Sculptor",
            type_line="Legendary Planeswalker — Jace",
            mana_cost="{2}{U}{U}",
            oracle_text="+2: Look at the top card of target player's library.",
            colors="U",
            color_identity="U",
        )
        assert "Planeswalker" in card.types
        assert any("loyalty" in n for n in result.notes)

    def test_a_battle_enters_play_but_says_it_does_nothing(self):
        result, card = built(
            name="Invasion of Ravnica",
            type_line="Battle — Siege",
            mana_cost="{3}{G}{U}",
            oracle_text="When this Siege enters, destroy target artifact.",
            colors="GU",
            color_identity="GU",
        )
        assert "Battle" in card.types
        assert any("defence" in n for n in result.notes)

    def test_a_kindred_card_drops_the_noise_type(self):
        result, card = built(
            name="Bound in Silence",
            type_line="Kindred Enchantment — Rebel Aura",
            mana_cost="{2}{W}",
            oracle_text="Enchant creature\nEnchanted creature can't attack or block.",
            colors="W",
            color_identity="W",
        )
        assert card.types == frozenset({"Enchantment"})
        assert any("Kindred" in n for n in result.notes)

    def test_a_modal_dfc_generates_its_front_face_loudly(self):
        result, card = built(
            name="Malakir Rebirth // Malakir Mire",
            type_line="Instant // Land",
            mana_cost="{B}",
            oracle_text="Until end of turn, target creature gains \"When this creature dies...\"",
            layout="modal_dfc",
            colors="B",
            color_identity="B",
        )
        assert card.types == frozenset({"Instant"})
        assert any("back face is not modelled" in n for n in result.notes)

    def test_a_variable_power_reads_as_zero_rather_than_failing_to_compile(self):
        # `compile_card` needs an int.  "*" is the characteristic-defining
        # ability this engine does not have, so the honest base is 0.
        result, card = built(
            name="Tarmogoyf",
            type_line="Creature — Lhurgoyf",
            mana_cost="{1}{G}",
            oracle_text="Tarmogoyf's power is equal to the number of card types among cards "
            "in all graveyards and its toughness is equal to that plus 1.",
            power="*",
            toughness="1+*",
            colors="G",
            color_identity="G",
        )
        assert (card.power, card.toughness) == (0, 0)
        assert any("variable" in n for n in result.notes)


# ----------------------------------------------------------------------
# refusals
# ----------------------------------------------------------------------


class TestCardsItRefusesToGenerate:
    def test_a_token_is_refused(self):
        # `validate_deck` rejects a token in a deck anyway; refusing here means
        # the import report names the card instead of the deck failing later.
        result = build_proxy(facts(name="Vampire", type_line="Token Creature — Vampire", is_token=True))
        assert result.model is None
        assert "deck" in result.error

    @pytest.mark.parametrize("layout", ["emblem", "art_series", "planar", "scheme", "vanguard"])
    def test_a_non_card_layout_is_refused(self, layout):
        result = build_proxy(facts(name="Whatever", type_line="Creature — Bear", layout=layout))
        assert result.model is None

    def test_a_type_the_engine_has_no_notion_of_is_refused(self):
        result = build_proxy(facts(name="Lost Mine of Phandelver", type_line="Dungeon"))
        assert result.model is None
        assert "no card type" in result.error


# ----------------------------------------------------------------------
# the residual
# ----------------------------------------------------------------------


class TestTheResidualIsHonest:
    def test_unimplemented_text_is_quoted_back(self):
        result, _ = built(
            name="Lightning Bolt",
            type_line="Instant",
            mana_cost="{R}",
            oracle_text="Lightning Bolt deals 3 damage to any target.",
            colors="R",
            color_identity="R",
        )
        assert result.coverage == "partial"
        assert any("deals 3 damage to any target" in n for n in result.notes)

    def test_a_card_whose_text_is_only_its_own_name_is_still_full(self):
        # Some tokens and older cards print the name alone.  Reporting that as
        # unimplemented rules text would be noise.
        result, _ = built(
            name="Grizzly Bears",
            type_line="Creature — Bear",
            mana_cost="{1}{G}",
            oracle_text="Grizzly Bears",
            power="2",
            toughness="2",
            colors="G",
            color_identity="G",
        )
        assert result.coverage == "full"

    def test_reminder_text_alone_never_counts_as_unimplemented(self):
        result, _ = built(
            name="Island",
            type_line="Basic Land — Island",
            oracle_text="({T}: Add {U}.)",
            produced_mana=("U",),
            color_identity="U",
        )
        assert result.coverage == "full"

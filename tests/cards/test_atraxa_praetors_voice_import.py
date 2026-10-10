"""A superfriends list, every card engine-native -- the pasted-link guarantee.

The earlier pins (`test_lucy_maclean_import.py`, `test_myrel_shield_of_argive_import.py`)
are creature decks. **Atraxa, Praetors' Voice** leads the other kind: thirty-odd
planeswalkers, and a support package that exists to make them bigger and keep them
alive -- full proliferate (Atraxa, Contentious Plan, Flux Channeler, Karn's Bastion,
Viral Drake, Tekuthal), counter doubling (Doubling Season, Deepglow Skate, Innkeeper's
Talent), extra loyalty on entry (Oath of Gideon), The Chain Veil's extra activation,
Teferi's and Narset's casting locks, and Gideon of the Trials' "you can't lose".

It started at **34 of 90 distinct cards** native, and the half that did not resolve
was the loyalty system's edges rather than a long tail: -X loyalty costs, compleated,
"until your next turn" on every temporary effect a +1 makes, damage prevention on a
permanent, the choice proliferate always was, linked exile off the library top, a
commander that is a planeswalker because it says so, and eleven tokens.

So this file pins the same claim as its siblings for a list that exercises the
planeswalker third of the engine: **every one of its 90 distinct cards resolving
`native`**, through the same `importer.import_deck` a pasted link goes through. A card
dropping out of `data/cards/auto/`, or an engine change invalidating one, turns a
`native` into a `partial` here rather than in somebody's game.

Deliberately a *list* and not a `data/decks/*.deck.json`, for the reason the Lucy pin
gives: the deliverable is card-level support reached through the importer, so the test
asserts what the importer says.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.images import load_index
from commanderblitz.cards.importer import import_deck
from commanderblitz.cards.moxfield import ParsedDeck
from commanderblitz.cards.registry import default_registry

COMMANDER = "Atraxa, Praetors' Voice"

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
DECK: tuple[tuple[str, int], ...] = (
    ("Ajani Steadfast", 1),
    ("Ajani Unyielding", 1),
    ("Ajani, Sleeper Agent", 1),
    ("Ajani, the Greathearted", 1),
    ("Aminatou, the Fateshifter", 1),
    ("Anguished Unmaking", 1),
    ("Arcane Sanctum", 1),
    ("Ash Barrens", 1),
    ("Ashiok, Dream Render", 1),
    ("Ashiok, Nightmare Weaver", 1),
    ("Brokers Ascendancy", 1),
    ("Call the Gatewatch", 1),
    ("Chromatic Lantern", 1),
    ("Command Tower", 1),
    ("Contentious Plan", 1),
    ("Cyclonic Rift", 1),
    ("Day of Judgment", 1),
    ("Deepglow Skate", 1),
    ("Deploy the Gatewatch", 1),
    ("Doubling Season", 1),
    ("Dovin Baan", 1),
    ("Elspeth, Sun's Champion", 1),
    ("Eternal Witness", 1),
    ("Evolving Wilds", 1),
    ("Flux Channeler", 1),
    ("Forest", 5),
    ("Fracture", 1),
    ("Gideon Jura", 1),
    ("Gideon of the Trials", 1),
    ("Gideon, Champion of Justice", 1),
    ("Hissing Quagmire", 1),
    ("Inexorable Tide", 1),
    ("Innkeeper's Talent", 1),
    ("Island", 3),
    ("Jace, Cunning Castaway", 1),
    ("Jace, Memory Adept", 1),
    ("Jace, Unraveler of Secrets", 1),
    ("Karn's Bastion", 1),
    ("Kasmina, Enigma Sage", 1),
    ("Kasmina, Enigmatic Mentor", 1),
    ("Kaya the Inexorable", 1),
    ("Kiora, Master of the Depths", 1),
    ("Kiora, the Crashing Wave", 1),
    ("Liliana, Dreadhorde General", 1),
    ("Liliana, the Last Hope", 1),
    ("Lumbering Falls", 1),
    ("Mortify", 1),
    ("Narset Transcendent", 1),
    ("Narset, Parter of Veils", 1),
    ("Nissa, Vital Force", 1),
    ("Nissa, Voice of Zendikar", 1),
    ("Oath of Ajani", 1),
    ("Oath of Gideon", 1),
    ("Oath of Nissa", 1),
    ("Ob Nixilis Reignited", 1),
    ("Oko, Thief of Crowns", 1),
    ("Opulent Palace", 1),
    ("Plains", 3),
    ("Prairie Stream", 1),
    ("Putrefy", 1),
    ("Rupture Spire", 1),
    ("Sandsteppe Citadel", 1),
    ("Seaside Citadel", 1),
    ("Shambling Vent", 1),
    ("Sol Ring", 1),
    ("Sorin, Grim Nemesis", 1),
    ("Sorin, Solemn Visitor", 1),
    ("Stirring Wildwood", 1),
    ("Sunpetal Grove", 1),
    ("Swamp", 3),
    ("Swords to Plowshares", 1),
    ("Tamiyo, Collector of Tales", 1),
    ("Tamiyo, Compleated Sage", 1),
    ("Tamiyo, Field Researcher", 1),
    ("Teferi's Protection", 1),
    ("Teferi, Temporal Archmage", 1),
    ("Teferi, Time Raveler", 1),
    ("Tekuthal, Inquiry Dominus", 1),
    ("Temple of Deceit", 1),
    ("Temple of Malady", 1),
    ("Temple of Mystery", 1),
    ("Temple of the False God", 1),
    ("The Chain Veil", 1),
    ("Viral Drake", 1),
    ("Vivid Creek", 1),
    ("Vivid Grove", 1),
    ("Vraska the Unseen", 1),
    ("Vraska, Relic Seeker", 1),
    ("Woodland Cemetery", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run -- it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="atraxapraetorsvoice",
        name=COMMANDER,
        format="commander",
        commanders=(COMMANDER,),
        cards=DECK,
    )
    return import_deck(deck, default_registry().registry, load_index(), dry_run=True)


class TestEveryCardIsNative:
    def test_the_list_is_a_hundred_cards(self, report):
        """A 99-card deck is not a deck, so the arithmetic is asserted first.

        If a name were dropped the count would fall and every other assertion
        here would still pass, which is the one way this file could lie.
        """
        assert report.total == 100
        assert len(report.cards) == 90

    def test_nothing_is_a_proxy(self, report):
        """The claim. `partial` means the printed text is inert."""
        not_native = sorted(c.name for c in report.cards if c.origin != "native")
        assert not_native == []

    def test_nothing_was_simplified(self, report):
        assert report.simplified == 0
        assert report.playable == 100

    def test_no_card_carries_a_note(self, report):
        """A note is the importer saying what it had to give up."""
        noted = {c.name: c.notes for c in report.cards if c.notes}
        assert noted == {}


class TestTheCommanderIsLegal:
    def test_atraxa_leads_the_deck(self, report):
        """A legendary creature, so 903.3 needs no sentence -- the near miss is the
        two walkers in the list that print "can be your commander" (Teferi,
        Temporal Archmage; Aminatou, the Fateshifter), which `validate_deck`
        now reads rather than waving every legendary planeswalker through."""
        card = default_registry().registry.by_name(COMMANDER)
        assert card is not None and card.is_creature and card.is_legendary


class TestTheManaBaseIsReal:
    def test_every_land_makes_mana_or_does_something(self, report):
        """Karn's Bastion proliferates and Rupture Spire sacrifices itself unless
        paid for; either generated as an inert permanent leaves a deck that looks
        like 36 lands and plays like fewer."""
        assert report.lands == 36
        assert report.lands_inert == 0

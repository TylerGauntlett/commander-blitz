"""A landfall list, every card engine-native -- the pasted-link guarantee.

**Aesi, Tyrant of Gyre Strait** leads "Lander Commander", a Simic lands deck whose
engine is the commander's two lines: an extra land drop each turn and a card for
every land that enters under your control. Forty-three lands, the ramp that puts
more of them down, and the payoffs that turn land drops into bodies and cards.

It started at **75 of 77 distinct cards** native. The other two took one token
and one capability: Verdant Kraken's 3/3 Forest Tentacle land creature token --
a land on every player's upkeep, so a card off Aesi on every upkeep -- and
Turntimber Symbiosis' "it enters with three additional +1/+1 counters", a real
614.1c enters-with on a card `look_at_top` puts onto the battlefield, with its
land face Turntimber, Serpentine Wood.

So this file pins the same claim as its siblings: **every one of its 77 distinct
cards resolving `native`**, through the same `importer.import_deck` a pasted link
goes through. A card dropping out of `data/cards/auto/`, or an engine change
invalidating one, turns a `native` into a `partial` here rather than in somebody's
game.

Deliberately a *list* and not a `data/decks/*.deck.json`, for the reason the Lucy pin
gives: the deliverable is card-level support reached through the importer, so the test
asserts what the importer says.
"""

from __future__ import annotations

import pytest

from automtg.cards.images import load_index
from automtg.cards.importer import import_deck
from automtg.cards.moxfield import ParsedDeck
from automtg.cards.registry import default_registry

COMMANDER = "Aesi, Tyrant of Gyre Strait"

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
DECK: tuple[tuple[str, int], ...] = (
    ("Acidic Slime", 1),
    ("Ancient Greenwarden", 1),
    ("Arcane Denial", 1),
    ("Arixmethes, Slumbering Isle", 1),
    ("Avenger of Zendikar", 1),
    ("Azusa, Lost but Seeking", 1),
    ("Beast Within", 1),
    ("Blighted Woodland", 1),
    ("Botanical Sanctum", 1),
    ("Burgeoning", 1),
    ("Coiling Oracle", 1),
    ("Command Tower", 1),
    ("Coral Atoll", 1),
    ("Counterspell", 1),
    ("Craterhoof Behemoth", 1),
    ("Cultivate", 1),
    ("Cultivator Colossus", 1),
    ("Cyclonic Rift", 1),
    ("Dreamroot Cascade", 1),
    ("Dryad of the Ilysian Grove", 1),
    ("Evolving Wilds", 1),
    ("Exploration", 1),
    ("Fabled Passage", 1),
    ("Field of Ruin", 1),
    ("Finale of Devastation", 1),
    ("Flooded Grove", 1),
    ("Forest", 13),
    ("Ghalta, Primal Hunger", 1),
    ("Ghost Quarter", 1),
    ("Goldvein Hydra", 1),
    ("Greensleeves, Maro-Sorcerer", 1),
    ("Growth Spiral", 1),
    ("Herd Heirloom", 1),
    ("Heroic Intervention", 1),
    ("Hinterland Harbor", 1),
    ("Imprisoned in the Moon", 1),
    ("Island", 12),
    ("Jin-Gitaxias, Progress Tyrant", 1),
    ("Jungle Basin", 1),
    ("Kodama of the East Tree", 1),
    ("Kodama's Reach", 1),
    ("Koma, Cosmos Serpent", 1),
    ("Lotus Cobra", 1),
    ("Mossborn Hydra", 1),
    ("Myriad Landscape", 1),
    ("Negate", 1),
    ("Nezahal, Primal Tide", 1),
    ("Oracle of Mul Daya", 1),
    ("Overwhelming Stampede", 1),
    ("Pongify", 1),
    ("Propaganda", 1),
    ("Rampaging Baloths", 1),
    ("Rampant Growth", 1),
    ("Ramunap Excavator", 1),
    ("Reclamation Sage", 1),
    ("Reliquary Tower", 1),
    ("Rhystic Study", 1),
    ("Scute Swarm", 1),
    ("Search for Tomorrow", 1),
    ("Simic Growth Chamber", 1),
    ("Simic Signet", 1),
    ("Sol Ring", 1),
    ("Springheart Nantuko", 1),
    ("Swiftfoot Boots", 1),
    ("Tatyova, Benthic Druid", 1),
    ("Terastodon", 1),
    ("Terramorphic Expanse", 1),
    ("Thought Vessel", 1),
    ("Tireless Provisioner", 1),
    ("Turntimber Symbiosis // Turntimber, Serpentine Wood", 1),
    ("Urban Evolution", 1),
    ("Verdant Kraken", 1),
    ("Waterlogged Grove", 1),
    ("Yavimaya Coast", 1),
    ("Yavimaya Elder", 1),
    ("Zendikar's Roil", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run -- it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="landercommander",
        name="Lander Commander",
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
        assert len(report.cards) == 77

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
    def test_aesi_leads_the_deck(self, report):
        """A legendary creature, so 903.3 needs no sentence."""
        card = default_registry().registry.by_name(COMMANDER)
        assert card is not None and card.is_creature and card.is_legendary


class TestTheTwoCardsThisDeckAdded:
    def test_the_kraken_names_a_token_the_pool_has(self):
        """A Verdant Kraken whose token id dangled would load and raise at the
        first upkeep -- every player's, in a four-player game."""
        registry = default_registry().registry
        assert registry.get("forest_tentacle_3_3_g_land") is not None

    def test_the_symbiosis_has_its_land_face(self):
        """An MDFC whose `second_face` dangled is a seven-mana sorcery that can
        never be played as the land drop this deck mostly wants it for."""
        registry = default_registry().registry
        symbiosis = registry.by_name("Turntimber Symbiosis // Turntimber, Serpentine Wood")
        assert symbiosis is not None
        back = registry.get(symbiosis.second_face)
        assert back is not None and back.name == "Turntimber, Serpentine Wood"
        assert back.is_land


class TestTheManaBaseIsReal:
    def test_every_land_makes_mana_or_does_something(self, report):
        """A landfall deck counts its lands twice -- once for mana, once for
        Aesi -- so one generated as an inert permanent costs it both."""
        assert report.lands == 43
        assert report.lands_inert == 0

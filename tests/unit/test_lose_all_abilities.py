"""What a permanent *has* — the engine's first derived ability list.

    Imprisoned in the Moon: "Enchanted permanent is a colorless land with
    "{T}: Add {C}" and loses all other card types and abilities."

Until this, no effect could take an ability away, so nothing needed to ask what
abilities a permanent has — every reader walked `state.card_of(obj).abilities`
and got the printed list. There are five such readers (`legality`, `costs`,
`triggers`, `characteristics._battlefield_statics`, `game._activate`), and with
a printed list each of them is a separate place for "loses all abilities" to be
forgotten. Forgetting it in *any one* is a permanent that visibly does nothing
and quietly still does something: an imprisoned Bloodghast still seeing
landfall, an imprisoned anthem still pumping, an imprisoned Sol Ring still
tapping for two.

So `characteristics.abilities_of` is the single answer and all five ask it. The
claims below are one per reader, plus the two continuous effects that come with
the sentence — a colour layer and 613.1d's subtype strip.

Two orderings are load-bearing and neither is visible on a board:

* **Removal comes before the grants** (613.1b). A keyword *is* an ability, so
  losing them all takes the printed keywords — but a Levitation played
  afterwards, and a vigilance counter (613.1f), still work.
* **The ability statics are collected off printed faces.** `_battlefield_statics`
  reads `abilities_of` and `abilities_of` reads the ability statics, so
  gathering both the same way is an infinite regress. The cost is one recorded
  divergence from 613.8: an Imprisoned in the Moon on another one does not
  switch the second off.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.registry import CardRegistry, authored_card_paths
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.costs import mana_sources
from automtg.engine.enums import Keyword
from automtg.engine.errors import DslError
from automtg.engine.primitives import attach
from automtg.engine.sandbox import GameBuilder
from tests.conftest import only_oid

MOON = "imprisoned_in_the_moon"


@pytest.fixture(scope="module")
def moon_registry() -> CardRegistry:
    """The shipped pool. Imprisoned in the Moon is in it once collected."""
    return CardRegistry.from_paths(authored_card_paths(Path("data/cards")))


@pytest.fixture
def board(moon_registry):
    def make(*cards: str, lands: int = 3):
        return (
            GameBuilder(moon_registry, players=2, seed=0)
            .battlefield(0, ["forest"] * lands)
            .battlefield(0, [*cards, MOON])
            .build(advance=False)
        )

    return make


def imprison(game, victim_id: str) -> int:
    """Attach the Aura, and hand back the victim's oid."""
    victim = only_oid(game, victim_id)
    attach(game.state, only_oid(game, MOON), victim)
    game.state.bump_chars()
    return victim


class TestTheAbilitiesGo:
    def test_a_printed_activated_ability_is_gone(self, board):
        """`legality` and `game._activate` read the derived list."""
        game = board("sol_ring")
        sol = imprison(game, "sol_ring")

        assert [a.text for a in abilities_of(game.state, sol)] == ["{T}: Add {C}."]

    def test_a_printed_triggered_ability_stops_listening(self, board):
        """`triggers.collect`. An imprisoned Lotus Cobra has no landfall."""
        game = board("lotus_cobra")
        cobra = imprison(game, "lotus_cobra")

        assert not any(a.is_triggered for a in abilities_of(game.state, cobra))

    def test_a_printed_static_stops_applying(self, board):
        """`characteristics._battlefield_statics` — the reader that no amount
        of work at the offer sites would have caught."""
        game = board("tatyova_benthic_druid", "oracle_of_mul_daya")
        oracle = imprison(game, "oracle_of_mul_daya")

        assert not any(a.is_static for a in abilities_of(game.state, oracle))

    def test_the_printed_keywords_go_too(self, board):
        """113.1a: a keyword *is* an ability. An imprisoned deathtoucher that
        kept deathtouch is the clearest possible half-implementation."""
        game = board("acidic_slime")
        slime = imprison(game, "acidic_slime")

        assert Keyword.DEATHTOUCH.value not in chars(game.state, slime).keywords

    def test_a_grant_made_afterwards_survives(self, board):
        """613.1b: what is added after the removal is not removed by it."""
        game = board("acidic_slime")
        slime = imprison(game, "acidic_slime")
        game.state.objects[slime].granted_keywords.add(Keyword.FLYING.value)
        game.state.bump_chars()

        assert Keyword.FLYING.value in chars(game.state, slime).keywords


class TestTheGrantedAbility:
    def test_the_permanent_has_it(self, board):
        game = board("lotus_cobra")
        cobra = imprison(game, "lotus_cobra")

        granted = abilities_of(game.state, cobra)
        assert [a.text for a in granted] == ["{T}: Add {C}."]
        assert granted[0].is_mana_ability

    def test_the_payment_solver_can_spend_it(self, board):
        """The whole point of putting this in the derived list rather than
        beside the op's grants: a granted mana ability the solver cannot see is
        a mana source the engine can never tap."""
        game = board("lotus_cobra")
        cobra = imprison(game, "lotus_cobra")

        sources = [s for s in mana_sources(game.state, 0) if s.oid == cobra]
        assert len(sources) == 1
        # One colourless: the last slot of the (W, U, B, R, G, C) tuple.
        assert sources[0].options == ((0, 0, 0, 0, 0, 1),)

    def test_its_index_addresses_the_derived_list(self, board):
        """`Action.ability_index` is a position, and legality and resolution
        have to be counting into the same list."""
        game = board("sol_ring")
        sol = imprison(game, "sol_ring")

        abilities = abilities_of(game.state, sol)
        assert [a.index for a in abilities] == list(range(len(abilities)))


class TestTheOtherLayers:
    def test_the_card_types_are_replaced(self, board):
        game = board("lotus_cobra")
        cobra = imprison(game, "lotus_cobra")

        assert chars(game.state, cobra).types == frozenset({"Land"})

    def test_the_colors_are_replaced(self, board):
        """No static could set a colour before this. It is load-bearing at
        once: the selector language reads `colors` and `shares_a_color_with`,
        and `protection` reads `from_colors`."""
        game = board("lotus_cobra")
        cobra = imprison(game, "lotus_cobra")

        assert chars(game.state, cobra).colors == frozenset()

    def test_the_orphaned_subtypes_go_with_their_type(self, board):
        """205.1b / 613.1d. A Snake that stops being a creature stops being a
        Snake — otherwise it reads "Land — Snake" and a Snake anthem still
        finds it."""
        game = board("lotus_cobra")
        cobra = imprison(game, "lotus_cobra")

        assert chars(game.state, cobra).subtypes == frozenset()

    def test_a_subtype_of_a_surviving_type_stays(self, board):
        """The strip is per type, not a blanket clear: the permanent is still a
        Land, so a land subtype has no reason to go."""
        game = board(lands=3)
        forest = game.state.battlefield_objects(0)[0].oid
        attach(game.state, only_oid(game, MOON), forest)
        game.state.bump_chars()

        assert "Forest" in chars(game.state, forest).subtypes


class TestItComesBack:
    def test_removing_the_aura_restores_everything(self, board):
        """Nothing is written onto the victim, so there is nothing to undo —
        which is the argument for making this a static rather than an op."""
        game = board("lotus_cobra")
        cobra = imprison(game, "lotus_cobra")
        moon = only_oid(game, MOON)

        from automtg.engine.enums import Zone
        from automtg.engine.zones import move_object

        move_object(game.state, moon, Zone.GRAVEYARD, to_player=0)
        game.state.bump_chars()

        c = chars(game.state, cobra)
        assert c.types == frozenset({"Creature"})
        assert c.colors == frozenset({"G"})
        assert "Snake" in c.subtypes
        assert any(a.is_triggered for a in abilities_of(game.state, cobra))


class TestTheLoaderRefusals:
    def base(self, **over):
        card = {
            "id": "x_moon",
            "name": "X Moon",
            "oracle_text": "Enchant permanent\nEnchanted permanent loses all abilities.",
            "mana_cost": "{U}",
            "types": ["Enchantment"],
            "subtypes": ["Aura"],
            "targets": [
                {"id": "e", "kind": "permanent", "selector": {"zone": "battlefield"}}
            ],
            "abilities": [
                {
                    "kind": "static",
                    "text": "Enchanted permanent loses all abilities.",
                    "effect": "lose_all_abilities",
                    "affects": {"attached": True},
                }
            ],
        }
        card.update(over)
        return card

    def compile(self, card):
        compile_card(CardModel.model_validate(card))

    def test_the_shape_it_is_meant_to_allow_loads(self):
        self.compile(self.base())

    def test_set_colors_without_colors_is_refused(self):
        """`[]` is colourless and is the point of the effect, so the check is
        for the field being absent — a `set_colors` saying nothing would
        silently repaint everything it touches."""
        card = self.base()
        card["abilities"][0] = {
            "kind": "static",
            "text": "Enchanted permanent loses all abilities.",
            "effect": "set_colors",
            "affects": {"attached": True},
        }
        with pytest.raises(DslError, match="set_colors needs 'colors'"):
            self.compile(card)

    def test_set_colors_with_an_unknown_colour_is_refused(self):
        card = self.base()
        card["abilities"][0] = {
            "kind": "static",
            "text": "Enchanted permanent loses all abilities.",
            "effect": "set_colors",
            "affects": {"attached": True},
            "colors": ["Q"],
        }
        with pytest.raises(DslError, match="unknown colour"):
            self.compile(card)

    def test_grant_ability_without_an_index_is_refused(self):
        card = self.base()
        card["abilities"][0] = {
            "kind": "static",
            "text": "Enchanted permanent loses all abilities.",
            "effect": "grant_ability",
            "affects": {"attached": True},
        }
        with pytest.raises(DslError, match="grant_ability needs 'ability'"):
            self.compile(card)

    def test_a_granted_mana_ability_is_allowed(self):
        """Narrowed from "triggered only", and exactly this far: 605.3a keeps a
        mana ability off the stack, so `stack.ability_of` — which must resolve
        off the printed list, since an ability outlives its source — is never
        asked about one."""
        card = self.base(
            grantable_abilities=[
                {
                    "kind": "activated",
                    "text": "{T}: Add {C}.",
                    "is_mana_ability": True,
                    "cost": {"tap": True},
                    "effects": [{"op": "add_mana", "mana": "{C}"}],
                }
            ]
        )
        self.compile(card)

    def test_a_granted_non_mana_activated_ability_is_still_refused(self):
        """It would reach `stack.ability_of` with an index into a list that no
        longer exists, and resolve as some other ability of that permanent."""
        card = self.base(
            grantable_abilities=[
                {
                    "kind": "activated",
                    "text": "{T}: Draw a card.",
                    "cost": {"tap": True},
                    "effects": [{"op": "draw", "amount": {"const": 1}}],
                }
            ]
        )
        with pytest.raises(DslError, match="only triggered and mana abilities"):
            self.compile(card)


class TestTheSubtypeTable:
    """`SUBTYPE_CLASS` is derived from the committed catalog, so the derivation
    is a test rather than a comment: a catalog refresh that adds a land or
    artifact type says so here instead of silently stripping it."""

    def test_it_agrees_with_the_catalog(self):
        import sqlite3
        from collections import defaultdict

        from automtg.cards.images import catalog_path
        from automtg.engine.enums import SUBTYPE_CLASS

        classes = {
            "Land", "Artifact", "Enchantment", "Planeswalker",
            "Creature", "Instant", "Sorcery", "Battle", "Dungeon",
        }
        con = sqlite3.connect(f"file:{catalog_path().as_posix()}?mode=ro", uri=True)
        owners: dict[str, set[str]] = defaultdict(set)
        query = "SELECT DISTINCT type_line FROM cards WHERE type_line IS NOT NULL"
        for (type_line,) in con.execute(query):
            for face in type_line.split(" // "):
                if "—" not in face:
                    continue
                left, right = face.split("—", 1)
                words = left.split()
                # "Tribal Instant — Goblin" would file Goblin under Instant.
                if "Kindred" in words or "Tribal" in words:
                    continue
                types = {t for t in words if t in classes}
                if {"Instant", "Sorcery"} & types:
                    types = (types - {"Instant", "Sorcery"}) | {"Spell"}
                if len(types) != 1:
                    continue
                for subtype in right.split():
                    owners[subtype].add(next(iter(types)))
        con.close()

        derived = {
            subtype: next(iter(seen))
            for subtype, seen in owners.items()
            if len(seen) == 1 and next(iter(seen)) != "Creature"
        }
        assert derived == SUBTYPE_CLASS

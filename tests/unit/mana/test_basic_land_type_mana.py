"""A basic land type is a mana ability: rule 305.6.

"An object with the land card type and a basic land type has the intrinsic
ability '{T}: Add [mana symbol],' even if the text box doesn't actually contain
that text." So the ability goes wherever the type goes. The land Xolatoyac, the
Smiling Flood floods is an Island "for as long as it has a flood counter on it",
and taps for {U} for exactly that long. Every land under Stormtide Leviathan,
Yavimaya or Urborg is an Island, a Forest or a Swamp, and taps for that colour.
Dryad Arbor prints no mana ability at all, only the reminder.

Without this the type is in name only. The land reads "Land -- Forest Island"
and taps for nothing it could not tap for before, and that is the whole point of
each of those cards.

The other direction matters as much. A basic land and a dual print the same
ability as reminder text, and the card JSON carries it as an ordinary ability.
Deriving a second copy would give every Island two "{T}: Add {U}." abilities and
change every board the AI and the client read. So a printed bare tap-for-that-
colour ability *is* the intrinsic one, and only a type it does not cover adds
one (`characteristics.intrinsic_mana_abilities`).
"""

from __future__ import annotations

import contextlib

from commanderblitz.engine.carddef import BASIC_LAND_MANA_ABILITIES
from commanderblitz.engine.characteristics import abilities_of, chars
from commanderblitz.engine.costs import can_pay_mana, mana_sources
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.mana import ManaCost
from commanderblitz.engine.primitives import attach, remove_counters
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy
from tests.conftest import action_for_card, hand_ids, only_oid

ISLAND = BASIC_LAND_MANA_ABILITIES["Island"]
FOREST = BASIC_LAND_MANA_ABILITIES["Forest"]


def board(builder, cards, *, sick: bool = False):
    """Player 0 controls ``cards``, in its own main phase. Returns the game."""
    return builder(players=2).battlefield(0, list(cards), sick=sick).build(advance=False)


def texts(game, oid: int) -> list[str]:
    return [ability.text for ability in abilities_of(game.state, oid)]


def pays(game, cost: str) -> bool:
    return can_pay_mana(game.state, 0, ManaCost.parse(cost))


def resolve(game, source: int, target: int, effects: list[dict]) -> None:
    ctx = EffectContext(
        state=game.state,
        controller=0,
        source_oid=source,
        targets={"t1": (TargetRef.obj(target),)},
    )
    gen = execute(ctx, effects)
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def flood(game, land: int, source: int) -> None:
    """Xolatoyac's trigger body, exactly as the card writes it."""
    resolve(
        game,
        source,
        land,
        [
            {"op": "add_counters", "counter": "flood", "amount": 1, "objects": {"target": "t1"}},
            {
                "op": "add_subtype",
                "subtypes": ["Island"],
                "objects": {"target": "t1"},
                "duration": "while_counter",
                "counter": "flood",
            },
        ],
    )


class TestPrintedBasicsGainNothing:
    def test_a_basic_land_has_its_printed_ability_only(self, builder):
        game = board(builder, ["island"])
        island = only_oid(game, "island")

        assert abilities_of(game.state, island) == game.state.card_of(
            game.state.objects[island]
        ).abilities

    def test_a_dual_reminder_covers_both_its_types(self, builder):
        """ "({T}: Add {U} or {B}.)" is the Island's ability and the Swamp's."""
        game = board(builder, ["watery_grave"])
        grave = only_oid(game, "watery_grave")

        assert texts(game, grave) == ["({T}: Add {U} or {B}.)"]

    def test_one_source_per_land_for_the_solver(self, builder):
        game = board(builder, ["island", "watery_grave"])

        assert len(mana_sources(game.state, 0)) == 2


class TestTheTypeBringsTheAbility:
    def test_a_land_that_prints_only_the_reminder_taps_for_it(self, builder):
        """Dryad Arbor: "(… it has "{T}: Add {G}.")", and nothing else."""
        game = board(builder, ["dryad_arbor"])
        arbor = only_oid(game, "dryad_arbor")

        assert abilities_of(game.state, arbor)[-1].text == FOREST.text
        assert pays(game, "{G}")

    def test_a_creature_land_is_still_summoning_sick(self, builder):
        """302.6: the {T} of a creature that arrived this turn cannot be paid."""
        game = board(builder, ["dryad_arbor"], sick=True)

        assert not pays(game, "{G}")

    def test_a_static_grant_brings_the_mana(self, builder):
        """Stormtide Leviathan: "All lands are Islands in addition to their other types." """
        game = board(builder, ["flooded_strand", "stormtide_leviathan"])
        strand = only_oid(game, "flooded_strand")

        assert "Island" in chars(game.state, strand).subtypes
        assert texts(game, strand)[-1] == ISLAND.text
        assert pays(game, "{U}")

    def test_the_mana_goes_with_the_granter(self, builder):
        game = board(builder, ["flooded_strand", "stormtide_leviathan"])
        destroy(game.state, only_oid(game, "stormtide_leviathan"))

        assert ISLAND.text not in texts(game, only_oid(game, "flooded_strand"))
        assert not pays(game, "{U}")

    def test_a_land_gains_one_ability_per_new_type(self, builder):
        """Under a Leviathan a Forest has its own {G} and the Island's {U}."""
        game = board(builder, ["forest", "stormtide_leviathan"])
        forest = only_oid(game, "forest")

        assert texts(game, forest) == [FOREST.text, ISLAND.text]

    def test_a_nonland_with_the_subtype_has_none(self, builder):
        """305.6 needs the land card type too, not the word alone."""
        game = board(builder, ["grizzly_bears"])
        bears = only_oid(game, "grizzly_bears")
        resolve(
            game,
            bears,
            bears,
            [{"op": "add_subtype", "subtypes": ["Forest"], "objects": {"target": "t1"}}],
        )

        assert "Forest" in chars(game.state, bears).subtypes
        assert not any(ability.is_mana_ability for ability in abilities_of(game.state, bears))


class TestForAsLongAsTheTypeLasts:
    def test_a_flooded_land_taps_for_blue(self, builder):
        game = board(builder, ["flooded_strand", "grizzly_bears"])
        strand = only_oid(game, "flooded_strand")
        flood(game, strand, only_oid(game, "grizzly_bears"))

        assert texts(game, strand)[-1] == ISLAND.text
        assert pays(game, "{U}")

    def test_it_stops_with_the_last_flood_counter(self, builder):
        game = board(builder, ["flooded_strand", "grizzly_bears"])
        strand = only_oid(game, "flooded_strand")
        flood(game, strand, only_oid(game, "grizzly_bears"))
        remove_counters(game.state, strand, "flood", 1)

        assert ISLAND.text not in texts(game, strand)
        assert not pays(game, "{U}")

    def test_a_flooded_land_casts_a_blue_spell(self, builder):
        """The activation itself, not just the solver's plan."""
        game = (
            builder(players=2)
            .battlefield(0, ["flooded_strand", "grizzly_bears"])
            .hand(0, ["opt"])
            .build()
        )
        strand = only_oid(game, "flooded_strand")
        flood(game, strand, only_oid(game, "grizzly_bears"))
        game.apply(action_for_card(game, ActionKind.CAST, "opt"))


        assert game.state.objects[strand].tapped
        assert "opt" not in hand_ids(game)


class TestLosingAbilities:
    def test_a_loss_of_all_abilities_takes_the_intrinsic_one(self, builder):
        """Song of the Dryads: a Forest that loses every ability and is granted
        "{T}: Add {G}." taps for {G} once, not twice (613.1d before 613.1f)."""
        game = board(builder, ["flooded_strand", "song_of_the_dryads"])
        strand = only_oid(game, "flooded_strand")
        attach(game.state, only_oid(game, "song_of_the_dryads"), strand)

        assert "Forest" in chars(game.state, strand).subtypes
        assert texts(game, strand) == [FOREST.text]
        assert len(mana_sources(game.state, 0)) == 1


class TestWhereItSits:
    def test_the_intrinsic_ability_comes_after_every_printed_one(self, builder):
        """Last, so a land gaining a type moves no other ability's index."""
        game = board(builder, ["bant_panorama", "stormtide_leviathan"])
        panorama = only_oid(game, "bant_panorama")
        printed = game.state.card_of(game.state.objects[panorama]).abilities

        derived = abilities_of(game.state, panorama)
        assert [a.text for a in derived[: len(printed)]] == [a.text for a in printed]
        assert derived[-1].text == ISLAND.text
        assert [a.index for a in derived] == list(range(len(derived)))

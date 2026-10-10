"""``mana_availability`` -- what the client's mana row is allowed to claim.

The interesting cases are the ambiguous sources.  "{T}: Add {G} or {U}" and
"{T}: Add {G}{U}" both produce the symbol set ``{G, U}``, but the first is one
mana and the second is two.  A colour histogram cannot tell them apart and would
overstate the first board by a mana, which is why the payload keeps one entry
per source instead of summing into per-colour totals.
"""

from __future__ import annotations

from commanderblitz.engine.costs import mana_availability


def sources(game, pid: int = 0) -> list[dict]:
    return mana_availability(game.state, pid)["sources"]


def total(game, pid: int = 0) -> int:
    return mana_availability(game.state, pid)["total"]


class TestBasics:
    def test_an_empty_board_produces_nothing(self, builder):
        game = builder().build(advance=False)
        assert mana_availability(game.state, 0) == {"pool": {}, "sources": [], "total": 0}

    def test_two_forests_are_two_single_colour_sources(self, builder):
        game = builder().battlefield(0, ["forest", "forest"]).build(advance=False)
        assert [s["symbols"] for s in sources(game)] == [["G"], ["G"]]
        assert [s["amount"] for s in sources(game)] == [1, 1]
        assert total(game) == 2

    def test_only_your_own_permanents_count(self, builder):
        game = (
            builder()
            .battlefield(0, ["forest"])
            .battlefield(1, ["island", "island"])
            .build(advance=False)
        )
        assert total(game, 0) == 1
        assert total(game, 1) == 2

    def test_floating_mana_is_included(self, builder):
        game = builder().battlefield(0, ["forest"]).build(advance=False)
        game.state.players[0].mana_pool.add("U", 2)
        result = mana_availability(game.state, 0)
        assert result["pool"] == {"U": 2}
        assert result["total"] == 3


class TestWhatDoesNotCount:
    def test_a_tapped_land_is_not_a_source(self, builder):
        game = builder().battlefield(0, ["forest"], tapped=True).build(advance=False)
        assert sources(game) == []
        assert total(game) == 0

    def test_a_summoning_sick_mana_creature_is_not_a_source(self, builder):
        game = builder().battlefield(0, ["llanowar_elves"], sick=True).build(advance=False)
        assert sources(game) == []

    def test_the_same_creature_counts_once_it_has_settled(self, builder):
        game = builder().battlefield(0, ["llanowar_elves"]).build(advance=False)
        assert [s["symbols"] for s in sources(game)] == [["G"]]


class TestAmbiguousSources:
    def test_a_choice_dual_is_one_mana_of_two_possible_colours(self, builder):
        """"{T}: Add {G} or {U}" -- one mana, not two. Two options of one."""
        game = builder().battlefield(0, ["t_dual_land"]).build(advance=False)
        (source,) = sources(game)
        # Options keep the order the card declares them in; only `symbols` is
        # normalised to WUBRG, because that is what colours a pip.
        assert source["options"] == [["G"], ["U"]]
        assert source["symbols"] == ["U", "G"]
        assert source["amount"] == 1
        assert total(game) == 1

    def test_a_both_colours_dual_is_two_mana(self, builder):
        """"{T}: Add {G}{U}" -- same symbol set as above, twice the mana."""
        game = builder().battlefield(0, ["simic_growth_chamber"]).build(advance=False)
        (source,) = sources(game)
        assert source["options"] == [["U", "G"]]
        assert source["symbols"] == ["U", "G"]
        assert source["amount"] == 2
        assert total(game) == 2

    def test_the_two_are_distinguishable_from_the_payload_alone(self, builder):
        """The point of the whole shape: a colour histogram would collapse these.

        Both sources can make {U} and both can make {G}, so the symbol union is
        identical. Only the option list says one is a choice and the other is
        both -- a difference of a full mana.
        """
        choice = builder().battlefield(0, ["t_dual_land"]).build(advance=False)
        both = builder().battlefield(0, ["simic_growth_chamber"]).build(advance=False)
        assert sources(choice)[0]["symbols"] == sources(both)[0]["symbols"]
        assert sources(choice)[0]["options"] != sources(both)[0]["options"]
        assert total(choice) == 1
        assert total(both) == 2

    def test_a_three_colour_source_lists_all_three(self, builder):
        game = builder().battlefield(0, ["nomad_outpost"]).build(advance=False)
        (source,) = sources(game)
        assert source["symbols"] == ["W", "B", "R"]
        assert source["options"] == [["W"], ["B"], ["R"]]
        assert source["amount"] == 1

    def test_a_basic_land_has_exactly_one_option(self, builder):
        game = builder().battlefield(0, ["forest"]).build(advance=False)
        assert sources(game)[0]["options"] == [["G"]]

    def test_symbols_are_in_wubrg_order_not_card_order(self, builder):
        """So {G}{U} and {U}{G} render as the same pip, whichever way it parsed."""
        game = builder().battlefield(0, ["t_dual_land"]).build(advance=False)
        assert sources(game)[0]["symbols"] == ["U", "G"]


class TestTwoAbilitiesOnePermanent:
    """A painland prints "{T}: Add {C}" and "{T}: Add {R} or {W}" -- two
    abilities, but the land taps once, so it is one source worth one mana.

    Listed per ability it was two entries sharing an oid, two pips on the
    client, and a claimed total of two for a land that makes one.
    """

    def test_a_painland_is_one_source_with_every_option(self, builder):
        game = builder().battlefield(0, ["t_painland"]).build(advance=False)
        (source,) = sources(game)
        assert source["options"] == [["C"], ["R"], ["W"]]
        assert source["symbols"] == ["W", "R", "C"]
        assert source["amount"] == 1
        assert total(game) == 1

    def test_two_painlands_are_two_mana(self, builder):
        game = builder().battlefield(0, ["t_painland", "t_painland"]).build(advance=False)
        assert len(sources(game)) == 2
        assert len({s["oid"] for s in sources(game)}) == 2
        assert total(game) == 2

    def test_the_heuristic_count_agrees(self, builder):
        from commanderblitz.engine.costs import available_mana

        alone = builder().battlefield(0, ["t_painland"]).build(advance=False)
        assert available_mana(alone.state, 0) == 1
        with_forest = builder().battlefield(0, ["t_painland", "forest"]).build(advance=False)
        assert available_mana(with_forest.state, 0) == 2


class TestSerialized:
    def test_it_reaches_the_player_view(self, builder):
        from commanderblitz.engine.serialize import player_view

        game = builder().battlefield(0, ["forest", "island"]).build(advance=False)
        view = player_view(game.state, 0)
        assert view["players"][0]["mana"]["total"] == 2

    def test_opponent_mana_is_visible_too(self, builder):
        """Untapped lands are public information; hiding them would be wrong."""
        from commanderblitz.engine.serialize import player_view

        game = builder().battlefield(1, ["island"]).build(advance=False)
        view = player_view(game.state, 0)
        assert view["players"][1]["mana"]["total"] == 1


class TestSharedSourceIndex:
    """Serializing a pod walks the battlefield once, not once per seat.

    ``mana_availability`` filtered the whole battlefield by controller, so a
    four-player response scanned it four times over.  ``sources_by_controller``
    partitions in one pass instead.  These tests exist to pin that the shortcut
    is a shortcut and not a behaviour change.
    """

    def test_it_matches_the_per_player_walk(self, builder):
        from commanderblitz.engine.costs import sources_by_controller

        game = (
            builder(players=4)
            .battlefield(0, ["forest", "t_dual_land", "t_painland"])
            .battlefield(1, ["island", "island", "llanowar_elves"])
            .battlefield(2, ["nomad_outpost"])
            .build(advance=False)
        )
        shared = sources_by_controller(game.state)
        for pid in range(4):
            assert mana_availability(game.state, pid, shared[pid]) == mana_availability(
                game.state, pid
            )

    def test_every_seat_gets_a_bucket_even_with_an_empty_board(self, builder):
        from commanderblitz.engine.costs import sources_by_controller

        game = builder(players=4).build(advance=False)
        assert sources_by_controller(game.state) == {0: [], 1: [], 2: [], 3: []}

    def test_a_tapped_permanent_is_excluded_from_the_shared_walk_too(self, builder):
        from commanderblitz.engine.costs import sources_by_controller

        game = (
            builder()
            .battlefield(0, ["forest"], tapped=True)
            .battlefield(0, ["island"])
            .build(advance=False)
        )
        (source,) = sources_by_controller(game.state)[0]
        assert source.oid == game.state.battlefield[1]

    def test_a_summoning_sick_creature_is_excluded_from_the_shared_walk_too(self, builder):
        from commanderblitz.engine.costs import sources_by_controller

        game = builder().battlefield(0, ["llanowar_elves"], sick=True).build(advance=False)
        assert sources_by_controller(game.state)[0] == []

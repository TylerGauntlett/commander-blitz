"""``card_view`` -- the printed facts the client cannot work out for itself.

``supertypes`` and ``produces`` were added so the board can colour a land by what
it taps for.  ``produces`` in particular has to come from here: "Island" is
inferable from a subtype, but a nonbasic dual is not, and parsing ``oracle_text``
in the browser would be exactly the guess the client's mana module refuses to
make.  See docs/playtest-feedback-02.md item 8.
"""

from __future__ import annotations

from automtg.engine.costs import produced_symbols
from automtg.engine.serialize import card_view


def view_of(game, card_id: str, pid: int = 0) -> dict:
    """The serialized view of the first ``card_id`` in ``pid``'s hand."""
    for oid in game.state.players[pid].hand:
        if game.state.objects[oid].def_id == card_id:
            return card_view(game.state, oid)
    raise AssertionError(f"{card_id} is not in player {pid}'s hand")


class TestProduces:
    def test_a_basic_produces_its_one_colour(self, builder):
        game = builder().hand(0, ["island", "mountain"]).build(advance=False)
        assert view_of(game, "island")["produces"] == ["U"]
        assert view_of(game, "mountain")["produces"] == ["R"]

    def test_an_either_or_land_produces_both(self, builder):
        """"{T}: Add {G} or {U}" -- one mana, but it could be either colour."""
        game = builder().hand(0, ["t_dual_land"]).build(advance=False)
        assert view_of(game, "t_dual_land")["produces"] == ["U", "G"]

    def test_a_two_mana_land_produces_both(self, builder):
        """"{T}: Add {G}{U}" -- the same symbol set, two mana.

        ``produces`` deliberately cannot tell these apart: it answers "what
        colour is this land", not "how much mana". Amounts live in
        ``mana_availability``, which keeps one entry per source for exactly this
        reason.
        """
        game = builder().hand(0, ["simic_growth_chamber"]).build(advance=False)
        assert view_of(game, "simic_growth_chamber")["produces"] == ["U", "G"]

    def test_a_non_mana_card_produces_nothing(self, builder):
        game = builder().hand(0, ["t_bear"]).build(advance=False)
        assert view_of(game, "t_bear")["produces"] == []

    def test_a_mana_creature_still_reports_what_it_makes(self, builder):
        """Not a land, but the payload is about abilities, not card type."""
        game = builder().hand(0, ["llanowar_elves"]).build(advance=False)
        assert view_of(game, "llanowar_elves")["produces"] == ["G"]

    def test_symbols_come_back_in_wubrg_order(self, builder):
        """So {G}{U} and {U}{G} render as the same row of pips."""
        game = builder().hand(0, ["t_dual_land"]).build(advance=False)
        produced = view_of(game, "t_dual_land")["produces"]
        assert produced == sorted(produced, key=["W", "U", "B", "R", "G", "C"].index)


class TestSupertypes:
    def test_a_basic_land_says_so(self, builder):
        game = builder().hand(0, ["forest"]).build(advance=False)
        assert "Basic" in view_of(game, "forest")["supertypes"]

    def test_a_nonbasic_land_does_not(self, builder):
        game = builder().hand(0, ["t_dual_land"]).build(advance=False)
        assert "Basic" not in view_of(game, "t_dual_land")["supertypes"]

    def test_a_legendary_creature_says_so(self, builder):
        game = builder().hand(0, ["t_bear"]).build(advance=False)
        assert view_of(game, "t_bear")["supertypes"] == []


class TestEveryZone:
    def test_the_fields_are_printed_so_they_survive_the_battlefield(self, builder):
        """Battlefield views send *derived* characteristics; these are printed.

        A land that only carried its colour in hand would go blank the moment it
        was played, which is the zone the colour is actually for.
        """
        game = builder().battlefield(0, ["island"]).build(advance=False)
        view = card_view(game.state, game.state.battlefield[0])
        assert view["produces"] == ["U"]
        assert "Basic" in view["supertypes"]

    def test_a_hidden_card_stays_hidden(self, builder):
        game = builder().hand(0, ["island"]).build(advance=False)
        oid = game.state.players[0].hand[0]
        assert card_view(game.state, oid, revealed=False) == {"oid": oid, "hidden": True}


class TestHelper:
    def test_produced_symbols_reads_the_card_not_the_object(self, builder, registry):
        """It is a ``CardDef`` question, so it needs no game state at all."""
        assert produced_symbols(registry.get("forest")) == ["G"]
        assert produced_symbols(registry.get("t_bear")) == []

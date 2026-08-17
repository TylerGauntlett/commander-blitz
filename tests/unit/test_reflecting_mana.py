""""…any color that a land an opponent controls could produce."

    Exotic Orchard — "{T}: Add one mana of any color that a land an opponent
    controls could produce."

Every other mana ability's output is a constant on the card, and `mana_options`
is computed once at load time precisely because of that: the payment solver
reads those tuples while *planning*, before anything is tapped. This is the
first ability whose options are a question about the board.

So the card names the permanents to **ask** rather than the colours to make, and
`costs.mana_options_of` narrows the static superset to what those permanents
actually produce. It is called from `_sources_of` (so the solver plans against
the real colours) and from `activate_mana_ability` (so the payment adds one of
them) — the same two callers, and the same reason, as `mana_produced`: a spell
offered on a colour and then paid in another would strand the payment mid-cast.

**`mana_options` still holds all five colours** at load time. An empty tuple
there would make `solver_taps` and `offerable_mana_ability` both conclude this
is not a mana source, so the ability would never be tapped whatever the
opponent's lands did.

**A reflecting ability does not ask another one.** Two Exotic Orchards facing
each other would otherwise interrogate each other forever, so the scan reads
only *printed* options — which is also what the card means.

An empty answer is a real answer: an opponent with no lands offers no colours
and the Orchard taps for nothing. The solver simply never picks a source that
produces nothing.
"""

from __future__ import annotations

from automtg.engine.costs import mana_options_of, mana_sources
from automtg.engine.mana import SYMBOL_INDEX
from tests.conftest import oids_of

ORCHARD = "t_orchard"


def colors_offered(game, oid: int) -> set[str]:
    ability = game.state.card(oid).abilities[0]
    out: set[str] = set()
    for option in mana_options_of(game.state, oid, ability):
        for symbol, index in SYMBOL_INDEX.items():
            if option[index]:
                out.add(symbol)
    return out


def board(builder, opponent_lands):
    game = (
        builder(players=2)
        .battlefield(0, [ORCHARD])
        .battlefield(1, list(opponent_lands))
        .build()
    )
    return game, oids_of(game, ORCHARD)[0]


class TestItReadsTheOpponentsBoard:
    def test_one_basic_offers_one_colour(self, builder):
        game, orchard = board(builder, ["forest"])
        assert colors_offered(game, orchard) == {"G"}

    def test_two_basics_offer_two(self, builder):
        game, orchard = board(builder, ["forest", "island"])
        assert colors_offered(game, orchard) == {"G", "U"}

    def test_a_dual_offers_both_its_colours(self, builder):
        """A modal mana ability's options are each read, not just the first."""
        game, orchard = board(builder, ["t_dual_land"])
        assert colors_offered(game, orchard) == {"G", "U"}

    def test_no_lands_offers_nothing(self, builder):
        game, orchard = board(builder, [])
        assert colors_offered(game, orchard) == set()

    def test_your_own_lands_do_not_count(self, builder):
        """"…a land an **opponent** controls."""
        game = (
            builder(players=2)
            .battlefield(0, [ORCHARD, "mountain"])
            .battlefield(1, [])
            .build()
        )
        assert colors_offered(game, oids_of(game, ORCHARD)[0]) == set()

    def test_a_colourless_land_offers_no_colour(self, builder):
        """Wastes produces {C}, and the printed line says "any **color**"."""
        game, orchard = board(builder, ["wastes"])
        assert colors_offered(game, orchard) == set()


class TestTheSolverSeesTheSameThing:
    def test_it_is_offered_as_a_source_with_a_colour_available(self, builder):
        game, orchard = board(builder, ["swamp"])
        sources = mana_sources(game.state, 0)
        assert any(s.oid == orchard for s in sources)

    def test_the_source_produces_what_the_board_offers(self, builder):
        game, orchard = board(builder, ["swamp"])
        source = next(s for s in mana_sources(game.state, 0) if s.oid == orchard)
        assert source.producible() == {SYMBOL_INDEX["B"]}

    def test_it_produces_nothing_against_an_empty_board(self, builder):
        game, orchard = board(builder, [])
        source = next(
            (s for s in mana_sources(game.state, 0) if s.oid == orchard), None
        )
        assert source is None or source.max_output() == 0


class TestTwoOrchardsDoNotAskEachOther:
    def test_facing_orchards_offer_nothing(self, builder):
        """Only printed options are read, so the scan terminates."""
        game = (
            builder(players=2)
            .battlefield(0, [ORCHARD])
            .battlefield(1, [ORCHARD])
            .build()
        )
        mine = next(
            o for o in game.state.battlefield if game.state.objects[o].controller == 0
        )
        assert colors_offered(game, mine) == set()

    def test_an_orchard_plus_a_real_land_reads_the_real_one(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [ORCHARD])
            .battlefield(1, [ORCHARD, "plains"])
            .build()
        )
        mine = next(
            o for o in game.state.battlefield if game.state.objects[o].controller == 0
        )
        assert colors_offered(game, mine) == {"W"}

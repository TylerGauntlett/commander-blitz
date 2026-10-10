""""…any color that a land an opponent controls could produce."

    Exotic Orchard — "{T}: Add one mana of any color that a land an opponent
    controls could produce."
    Fellwar Stone — the same sentence off an artifact, and the card the
    `opponent_land_mana_colors` gap record named.

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

**A land whose own colours are also a question about the game must be asked the
same question.** `mana_options` carries a five-colour superset for exactly two
abilities — `reflecting` and `in_commander_identity` — because an empty tuple
at load time makes `solver_taps` decide it is not a mana source at all. Reading
that superset off an opponent's Path of Ancestry told a Fellwar Stone it "could
produce" all five colours, which is the unconditional any-colour approximation
this whole capability exists to refuse, arriving through the back door. So the
scan asks `mana_options_of` rather than reading the field. It still terminates,
because the only self-referential branch — `reflecting` — is skipped before the
recursion.

It never asks a *player* anything. Narrowing the option list narrows the choice
every modal mana ability already had; no `ask_*`, no generator, no stack, so the
ability stays a mana ability for 605.1a.
"""

from __future__ import annotations

from commanderblitz.engine.costs import mana_options_of, mana_sources
from commanderblitz.engine.mana import SYMBOL_INDEX
from tests.conftest import oids_of

ORCHARD = "t_orchard"
TOWER = "t_command_tower"
MONO_BLACK = "t_bats"          # color_identity ["B"]
TWO_COLOUR = "t_bw_commander"  # ["B", "W"]
COLOURLESS = "t_colorless_commander"


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


def facing(builder, *, opponent_lands, opponent_commander=None):
    """The Orchard, against an opponent board and an opponent command zone."""
    make = (
        builder(players=2)
        .battlefield(0, [ORCHARD])
        .battlefield(1, list(opponent_lands))
    )
    if opponent_commander is not None:
        make = make.commander(1, [opponent_commander])
    game = make.build()
    return game, oids_of(game, ORCHARD)[0]


class TestALandThatIsItselfAQuestionIsAsked:
    """An opponent's Path of Ancestry taps for its *controller's* commander's
    identity, not for five colours — and that is what it "could produce"."""

    def test_a_commander_identity_land_offers_only_that_identity(self, builder):
        game, orchard = facing(
            builder, opponent_lands=[TOWER], opponent_commander=MONO_BLACK
        )
        assert colors_offered(game, orchard) == {"B"}

    def test_it_is_not_all_five(self, builder):
        """The regression. Reading the load-time superset said {W,U,B,R,G}, which
        is the unconditional any-colour card this capability exists to refuse."""
        game, orchard = facing(
            builder, opponent_lands=[TOWER], opponent_commander=MONO_BLACK
        )
        assert len(colors_offered(game, orchard)) < 5

    def test_a_two_colour_identity_offers_both(self, builder):
        game, orchard = facing(
            builder, opponent_lands=[TOWER], opponent_commander=TWO_COLOUR
        )
        assert colors_offered(game, orchard) == {"B", "W"}

    def test_it_is_read_off_the_other_players_command_zone(self, builder):
        """*Whose* commander decides it. My own general must not leak in."""
        game = (
            builder(players=2)
            .battlefield(0, [ORCHARD])
            .battlefield(1, [TOWER])
            .commander(0, [TWO_COLOUR])
            .commander(1, [MONO_BLACK])
            .build()
        )
        assert colors_offered(game, oids_of(game, ORCHARD)[0]) == {"B"}

    def test_a_colourless_commander_offers_nothing(self, builder):
        """The Tower taps for nothing, so there is nothing to reflect."""
        game, orchard = facing(
            builder, opponent_lands=[TOWER], opponent_commander=COLOURLESS
        )
        assert colors_offered(game, orchard) == set()

    def test_it_joins_what_the_plain_lands_offer(self, builder):
        game, orchard = facing(
            builder, opponent_lands=[TOWER, "forest"], opponent_commander=MONO_BLACK
        )
        assert colors_offered(game, orchard) == {"B", "G"}

    def test_the_scan_still_terminates_against_both_kinds_at_once(self, builder):
        """A reflecting land is skipped, an identity land recurses one level."""
        game, orchard = facing(
            builder, opponent_lands=[ORCHARD, TOWER], opponent_commander=MONO_BLACK
        )
        assert colors_offered(game, orchard) == {"B"}


class TestFellwarStone:
    """The same sentence off an artifact — the card the gap record named.

    The board here is the one `authoring/verify.build_sandbox` puts every card
    through: the opponent controls a Forest and an Island. The authoring
    expectation language has no key for a mana pool (it can assert life, zones,
    counters, tokens and board counts), so this is the strongest statement of
    what the card does that anything in the repo can make, and it belongs here.
    """

    STONE = "fellwar_stone"

    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [self.STONE])
            .battlefield(1, ["forest", "island"])
            .build()
        )
        return game, oids_of(game, self.STONE)[0]

    def test_it_offers_exactly_the_opponents_two_colours(self, builder):
        game, stone = self.board(builder)
        assert colors_offered(game, stone) == {"G", "U"}

    def test_and_not_the_other_three(self, builder):
        """The free tier's starting point was five fixed modes. That is a
        strictly better card than the printed one."""
        game, stone = self.board(builder)
        assert colors_offered(game, stone) & {"W", "B", "R"} == set()

    def test_the_solver_sees_it_as_a_non_land_source(self, builder):
        """An artifact, not a land — it still has to reach the solver."""
        game, stone = self.board(builder)
        source = next(s for s in mana_sources(game.state, 0) if s.oid == stone)
        assert not source.is_land
        assert source.producible() == {SYMBOL_INDEX["G"], SYMBOL_INDEX["U"]}

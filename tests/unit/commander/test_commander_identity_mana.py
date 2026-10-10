""""Add one mana of any color in your commander's color identity."

    Command Tower, Arcane Signet, Commander's Sphere, Path of Ancestry.

The colours are a question about the game, not about the card, so the ability
cannot name them at load time. Written as five fixed modes -- the obvious
spelling, and the one the authoring templates reach for -- Command Tower is
correct in a five-colour deck and a *strictly better card* in every deck
narrower than that: it pays for spells the printed card cannot pay for.

Same shape as `reflecting` (Exotic Orchard) and for the same reason, but the
question is asked of the **command zone** rather than of the board. `Ability`
carries the five-colour superset in `mana_options` so the solver still sees a
mana source at all, and `mana_options_of` narrows it when the ability is
activated.

Read off the **printed** `color_identity`, wherever the commander happens to
be. Colour identity is a deck-construction fact fixed by the card -- it counts
mana symbols in rules text, and it is the same set in the command zone, on the
battlefield, or in a graveyard. Asking `chars()` for the object's current
colours would give a smaller set on most commanders and a wrong one on all of
them the turn somebody animates or changes the general's colour.

**A colourless commander narrows this to nothing**, and the land taps for
nothing. That is the printed card, not a defect: the solver never picks a
source that produces nothing.

The chips legality offers had to move onto the narrowed list too. They read
`ability.mana_options` -- the printed superset -- while `activate_mana_ability`
indexes the narrowed one, so an offered index either named a colour the game
could not make or, past the end, refused the very activation the panel had just
shown. Exotic Orchard had the same seam; this closes it for both.
"""

from __future__ import annotations

from commanderblitz.engine.costs import mana_options_of
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.mana import SYMBOLS
from tests.conftest import only_oid

TOWER = "t_command_tower"
MONO_BLACK = "t_bats"      # color_identity ["B"]
TWO_COLOUR = "t_bw_commander"  # ["B", "W"]
COLOURLESS = "t_colorless_commander"


def colors_offered(game, oid: int) -> set[str]:
    """Which symbols the ability would actually produce right now."""
    ability = game.state.card(oid).abilities[0]
    out: set[str] = set()
    for option in mana_options_of(game.state, oid, ability):
        for index, amount in enumerate(option):
            if amount:
                out.add(SYMBOLS[index])
    return out


def board(builder, commander: str, *, manual: bool = False):
    """A main phase with the Tower down and the commander in the command zone.

    `manual_mana` decides which actions exist, so it is set before the game
    advances into its first window rather than after.
    """
    game = (
        builder(players=2)
        .battlefield(0, [TOWER])
        .hand(0, ["mountain"])
        .library(0, ["swamp"] * 20)
        .commander(0, [commander])
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )
    game.state.players[0].manual_mana = manual
    game._advance()
    return game, only_oid(game, TOWER)


class TestTheIdentityNarrowsIt:
    def test_a_mono_black_commander_offers_only_black(self, builder):
        game, tower = board(builder, MONO_BLACK)
        assert colors_offered(game, tower) == {"B"}

    def test_a_two_colour_commander_offers_both(self, builder):
        game, tower = board(builder, TWO_COLOUR)
        assert colors_offered(game, tower) == {"B", "W"}

    def test_it_is_not_five_colours(self, builder):
        """The whole point. Five fixed modes is a different, better card."""
        game, tower = board(builder, MONO_BLACK)
        assert len(colors_offered(game, tower)) < 5


class TestWhereTheCommanderIs:
    def test_the_command_zone_counts(self, builder):
        """Which is where a commander sits for most of the game."""
        game, tower = board(builder, MONO_BLACK)
        assert colors_offered(game, tower) == {"B"}


class TestWhatLegalityOffers:
    def chips(self, game, oid: int) -> list[str]:
        return [
            a.option_label
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid
        ]

    def test_one_chip_per_colour_in_the_identity(self, builder):
        game, tower = board(builder, TWO_COLOUR, manual=True)
        assert len(self.chips(game, tower)) == 2

    def test_the_chips_name_the_right_colours(self, builder):
        game, tower = board(builder, TWO_COLOUR, manual=True)
        assert set(self.chips(game, tower)) == {"{B}", "{W}"}

    def test_every_offered_index_is_activatable(self, builder):
        """The seam this closes: an index into the printed superset could name
        a colour the game cannot make, or run off the end of the narrowed list
        and refuse the activation the panel had just offered."""
        game, tower = board(builder, TWO_COLOUR, manual=True)
        offered = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == tower
        ]
        ability = game.state.card(tower).abilities[0]
        assert offered
        for action in offered:
            assert action.mana_option is not None
            assert action.mana_option < len(mana_options_of(game.state, tower, ability))


class TestTheColourlessBoundary:
    def test_a_colourless_commander_taps_for_nothing(self, builder):
        """The printed card, not a defect: the solver never picks a source that
        produces nothing."""
        game, tower = board(builder, COLOURLESS)
        assert colors_offered(game, tower) == set()

    def test_and_legality_offers_no_chip(self, builder):
        game, tower = board(builder, COLOURLESS, manual=True)
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == tower
        ]

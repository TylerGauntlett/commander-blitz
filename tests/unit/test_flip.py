"""Flip cards — free, and the census recorded a decision instead of checking.

    "Test Initiate {1}{W} — Creature — Human Monk  2/2
     At the beginning of the end step, if you control three or more Elks, flip
     Test Initiate.
     ----
     Test Enlightened Master — Legendary Creature — Human Monk  4/4, flying"

Flip was one of five `refused` rows, filed as needing "a card-wide designated
state the engine has no place to keep". It needs no such thing. Rule 711 is
`back_face` plus the `transform` op, both of which shipped for Bloodline Keeper,
and the differences between a flip card and a transforming double-faced one are
all differences in *flavour text about cardboard*:

| | DFC | flip card |
|---|---|---|
| what the player does | turns the card over | turns it 180° |
| how the engine says it | `card_of` returns the other `CardDef` | the same |
| what the other side has | its own name, types, P/T | the same |
| may it be in a deck alone | no (`front_face` is set) | no, for the same reason |
| what survives the change | counters, auras, damage, tapped (711.4) | the same, because nothing moves |

So this file is a **witness**, not an implementation. It exists because "free"
is a claim about the engine that ought to be demonstrable, and the census's own
rule is that a status nobody checked is a status nobody should trust.

The one thing worth pinning is 711.4 — a flipped permanent is the *same*
permanent — because an implementation that recreated the object would look
identical on the board and lose every counter on it.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import Keyword, Zone
from automtg.engine.objects import PLUS_ONE
from automtg.engine.primitives import add_counters, transform
from tests.conftest import only_oid

PLAINS = "plains"
INITIATE = "t_flipper"   # {1}{W} 2/2 Human Monk
MASTER = "t_flipped"     # the flipped side: 4/4 legendary flier


def position(builder):
    game = (
        builder(players=2)
        .battlefield(0, [PLAINS] * 4)
        .battlefield(0, [INITIATE])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build(advance=False)
    )
    return game, only_oid(game, INITIATE)


class TestBeforeItFlips:
    def test_it_is_the_printed_creature(self, builder):
        game, monk = position(builder)
        c = chars(game.state, monk)

        assert (c.power, c.toughness) == (2, 2)
        assert Keyword.FLYING.value not in c.keywords

    def test_the_other_side_is_not_a_card_anyone_owns(self, builder):
        """`front_face` is set on it, which is what every deck guard tests."""
        game, _ = position(builder)
        assert game.state.registry.get(MASTER).front_face == INITIATE


class TestFlipping:
    def test_it_becomes_the_other_side(self, builder):
        game, monk = position(builder)
        transform(game.state, monk, to_back=True)

        c = chars(game.state, monk)
        assert (c.power, c.toughness) == (4, 4)
        assert Keyword.FLYING.value in c.keywords

    def test_it_takes_the_supertype_with_it(self, builder):
        """The flipped side is legendary and the unflipped one is not."""
        game, monk = position(builder)
        transform(game.state, monk, to_back=True)

        assert "Legendary" in chars(game.state, monk).supertypes

    def test_card_of_answers_with_it_everywhere(self, builder):
        game, monk = position(builder)
        transform(game.state, monk, to_back=True)

        assert game.state.card_of(game.state.objects[monk]).id == MASTER


class TestItIsTheSamePermanent:
    def test_counters_survive_the_flip(self, builder):
        """711.4, and the reason is that nothing moves."""
        game, monk = position(builder)
        add_counters(game.state, monk, PLUS_ONE, 2)

        transform(game.state, monk, to_back=True)

        assert game.state.objects[monk].counter(PLUS_ONE) == 2
        assert chars(game.state, monk).power == 6, "4/4 plus two counters"

    def test_tapped_stays_tapped(self, builder):
        game, monk = position(builder)
        game.state.objects[monk].tapped = True

        transform(game.state, monk, to_back=True)

        assert game.state.objects[monk].tapped

    def test_it_never_left_the_battlefield(self, builder):
        game, monk = position(builder)
        entered = game.state.objects[monk].entered_turn

        transform(game.state, monk, to_back=True)

        assert game.state.objects[monk].zone is Zone.BATTLEFIELD
        assert game.state.objects[monk].entered_turn == entered


class TestComingBack:
    def test_a_flipped_permanent_that_leaves_returns_unflipped(self, builder):
        """712.13a's rule, shared: a permanent enters front face up."""
        from automtg.engine.zones import move_object

        game, monk = position(builder)
        transform(game.state, monk, to_back=True)

        move_object(game.state, monk, Zone.HAND, to_player=0)

        assert not game.state.objects[monk].transformed
        assert game.state.card_of(game.state.objects[monk]).id == INITIATE

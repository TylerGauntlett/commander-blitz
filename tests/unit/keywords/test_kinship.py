"""Kinship — an upkeep look at the top card, tested against this creature's types.

    "Kinship — At the beginning of your upkeep, you may look at the top card of
    your library. If it shares a creature type with this creature, you may
    reveal it and …"

The census filed this as routed: "`upkeep` trigger; needs to look at the library
top and read its subtypes." Both halves were already there and had never been
put together.

`snapshot` binds the **first** object of a pool, and a library selector is
ordered top-first — which is the Coiling Oracle idiom in card-dsl.md. And
`shares_a_type_with` names a binding, with `self` bound on every trigger. So

    snapshot the top card → `exists` on {binding, zone: library, shares_a_type_with: "self"}

is kinship, with nothing new underneath it.

Two things that would be wrong if this were written the obvious way instead:

- `look_at_top` **moves** what it finds; kinship leaves the card on top whether
  or not it matched, and the card staying is most of what makes the ability
  worth building a deck around.
- `{"exists": {"zone": "library", "subtypes": ["Ox"]}}` asks whether an Ox is
  *anywhere* in the deck, which in an Ox deck is true essentially always — the
  same near miss `top_of_library` exists to refuse for Vampire Nocturnus.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind
from tests.conftest import _default_answer, only_oid

FOREST = "forest"
OX = "t_kinship"          # an Ox
BEAR = "t_bear"           # a Bear
OTHER_OX = "t_echoer"     # also an Ox


def position(builder, top: str):
    return (
        builder(players=2)
        .battlefield(0, [FOREST] * 3)
        .battlefield(0, [OX])
        .library(0, [top] + [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )


#: The Ox is on the battlefield before turn 1's upkeep is advanced past, so the
#: first of *your* upkeeps it sees is turn 3's -- and nothing has been drawn from
#: your library by then, which is what keeps the stacked top where it was put.
FIRST_UPKEEP = 3


def to_kinship_question(game, *, until_turn: int = FIRST_UPKEEP):
    """Run until the "reveal it?" is offered, or ``until_turn`` is over.

    The window is one upkeep on purpose. Kinship fires every upkeep, so a wider
    one would let a later turn's top card answer for the one under test -- the
    negative cases pass vacuously and then start passing for the wrong reason
    once a draw shuffles the stacked library along.
    """
    for _ in range(800):
        decision = game.pending()
        if decision is None or game.state.turn > until_turn:
            return None
        if any(a.kind is ActionKind.YES for a in game.legal_actions()):
            return decision
        game.apply(_default_answer(game, decision))
    return None


class TestTheTypeTest:
    def test_a_sharing_top_card_offers_the_reveal(self, builder):
        game = position(builder, OTHER_OX)
        assert to_kinship_question(game) is not None, "Ox on top of an Ox's deck"

    def test_a_non_sharing_top_card_offers_nothing(self, builder):
        """The `if` is false, so there is no question at all."""
        game = position(builder, BEAR)
        assert to_kinship_question(game) is None

    def test_it_reads_the_top_card_and_not_the_whole_library(self, builder):
        """The near miss: `exists` over the library is true in any Ox deck."""
        game = (
            builder(players=2)
            .battlefield(0, [FOREST] * 3)
            .battlefield(0, [OX])
            .library(0, [BEAR, OTHER_OX] + [FOREST] * 20)
            .library(1, [FOREST] * 20)
            .build()
        )
        assert to_kinship_question(game) is None, "the Ox is second, not on top"


class TestTheEffect:
    def test_accepting_gains_the_life(self, builder):
        game = position(builder, OTHER_OX)
        to_kinship_question(game)
        life = game.state.players[0].life
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))

        assert game.state.players[0].life == life + 2

    def test_the_look_moves_nothing(self, builder):
        """Kinship *looks*; `look_at_top` would have taken the card.

        Asserted while the question is still open, which is the moment that
        separates the two: `look_at_top` moves what it finds before anything is
        asked, so by here the card would already be gone.
        """
        game = position(builder, OTHER_OX)
        before = len(game.state.players[0].library)
        to_kinship_question(game)

        library = game.state.players[0].library
        assert len(library) == before
        assert game.state.objects[library[0]].def_id == OTHER_OX

    def test_declining_gains_nothing(self, builder):
        game = position(builder, OTHER_OX)
        to_kinship_question(game)
        life = game.state.players[0].life
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.NO))

        assert game.state.players[0].life == life


class TestItIsAboutThisCreature:
    def test_a_second_creature_of_another_type_does_not_matter(self, builder):
        """`shares_a_type_with: "self"` — the Bear on the board is not the asker."""
        game = (
            builder(players=2)
            .battlefield(0, [FOREST] * 3)
            .battlefield(0, [OX, BEAR])
            .library(0, [BEAR] + [FOREST] * 20)
            .library(1, [FOREST] * 20)
            .build()
        )
        assert only_oid(game, OX) is not None
        assert to_kinship_question(game) is None, "the Ox does not share with a Bear"

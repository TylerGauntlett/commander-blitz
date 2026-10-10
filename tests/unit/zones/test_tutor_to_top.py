""""…then shuffle and put that card on top" — the order the words are in.

    Forerunner of the Legion — "When this creature enters, you may search your
    library for a Vampire card, reveal it, then shuffle and put that card on
    top."

`search_library` already had `destination: "library_top"`, and it did not work.
`_search` moved the found cards and *then* shuffled (701.19c: a search of a
hidden zone ends in a shuffle), so the card was placed on top and immediately
shuffled back into a random position. A tutor that finds nothing, and nothing on
screen would say so — the search happened, the card was revealed, and the top of
the library was whatever it had always been.

The fix is the printed order, which is also the rules order: the shuffle happens
and *then* the card is put on top. Only `library_top` cares, because a card on
its way to a hand or the battlefield is not in the library to be shuffled.

`reveal` is a flag on the search rather than a second op, because nothing could
name the cards a search had found: `resolve_pool` reaches a pool by `target` or
by `binding`, and a search recorded neither. Revealing on the way out is also
when the printed line says it happens — before the shuffle, not after.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone

FORERUNNER = "t_forerunner"  # searches for a Bear, reveals, shuffles, puts on top
BEAR = "t_bear"
FOREST = "forest"


def board(builder, library):
    """The Forerunner in hand with mana up, and a library to search."""
    return (
        builder(players=2)
        .battlefield(0, [FOREST] * 4)
        .hand(0, [FORERUNNER])
        .library(0, list(library))
        .active(0)
        .max_turns(1)
        .build()
    )


def cast_and_search(game):
    """Cast the Forerunner and *take* the search.

    The search is a "you may", so the passive answer declines it -- and a test
    that declined would pass whatever the shuffle order did. Every CHOOSE is
    taken and then the declaration finished, which picks the one legal card.
    """
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == FORERUNNER
        )
    )
    for _ in range(40):
        decision = game.pending()
        if decision is None:
            break
        actions = game.legal_actions()
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choose = [a for a in actions if a.kind is ActionKind.CHOOSE]
            if choose:
                game.apply(choose[0])
                continue
            finish = [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            if finish:
                game.apply(finish[0])
                continue
        if not game.state.pending_triggers and not game.state.stack:
            break
        passes = [a for a in actions if a.kind is ActionKind.PASS]
        if not passes:
            break
        game.apply(passes[0])


def top_card(game) -> str | None:
    library = game.state.players[0].library
    return game.state.card_of(game.state.objects[library[0]]).id if library else None


class TestTheFoundCardEndsUpOnTop:
    def test_the_bear_is_on_top(self, builder):
        """The whole card. Before the fix this was a random Forest."""
        game = board(builder, [FOREST] * 10 + [BEAR])
        cast_and_search(game)
        assert top_card(game) == BEAR

    def test_it_is_still_in_the_library(self, builder):
        game = board(builder, [FOREST] * 10 + [BEAR])
        before = len(game.state.players[0].library)
        cast_and_search(game)
        assert len(game.state.players[0].library) == before

    def test_the_bear_did_not_go_to_hand(self, builder):
        game = board(builder, [FOREST] * 10 + [BEAR])
        cast_and_search(game)
        hand_ids = [
            game.state.card_of(game.state.objects[o]).id
            for o in game.state.players[0].hand
        ]
        assert BEAR not in hand_ids

    def test_a_library_with_nothing_matching_is_left_alone(self, builder):
        game = board(builder, [FOREST] * 10)
        cast_and_search(game)
        assert all(
            game.state.card_of(game.state.objects[o]).id == FOREST
            for o in game.state.players[0].library
        )


class TestItIsRevealed:
    def test_the_reveal_event_names_the_card(self, builder):
        game = board(builder, [FOREST] * 10 + [BEAR])
        before = len(game.state.events)
        cast_and_search(game)
        reveals = [
            e for e in game.state.events[before:] if e.type == "reveal"
        ]
        assert reveals, "the printed line says to reveal it"
        assert BEAR in reveals[0].data["cards"]

    def test_nothing_is_revealed_when_nothing_is_found(self, builder):
        game = board(builder, [FOREST] * 10)
        before = len(game.state.events)
        cast_and_search(game)
        assert not [e for e in game.state.events[before:] if e.type == "reveal"]


class TestTheShuffleStillHappens:
    def test_the_permanent_is_on_the_battlefield(self, builder):
        """A sanity check that the whole line resolved, not just its tail."""
        game = board(builder, [FOREST] * 10 + [BEAR])
        cast_and_search(game)
        assert any(
            game.state.card_of(game.state.objects[o]).id == FORERUNNER
            for o in game.state.battlefield
        )

    def test_the_library_is_not_left_ordered_by_the_search(self, builder):
        """Only the found card is placed; the rest were shuffled first."""
        game = board(builder, [FOREST] * 10 + [BEAR])
        cast_and_search(game)
        library = game.state.players[0].library
        assert top_card(game) == BEAR
        assert all(
            game.state.objects[o].zone is Zone.LIBRARY for o in library
        )

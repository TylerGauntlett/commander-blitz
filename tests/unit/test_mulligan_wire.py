"""What a mulligan puts on the wire, and why the client needs both halves.

Two fields, both added for ``OpeningHand`` -- the client's full-screen opening
hand -- and both closing the same kind of hole: a fact the engine knew and no
client could reach without parsing a sentence written for a human.

``mulligans_taken`` lived on ``Player`` from the first London-mulligan commit and
was serialised only by ``full_view``, the dev endpoint.  The count reached a
player exactly once, inside the decision's own prompt string --
``"Mulligan? (2 taken)"`` -- which is not a number, it is prose about a number.

``purpose`` is the tag ``ask_objects`` documents itself as carrying so that
"agents and the UI branch on it; without it they would have to pattern-match on
the human-readable prompt".  The bottoming step is a ``CHOOSE_OBJECTS`` like any
other, and the tag is the only thing that says which one it is.

These use ``create_game`` rather than the ``builder`` fixture on purpose:
``engine/sandbox.py`` builds a position "skipping setup and mulligans", so the
one thing under test here does not exist in a built game.
"""

from __future__ import annotations

import pytest

from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.game import create_game
from automtg.engine.serialize import player_view


@pytest.fixture
def opening():
    """A two-player game stopped on seat 0's first mulligan question.

    The real registry, because the decks have to be real: `create_game` takes
    `GameData` and the suite's `registry` fixture is a bare `CardRegistry`.
    """
    game = create_game(["aesi", "edgar"], seed=7)
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.MULLIGAN
    assert decision.player == 0
    return game


def answer(game, kind: ActionKind):
    """Apply the pending decision's action of ``kind``."""
    action = next(a for a in game.legal_actions() if a.kind is kind)
    return game.apply(action)


def test_every_seat_reports_its_mulligan_count(opening):
    """Public, and for every seat -- how many times somebody went back for a new
    hand is not private at a real table."""
    view = player_view(opening.state, 0)
    assert [p["mulligans_taken"] for p in view["players"]] == [0, 0]


def test_the_count_climbs_with_each_mulligan(opening):
    """And it is the same number the prompt has been saying in words."""
    assert "(0 taken)" in opening.pending().prompt
    assert player_view(opening.state, 0)["players"][0]["mulligans_taken"] == 0

    answer(opening, ActionKind.MULLIGAN)

    decision = opening.pending()
    assert decision is not None and decision.kind is DecisionKind.MULLIGAN
    assert "(1 taken)" in decision.prompt
    assert player_view(opening.state, 0)["players"][0]["mulligans_taken"] == 1


def test_the_bottoming_step_names_itself(opening):
    """A mulligan's second question, told apart from every other
    ``choose_objects`` by its tag rather than by its prompt.

    The prompt is asserted too, but only to show that it is the WRONG thing to
    branch on: it is a sentence with a count interpolated into it, and a client
    matching on that is one wording change away from drawing the generic dialog
    over the screen built for this.
    """
    answer(opening, ActionKind.MULLIGAN)
    answer(opening, ActionKind.KEEP)

    decision = opening.pending()
    assert decision is not None
    assert decision.kind is DecisionKind.CHOOSE_OBJECTS
    assert decision.player == 0
    assert decision.context["purpose"] == "mulligan_bottom"
    assert decision.context["source_name"] == "Mulligan"
    # One mulligan taken, so exactly one card goes back -- no more, no fewer.
    assert decision.min_count == decision.max_count == 1
    assert "bottom of your library" in decision.prompt

    # And it survives serialisation, which is the half a client actually sees.
    view = player_view(opening.state, 0)
    assert view["pending"]["context"]["purpose"] == "mulligan_bottom"
    assert view["players"][0]["mulligans_taken"] == 1


def test_one_mulligan_costs_exactly_one_card(opening):
    """The price the screen prints, checked against what the engine charges.

    `OpeningHand` puts "Shuffle back, draw seven, keep 6" under the Mulligan
    button, and a subtitle that is one off is worse than no subtitle -- it is the
    game telling you the wrong price for an irreversible choice. So: seven dealt,
    seven redrawn, one bottomed, six kept.
    """
    assert len(opening.state.players[0].hand) == 7

    answer(opening, ActionKind.MULLIGAN)
    # A mulligan is a whole new seven; the bottoming has not happened yet.
    assert len(opening.state.players[0].hand) == 7

    answer(opening, ActionKind.KEEP)
    assert len(opening.state.players[0].hand) == 7

    answer(opening, ActionKind.CHOOSE)
    assert len(opening.state.players[0].hand) == 6


def test_keeping_on_the_first_ask_bottoms_nothing(opening):
    """The guard that keeps the tag honest.

    ``bottom = min(mulligans_taken, len(hand))``, so a seat that keeps its first
    seven is never asked the second question at all -- which is the common case,
    and the reason the client cannot treat "a mulligan happened" as "a bottoming
    step is coming".
    """
    answer(opening, ActionKind.KEEP)

    decision = opening.pending()
    # Either the game has moved on to the next seat's mulligan or to turn one;
    # either way nothing has asked seat 0 to bottom a card.
    assert decision is None or decision.context.get("purpose") != "mulligan_bottom"
    assert player_view(opening.state, 0)["players"][0]["mulligans_taken"] == 0

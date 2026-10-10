"""Decision options carry a card face, so a prompt is not a row of names.

``DecisionOption`` holds a label and a bare object ref.  The client used to
recover the card itself, from the zones ``player_view`` sends -- which excludes
libraries.  So every "search your library", scry, surveil and mulligan-bottom
prompt degraded to buttons reading only a card name, with no way to see what you
were choosing between.  A cycle-2 playtest finding (item 9).

The face is attached in ``serialize._pending`` rather than in
``PendingDecision.to_dict``, which keeps ``actions.py`` free of display concerns
and leaves the RL/agent path untouched.  The invariant that matters is the seat
guard: only the player who has to answer sees the cards.
"""

from __future__ import annotations

import pytest

from automtg.engine.actions import PendingDecision
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.serialize import player_view
from tests.conftest import action_for_card, pass_until


@pytest.fixture
def searching(builder):
    """A game stopped on "Search your library" for a basic land."""
    game = (
        builder()
        .hand(0, ["rampant_growth"])
        .battlefield(0, ["forest", "forest"])
        .library(0, ["mountain", "plains", "island"])
        .build(advance=False)
    )
    # Priority is handed over explicitly: `advance=True` would auto-pass on a
    # board this quiet and roll the turn past the window we want.
    game.state.pending_decision = PendingDecision(kind=DecisionKind.PRIORITY, player=0)
    game.apply(action_for_card(game, ActionKind.CAST, "rampant_growth"))
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.CHOOSE_OBJECTS,
    )
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS
    return game


def options(view: dict) -> list[dict]:
    return view["pending"]["options"]


class TestLibraryPrompt:
    def test_the_chooser_sees_a_card_on_every_option(self, searching):
        opts = options(player_view(searching.state, 0))
        assert opts, "the search prompt offered nothing"
        for option in opts:
            assert option["card"] is not None, f"{option['label']} has no card face"

    def test_the_card_is_the_one_the_option_refers_to(self, searching):
        for option in options(player_view(searching.state, 0)):
            assert option["card"]["oid"] == option["ref"]["id"]
            assert option["card"]["name"] == option["label"]

    def test_the_face_carries_what_a_card_needs_to_render(self, searching):
        card = options(player_view(searching.state, 0))[0]["card"]
        # The fields CardFace reads. A payload missing any of these renders as a
        # blank frame, which is worse than the name-only button it replaced.
        for field in ("name", "type_line", "mana_cost", "types", "colors", "produces"):
            assert field in card, f"card view is missing {field}"

    def test_library_cards_reach_the_client_no_other_way(self, searching):
        """The precise gap this closes.

        ``player_view`` sends libraries as a count, so the oid on the option ref
        appears in no zone the client can search.  Without the attached face
        there is nothing to render but the label.
        """
        view = player_view(searching.state, 0)
        oid = view["pending"]["options"][0]["ref"]["id"]
        visible = {c["oid"] for c in view["battlefield"]}
        for player in view["players"]:
            for zone in ("hand", "graveyard", "exile", "command"):
                for card in player[zone] or []:
                    visible.add(card["oid"])
        assert oid not in visible


class TestSeatGuard:
    def test_another_seat_gets_the_labels_but_not_the_cards(self, searching):
        """Seat 1 is not the chooser and must not learn seat 0's library."""
        opts = options(player_view(searching.state, 1))
        assert opts, "the decision itself is public"
        assert all("card" not in option for option in opts)

    def test_the_decision_shape_is_otherwise_identical(self, searching):
        mine = player_view(searching.state, 0)["pending"]
        theirs = player_view(searching.state, 1)["pending"]
        assert mine["kind"] == theirs["kind"]
        assert mine["player"] == theirs["player"]
        assert [o["label"] for o in mine["options"]] == [
            o["label"] for o in theirs["options"]
        ]


class TestOtherDecisions:
    def test_a_visible_zone_prompt_also_gets_faces(self, builder):
        """Sacrifice/discard prompts already rendered; they must keep doing so."""
        game = builder().battlefield(0, ["t_bear", "forest"]).build(advance=False)
        state = game.state
        state.pending_decision = PendingDecision(
            kind=DecisionKind.CHOOSE_OBJECTS,
            player=0,
            prompt="Sacrifice a permanent",
            options=tuple(
                _option(state, oid) for oid in state.battlefield
            ),
            min_count=1,
            max_count=1,
        )
        assert all(o["card"] is not None for o in options(player_view(state, 0)))

    def test_an_option_with_no_object_ref_is_left_alone(self, builder):
        """Yes/no and modal prompts have nothing to draw, and must not crash."""
        game = builder().build(advance=False)
        state = game.state
        state.pending_decision = PendingDecision(
            kind=DecisionKind.MAY,
            player=0,
            prompt="Draw a card?",
            options=_yes_no(),
            min_count=1,
            max_count=1,
        )
        assert [o["label"] for o in options(player_view(state, 0))] == ["Yes", "No"]
        assert all("card" not in o for o in options(player_view(state, 0)))

    def test_no_decision_serializes_as_none(self, builder):
        game = builder().build(advance=False)
        game.state.pending_decision = None
        assert player_view(game.state, 0)["pending"] is None


def _option(state, oid: int):
    from automtg.engine.actions import DecisionOption
    from automtg.engine.structs import TargetRef

    return DecisionOption(
        label=state.card(oid).name, ref=TargetRef.obj(oid), value=oid
    )


def _yes_no():
    from automtg.engine.actions import DecisionOption

    return (
        DecisionOption(label="Yes", value=True),
        DecisionOption(label="No", value=False),
    )

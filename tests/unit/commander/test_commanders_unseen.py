"""A seat's commander stays on the wire when it leaves every zone the view sends.

The client draws each seat's commander as that seat's portrait, and found it by
searching the zones `player_view` sends. Oubliette phases a commander out, a
phased-out permanent leaves `state.battlefield` (702.26), and the portrait --
the one thing that says whose seat this is -- vanished with it.
`commanders_unseen` is the commander's identity, sent for exactly those cases.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Zone
from commanderblitz.engine.serialize import player_view
from commanderblitz.engine.turn import phase_out
from commanderblitz.engine.zones import move_object

GENERAL = "t_cz_general"


def board(builder):
    return (
        builder(players=2)
        .commander(0, [GENERAL])
        .library(0, ["forest"] * 5)
        .library(1, ["forest"] * 5)
        .build()
    )


def unseen(game, pid: int, seat: int) -> list[dict]:
    return player_view(game.state, seat)["players"][pid]["commanders_unseen"]


def test_a_commander_in_a_sent_zone_is_not_repeated(builder):
    game = board(builder)
    assert unseen(game, 0, 0) == []


def test_a_phased_out_commander_is_sent_to_every_seat(builder):
    game = board(builder)
    oid = game.state.players[0].commanders[0]
    move_object(game.state, oid, Zone.BATTLEFIELD)
    phase_out(game.state, oid)

    view = player_view(game.state, 1)
    assert all(card["oid"] != oid for card in view["battlefield"])
    for seat in (0, 1):
        [card] = unseen(game, 0, seat)
        assert card["oid"] == oid
        assert card["card_id"] == GENERAL
        assert card["phased_out"] is True


def test_a_commander_in_a_hidden_zone_is_sent_without_its_neighbours(builder):
    game = board(builder)
    state = game.state
    oid = state.players[0].commanders[0]
    # Placed by hand rather than moved: 903.9a offers the command zone instead,
    # and what is under test is the view of a commander that is in the library.
    state.players[0].command.remove(oid)
    state.players[0].library.insert(0, oid)
    state.objects[oid].zone = Zone.LIBRARY

    [card] = unseen(game, 0, 1)
    assert card["oid"] == oid
    assert card["zone"] == "library"
    assert "phased_out" not in card

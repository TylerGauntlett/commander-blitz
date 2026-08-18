"""A game with two humans in it.

Everything downstream of the deal.  The engine has always been N-seat, so what
is actually new here is the authorisation boundary -- one token, one seat -- and
the two places the old single-player code leaked across it: the event log, which
was global, and undo, which rebuilds the game.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from automtg.cards.registry import default_registry
from automtg.server.app import create_app


@pytest.fixture(scope="module")
def data():
    return default_registry()


@pytest.fixture
def client(data) -> TestClient:
    return TestClient(create_app(data, allow_art_fetch=False))


def auth(token: str) -> dict[str, str]:
    return {"X-Player-Token": token}


def dealt(client: TestClient, *, seed: int = 7) -> tuple[str, str, str]:
    """A two-human game over the pod flow.  Returns ``(game_id, host, guest)``."""
    opened = client.post(
        "/api/pods", json={"name": "Host", "deck_id": "aesi", "seed": seed}
    ).json()
    code, host = opened["pod"]["code"], opened["player_token"]
    guest = client.post(f"/api/pods/{code}/join", json={"name": "Guest"}).json()["player_token"]
    client.patch(
        f"/api/pods/{code}/seat",
        json={"deck_id": "edgar", "locked": True},
        headers=auth(guest),
    )
    client.patch(f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(host))
    view = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()
    return view["game_id"], host, guest


def state(client: TestClient, game_id: str, token: str, **params) -> dict:
    response = client.get(
        f"/api/games/{game_id}/state", headers=auth(token), params=params
    )
    assert response.status_code == 200, response.text
    return response.json()


def _pick(actions: list[dict]) -> dict:
    """The same crude, decisive policy ``test_api.py`` plays with."""
    for kind in ("play_land", "cast", "add_attacker", "choose", "yes", "keep"):
        for action in actions:
            if action["kind"] == kind:
                return action
    return actions[0]


class TestTokenAuth:
    def test_your_token_tells_you_your_seat(self, client):
        game_id, host, guest = dealt(client)
        assert state(client, game_id, host)["your_seat"] == 0
        assert state(client, game_id, guest)["your_seat"] == 1

    def test_a_seat_that_is_not_yours_is_a_403(self, client):
        game_id, _host, guest = dealt(client)
        response = client.get(f"/api/games/{game_id}/state?seat=0", headers=auth(guest))
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "not_your_seat"

    def test_acting_as_somebody_else_is_a_403(self, client):
        game_id, host, guest = dealt(client)
        actions = state(client, game_id, host)["actions"]
        response = client.post(
            f"/api/games/{game_id}/actions",
            json={"seat": 0, "action_id": actions[0]["id"]},
            headers=auth(guest),
        )
        assert response.status_code == 403

    def test_no_token_at_all_is_a_403(self, client):
        """A `game_id` on its own must not be enough to read a hand."""
        game_id, _, _ = dealt(client)
        assert client.get(f"/api/games/{game_id}/state?seat=1").status_code == 403

    def test_a_session_with_no_token_map_still_accepts_any_seat(self, client):
        """The regression guard for the CLI, `smoke_http.py` and single-player.

        Making the token map optional is the whole reason none of those had to
        change, so it is worth a test that says so out loud.
        """
        body = client.post(
            "/api/games",
            json={
                "seats": [
                    {"deck_id": "aesi", "kind": "human"},
                    {"deck_id": "edgar", "kind": "ai"},
                ],
                "seed": 3,
            },
        ).json()
        game_id = body["game_id"]
        assert client.get(f"/api/games/{game_id}/state?seat=1").status_code == 200


class TestTwoHumans:
    def test_a_full_game_is_played_to_a_result(self, client):
        """Both seats driven by the same policy, alternating on whoever is up."""
        game_id, host, guest = dealt(client, seed=11)
        tokens = {0: host, 1: guest}
        seen_seats = set()

        current = state(client, game_id, host)
        for _ in range(6000):
            if current["state"]["game_over"]:
                break
            pending = current["state"]["pending"]
            if pending is None:
                break
            seat = pending["player"]
            seen_seats.add(seat)
            view = state(client, game_id, tokens[seat])
            if not view["actions"]:
                break
            response = client.post(
                f"/api/games/{game_id}/actions",
                json={"seat": seat, "action_id": _pick(view["actions"])["id"]},
                headers=auth(tokens[seat]),
            )
            assert response.status_code == 200, response.text
            current = response.json()

        assert current["state"]["game_over"], "the game never finished"
        assert current["state"]["result"] in ("win", "draw")
        assert seen_seats == {0, 1}, "one of the humans never got a decision"

    def test_each_seat_only_ever_sees_its_own_hand(self, client):
        game_id, host, guest = dealt(client)
        for seat, token in ((0, host), (1, guest)):
            players = state(client, game_id, token)["state"]["players"]
            assert players[seat]["hand"] is not None
            assert players[1 - seat]["hand"] is None
            assert players[1 - seat]["hand_count"] >= 1


def put_on_battlefield(client: TestClient, game_id: str, seat: int, card_id: str) -> int:
    """Drop a permanent straight onto ``seat``'s battlefield, mid-session.

    The two top-card statics only ever arrive by playing a creature, and no
    policy this file can write will reliably draw and cast a particular one. The
    boundary under test is HTTP, not the cast, so the board is arranged directly
    and then read back through the endpoint like any other state.
    """
    from automtg.engine.enums import Zone
    from automtg.engine.state import new_object

    session = client.app.state.sessions.get(game_id)
    with session._lock:
        obj = new_object(session.game.state, card_id, owner=seat, zone=Zone.BATTLEFIELD)
        session.game.state.battlefield.append(obj.oid)
        session.game.state.bump_chars()
    return obj.oid


class TestTopCardVisibility:
    """The top of a library reaches a seat two ways, and they differ in *who*.

    `reveal_library_top` is Vampire Nocturnus -- the card is public, so it is
    sent to every seat. `look_at_library_top` is Verge Rangers -- "you may look
    at the top card of your library any time", which shows the card to nobody
    else. Serving the private one to an opponent would be the same class of leak
    as serving them a hand, so it is asserted here, at the HTTP boundary, from
    the seat that must not see it.
    """

    def test_the_controller_is_sent_their_own_top_card(self, client):
        game_id, host, _guest = dealt(client)
        put_on_battlefield(client, game_id, 0, "verge_rangers")
        players = state(client, game_id, host)["state"]["players"]
        assert players[0]["library_top"] is not None
        assert players[0]["library_top_public"] is False

    def test_the_opponent_is_not(self, client):
        """The whole reason `look_at_library_top` is not `reveal_library_top`."""
        game_id, _host, guest = dealt(client)
        put_on_battlefield(client, game_id, 0, "verge_rangers")
        players = state(client, game_id, guest)["state"]["players"]
        assert players[0]["library_top"] is None
        assert players[0]["library_top_public"] is False
        assert players[0]["library_count"] >= 1, "…while the count is public as ever"

    def test_a_revealed_top_card_still_reaches_both_seats(self, client):
        game_id, host, guest = dealt(client)
        put_on_battlefield(client, game_id, 0, "vampire_nocturnus")
        for token in (host, guest):
            players = state(client, game_id, token)["state"]["players"]
            assert players[0]["library_top"] is not None
            assert players[0]["library_top_public"] is True

    def test_neither_seat_sees_a_top_card_with_nothing_showing_it(self, client):
        game_id, host, guest = dealt(client)
        for token in (host, guest):
            for player in state(client, game_id, token)["state"]["players"]:
                assert player["library_top"] is None
                assert player["library_top_public"] is False


class TestEventRedaction:
    """``player_view`` hid the hands; the event log ran alongside it unfiltered.

    Structurally parallel to ``TestHiddenInformation`` in ``test_api.py``, and
    for the same reason: an opaque object id is not a card name today, but the
    client accumulates every id it has ever seen, so an id drawn now and played
    later is retroactively identified.
    """

    def test_another_seats_draws_carry_no_object_id(self, client):
        game_id, _host, guest = dealt(client)
        events = state(client, game_id, guest)["events"]
        theirs = [e for e in events if e["type"] == "draw" and e["player"] == 0]
        assert theirs, "seat 0 never drew, so this test proves nothing"
        for event in theirs:
            assert event["source"] is None
            assert "oid" not in event["data"]

    def test_your_own_draws_are_untouched(self, client):
        game_id, _host, guest = dealt(client)
        events = state(client, game_id, guest)["events"]
        mine = [e for e in events if e["type"] == "draw" and e["player"] == 1]
        assert mine and all(e["data"].get("oid") is not None for e in mine)

    def test_the_event_is_still_there_so_the_play_by_play_reads(self, client):
        """A silently shorter log is indistinguishable from a bug."""
        game_id, host, guest = dealt(client)
        mine = state(client, game_id, host)["events"]
        theirs = state(client, game_id, guest)["events"]
        assert len(mine) == len(theirs)
        assert [e["type"] for e in mine] == [e["type"] for e in theirs]

    def test_public_events_are_identical_for_both_seats(self, client):
        game_id, host, guest = dealt(client)
        private = {"draw", "discard", "mill"}
        mine = [e for e in state(client, game_id, host)["events"] if e["type"] not in private]
        theirs = [e for e in state(client, game_id, guest)["events"] if e["type"] not in private]
        assert mine == theirs

    def test_the_debug_endpoint_still_reveals_everything(self, client):
        """The dev endpoint is the deliberate exception and must stay separate."""
        game_id, _, _ = dealt(client)
        body = client.get(f"/api/games/{game_id}/debug").json()
        assert body["players"][1]["zones"]["hand"]


class TestUndoRefused:
    def test_undo_is_refused_with_two_humans(self, client):
        """Replay builds a new Game; the other player is holding the old one."""
        game_id, host, _ = dealt(client)
        actions = state(client, game_id, host)["actions"]
        client.post(
            f"/api/games/{game_id}/actions",
            json={"seat": 0, "action_id": actions[0]["id"]},
            headers=auth(host),
        )
        response = client.post(
            f"/api/games/{game_id}/undo", json={"seat": 0}, headers=auth(host)
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "multiplayer_undo"

    def test_undo_still_works_in_a_single_human_game(self, client):
        body = client.post(
            "/api/games",
            json={
                "seats": [
                    {"deck_id": "aesi", "kind": "human"},
                    {"deck_id": "edgar", "kind": "ai"},
                ],
                "seed": 11,
            },
        ).json()
        game_id = body["game_id"]
        client.post(
            f"/api/games/{game_id}/actions",
            json={"seat": 0, "action_id": body["actions"][0]["id"]},
        )
        assert client.post(f"/api/games/{game_id}/undo", json={"seat": 0}).status_code == 200


class TestGameLongPoll:
    def test_the_first_fetch_returns_immediately(self, client):
        game_id, host, _ = dealt(client)
        started = time.monotonic()
        state(client, game_id, host)
        assert time.monotonic() - started < 1.0

    def test_a_poll_that_finds_nothing_returns_the_same_version(self, client):
        game_id, _, guest = dealt(client)
        current = state(client, game_id, guest)["version"]
        polled = state(client, game_id, guest, since_version=current, timeout=0.4)
        assert polled["version"] == current

    def test_the_other_seat_acting_wakes_a_waiter(self, client):
        game_id, host, guest = dealt(client)
        current = state(client, game_id, guest)["version"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            waiting = pool.submit(
                client.get,
                f"/api/games/{game_id}/state",
                headers=auth(guest),
                params={"since_version": current, "timeout": 20},
            )
            time.sleep(0.3)
            actions = state(client, game_id, host)["actions"]
            pool.submit(
                client.post,
                f"/api/games/{game_id}/actions",
                json={"seat": 0, "action_id": _pick(actions)["id"]},
                headers=auth(host),
            ).result()
            started = time.monotonic()
            woken = waiting.result(timeout=20)

        assert woken.status_code == 200
        assert woken.json()["version"] > current
        assert time.monotonic() - started < 15.0

"""Dropping out and coming back.

The whole reconnect story is one sentence: the token is the identity, and it
outlives the connection.  A refreshed tab hands back the token it kept in
``sessionStorage`` and is indistinguishable from one that never left.

These are the cases where that sentence has to actually hold.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from automtg.cards.registry import default_registry
from automtg.server import lobby as L
from automtg.server.app import create_app


@pytest.fixture(scope="module")
def data():
    return default_registry()


@pytest.fixture
def client(data) -> TestClient:
    return TestClient(create_app(data, allow_art_fetch=False))


def auth(token: str) -> dict[str, str]:
    return {"X-Player-Token": token}


def pod_with_guest(client: TestClient) -> tuple[str, str, str]:
    opened = client.post(
        "/api/pods", json={"name": "Host", "deck_id": "aesi", "seed": 5}
    ).json()
    code, host = opened["pod"]["code"], opened["player_token"]
    guest = client.post(f"/api/pods/{code}/join", json={"name": "Guest"}).json()["player_token"]
    return code, host, guest


class TestMidLobby:
    def test_rejoining_restores_the_same_seat_and_deck(self, client):
        code, _host, guest = pod_with_guest(client)
        client.patch(f"/api/pods/{code}/seat", json={"deck_id": "zurgo"}, headers=auth(guest))

        back = client.post(
            f"/api/pods/{code}/join", json={"name": "Guest"}, headers=auth(guest)
        )
        assert back.status_code == 201
        view = back.json()["pod"]
        assert view["your_seat"] == 1
        assert view["seats"][1]["deck"]["id"] == "zurgo"

    def test_rejoining_does_not_take_a_second_chair(self, client):
        code, _host, guest = pod_with_guest(client)
        for _ in range(3):
            client.post(f"/api/pods/{code}/join", json={"name": "Guest"}, headers=auth(guest))
        kinds = [s["kind"] for s in client.get(f"/api/pods/{code}").json()["seats"]]
        assert kinds == ["human", "human", "empty", "empty"]

    def test_the_token_you_get_back_is_the_one_you_sent(self, client):
        code, _, guest = pod_with_guest(client)
        again = client.post(
            f"/api/pods/{code}/join", json={"name": "Guest"}, headers=auth(guest)
        ).json()
        assert again["player_token"] == guest

    def test_the_host_who_comes_back_is_still_the_host(self, client):
        code, host, _ = pod_with_guest(client)
        back = client.post(
            f"/api/pods/{code}/join", json={"name": "Host"}, headers=auth(host)
        ).json()
        assert back["pod"]["you_are_host"]

    def test_reading_the_pod_with_a_stale_token_still_works_blind(self, client):
        """A dead end here would turn a reconnect into a dead end, not a rejoin."""
        code, _, _ = pod_with_guest(client)
        response = client.get(f"/api/pods/{code}", headers=auth("not-a-real-token"))
        assert response.status_code == 200
        assert response.json()["your_seat"] is None


class TestAfterTheDeal:
    def _deal(self, client) -> tuple[str, str, str, str]:
        code, host, guest = pod_with_guest(client)
        client.patch(
            f"/api/pods/{code}/seat",
            json={"deck_id": "edgar", "locked": True},
            headers=auth(guest),
        )
        client.patch(f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(host))
        game_id = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()["game_id"]
        return code, host, guest, game_id

    def test_rejoining_routes_you_to_the_table(self, client):
        code, _host, guest, game_id = self._deal(client)
        response = client.post(
            f"/api/pods/{code}/join", json={"name": "Guest"}, headers=auth(guest)
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "already_started"
        assert detail["game_id"] == game_id

    def test_the_pod_still_says_where_the_game_is(self, client):
        """A client that polls after the transition is told, not left hanging."""
        code, _, guest, game_id = self._deal(client)
        view = client.get(f"/api/pods/{code}", headers=auth(guest)).json()
        assert view["status"] == "in_game" and view["game_id"] == game_id

    def test_the_token_still_authorises_against_the_game(self, client):
        _code, _host, guest, game_id = self._deal(client)
        response = client.get(f"/api/games/{game_id}/state", headers=auth(guest))
        assert response.status_code == 200
        assert response.json()["your_seat"] == 1

    def test_a_returning_player_picks_the_game_up_mid_turn(self, client):
        _code, host, _guest, game_id = self._deal(client)
        first = client.get(f"/api/games/{game_id}/state", headers=auth(host)).json()
        client.post(
            f"/api/games/{game_id}/actions",
            json={"seat": 0, "action_id": first["actions"][0]["id"]},
            headers=auth(host),
        )
        # A brand-new client with nothing but the stored token and game id.
        fresh = client.get(f"/api/games/{game_id}/state", headers=auth(host)).json()
        assert fresh["version"] > first["version"]
        assert fresh["state"]["players"][0]["hand"] is not None


class TestSweptPlayers:
    def test_an_idle_player_loses_their_chair(self, client):
        code, host, _guest = pod_with_guest(client)
        pods = client.app.state.pods
        pod = pods.get(code)
        # Keep the host alive; only the guest has gone quiet.
        later = L.PLAYER_TTL_SECONDS + 1
        for player in pod.players.values():
            if player.token == host:
                player.last_seen += later
        pods.sweep(now=pod.created + later)

        assert client.get(f"/api/pods/{code}").json()["seats"][1]["kind"] == "open"

    def test_a_swept_players_token_no_longer_authorises(self, client):
        code, host, guest = pod_with_guest(client)
        pods = client.app.state.pods
        pod = pods.get(code)
        later = L.PLAYER_TTL_SECONDS + 1
        for player in pod.players.values():
            if player.token == host:
                player.last_seen += later
        pods.sweep(now=pod.created + later)

        response = client.patch(
            f"/api/pods/{code}/seat", json={"deck_id": "aesi"}, headers=auth(guest)
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "bad_token"

    def test_but_the_chair_is_free_to_take_again(self, client):
        """Being swept is not a ban -- the same person just rejoins."""
        code, host, guest = pod_with_guest(client)
        pods = client.app.state.pods
        pod = pods.get(code)
        later = L.PLAYER_TTL_SECONDS + 1
        for player in pod.players.values():
            if player.token == host:
                player.last_seen += later
        pods.sweep(now=pod.created + later)

        back = client.post(
            f"/api/pods/{code}/join", json={"name": "Guest"}, headers=auth(guest)
        )
        assert back.status_code == 201
        assert back.json()["pod"]["your_seat"] == 1
        assert back.json()["player_token"] != guest

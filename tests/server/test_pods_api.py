"""The pod HTTP surface.

``test_lobby.py`` covers the rules; this file covers the wire -- status codes,
the token header, and the long-poll semantics that the client's whole
refresh strategy is built on.

Each test gets a fresh app.  Pods live in process memory keyed by a random code,
so a module-scoped client would let one test's abandoned pod be swept in the
middle of another's.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from commanderblitz.cards.registry import default_registry
from commanderblitz.server.app import create_app


@pytest.fixture(scope="module")
def data():
    return default_registry()


@pytest.fixture
def client(data) -> TestClient:
    return TestClient(create_app(data, allow_art_fetch=False))


def auth(token: str) -> dict[str, str]:
    return {"X-Player-Token": token}


def create(client: TestClient, **body) -> tuple[str, str, dict]:
    """Open a pod.  Returns ``(code, host_token, view)``."""
    response = client.post("/api/pods", json={"name": "Host", **body})
    assert response.status_code == 201, response.text
    payload = response.json()
    return payload["pod"]["code"], payload["player_token"], payload["pod"]


def join(client: TestClient, code: str, name="Guest", **kwargs) -> tuple[str, dict]:
    response = client.post(f"/api/pods/{code}/join", json={"name": name}, **kwargs)
    assert response.status_code == 201, response.text
    payload = response.json()
    return payload["player_token"], payload["pod"]


def ready_pod(client: TestClient, *, seed: int | None = 7) -> tuple[str, str, str]:
    """A host and a guest, both locked in.  Returns ``(code, host, guest)``."""
    code, host, _ = create(client, deck_id="aesi", seed=seed)
    guest, _ = join(client, code)
    client.patch(
        f"/api/pods/{code}/seat", json={"deck_id": "edgar", "locked": True}, headers=auth(guest)
    )
    client.patch(f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(host))
    return code, host, guest


class TestCreateAndJoin:
    def test_creating_seats_the_host_and_issues_a_token(self, client):
        code, token, view = create(client, deck_id="aesi")
        assert token
        assert view["your_seat"] == 0 and view["you_are_host"]
        assert len(view["seats"]) == 4
        assert view["seats"][0]["kind"] == "human"
        assert [s["kind"] for s in view["seats"][1:]] == ["empty"] * 3
        assert view["status"] == "open"
        # The exact shape, not just the code: the client routes on this path,
        # so a change to it is a change to where an invite link lands.
        assert view["invite_link"] == f"/pods/{code}"

    def test_the_code_looks_like_a_code(self, client):
        code, _, _ = create(client)
        word, _, digits = code.partition("-")
        assert word.isalpha() and word.isupper() and len(digits) == 4

    def test_a_guest_takes_the_next_chair(self, client):
        code, _, _ = create(client)
        _, view = join(client, code, "Priya")
        assert view["your_seat"] == 1 and not view["you_are_host"]
        assert view["seats"][1]["name"] == "Priya"

    def test_a_code_read_aloud_still_joins(self, client):
        code, _, _ = create(client)
        _token, view = join(client, code.lower().replace("-", ""))
        assert view["code"] == code

    def test_a_bad_code_is_a_404(self, client):
        response = client.post("/api/pods/GYRE-0000/join", json={"name": "Nobody"})
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"

    def test_the_same_token_twice_is_the_same_seat(self, client):
        code, _, _ = create(client)
        token, first = join(client, code)
        _, again = join(client, code, "Renamed", headers=auth(token))
        assert again["your_seat"] == first["your_seat"]
        assert [s["kind"] for s in again["seats"]] == [s["kind"] for s in first["seats"]]

    def test_a_full_pod_is_a_409(self, client):
        code, _, _ = create(client)
        for i in range(3):
            join(client, code, f"Guest {i}")
        response = client.post(f"/api/pods/{code}/join", json={"name": "Fifth"})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "pod_full"

    def test_joining_a_dealt_pod_carries_the_game_id(self, client):
        """So a latecomer is routed to the table rather than bounced."""
        code, host, _ = ready_pod(client)
        game_id = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()["game_id"]
        response = client.post(f"/api/pods/{code}/join", json={"name": "Late"})
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "already_started" and detail["game_id"] == game_id

    def test_creating_with_an_unknown_deck_is_a_400(self, client):
        response = client.post("/api/pods", json={"name": "Host", "deck_id": "nope"})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "unknown_deck"


class TestAuthorisation:
    def test_no_token_cannot_mutate(self, client):
        code, _, _ = create(client)
        assert client.patch(f"/api/pods/{code}/seat", json={"deck_id": "aesi"}).status_code == 401

    def test_a_guest_cannot_patch_the_hosts_seat(self, client):
        code, _host, _ = create(client, deck_id="aesi")
        guest, _ = join(client, code)
        response = client.patch(
            f"/api/pods/{code}/seats/0",
            json={"action": "clear"},
            headers=auth(guest),
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "not_host"

    def test_a_guest_cannot_administer_a_seat(self, client):
        code, _, _ = create(client)
        guest, _ = join(client, code)
        response = client.patch(
            f"/api/pods/{code}/seats/2", json={"action": "add_cpu"}, headers=auth(guest)
        )
        assert response.status_code == 403

    def test_not_even_the_host_touches_a_players_chair(self, client):
        code, host, _ = create(client)
        join(client, code)
        response = client.patch(
            f"/api/pods/{code}/seats/1", json={"action": "clear"}, headers=auth(host)
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "not_your_seat"

    def test_a_token_from_one_pod_is_useless_in_another(self, client):
        _, first, _ = create(client)
        second_code, _, _ = create(client)
        response = client.patch(
            f"/api/pods/{second_code}/seat", json={"deck_id": "aesi"}, headers=auth(first)
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "bad_token"

    def test_reading_without_a_token_is_allowed_and_blind(self, client):
        """An invite link renders the pod before anybody has joined it."""
        code, host, _ = create(client, deck_id="aesi")
        client.patch(f"/api/pods/{code}/seat", json={"deck_id": "zurgo"}, headers=auth(host))
        view = client.get(f"/api/pods/{code}").json()
        assert view["your_seat"] is None
        assert view["seats"][0]["deck"] is None


class TestSeatAdmin:
    def test_each_action_lands_on_the_seat(self, client):
        code, host, view = create(client)
        version = view["version"]

        after = client.patch(
            f"/api/pods/{code}/seats/1",
            json={"action": "add_cpu", "deck_id": "edgar", "agent": "random"},
            headers=auth(host),
        ).json()
        assert after["version"] > version
        seat = after["seats"][1]
        assert (seat["kind"], seat["deck"]["id"], seat["agent"]) == ("cpu", "edgar", "random")
        assert seat["ready"]

        after = client.patch(
            f"/api/pods/{code}/seats/1",
            json={"action": "set_deck", "deck_id": "zurgo"},
            headers=auth(host),
        ).json()
        assert after["seats"][1]["deck"]["id"] == "zurgo"

        after = client.patch(
            f"/api/pods/{code}/seats/1", json={"action": "open_chair"}, headers=auth(host)
        ).json()
        assert after["seats"][1]["kind"] == "open"

        after = client.patch(
            f"/api/pods/{code}/seats/1", json={"action": "clear"}, headers=auth(host)
        ).json()
        assert after["seats"][1]["kind"] == "empty"

    def test_set_deck_with_an_unknown_deck_is_a_400(self, client):
        code, host, _ = create(client)
        client.patch(
            f"/api/pods/{code}/seats/1", json={"action": "add_cpu"}, headers=auth(host)
        )
        response = client.patch(
            f"/api/pods/{code}/seats/1",
            json={"action": "set_deck", "deck_id": "black_lotus"},
            headers=auth(host),
        )
        assert response.status_code == 400

    def test_an_out_of_range_seat_is_a_404(self, client):
        code, host, _ = create(client)
        response = client.patch(
            f"/api/pods/{code}/seats/9", json={"action": "add_cpu"}, headers=auth(host)
        )
        assert response.status_code == 404


class TestLockIn:
    def test_lock_and_unlock(self, client):
        code, host, _ = create(client, deck_id="aesi")
        view = client.patch(
            f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(host)
        ).json()
        assert view["seats"][0]["locked"] and view["seats"][0]["ready"]
        view = client.patch(
            f"/api/pods/{code}/seat", json={"locked": False}, headers=auth(host)
        ).json()
        assert not view["seats"][0]["locked"]

    def test_locking_with_no_deck_is_a_409(self, client):
        code, host, _ = create(client)
        response = client.patch(
            f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(host)
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "not_ready"

    def test_a_guests_deck_appears_to_the_host_only_on_lock(self, client):
        code, host, _ = create(client, deck_id="aesi")
        guest, _ = join(client, code)
        client.patch(f"/api/pods/{code}/seat", json={"deck_id": "edgar"}, headers=auth(guest))

        assert client.get(f"/api/pods/{code}", headers=auth(host)).json()["seats"][1]["deck"] is None
        client.patch(f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(guest))
        seen = client.get(f"/api/pods/{code}", headers=auth(host)).json()["seats"][1]["deck"]
        assert seen["id"] == "edgar"


class TestNaming:
    """Who you are at this table, said from your own chair.

    The front door does not ask -- it is two buttons and a code field -- so an
    unnamed chair is named after its seat and you rename from the plate.
    """

    def test_an_unnamed_chair_is_named_after_its_seat(self, client):
        """Not "You": a host who never renames would have the rest of the pod
        reading "Waiting on You" about somebody else.

        Posted raw rather than through the ``create``/``join`` helpers, which
        both send a name -- this is the shape the *client* sends, which stopped
        carrying one when the field moved off the front door.
        """
        opened = client.post("/api/pods", json={}).json()
        code = opened["pod"]["code"]
        assert opened["pod"]["seats"][0]["name"] == "Player 1"

        joined = client.post(f"/api/pods/{code}/join", json={}).json()
        assert joined["pod"]["seats"][1]["name"] == "Player 2"

    def test_you_can_rename_your_own_seat(self, client):
        code, host, _ = create(client)
        view = client.patch(
            f"/api/pods/{code}/seat", json={"name": "Tyler"}, headers=auth(host)
        ).json()
        assert view["seats"][0]["name"] == "Tyler"

    def test_the_rest_of_the_pod_sees_it(self, client):
        code, host, _ = create(client)
        guest, _ = join(client, code)
        client.patch(f"/api/pods/{code}/seat", json={"name": "Tyler"}, headers=auth(host))
        seen = client.get(f"/api/pods/{code}", headers=auth(guest)).json()
        assert seen["seats"][0]["name"] == "Tyler"

    def test_a_rename_moves_the_version(self, client):
        """The whole multiplayer story is the long poll: a rename that did not
        wake it would be invisible until some unrelated change came along."""
        code, host, view = create(client)
        after = client.patch(
            f"/api/pods/{code}/seat", json={"name": "Tyler"}, headers=auth(host)
        ).json()
        assert after["version"] > view["version"]

    def test_whitespace_is_collapsed(self, client):
        code, host, _ = create(client)
        view = client.patch(
            f"/api/pods/{code}/seat", json={"name": "  Ty    ler  "}, headers=auth(host)
        ).json()
        assert view["seats"][0]["name"] == "Ty ler"

    def test_a_blank_name_is_refused(self, client):
        code, host, _ = create(client)
        response = client.patch(
            f"/api/pods/{code}/seat", json={"name": "   "}, headers=auth(host)
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "bad_name"

    def test_a_name_past_the_cap_is_refused(self, client):
        code, host, _ = create(client)
        response = client.patch(
            f"/api/pods/{code}/seat", json={"name": "x" * 25}, headers=auth(host)
        )
        assert response.status_code == 422

    def test_renaming_leaves_the_deck_and_the_lock_alone(self, client):
        """Not gated on `locked`: the lock commits a *deck*, and making somebody
        unlock -- which un-readies the pod for everybody -- to fix a typo would
        be a worse rule than the one it enforced."""
        code, host, _ = create(client, deck_id="aesi")
        client.patch(f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(host))
        view = client.patch(
            f"/api/pods/{code}/seat", json={"name": "Tyler"}, headers=auth(host)
        ).json()
        assert view["seats"][0]["locked"]
        assert view["seats"][0]["deck"]["id"] == "aesi"
        assert view["seats"][0]["name"] == "Tyler"

    def test_renaming_after_the_deal_is_refused(self, client):
        code, host, _ = ready_pod(client)
        client.post(f"/api/pods/{code}/start", headers=auth(host))
        response = client.patch(
            f"/api/pods/{code}/seat", json={"name": "Tyler"}, headers=auth(host)
        )
        assert response.status_code == 409

    def test_a_rename_reaches_the_table(self, client):
        """The point of the field. `SeatConfig(name=seat.name)` at deal time is
        what carries it into the game, and a rename that stopped at the lobby
        would be a name nobody at the table ever sees."""
        code, host, guest = ready_pod(client)
        client.patch(f"/api/pods/{code}/seat", json={"name": "Tyler"}, headers=auth(host))
        client.patch(f"/api/pods/{code}/seat", json={"name": "Priya"}, headers=auth(guest))
        game_id = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()["game_id"]

        state = client.get(f"/api/games/{game_id}/state", headers=auth(host)).json()["state"]
        assert [player["name"] for player in state["players"]] == ["Tyler", "Priya"]

    def test_a_name_given_at_the_door_still_works(self, client):
        """Nothing in the client sends one any more, but the field is still on
        `CreatePodRequest` and `scripts/smoke_http.py` uses it."""
        _, _, view = create(client, name="Scripted")
        assert view["seats"][0]["name"] == "Scripted"


class TestStart:
    def test_a_solo_pod_cannot_deal(self, client):
        code, host, _ = create(client, deck_id="aesi")
        client.patch(f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(host))
        response = client.post(f"/api/pods/{code}/start", headers=auth(host))
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "not_ready"

    def test_an_unlocked_guest_blocks_the_deal(self, client):
        code, host, _ = create(client, deck_id="aesi")
        guest, _ = join(client, code)
        client.patch(f"/api/pods/{code}/seat", json={"deck_id": "edgar"}, headers=auth(guest))
        client.patch(f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(host))
        assert client.post(f"/api/pods/{code}/start", headers=auth(host)).status_code == 409

    def test_an_unlocked_host_blocks_the_deal(self, client):
        code, host, _ = create(client, deck_id="aesi")
        guest, _ = join(client, code)
        client.patch(
            f"/api/pods/{code}/seat",
            json={"deck_id": "edgar", "locked": True},
            headers=auth(guest),
        )
        assert client.post(f"/api/pods/{code}/start", headers=auth(host)).status_code == 409

    def test_a_guest_cannot_deal(self, client):
        code, _host, guest = ready_pod(client)
        response = client.post(f"/api/pods/{code}/start", headers=auth(guest))
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "not_host"

    def test_dealing_hands_everybody_the_same_game_id(self, client):
        code, host, guest = ready_pod(client)
        dealt = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()
        assert dealt["status"] == "in_game" and dealt["game_id"]
        seen = client.get(f"/api/pods/{code}", headers=auth(guest)).json()
        assert seen["game_id"] == dealt["game_id"]

    def test_open_chairs_become_cpus(self, client):
        code, host, _ = create(client, deck_id="aesi")
        client.patch(
            f"/api/pods/{code}/seats/1", json={"action": "open_chair"}, headers=auth(host)
        )
        client.patch(f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(host))
        view = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()
        assert view["seats"][1]["kind"] == "cpu"
        assert view["status"] == "in_game"

    def test_a_two_filled_pod_makes_a_two_player_game(self, client):
        code, host, _guest = ready_pod(client)
        game_id = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()["game_id"]
        state = client.get(f"/api/games/{game_id}/state", headers=auth(host)).json()["state"]
        assert len(state["players"]) == 2

    def test_a_seed_on_the_deal_beats_the_one_from_create(self, client):
        """The host types a seed in the rail, not on the front door.

        This is the path the client actually uses -- the lobby has a seed field
        and the home screen does not -- so a seed that only worked at create
        time would be a field that silently did nothing.
        """
        code, host, _ = ready_pod(client, seed=1)
        dealt = client.post(
            f"/api/pods/{code}/start", json={"seed": 4242}, headers=auth(host)
        ).json()
        session = client.app.state.sessions.get(dealt["game_id"])
        assert session.seed == 4242

    def test_dealing_with_no_body_still_works(self, client):
        """`smoke_http.py` and anything driving this by hand send nothing."""
        code, host, _ = ready_pod(client, seed=9)
        dealt = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()
        assert client.app.state.sessions.get(dealt["game_id"]).seed == 9

    def test_the_seed_is_honoured(self, client, data):
        first, host, _ = ready_pod(client, seed=99)
        one = client.post(f"/api/pods/{first}/start", headers=auth(host)).json()["game_id"]

        second, host2, _ = ready_pod(client, seed=99)
        two = client.post(f"/api/pods/{second}/start", headers=auth(host2)).json()["game_id"]

        def opening(game_id, token):
            state = client.get(f"/api/games/{game_id}/state", headers=auth(token)).json()
            return [card["name"] for card in state["state"]["players"][0]["hand"]]

        assert opening(one, host) == opening(two, host2)

    def test_dealing_twice_is_a_409(self, client):
        code, host, _ = ready_pod(client)
        client.post(f"/api/pods/{code}/start", headers=auth(host))
        assert client.post(f"/api/pods/{code}/start", headers=auth(host)).status_code == 409


class TestLeaving:
    def test_leaving_reopens_the_chair(self, client):
        code, _host, _ = create(client)
        guest, _ = join(client, code)
        assert client.post(f"/api/pods/{code}/leave", headers=auth(guest)).status_code == 204
        assert client.get(f"/api/pods/{code}").json()["seats"][1]["kind"] == "open"

    def test_the_host_leaving_promotes_the_guest(self, client):
        code, host, _ = create(client)
        guest, _ = join(client, code)
        client.post(f"/api/pods/{code}/leave", headers=auth(host))
        assert client.get(f"/api/pods/{code}", headers=auth(guest)).json()["you_are_host"]

    def test_the_last_player_leaving_closes_the_pod(self, client):
        code, host, _ = create(client)
        client.post(f"/api/pods/{code}/leave", headers=auth(host))
        assert client.get(f"/api/pods/{code}").json()["status"] == "closed"

    def test_a_closed_pod_cannot_be_joined(self, client):
        code, host, _ = create(client)
        client.post(f"/api/pods/{code}/leave", headers=auth(host))
        response = client.post(f"/api/pods/{code}/join", json={"name": "Nobody"})
        assert response.status_code == 410
        assert response.json()["detail"]["code"] == "pod_closed"


class TestLongPoll:
    def test_the_first_fetch_returns_immediately(self, client):
        code, _, _ = create(client)
        started = time.monotonic()
        assert client.get(f"/api/pods/{code}?since=0").status_code == 200
        assert time.monotonic() - started < 1.0

    def test_a_poll_that_finds_nothing_returns_200_not_an_error(self, client):
        """A timed-out long poll must be indistinguishable from a slow one."""
        code, _, view = create(client)
        started = time.monotonic()
        response = client.get(f"/api/pods/{code}?since={view['version']}&timeout=0.4")
        elapsed = time.monotonic() - started
        assert response.status_code == 200
        assert response.json()["version"] == view["version"]
        assert 0.3 < elapsed < 5.0, elapsed

    def test_a_mutation_wakes_a_waiter(self, client):
        code, host, view = create(client)

        with ThreadPoolExecutor(max_workers=2) as pool:
            waiting = pool.submit(
                client.get, f"/api/pods/{code}?since={view['version']}&timeout=20"
            )
            time.sleep(0.3)
            pool.submit(
                client.patch,
                f"/api/pods/{code}/seats/1",
                json={"action": "add_cpu"},
                headers=auth(host),
            ).result()
            started = time.monotonic()
            woken = waiting.result(timeout=20)

        assert woken.status_code == 200
        assert woken.json()["version"] > view["version"]
        assert woken.json()["seats"][1]["kind"] == "cpu"
        # It was already awake by the time we asked -- the point is that it did
        # not sit out the full 20 s.
        assert time.monotonic() - started < 15.0

    def test_a_timeout_above_the_ceiling_is_refused(self, client):
        """The ceiling exists so a poll always beats a proxy's idle timeout."""
        code, _, _ = create(client)
        assert client.get(f"/api/pods/{code}?since=1&timeout=600").status_code == 422


class TestHealth:
    def test_live_pods_are_reported(self, client):
        assert client.get("/health").json()["pods"] == 0
        create(client)
        assert client.get("/health").json()["pods"] == 1

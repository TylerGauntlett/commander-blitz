"""A game outlives the process that dealt it (ADR 0023).

Every test builds two apps over one directory, which is what a deploy is: the
process that dealt the game stops answering and another one picks it up.  The
second app has never seen the game in memory, so whatever it answers came off
disk and through a full replay of the tape.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from commanderblitz.cards.registry import default_registry
from commanderblitz.engine.actions import Action
from commanderblitz.engine.enums import ActionKind
from commanderblitz.server.app import create_app


@pytest.fixture(scope="module")
def data():
    return default_registry()


@pytest.fixture
def make(data, tmp_path):
    """``make()`` is one more process over the same sessions directory."""

    def build() -> TestClient:
        return TestClient(create_app(data, allow_art_fetch=False, sessions_dir=tmp_path))

    return build


SEATS = [
    {"deck_id": "aesi", "kind": "human", "name": "You"},
    {"deck_id": "edgar", "kind": "ai", "agent": "heuristic"},
]


def new_game(client: TestClient, seed: int = 3) -> str:
    response = client.post("/api/games", json={"seats": SEATS, "seed": seed})
    assert response.status_code == 201, response.text
    return response.json()["game_id"]


def state(client: TestClient, game_id: str) -> dict:
    response = client.get(f"/api/games/{game_id}/state", params={"seat": 0})
    assert response.status_code == 200, response.text
    return response.json()


def play(client: TestClient, game_id: str, moves: int) -> dict:
    """Take ``moves`` actions, preferring anything that is not a pass."""
    current = state(client, game_id)
    for _ in range(moves):
        actions = current["actions"]
        assert actions, "the game stopped asking"
        pick = next((a for a in actions if a["kind"] != "pass"), actions[0])
        response = client.post(
            f"/api/games/{game_id}/actions",
            json={"seat": 0, "action_id": pick["id"], "version": current["version"]},
        )
        assert response.status_code == 200, response.text
        current = response.json()
    return current


def same_table(a: dict, b: dict) -> None:
    assert b["version"] == a["version"]
    assert b["state"] == a["state"]
    assert b["actions"] == a["actions"]


class TestTheGameComesBack:
    def test_a_second_process_continues_the_same_game(self, make):
        first = make()
        game_id = new_game(first)
        before = play(first, game_id, 6)

        second = make()
        after = state(second, game_id)
        same_table(before, after)

        # And it is a live game, not a picture of one: the same next move lands
        # on both sides of the restart and leaves the same table.
        mirror = make()
        same_table(play(second, game_id, 4), state(mirror, game_id))

    def test_the_old_process_would_have_played_the_same_next_move(self, make, data):
        """The restored game is the game, not a game that looks like it."""
        game_id = new_game(make())
        played = make()
        play(played, game_id, 3)
        # A process that never restarted: a fresh in-memory app, same seed,
        # same choices.
        reference = TestClient(create_app(data, allow_art_fetch=False))
        ref_id = new_game(reference)
        ref = play(reference, ref_id, 3)
        restored = state(make(), game_id)
        assert restored["state"] == ref["state"]
        assert [a["id"] for a in restored["actions"]] == [a["id"] for a in ref["actions"]]

    def test_a_click_read_before_the_restart_is_still_stale_after_it(self, make):
        first = make()
        game_id = new_game(first)
        old = state(first, game_id)
        play(first, game_id, 2)

        response = make().post(
            f"/api/games/{game_id}/actions",
            json={"seat": 0, "action_id": old["actions"][0]["id"], "version": old["version"]},
        )
        assert response.status_code == 409

    def test_stops_and_tapping_settings_come_back_with_the_game(self, make):
        first = make()
        game_id = new_game(first)
        first.post(f"/api/games/{game_id}/options", json={"seat": 0, "full_control": True})
        before = play(first, game_id, 3)
        first.post(f"/api/games/{game_id}/options", json={"seat": 0, "full_control": False})
        before = state(first, game_id)

        after = state(make(), game_id)
        same_table(before, after)

    def test_undo_works_on_a_restored_game(self, make):
        first = make()
        game_id = new_game(first)
        play(first, game_id, 4)
        second = make()
        undone = second.post(f"/api/games/{game_id}/undo", json={"seat": 0})
        assert undone.status_code == 200, undone.text


class TestHandover:
    def test_whichever_side_answers_next_sees_the_other_sides_last_move(self, make):
        """Blue and green over one disk: a move on one is visible on the other."""
        blue, green = make(), make()
        game_id = new_game(blue)
        state(green, game_id)  # green has it in memory now

        moved = play(blue, game_id, 3)
        same_table(moved, state(green, game_id))

        moved = play(green, game_id, 2)
        same_table(moved, state(blue, game_id))

    def test_a_deleted_game_is_gone_for_both(self, make):
        blue, green = make(), make()
        game_id = new_game(blue)
        blue.delete(f"/api/games/{game_id}")
        assert green.get(f"/api/games/{game_id}/state").status_code == 404


class TestWholeOrNotAtAll:
    def test_a_tape_that_no_longer_replays_is_dropped(self, make, tmp_path):
        first = make()
        game_id = new_game(first)
        play(first, game_id, 4)

        path = tmp_path / f"{game_id}.json"
        record = json.loads(path.read_text())
        # An action this build would never offer at that point: what a card
        # whose rules changed between deploys looks like to the replay.
        record["tape"][-1]["action"] = Action(ActionKind.ACTIVATE, source=99999).to_record()
        path.write_text(json.dumps(record))

        assert make().get(f"/api/games/{game_id}/state").status_code == 404
        assert not path.exists()

    def test_a_file_that_is_not_json_is_dropped(self, make, tmp_path):
        game_id = new_game(make())
        path = tmp_path / f"{game_id}.json"
        path.write_text("{not json")
        assert make().get(f"/api/games/{game_id}/state").status_code == 404
        assert not path.exists()

    def test_an_id_that_is_not_one_ours_never_becomes_a_path(self, make):
        assert make().get("/api/games/..%2F..%2Fetc/state").status_code == 404


class TestPods:
    def test_a_lobby_survives_the_restart_with_its_tokens(self, make):
        first = make()
        opened = first.post(
            "/api/pods", json={"name": "Host", "deck_id": "aesi", "seed": 5}
        ).json()
        code, host = opened["pod"]["code"], opened["player_token"]
        guest = first.post(f"/api/pods/{code}/join", json={"name": "Guest"}).json()[
            "player_token"
        ]
        first.patch(
            f"/api/pods/{code}/seat",
            json={"deck_id": "zurgo", "locked": True},
            headers={"X-Player-Token": guest},
        )
        first.patch(
            f"/api/pods/{code}/seat", json={"locked": True}, headers={"X-Player-Token": host}
        )

        second = make()
        view = second.get(f"/api/pods/{code}", headers={"X-Player-Token": host}).json()
        assert view["you_are_host"]
        assert view["seats"][1]["deck"]["id"] == "zurgo"
        assert view["seats"][1]["locked"]

        dealt = second.post(
            f"/api/pods/{code}/start", json={}, headers={"X-Player-Token": host}
        )
        assert dealt.status_code in (200, 201), dealt.text
        game_id = dealt.json()["game_id"]
        # The guest's token is still their seat at the table the second process
        # dealt, read by a third.
        table = make().get(
            f"/api/games/{game_id}/state", headers={"X-Player-Token": guest}
        )
        assert table.status_code == 200, table.text
        assert table.json()["your_seat"] == 1


class TestSweep:
    def test_a_swept_game_takes_its_file_with_it(self, make, tmp_path):
        client = make()
        game_id = new_game(client)
        client.app.state.sessions.sweep(now=float("inf"))
        assert not (tmp_path / f"{game_id}.json").exists()

    def test_a_file_nobody_holds_ages_out(self, make, tmp_path):
        import os

        game_id = new_game(make())
        path = tmp_path / f"{game_id}.json"
        os.utime(path, (0, 0))
        make().app.state.sessions.sweep()
        assert not path.exists()

    def test_an_app_without_a_directory_writes_nothing(self, data, tmp_path):
        client = TestClient(create_app(data, allow_art_fetch=False))
        new_game(client)
        assert not any(tmp_path.iterdir())


class TestWaiters:
    def test_a_long_poll_on_a_replaced_copy_returns_at_once(self, make):
        """Otherwise it waits out its timeout on an object nothing will bump."""
        import threading
        import time

        blue, green = make(), make()
        game_id = new_game(blue)
        held = green.app.state.sessions.get(game_id)
        since = held.version
        returned = threading.Event()

        def poll() -> None:
            held.wait_for_change(since, timeout=20)
            returned.set()

        waiter = threading.Thread(target=poll)
        waiter.start()
        play(blue, game_id, 2)
        started = time.monotonic()
        fresh = green.app.state.sessions.get(game_id)
        waiter.join(timeout=5)
        assert returned.is_set() and time.monotonic() - started < 5
        assert fresh is not held and fresh.version > since

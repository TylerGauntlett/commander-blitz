"""The HTTP API, exercised end to end with FastAPI's TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from automtg.server.app import create_app


@pytest.fixture(scope="module")
def client(game_data_module) -> TestClient:
    return TestClient(create_app(game_data_module))


@pytest.fixture(scope="module")
def game_data_module():
    from automtg.cards.registry import default_registry

    return default_registry()


def new_game(client: TestClient, *, seed: int = 1, seats=None) -> dict:
    seats = seats or [
        {"deck_id": "aesi", "kind": "human", "name": "You"},
        {"deck_id": "edgar", "kind": "ai", "agent": "heuristic"},
    ]
    response = client.post("/api/games", json={"seats": seats, "seed": seed})
    assert response.status_code == 201, response.text
    return response.json()


class TestStaticData:
    def test_health(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        # The fixture pins this client to `default_registry()`, so this is the
        # shipped set regardless of what anyone has imported locally.
        assert set(body["decks"]) == {"aesi", "edgar", "isperia", "zurgo"}

    def test_deck_list(self, client):
        decks = client.get("/api/decks").json()
        assert {d["id"] for d in decks} == {"aesi", "edgar", "isperia", "zurgo"}
        for deck in decks:
            assert deck["card_count"] == 100
            assert deck["commander_names"]
            # A precon is hand-written all the way through, so it has nothing
            # to admit -- an imported deck is where these are non-zero.
            assert deck["source"] == "precon"
            assert deck["simplified"] == 0

    def test_card_lookup(self, client):
        card = client.get("/api/cards/edgar_markov").json()
        assert card["name"] == "Edgar Markov"
        assert card["power"] == 4

    def test_unknown_card_is_404(self, client):
        assert client.get("/api/cards/black_lotus").status_code == 404


class TestGameLifecycle:
    def test_create_returns_a_playable_position(self, client):
        body = new_game(client)
        assert body["game_id"]
        assert body["your_seat"] == 0
        assert body["state"]["players"][0]["hand"] is not None
        assert body["actions"], "no actions offered at the start of the game"

    def test_unknown_deck_is_rejected(self, client):
        response = client.post(
            "/api/games",
            json={"seats": [{"deck_id": "nope"}, {"deck_id": "edgar"}], "seed": 0},
        )
        assert response.status_code == 400

    def test_four_player_pod(self, client):
        body = new_game(
            client,
            seats=[
                {"deck_id": "aesi", "kind": "human"},
                {"deck_id": "edgar", "kind": "ai"},
                {"deck_id": "aesi", "kind": "ai"},
                {"deck_id": "edgar", "kind": "ai"},
            ],
        )
        assert len(body["state"]["players"]) == 4

    def test_delete(self, client):
        game_id = new_game(client)["game_id"]
        assert client.delete(f"/api/games/{game_id}").status_code == 204
        assert client.get(f"/api/games/{game_id}/state").status_code == 404


class TestHiddenInformation:
    def test_opponent_hands_are_counts_only(self, client):
        body = new_game(client)
        players = body["state"]["players"]
        assert players[0]["hand"] is not None
        assert players[1]["hand"] is None
        assert players[1]["hand_count"] >= 1

    def test_libraries_are_never_listed(self, client):
        body = new_game(client)
        for player in body["state"]["players"]:
            assert "library" not in player
            assert player["library_count"] > 0

    def test_the_debug_endpoint_does_reveal_everything(self, client):
        """The dev endpoint is the deliberate exception, and must stay separate."""
        game_id = new_game(client)["game_id"]
        body = client.get(f"/api/games/{game_id}/debug").json()
        assert body["players"][1]["zones"]["hand"]


class TestPlayingThroughHttp:
    def test_actions_are_only_offered_to_the_seat_on_turn(self, client):
        body = new_game(client)
        game_id = body["game_id"]
        assert client.get(f"/api/games/{game_id}/actions?seat=1").json() == []

    def test_applying_an_unknown_action_id_is_a_400(self, client):
        game_id = new_game(client)["game_id"]
        response = client.post(
            f"/api/games/{game_id}/actions", json={"seat": 0, "action_id": "a999-bogus"}
        )
        assert response.status_code == 400

    def test_acting_out_of_turn_is_a_400(self, client):
        body = new_game(client)
        game_id = body["game_id"]
        action_id = body["actions"][0]["id"]
        response = client.post(
            f"/api/games/{game_id}/actions", json={"seat": 1, "action_id": action_id}
        )
        assert response.status_code == 400

    def test_a_full_game_can_be_played_to_a_result(self, client):
        """Play the human seat with a simple policy until somebody wins."""
        body = new_game(client, seed=7)
        game_id = body["game_id"]
        state, actions = body["state"], body["actions"]

        for _ in range(4000):
            if state["game_over"]:
                break
            if not actions:
                break
            chosen = _pick(actions)
            response = client.post(
                f"/api/games/{game_id}/actions",
                json={"seat": 0, "action_id": chosen["id"]},
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            state, actions = payload["state"], payload["actions"]

        assert state["game_over"], "the game never finished"
        assert state["result"] in ("win", "draw")

    def test_events_stream_forward(self, client):
        body = new_game(client, seed=3)
        game_id = body["game_id"]
        first = client.get(f"/api/games/{game_id}/events?since=0").json()
        assert first["events"]
        cursor = first["cursor"]
        client.post(
            f"/api/games/{game_id}/actions",
            json={"seat": 0, "action_id": body["actions"][0]["id"]},
        )
        later = client.get(f"/api/games/{game_id}/events?since={cursor}").json()
        assert later["cursor"] >= cursor

    def test_undo_rewinds_the_last_human_action(self, client):
        body = new_game(client, seed=11)
        game_id = body["game_id"]
        land = next(
            (a for a in body["actions"] if a["kind"] == "play_land"), body["actions"][0]
        )
        before = body["state"]["players"][0]["hand_count"]

        client.post(
            f"/api/games/{game_id}/actions", json={"seat": 0, "action_id": land["id"]}
        )
        undone = client.post(f"/api/games/{game_id}/undo", json={"seat": 0}).json()
        assert undone["state"]["turn"] == body["state"]["turn"]
        assert undone["state"]["players"][0]["hand_count"] == before

    def test_undo_with_nothing_to_undo_is_a_400(self, client):
        game_id = new_game(client)["game_id"]
        assert client.post(f"/api/games/{game_id}/undo", json={"seat": 0}).status_code == 400


class TestStaleActions:
    """Action ids are positional, so a click is only meaningful against the
    list it was read from.

    The bug report was a double click: the first request played the land, the
    second carried the same `a1-play_land` against the list that came after,
    and the player got a 400 for an id they never typed. Worse, an id that
    *does* exist in the new list names whatever sits at that index now -- a
    second Pass passes the next window too. The client sends the version its
    list came from; a version the actions have moved past is a 409 with a code
    the client answers by refetching, not by showing an error.
    """

    def _post(self, client, game_id, action_id, version=None):
        body = {"seat": 0, "action_id": action_id}
        if version is not None:
            body["version"] = version
        return client.post(f"/api/games/{game_id}/actions", json=body)

    def test_the_version_the_list_came_with_is_accepted(self, client):
        body = new_game(client)
        response = self._post(client, body["game_id"], body["actions"][0]["id"], body["version"])
        assert response.status_code == 200, response.text

    def test_an_id_from_a_replaced_list_is_a_409(self, client):
        body = new_game(client)
        game_id, first = body["game_id"], body["actions"][0]["id"]
        assert self._post(client, game_id, first, body["version"]).status_code == 200

        # The same click again, from the same (now replaced) list.
        again = self._post(client, game_id, first, body["version"])
        assert again.status_code == 409, again.text
        detail = again.json()["detail"]
        assert detail["code"] == "stale_action"
        assert detail["version"] > body["version"]

    def test_a_stale_id_that_still_resolves_is_refused_too(self, client):
        """The dangerous half: the id exists in the new list, at the same
        index, and would have applied something the player never clicked."""
        body = new_game(client)
        game_id = body["game_id"]
        after = self._post(client, game_id, body["actions"][0]["id"], body["version"]).json()
        assert after["actions"], "the test needs a decision after the first"
        reused = after["actions"][0]["id"]
        stale = self._post(client, game_id, reused, body["version"])
        assert stale.status_code == 409, stale.text
        # ...and with the version it actually came from, it is fine.
        fresh = self._post(client, game_id, reused, after["version"])
        assert fresh.status_code == 200, fresh.text

    def test_a_version_compare_uses_the_version_the_client_saw(self, client):
        """`_refresh_actions` runs before `_bump`, so a list must belong to the
        version its *response* carried, not the one before it. If it belonged
        to the earlier number, the response's own version would read as newer
        than the list and nothing would be stale; if to a later one, every
        click would be."""
        body = new_game(client)
        session = client.app.state.sessions.get(body["game_id"])
        after = self._post(client, body["game_id"], body["actions"][0]["id"], body["version"])
        assert session.actions_version == after.json()["version"] == session.version

    def test_a_bump_that_leaves_the_list_alone_keeps_it_valid(self, client):
        """Somebody else's settings change bumps the version without touching
        this seat's list; the list on screen is still the right one."""
        body = new_game(client)
        session = client.app.state.sessions.get(body["game_id"])
        session.set_full_control(1, True)
        assert session.version > body["version"]
        response = self._post(client, body["game_id"], body["actions"][0]["id"], body["version"])
        assert response.status_code == 200, response.text

    def test_a_garbage_id_is_still_a_400(self, client):
        body = new_game(client)
        game_id, version = body["game_id"], body["version"]
        assert self._post(client, game_id, "nonsense", version).status_code == 400
        # Shaped like a real id, but the version is current: genuinely invalid.
        assert self._post(client, game_id, "a999-play_land", version).status_code == 400
        # And without a version, a shape this server never mints is not stale.
        assert self._post(client, game_id, "a999-bogus").status_code == 400

    def test_an_old_client_without_a_version_gets_409_for_a_vanished_id(self, client):
        body = new_game(client)
        # Keep, not Mulligan: a mulligan offers the same `a0-mulligan` again.
        game_id = body["game_id"]
        first = next(a["id"] for a in body["actions"] if a["kind"] == "keep")
        after = self._post(client, game_id, first).json()
        assert all(a["id"] != first for a in after["actions"]), "the id did not vanish"
        again = self._post(client, game_id, first)
        assert again.status_code == 409, again.text
        assert again.json()["detail"]["code"] == "stale_action"


class TestPriorityStops:
    """The human seat skips priority windows with nothing to respond to.

    The AI seats keep every window, so nothing about training or the golden
    tests changes; only the human's click count does.
    """

    def test_a_human_seat_starts_on_smart_stops(self, client):
        body = new_game(client)
        game_id = body["game_id"]
        assert body["state"]["full_control"] is False
        registry = client.app.state.sessions
        session = registry.get(game_id)
        assert session.game.state.players[0].auto_pass is True
        assert all(
            session.game.state.players[pid].auto_pass is False
            for pid in range(1, len(session.seats))
        )

    def test_full_control_round_trips(self, client):
        game_id = new_game(client)["game_id"]
        on = client.post(
            f"/api/games/{game_id}/options", json={"seat": 0, "full_control": True}
        )
        assert on.status_code == 200
        assert on.json()["state"]["full_control"] is True

        off = client.post(
            f"/api/games/{game_id}/options", json={"seat": 0, "full_control": False}
        )
        assert off.json()["state"]["full_control"] is False

    def test_the_setting_survives_undo(self, client):
        """Undo rebuilds the game by replaying the tape, which resets the state
        the flag lives on -- the session has to put it back."""
        body = new_game(client, seed=11)
        game_id = body["game_id"]
        client.post(
            f"/api/games/{game_id}/options", json={"seat": 0, "full_control": True}
        )
        actions = client.get(f"/api/games/{game_id}/actions?seat=0").json()
        client.post(
            f"/api/games/{game_id}/actions",
            json={"seat": 0, "action_id": actions[0]["id"]},
        )
        undone = client.post(f"/api/games/{game_id}/undo", json={"seat": 0}).json()
        assert undone["state"]["full_control"] is True

    def test_changing_options_rebuilds_the_action_list(self, client):
        """Both settings change what `legality` offers, so the response has to be
        recomputed rather than served from the cache the last action left behind.

        `actions_for` reads `GameSession._action_ids`, and the two setters used to
        bump the version without refreshing it -- so `POST /options` answered with
        the list from *before* the toggle, and Manual mana appeared to do nothing
        until the player took another action. Emptying the cache first is the only
        way to tell a refreshed list from a stale one that happens to match.
        """
        game_id = new_game(client)["game_id"]
        session = client.app.state.sessions.get(game_id)

        session._action_ids = {}
        on = client.post(
            f"/api/games/{game_id}/options",
            json={"seat": 0, "full_control": False, "manual_mana": True},
        ).json()
        assert on["actions"], "manual mana served a stale action list"

        session._action_ids = {}
        full = client.post(
            f"/api/games/{game_id}/options", json={"seat": 0, "full_control": True}
        ).json()
        assert full["actions"], "full control served a stale action list"

    def test_an_unseated_player_cannot_change_options(self, client):
        game_id = new_game(client)["game_id"]
        response = client.post(
            f"/api/games/{game_id}/options", json={"seat": 1, "full_control": True}
        )
        assert response.status_code == 400


class TestAiStepping:
    """``?ai_steps=N`` lets a client watch the opponents instead of being handed
    their finished turns.  The default must keep behaving as it always has."""

    def _pass_until_ai_turn(self, client, game_id: str, actions: list) -> dict:
        """Pass priority until the opponent is the one deciding."""
        for _ in range(200):
            passer = next((a for a in actions if a["kind"] == "pass"), actions[0])
            payload = client.post(
                f"/api/games/{game_id}/actions?ai_steps=1",
                json={"seat": 0, "action_id": passer["id"]},
            ).json()
            if not payload["actions"] and not payload["state"]["game_over"]:
                return payload
            actions = payload["actions"]
            if not actions:
                return payload
        raise AssertionError("never handed priority to the AI")

    def test_ai_steps_yields_control_back_before_the_ai_turn_is_over(self, client):
        body = new_game(client, seed=5)
        game_id = body["game_id"]
        payload = self._pass_until_ai_turn(client, game_id, body["actions"])

        # No actions and not over: the AI still owes a decision, so the client
        # has been handed back a mid-turn state it can animate.
        assert payload["actions"] == []
        assert not payload["state"]["game_over"]

        pumped = client.post(
            f"/api/games/{game_id}/advance?ai_steps=1", json={"seat": 0}
        )
        assert pumped.status_code == 200, pumped.text

    def test_the_default_still_drives_to_the_next_human_decision(self, client):
        """No ai_steps: one round trip must come back with the human on turn."""
        body = new_game(client, seed=5)
        game_id = body["game_id"]
        state, actions = body["state"], body["actions"]

        for _ in range(400):
            if state["game_over"]:
                return
            assert actions, "default mode handed back a state with nothing to do"
            passer = next((a for a in actions if a["kind"] == "pass"), actions[0])
            payload = client.post(
                f"/api/games/{game_id}/actions",
                json={"seat": 0, "action_id": passer["id"]},
            ).json()
            state, actions = payload["state"], payload["actions"]

    def test_ai_steps_must_be_at_least_one(self, client):
        game_id = new_game(client)["game_id"]
        response = client.post(
            f"/api/games/{game_id}/advance?ai_steps=0", json={"seat": 0}
        )
        assert response.status_code == 422


class TestCombatDeclaration:
    def test_declare_accepts_a_whole_attack_at_once(self, client):
        """The client selects everything and confirms; the server loops the increments."""
        for seed in range(1, 12):
            body = new_game(client, seed=seed)
            game_id = body["game_id"]
            state, actions = body["state"], body["actions"]

            for _ in range(2000):
                if state["game_over"] or not actions:
                    break
                pending = state.get("pending") or {}
                attacks = [a for a in actions if a["kind"] == "add_attacker"]
                if pending.get("kind") == "declare_attackers" and attacks:
                    pairs = [[a["source_oid"], a["targets"][0]["id"]] for a in attacks[:2]]
                    response = client.post(
                        f"/api/games/{game_id}/declare",
                        json={"seat": 0, "kind": "attackers", "pairs": pairs},
                    )
                    assert response.status_code == 200, response.text
                    assert response.json()["state"]["step"] != "DECLARE_ATTACKERS"
                    return
                payload = client.post(
                    f"/api/games/{game_id}/actions",
                    json={"seat": 0, "action_id": _pick(actions)["id"]},
                ).json()
                state, actions = payload["state"], payload["actions"]
        raise AssertionError("never reached a declare-attackers decision in 11 games")

    def test_an_impossible_declaration_is_a_400(self, client):
        game_id = new_game(client)["game_id"]
        response = client.post(
            f"/api/games/{game_id}/declare",
            json={"seat": 0, "kind": "attackers", "pairs": [[999, 1]]},
        )
        assert response.status_code == 400

    def test_a_creature_cannot_be_declared_twice(self, client):
        """In a pod the same creature is offered against every opponent, but it
        can only attack one -- reject that before applying any of the set."""
        game_id = new_game(client)["game_id"]
        response = client.post(
            f"/api/games/{game_id}/declare",
            json={"seat": 0, "kind": "attackers", "pairs": [[5, 1], [5, 2]]},
        )
        assert response.status_code == 400
        assert "more than once" in response.json()["detail"]


def _pick(actions: list[dict]) -> dict:
    """A crude but decisive client policy: act rather than pass where possible."""
    for kind in ("play_land", "cast", "add_attacker", "choose", "yes", "keep"):
        for action in actions:
            if action["kind"] == kind:
                return action
    return actions[0]


class TestSeeding:
    """A game nobody seeded has to be a different game every time.

    The seed used to ride on the UI; when that control came out, the omitted
    seed fell through to a literal 0 and every unseeded game dealt the same
    opening hand in the same order.
    """

    SEATS = [
        {"deck_id": "aesi", "kind": "human", "name": "You"},
        {"deck_id": "edgar", "kind": "ai", "agent": "heuristic"},
    ]

    def _hand(self, client, body: dict | None) -> list[str]:
        response = client.post("/api/games", json={"seats": self.SEATS, **(body or {})})
        assert response.status_code == 201, response.text
        hand = response.json()["state"]["players"][0]["hand"]
        assert hand, "the opening hand is never empty"
        return [card["card_id"] for card in hand]

    def test_unseeded_games_differ(self, client):
        """Five deals, and at least two of them disagree.

        Stated as "not all identical" rather than "all distinct": two random
        seeds are allowed to deal the same hand, a constant seed is not.
        """
        hands = [self._hand(client, None) for _ in range(5)]
        assert len({tuple(hand) for hand in hands}) > 1

    def test_an_explicit_seed_still_reproduces(self, client):
        """The fix must not cost reproducibility -- golden replays need it."""
        assert self._hand(client, {"seed": 4242}) == self._hand(client, {"seed": 4242})


class TestChooseSeveral:
    """A pick-several decision answered with the whole set at once.

    The London mulligan's "put N on the bottom" is the multi-pick a fresh game
    reaches without luck: three mulligans (the first is free) bottoms two.
    """

    @staticmethod
    def _to_bottoming(client) -> tuple[str, dict]:
        body = new_game(client)
        game_id, state, actions = body["game_id"], body["state"], body["actions"]
        for _ in range(10):
            pending = state.get("pending") or {}
            if pending.get("kind") == "choose_objects":
                return game_id, pending
            mulligans = [a for a in actions if a["kind"] == "mulligan"]
            taken = state["players"][0].get("mulligans_taken", 0)
            want = mulligans if mulligans and taken < 3 else [a for a in actions if a["kind"] == "keep"]
            payload = client.post(
                f"/api/games/{game_id}/actions", json={"seat": 0, "action_id": want[0]["id"]}
            ).json()
            state, actions = payload["state"], payload["actions"]
        raise AssertionError("never reached the bottoming decision")

    def test_the_whole_set_is_applied(self, client):
        game_id, pending = self._to_bottoming(client)
        assert pending["min_count"] == pending["max_count"] == 2
        response = client.post(
            f"/api/games/{game_id}/choose", json={"seat": 0, "choices": [3, 0]}
        )
        assert response.status_code == 200, response.text
        after = response.json()["state"].get("pending") or {}
        assert after.get("kind") != "choose_objects"

    def test_a_repeated_option_is_a_400(self, client):
        game_id, _ = self._to_bottoming(client)
        response = client.post(
            f"/api/games/{game_id}/choose", json={"seat": 0, "choices": [1, 1]}
        )
        assert response.status_code == 400
        assert "more than once" in response.json()["detail"]

    def test_the_wrong_number_is_a_400_and_applies_nothing(self, client):
        game_id, _ = self._to_bottoming(client)
        response = client.post(f"/api/games/{game_id}/choose", json={"seat": 0, "choices": [1]})
        assert response.status_code == 400
        state = client.get(f"/api/games/{game_id}/state", params={"seat": 0, "timeout": 0}).json()["state"]
        assert state["pending"]["kind"] == "choose_objects"
        assert state["pending"]["selected"] == []

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

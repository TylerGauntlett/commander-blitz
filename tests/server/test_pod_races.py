"""Two people doing the same thing at the same time.

This is the file that finds the mistakes in the other five.  Every handler is a
sync ``def``, which means Starlette runs it in a thread pool, which means two
guests claiming the last chair are *genuinely* concurrent -- not interleaved by
an event loop at await points, but preempted anywhere.

The shape of every test here is the same: fire N requests at one pod from N
threads, then assert on the *set* of outcomes rather than on any one of them.
A test that asserted "the second one gets a 409" would be asserting an ordering
the scheduler never promised.

Every ``.result()`` carries a timeout.  A deadlock is the failure mode this file
exists to catch, and a hung test that never reports is not a caught deadlock.
"""

from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from commanderblitz.cards.registry import default_registry
from commanderblitz.server.app import create_app

#: Generous against a cold thread pool, and still far under any long poll.
DEADLINE = 30.0


@pytest.fixture(scope="module")
def data():
    return default_registry()


@pytest.fixture
def client(data) -> TestClient:
    return TestClient(create_app(data, allow_art_fetch=False))


def auth(token: str) -> dict[str, str]:
    return {"X-Player-Token": token}


def race(*calls, timeout: float = DEADLINE) -> list:
    """Run every call at once and collect the results in submission order.

    Not a ``with`` block: if one worker really is wedged, blocking teardown on
    it turns a failing assertion into a hang with no message.
    """
    pool = ThreadPoolExecutor(max_workers=len(calls))
    try:
        futures = [pool.submit(call) for call in calls]
        return [future.result(timeout=timeout) for future in futures]
    finally:
        pool.shutdown(wait=False)


def one_chair_left(client: TestClient) -> tuple[str, str]:
    """A pod with the host, two CPUs, and exactly one seat a human could take."""
    opened = client.post(
        "/api/pods", json={"name": "Host", "deck_id": "aesi", "seed": 3}
    ).json()
    code, host = opened["pod"]["code"], opened["player_token"]
    for index in (1, 2):
        client.patch(
            f"/api/pods/{code}/seats/{index}",
            json={"action": "add_cpu", "deck_id": "edgar"},
            headers=auth(host),
        )
    return code, host


def ready_pod(client: TestClient) -> tuple[str, str, str]:
    opened = client.post(
        "/api/pods", json={"name": "Host", "deck_id": "aesi", "seed": 3}
    ).json()
    code, host = opened["pod"]["code"], opened["player_token"]
    guest = client.post(f"/api/pods/{code}/join", json={"name": "Guest"}).json()["player_token"]
    client.patch(
        f"/api/pods/{code}/seat",
        json={"deck_id": "edgar", "locked": True},
        headers=auth(guest),
    )
    client.patch(f"/api/pods/{code}/seat", json={"locked": True}, headers=auth(host))
    return code, host, guest


class TestTheLastChair:
    def test_exactly_one_of_four_arrivals_gets_it(self, client):
        code, _ = one_chair_left(client)
        results = race(
            *[
                (lambda n=n: client.post(f"/api/pods/{code}/join", json={"name": f"P{n}"}))
                for n in range(4)
            ]
        )
        statuses = Counter(r.status_code for r in results)
        assert statuses == {201: 1, 409: 3}, statuses
        assert all(
            r.json()["detail"]["code"] == "pod_full" for r in results if r.status_code == 409
        )

    def test_the_pod_holds_exactly_one_new_player(self, client):
        code, _ = one_chair_left(client)
        race(
            *[
                (lambda n=n: client.post(f"/api/pods/{code}/join", json={"name": f"P{n}"}))
                for n in range(4)
            ]
        )
        seats = client.get(f"/api/pods/{code}").json()["seats"]
        assert [s["kind"] for s in seats] == ["human", "cpu", "cpu", "human"]

    def test_two_arrivals_never_share_a_chair(self, client):
        """Three chairs, three arrivals: everybody gets one, and a distinct one."""
        opened = client.post("/api/pods", json={"name": "Host", "deck_id": "aesi"}).json()
        code = opened["pod"]["code"]
        results = race(
            *[
                (lambda n=n: client.post(f"/api/pods/{code}/join", json={"name": f"P{n}"}))
                for n in range(3)
            ]
        )
        assert all(r.status_code == 201 for r in results)
        seats = sorted(r.json()["pod"]["your_seat"] for r in results)
        assert seats == [1, 2, 3]


class TestDealingTwice:
    def test_only_one_start_wins(self, client):
        code, host, _ = ready_pod(client)
        results = race(
            *[
                (lambda: client.post(f"/api/pods/{code}/start", headers=auth(host)))
                for _ in range(2)
            ]
        )
        statuses = Counter(r.status_code for r in results)
        assert statuses == {200: 1, 409: 1}, statuses

    def test_only_one_game_is_created(self, client):
        """The expensive half of a double-deal: two shuffled games, one pod."""
        code, host, _ = ready_pod(client)
        race(
            *[
                (lambda: client.post(f"/api/pods/{code}/start", headers=auth(host)))
                for _ in range(3)
            ]
        )
        assert len(client.app.state.sessions) == 1
        assert client.get("/health").json()["games"] == 1

    def test_everybody_is_pointed_at_the_same_game(self, client):
        code, host, guest = ready_pod(client)
        race(
            *[
                (lambda: client.post(f"/api/pods/{code}/start", headers=auth(host)))
                for _ in range(3)
            ]
        )
        seen = {
            client.get(f"/api/pods/{code}", headers=auth(token)).json()["game_id"]
            for token in (host, guest)
        }
        assert len(seen) == 1 and None not in seen


class TestUnlockingWhileStarting:
    def test_a_game_never_starts_with_an_unready_seat(self, client):
        """Either the deal wins and everybody was locked, or the unlock wins
        and the deal is refused.  There is no third outcome."""
        for _ in range(12):
            code, host, guest = ready_pod(client)
            # Bound as defaults rather than closed over: `race` consumes them
            # inside the iteration, but a lambda that reads a loop variable is
            # the kind of thing that stops being true the moment somebody makes
            # this lazy.
            started, unlocked = race(
                lambda c=code, h=host: client.post(f"/api/pods/{c}/start", headers=auth(h)),
                lambda c=code, g=guest: client.patch(
                    f"/api/pods/{c}/seat", json={"locked": False}, headers=auth(g)
                ),
            )
            assert started.status_code in (200, 409), started.text
            if started.status_code == 200:
                game_id = started.json()["game_id"]
                state = client.get(
                    f"/api/games/{game_id}/state", headers=auth(host)
                ).json()["state"]
                assert len(state["players"]) == 2
            else:
                assert started.json()["detail"]["code"] == "not_ready"
                assert unlocked.status_code == 200
                assert client.get(f"/api/pods/{code}").json()["game_id"] is None


class TestConcurrentActions:
    def test_the_seat_that_is_not_on_turn_is_refused(self, client):
        code, host, guest = ready_pod(client)
        game_id = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()["game_id"]

        before = client.get(f"/api/games/{game_id}/state", headers=auth(host)).json()
        on_turn = before["state"]["pending"]["player"]
        action = before["actions"][0]["id"] if on_turn == 0 else None
        if action is None:  # pragma: no cover -- seat 0 always opens
            pytest.skip("seat 0 was not on turn")

        mine, theirs = race(
            lambda: client.post(
                f"/api/games/{game_id}/actions",
                json={"seat": 0, "action_id": action},
                headers=auth(host),
            ),
            lambda: client.post(
                f"/api/games/{game_id}/actions",
                json={"seat": 1, "action_id": action},
                headers=auth(guest),
            ),
        )
        assert mine.status_code == 200, mine.text
        # 403 if the token check catches it first, 400 if the engine does. Both
        # are refusals; which one wins is a scheduling detail.
        assert theirs.status_code in (400, 403)

    def test_the_game_is_not_corrupted_by_the_refusal(self, client):
        code, host, guest = ready_pod(client)
        game_id = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()["game_id"]
        session = client.app.state.sessions.get(game_id)

        from commanderblitz.engine.serialize import fingerprint

        versions = [session.version]
        for _ in range(6):
            view = client.get(f"/api/games/{game_id}/state", headers=auth(host)).json()
            if view["state"]["game_over"] or not view["actions"]:
                break
            action = view["actions"][0]["id"]
            race(
                lambda a=action: client.post(
                    f"/api/games/{game_id}/actions",
                    json={"seat": 0, "action_id": a},
                    headers=auth(host),
                ),
                lambda a=action: client.post(
                    f"/api/games/{game_id}/actions",
                    json={"seat": 1, "action_id": a},
                    headers=auth(guest),
                ),
            )
            versions.append(session.version)
            assert fingerprint(session.game.state)

        assert versions == sorted(versions), "the version counter went backwards"
        assert len(set(versions)) > 1, "nothing actually happened"

    def test_concurrent_reads_never_see_a_torn_action_list(self, client):
        """``_refresh_actions`` empties ``_action_ids`` before refilling it."""
        code, host, guest = ready_pod(client)
        game_id = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()["game_id"]
        action = client.get(
            f"/api/games/{game_id}/state", headers=auth(host)
        ).json()["actions"][0]["id"]

        results = race(
            lambda: client.post(
                f"/api/games/{game_id}/actions",
                json={"seat": 0, "action_id": action},
                headers=auth(host),
            ),
            *[
                (lambda: client.get(f"/api/games/{game_id}/state", headers=auth(guest)))
                for _ in range(4)
            ],
        )
        for response in results[1:]:
            assert response.status_code == 200, response.text
            body = response.json()
            # Seat 1 is never on turn during seat 0's action, so its action list
            # is empty either way -- what must not happen is a 500 from reading
            # a dict that another thread is rebuilding.
            assert body["actions"] == []


class TestNoDeadlock:
    def test_a_long_poller_does_not_block_a_mutator(self, client):
        """``wait_for`` releases the pod lock while it blocks.  If it did not,
        this would hang for the full timeout and then fail."""
        code, host, _ = ready_pod(client)
        version = client.get(f"/api/pods/{code}").json()["version"]

        started = time.monotonic()
        polled, patched = race(
            lambda: client.get(f"/api/pods/{code}", params={"since": version, "timeout": 20}),
            lambda: (
                time.sleep(0.2)
                or client.patch(
                    f"/api/pods/{code}/seats/3",
                    json={"action": "add_cpu", "deck_id": "zurgo"},
                    headers=auth(host),
                )
            ),
        )
        elapsed = time.monotonic() - started

        assert patched.status_code == 200
        assert polled.status_code == 200
        assert polled.json()["version"] > version
        assert elapsed < 15.0, f"the poll did not wake early ({elapsed:.1f}s)"

    def test_many_pollers_all_wake_on_one_change(self, client):
        """``notify_all``, not ``notify`` -- a pod has up to four watchers."""
        code, host, _ = ready_pod(client)
        version = client.get(f"/api/pods/{code}").json()["version"]

        results = race(
            *[
                (
                    lambda: client.get(
                        f"/api/pods/{code}", params={"since": version, "timeout": 20}
                    )
                )
                for _ in range(4)
            ],
            lambda: (
                time.sleep(0.3)
                or client.patch(
                    f"/api/pods/{code}/seats/3",
                    json={"action": "add_cpu", "deck_id": "zurgo"},
                    headers=auth(host),
                )
            ),
        )
        for response in results[:4]:
            assert response.status_code == 200
            assert response.json()["version"] > version

    def test_a_game_poller_does_not_block_the_player_on_turn(self, client):
        code, host, guest = ready_pod(client)
        game_id = client.post(f"/api/pods/{code}/start", headers=auth(host)).json()["game_id"]
        view = client.get(f"/api/games/{game_id}/state", headers=auth(host)).json()
        version, action = view["version"], view["actions"][0]["id"]

        started = time.monotonic()
        polled, acted = race(
            lambda: client.get(
                f"/api/games/{game_id}/state",
                headers=auth(guest),
                params={"since_version": version, "timeout": 20},
            ),
            lambda: (
                time.sleep(0.2)
                or client.post(
                    f"/api/games/{game_id}/actions",
                    json={"seat": 0, "action_id": action},
                    headers=auth(host),
                )
            ),
        )

        assert acted.status_code == 200, acted.text
        assert polled.status_code == 200
        assert polled.json()["version"] > version
        assert time.monotonic() - started < 15.0

    def test_sweeping_while_people_are_joining_does_not_deadlock(self, client):
        """``sweep`` takes the registry lock and then each pod's, in that order.

        Anything that took them the other way round would eventually wedge here.
        """
        code, _ = one_chair_left(client)
        pods = client.app.state.pods
        results = race(
            lambda: client.post(f"/api/pods/{code}/join", json={"name": "Arrival"}),
            lambda: pods.sweep(),
            lambda: client.post("/api/pods", json={"name": "Elsewhere"}),
            lambda: client.get(f"/api/pods/{code}"),
        )
        assert results[0].status_code == 201
        assert results[2].status_code == 201
        assert results[3].status_code == 200

"""The retired Edgar and Aesi lists: there for tests, invisible to players."""

from __future__ import annotations

import pytest

from commanderblitz.cards.registry import default_registry, server_registry
from commanderblitz.server.lobby import Pod, PodRegistry
from commanderblitz.server.sessions import SessionRegistry


@pytest.fixture
def fresh_server_registry():
    server_registry.cache_clear()
    yield
    server_registry.cache_clear()


class TestTheServerHidesThem:
    def test_a_player_never_sees_the_fixtures(self, fresh_server_registry, monkeypatch):
        monkeypatch.delenv("COMMANDERBLITZ_FIXTURE_DECKS", raising=False)
        data = server_registry()
        assert "aesi" not in data.decks and "edgar" not in data.decks
        assert "edgar_markov" in data.decks
        assert data.seating == ()

    def test_a_test_server_asks_for_them(self, fresh_server_registry, monkeypatch):
        monkeypatch.setenv("COMMANDERBLITZ_FIXTURE_DECKS", "1")
        data = server_registry()
        assert {"aesi", "edgar"} <= set(data.decks)
        assert data.seating == ("aesi", "edgar", "isperia", "zurgo")


class TestTheTestsAlwaysHaveThem:
    def test_the_authored_registry_carries_them(self):
        assert {"aesi", "edgar"} <= set(default_registry().decks)


class TestSeating:
    def test_cpus_are_dealt_the_pinned_order(self):
        """The order every seeded pod was written against, despite the new
        precons sorting ahead of `edgar`."""
        pods = PodRegistry(SessionRegistry(default_registry()))
        pod = Pod(code="TEST", host_id="host")
        dealt = []
        for seat in pod.seats:
            seat.kind, seat.deck_id = "cpu", pods._free_deck(pod)
            dealt.append(seat.deck_id)
        assert dealt == ["aesi", "edgar", "isperia", "zurgo"]

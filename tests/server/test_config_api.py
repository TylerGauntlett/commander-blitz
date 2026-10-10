"""``GET /api/config``: what the client knows about the server it is talking to.

The desktop build runs this server as a sidecar and the client learns from
this route, not from its origin, that it is on the desktop and whether the
hosted server is reachable.  The probe behind ``online`` is cached, never
raises, and asks exactly ``{remote}/health``.
"""

from __future__ import annotations

import io
import urllib.error
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from automtg import __version__
from automtg.server.app import create_app
from automtg.server.connectivity import RemoteProbe
from automtg.server.settings import ServerSettings, settings_from_env

REMOTE = "http://remote.test:9"


@pytest.fixture(scope="module")
def data():
    from automtg.cards.registry import default_registry

    return default_registry()


class FakeResponse(io.BytesIO):
    def __init__(self, status: int = 200) -> None:
        super().__init__(b'{"status":"ok"}')
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class CountingOpener:
    """An ``urlopen`` that records every call and answers as told."""

    def __init__(self, *, status: int | None = 200) -> None:
        self.calls: list[tuple[str, float]] = []
        self.status = status

    def __call__(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        if self.status is None:
            raise urllib.error.URLError("no route to host")
        return FakeResponse(self.status)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TestTheHostedServer:
    def test_the_default_is_hosted_and_online(self, data):
        client = TestClient(create_app(data))
        body = client.get("/api/config").json()
        assert body == {
            "mode": "hosted",
            "online": True,
            "remote_origin": None,
            "app_version": __version__,
            "content_version": __version__,
        }

    def test_health_is_unchanged(self, data):
        # The desktop shell reads `/health` as its readiness probe; this route
        # must not have grown into it.
        body = TestClient(create_app(data)).get("/health").json()
        assert body["status"] == "ok"
        assert "mode" not in body


class TestTheDesktopServer:
    @pytest.fixture
    def desktop(self, data):
        @contextmanager
        def make(opener):
            settings = ServerSettings(
                mode="desktop", remote_origin=REMOTE, content_version="2.3.4"
            )
            probe = RemoteProbe(REMOTE, opener=opener)
            yield TestClient(create_app(data, settings=settings, probe=probe))

        return make

    def test_offline_when_the_remote_does_not_answer(self, desktop):
        with desktop(CountingOpener(status=None)) as client:
            body = client.get("/api/config").json()
        assert body["mode"] == "desktop"
        assert body["online"] is False
        assert body["remote_origin"] == REMOTE
        assert body["content_version"] == "2.3.4"
        assert body["app_version"] == __version__

    def test_online_when_it_does(self, desktop):
        with desktop(CountingOpener(status=200)) as client:
            assert client.get("/api/config").json()["online"] is True

    def test_a_server_error_is_offline(self, desktop):
        # A 503 from the hosted server is "cannot play online right now",
        # which is the same thing as unreachable from the door's point of view.
        with desktop(CountingOpener(status=503)) as client:
            assert client.get("/api/config").json()["online"] is False

    def test_the_probe_asks_health_exactly(self, desktop):
        opener = CountingOpener()
        with desktop(opener) as client:
            client.get("/api/config")
        assert opener.calls == [(f"{REMOTE}/health", RemoteProbe(REMOTE)._timeout)]


class TestTheProbe:
    def test_the_answer_is_cached_for_the_ttl(self):
        opener, clock = CountingOpener(), FakeClock()
        probe = RemoteProbe(REMOTE, opener=opener, clock=clock, ttl=30)
        assert probe.online() and probe.online()
        assert len(opener.calls) == 1
        clock.now += 29.9
        probe.online()
        assert len(opener.calls) == 1
        clock.now += 0.1
        probe.online()
        assert len(opener.calls) == 2

    def test_forget_asks_again(self):
        opener = CountingOpener()
        probe = RemoteProbe(REMOTE, opener=opener)
        probe.online()
        probe.forget()
        probe.online()
        assert len(opener.calls) == 2

    def test_no_remote_is_always_online_and_never_asks(self):
        opener = CountingOpener()
        probe = RemoteProbe(None, opener=opener)
        assert probe.online() is True
        assert opener.calls == []

    def test_a_trailing_slash_is_dropped(self):
        assert RemoteProbe(REMOTE + "/").url == f"{REMOTE}/health"

    @pytest.mark.parametrize(
        "error", [urllib.error.URLError("x"), TimeoutError(), OSError(), ValueError("bad url")]
    )
    def test_nothing_the_network_does_raises(self, error):
        def opener(request, timeout):
            raise error

        assert RemoteProbe(REMOTE, opener=opener).online() is False


class TestSettingsFromEnv:
    def test_empty_is_hosted(self):
        assert settings_from_env({}) == ServerSettings()

    def test_desktop(self):
        settings = settings_from_env(
            {
                "AUTOMTG_MODE": "desktop",
                "AUTOMTG_REMOTE_ORIGIN": "https://commanderblitz.com/",
                "AUTOMTG_CONTENT_VERSION": "1.2.3",
                "AUTOMTG_EAGER_ART": "1",
            }
        )
        assert settings == ServerSettings(
            mode="desktop",
            remote_origin="https://commanderblitz.com",
            content_version="1.2.3",
            eager_art=True,
        )

    def test_an_unknown_mode_is_refused(self):
        with pytest.raises(ValueError, match="AUTOMTG_MODE"):
            settings_from_env({"AUTOMTG_MODE": "kiosk"})

    def test_blank_values_mean_unset(self):
        settings = settings_from_env({"AUTOMTG_REMOTE_ORIGIN": "", "AUTOMTG_CONTENT_VERSION": ""})
        assert settings.remote_origin is None
        assert settings.content_version == __version__

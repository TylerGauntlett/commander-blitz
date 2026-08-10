"""Serving the built client, and every address inside it.

The client has real routes now -- ``/pods/GYRE-8412``, ``/games/abc`` -- and
nothing on disk sits at those paths.  Vite's dev and preview servers already
answer them with ``index.html``; these tests pin the same rule for a real
deployment, where there is no Vite.

The two that matter are the ones about what the fallback must *not* swallow: an
unrouted ``/api`` path staying a machine-readable 404, and a ``..`` never
reaching outside the build directory.  A catch-all is the easiest route in any
app to make too greedy.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from automtg.cards.registry import default_registry
from automtg.server.app import create_app

INDEX = "<!doctype html><title>Auto MTG</title><div id=root></div>"


@pytest.fixture(scope="module")
def data():
    return default_registry()


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A stand-in for ``frontend/dist``: a document and one hashed asset."""
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "symbols").mkdir()
    (tmp_path / "symbols" / "W.svg").write_text("<svg/>", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(data, dist) -> TestClient:
    return TestClient(
        create_app(data, allow_art_fetch=False, serve_client=True, client_dir=dist)
    )


class TestClientRoutes:
    @pytest.mark.parametrize(
        "path",
        ["/", "/pods/GYRE-8412", "/games/abc123", "/decks", "/decks/aesi", "/nonsense"],
    )
    def test_every_client_address_gets_the_document(self, client, path):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == INDEX
        assert "text/html" in response.headers["content-type"]

    def test_the_document_is_not_cached(self, client):
        # It names the hashed bundles; a stale copy names ones that are gone.
        assert client.get("/pods/GYRE-8412").headers["cache-control"] == "no-store"

    def test_real_files_are_served_as_themselves(self, client):
        assert client.get("/assets/index-abc123.js").text == "console.log(1)"
        assert client.get("/symbols/W.svg").text == "<svg/>"

    def test_a_post_to_a_client_address_is_not_a_document(self, client):
        # GET only.  A mistyped POST should fail as a wrong method, not arrive
        # at a page that will never handle it.
        assert client.post("/pods/GYRE-8412").status_code in (404, 405)


class TestTheFallbackStaysOutOfTheWay:
    def test_the_api_still_answers(self, client):
        assert client.get("/api/decks").status_code == 200

    def test_an_unrouted_api_path_is_a_readable_404(self, client):
        response = client.get("/api/nope")
        assert response.status_code == 404
        # The client parses this as JSON.  Handing it HTML turns a clean "no
        # such thing" into a parse error nowhere near the cause.
        assert "text/html" not in response.headers["content-type"]

    def test_health_is_still_json(self, client):
        assert client.get("/health").json()["status"] == "ok"

    def test_a_missing_art_file_is_still_a_404(self, client):
        assert client.get("/art/no_such_card.jpg").status_code == 404

    @pytest.mark.parametrize(
        "path",
        ["/../pyproject.toml", "/..%2Fpyproject.toml", "/assets/../../pyproject.toml"],
    )
    def test_traversal_never_escapes_the_build(self, client, path):
        response = client.get(path)
        # Either refused outright or handed the document -- never a file from
        # outside `dist`.
        assert response.status_code != 200 or response.text == INDEX


class TestOptIn:
    def test_the_default_app_serves_no_client(self, data):
        # The proof that every other server test is untouched by this: without
        # `serve_client` there is no catch-all, whether or not a build exists.
        client = TestClient(create_app(data, allow_art_fetch=False))
        assert client.get("/pods/GYRE-8412").status_code == 404

    def test_a_missing_build_registers_nothing(self, data, tmp_path):
        client = TestClient(
            create_app(
                data, allow_art_fetch=False, serve_client=True, client_dir=tmp_path
            )
        )
        assert client.get("/pods/GYRE-8412").status_code == 404

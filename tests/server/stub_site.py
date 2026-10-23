"""A stand-in for ``commanderblitz.com``, for the tests of a Deck's import.

    python -m tests.server.stub_site --port 8011 --generated-dir /tmp/site

It is the real hosted app -- the import route, the bundle route, ``/health`` --
with two things answered here instead of by a third party:

* **Moxfield** is the trimmed fixture deck (``tests/data/moxfield_deck.json``)
  for any link, so the site's import runs end to end and never leaves the
  machine.
* **``/art``** is one committed illustration for any file name, counted, so a test can say
  exactly what the Deck fetched and that it fetched nothing twice.

And a switch, under ``/__stub``, that a test flips over HTTP:

``POST /__stub/state {"online": false}``
    Every other path answers 503, which is what the sidecar's probe and its
    import both read as the site being down.
``POST /__stub/state {"hang_after": n}``
    The art route serves ``n`` files and then holds every later request open
    until the setting changes -- an import caught halfway, for a test that
    stops the sidecar at that moment.
``GET /__stub/stats``
    ``{"art": [file names served, in order], "offline_art": [file names asked
    for while switched off], "offline_hits": n, "online": bool}``.

Its own process, so that the sidecar under test reaches it over a real
socket as it would reach the site, and so the Playwright sidecar config can
start it as one more web server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parents[1] / "data" / "moxfield_deck.json"

#: What every ``/art`` request is answered with: a real illustration the
#: repository owns, so a browser draws it rather than the no-art plate a
#: byte string shaped like a JPEG would leave it with.
ILLUSTRATION = next((Path(__file__).resolve().parents[2] / "data" / "art").glob("*.jpg"))


class StubSite:
    """An ASGI wrapper: the switch and the art here, everything else the app's."""

    def __init__(self, app, *, online: bool = True) -> None:
        self.app = app
        self.online = online
        self.hang_after: int | None = None
        self.art: list[str] = []
        self.offline_hits = 0
        #: Art asked for while switched off: what a board went looking for.
        self.offline_art: list[str] = []
        self.illustration = ILLUSTRATION.read_bytes()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        if path.startswith("/__stub/"):
            await self._control(scope, receive, send)
        elif not self.online:
            self.offline_hits += 1
            if path.startswith("/art/"):
                self.offline_art.append(path.removeprefix("/art/"))
            await _respond(send, 503, b"offline", "text/plain")
        elif path.startswith("/art/"):
            if self.hang_after is not None and len(self.art) >= self.hang_after:
                # Held, and never served: by the time the switch moves, the
                # caller is a sidecar the test has stopped.
                while self.hang_after is not None:
                    await asyncio.sleep(0.05)
                await _respond(send, 503, b"held", "text/plain")
                return
            self.art.append(path.removeprefix("/art/"))
            await _respond(send, 200, self.illustration, "image/jpeg")
        else:
            await self.app(scope, receive, send)

    async def _control(self, scope, receive, send) -> None:
        if scope["path"] == "/__stub/stats":
            body = {
                "art": self.art,
                "offline_art": self.offline_art,
                "offline_hits": self.offline_hits,
                "online": self.online,
            }
            await _respond(send, 200, json.dumps(body).encode(), "application/json")
            return
        raw = b""
        more = True
        while more:
            message = await receive()
            raw += message.get("body", b"")
            more = message.get("more_body", False)
        change = json.loads(raw or b"{}")
        if "online" in change:
            self.online = bool(change["online"])
        if "hang_after" in change:
            self.hang_after = change["hang_after"]
        await _respond(send, 204, b"", "text/plain")


async def _respond(send, status: int, body: bytes, kind: str) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", kind.encode()), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


def answer_moxfield_from_the_fixture() -> None:
    """Every Moxfield link is the fixture deck, read once."""
    from commanderblitz.cards import moxfield

    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    moxfield.fetch_deck = lambda public_id, *, opener=None: payload


def build(*, online: bool = True) -> StubSite:
    from commanderblitz.server.app import create_app

    answer_moxfield_from_the_fixture()
    return StubSite(create_app(allow_art_fetch=False), online=online)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stub_site")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--generated-dir", required=True)
    parser.add_argument("--offline", action="store_true", help="start switched off")
    args = parser.parse_args(argv)
    # Before the app is built: the registry reads it at call time, and the
    # site's imports must land in a scratch directory, never the checkout's.
    os.environ["COMMANDERBLITZ_GENERATED_DIR"] = args.generated_dir
    os.environ.pop("COMMANDERBLITZ_MODE", None)

    import uvicorn

    uvicorn.run(build(online=not args.offline), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

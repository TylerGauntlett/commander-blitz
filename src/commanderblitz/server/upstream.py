"""The desktop sidecar's import, asked of the hosted site first (ADR 0022).

The sidecar posts the Moxfield link to the site's own import route, under the
Deck's library id, and fetches the deck back as a bundle
(``GET /api/decks/{deck_id}/bundle``).  Two kinds of failure, and they go to
two places:

* **The site answered with a code** -- a private deck, a missing one, an
  illegal list.  That is Moxfield's answer relayed, and asking Moxfield
  directly would only hear it again, so it is raised as ``ImportFailed``.
* **The site did not answer usefully** -- no connection, a timeout, a server
  error, a body that is not ours.  That is ``SiteUnavailable``, and the caller
  falls back to reading Moxfield itself.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from commanderblitz.cards.moxfield import ImportFailed

#: Generous: the site's import reads Moxfield and builds a hundred proxies
#: before it answers, and a player watching a spinner is better served by a
#: slow answer than by a fall-back that does the same work again.
IMPORT_TIMEOUT = 60.0

HEADERS = {
    "User-Agent": "CommanderBlitz-desktop",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


class SiteUnavailable(Exception):
    """The site could not be asked; read Moxfield directly instead."""


class Site:
    """The hosted origin, as the sidecar's import sees it."""

    def __init__(
        self,
        origin: str,
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        timeout: float = IMPORT_TIMEOUT,
    ) -> None:
        self.origin = origin.rstrip("/")
        self._opener = opener
        self._timeout = timeout

    def import_deck(self, url: str, library: str | None) -> tuple[dict, dict]:
        """``(the site's import report, the deck's bundle)``."""
        report = self._call("POST", "/api/decks/import", library, {"url": url})
        try:
            deck_id = report["deck"]["id"]
        except (KeyError, TypeError):
            raise SiteUnavailable("the import report names no deck") from None
        bundle = self._call(
            "GET", f"/api/decks/{urllib.parse.quote(str(deck_id), safe='')}/bundle", library
        )
        return report, bundle

    def _call(self, method: str, path: str, library: str | None, body: dict | None = None):
        headers = dict(HEADERS)
        if library:
            headers["X-Library-Id"] = library
        request = urllib.request.Request(
            self.origin + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers=headers,
            method=method,
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            refusal = _refusal(exc) if 400 <= exc.code < 500 else None
            if refusal is not None:
                raise refusal from None
            raise SiteUnavailable(f"{method} {path}: {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise SiteUnavailable(f"{method} {path}: {exc}") from None
        if not isinstance(payload, dict):
            raise SiteUnavailable(f"{method} {path}: not an object")
        return payload


def _refusal(exc: urllib.error.HTTPError) -> ImportFailed | None:
    """The importer's own refusal, if that is what the site sent.

    The import route answers ``{"detail": {"detail": message, "code": code}}``;
    anything else -- a validation error, a proxy's page -- is not an answer
    about the deck, and is treated as the site being unavailable.
    """
    try:
        detail = json.loads(exc.read().decode("utf-8")).get("detail")
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        return ImportFailed(detail["code"], str(detail.get("detail", "")))
    return None

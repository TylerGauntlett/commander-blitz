"""What kind of server this is, and where the other one lives.

The same package serves ``commanderblitz.com`` and runs inside the desktop
build, where it is a sidecar on ``127.0.0.1`` that the shell starts on every
launch.  The two differ in exactly the ways listed here, all of which the
client learns from ``GET /api/config`` rather than guessing from its origin.

Read from the environment once at boot (``settings_from_env``), because the
desktop entry point sets these variables before building the app and the
Docker image sets none of them -- which is the ``hosted`` default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from commanderblitz import __version__

Mode = Literal["desktop", "hosted"]


@dataclass(frozen=True)
class ServerSettings:
    #: ``desktop`` is the sidecar; ``hosted`` is the site.  The client greys
    #: out what needs the other one when it is not reachable.
    mode: Mode = "hosted"
    #: Where the hosted server is, from the desktop's point of view.  ``None``
    #: on the hosted server itself, which is the one place there is no remote.
    remote_origin: str | None = None
    #: The version of the content package (server, client and data together)
    #: the desktop shell is running.  The package version on the hosted server,
    #: where there is no separate package.
    content_version: str = __version__
    #: Fetch a freshly imported deck's art at once, rather than the first time
    #: a board shows it.  The desktop needs that: the next launch may be
    #: offline, and a deck without its art is a deck of grey rectangles.
    eager_art: bool = False


def settings_from_env(environ: dict[str, str] | None = None) -> ServerSettings:
    env = os.environ if environ is None else environ
    mode = env.get("COMMANDERBLITZ_MODE", "hosted")
    if mode not in ("desktop", "hosted"):
        raise ValueError(f"COMMANDERBLITZ_MODE must be 'desktop' or 'hosted', not {mode!r}")
    remote = env.get("COMMANDERBLITZ_REMOTE_ORIGIN") or None
    return ServerSettings(
        mode=mode,
        remote_origin=remote.rstrip("/") if remote else None,
        content_version=env.get("COMMANDERBLITZ_CONTENT_VERSION") or __version__,
        eager_art=env.get("COMMANDERBLITZ_EAGER_ART") == "1",
    )

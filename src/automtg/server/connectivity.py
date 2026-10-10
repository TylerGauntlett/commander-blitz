"""Is the hosted server reachable from here?

The desktop sidecar answers that on behalf of the client, which has no better
way to ask: a ``fetch`` to another origin from the page would be a CORS
question as well as a network one.  The probe is a plain ``GET /health``
against the remote origin, remembered for ``ttl`` seconds so that a client
polling ``/api/config`` every half minute costs one request, not one per poll.

It never raises.  Being offline is a normal state here, not an error.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

#: Short, because the answer gates a greyed-out button, not a request.  A
#: Steam Deck on a bad hotel network should find out it is "offline" in the
#: time it takes the door to draw, not hang a settings screen for a minute.
PROBE_TIMEOUT = 3.0

#: How long one answer is trusted.  The client refetches on this cadence too.
PROBE_TTL = 30.0


class RemoteProbe:
    """A cached, lock-guarded reachability check against one origin."""

    def __init__(
        self,
        origin: str | None,
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        clock: Callable[[], float] = time.monotonic,
        ttl: float = PROBE_TTL,
        timeout: float = PROBE_TIMEOUT,
    ) -> None:
        self.origin = origin.rstrip("/") if origin else None
        self._opener = opener
        self._clock = clock
        self._ttl = ttl
        self._timeout = timeout
        self._lock = threading.Lock()
        self._answer: bool | None = None
        self._asked_at = float("-inf")

    @property
    def url(self) -> str | None:
        return None if self.origin is None else f"{self.origin}/health"

    def online(self) -> bool:
        """Whether the remote answered recently.

        No remote means nothing to be cut off from: the hosted server is
        "online" by definition, and the client never greys anything there.
        """
        if self.url is None:
            return True
        with self._lock:
            now = self._clock()
            if self._answer is None or now - self._asked_at >= self._ttl:
                self._answer = self._ask()
                self._asked_at = now
            return self._answer

    def forget(self) -> None:
        """Drop the cached answer, so the next call asks again."""
        with self._lock:
            self._answer = None

    def _ask(self) -> bool:
        assert self.url is not None
        request = urllib.request.Request(self.url, headers={"User-Agent": "commanderblitz-probe"})
        try:
            with self._opener(request, timeout=self._timeout) as response:
                return 200 <= getattr(response, "status", 200) < 300
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return False

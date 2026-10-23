"""Games and pods on disk, so they outlive the process (ADR 0023).

One JSON file per game and one per pod.  The memory copy each registry holds is
a cache of its file: written after every change, read on a miss, and read again
when another process has written a newer one -- which is what lets one container
hand the site to the next without a game noticing.

The file is the *input* to a game, never its state.  What a session writes is
what ``undo`` already replays from; :meth:`GameSession.to_record` owns its shape.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: Game ids and pod codes are minted by this server, so anything else asked for
#: is not on disk -- and never becomes a path, which is the traversal guard.
_NAME = re.compile(r"^[A-Za-z0-9-]{1,32}$")


class JsonStore:
    """A directory of ``<name>.json`` files, each written whole or not at all."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, name: str) -> Path | None:
        return self.root / f"{name}.json" if _NAME.fullmatch(name) else None

    def save(self, name: str, record: dict[str, Any]) -> int | None:
        """Write ``record`` and return the file's ``st_mtime_ns``.

        A temporary file in the same directory renamed over the old one: a
        reader in another process sees the previous description or this one,
        never half of either.  A failed write is logged and the game goes on in
        memory; losing a restart is better than losing the request.
        """
        path = self._path(name)
        if path is None:
            return None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.root, prefix=f".{name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(record, handle, separators=(",", ":"))
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
            return path.stat().st_mtime_ns
        except OSError:
            log.exception("could not write %s", path)
            return None

    def load(self, name: str) -> tuple[dict[str, Any], int] | None:
        """The record and its ``st_mtime_ns``, or ``None`` if there is none."""
        path = self._path(name)
        if path is None:
            return None
        try:
            stamp = path.stat().st_mtime_ns
            with path.open(encoding="utf-8") as handle:
                return json.load(handle), stamp
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            log.exception("could not read %s; dropping it", path)
            self.delete(name)
            return None

    def stamp(self, name: str) -> int | None:
        """``st_mtime_ns`` of the file, or ``None`` if there is none."""
        path = self._path(name)
        if path is None:
            return None
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return None

    def names(self) -> set[str]:
        """Every name with a file, for minting one that is not taken."""
        try:
            return {path.stem for path in self.root.glob("*.json")}
        except OSError:
            return set()

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path is not None:
            path.unlink(missing_ok=True)

    def sweep(self, ttl: float, *, keep: set[str], now: float | None = None) -> int:
        """Delete files untouched for ``ttl`` seconds, other than ``keep``.

        The modification time is the wall-clock stamp: a file nobody has
        rewritten in ``ttl`` is a game nobody has moved in that long.  ``keep``
        is what this process still holds, whose idleness the registry's own
        sweep decides from reads as well as writes.
        """
        cutoff = (time.time() if now is None else now) - ttl
        dropped = 0
        try:
            paths = list(self.root.glob("*.json"))
        except OSError:
            return 0
        for path in paths:
            if path.stem in keep:
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    dropped += 1
            except OSError:
                continue
        return dropped


def session_store(root: Path) -> tuple[JsonStore, JsonStore]:
    """The game store and the pod store under one ``sessions`` directory."""
    return JsonStore(root), JsonStore(root / "pods")

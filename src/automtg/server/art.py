"""Serving card art from this server, never from Scryfall.

The client is only ever given ``/art/{card_id}.jpg``.  What sits behind that
path is a local file, so a game keeps rendering when Scryfall is rate limiting,
down, or blocked -- which is the whole reason the bytes were downloaded in the
first place.

The one exception is the *lazy fill*: a card outside ``data/cards/`` (a future
deck, a catalog search result) has no file yet, so the first request for it
fetches once, writes it to the cache, and serves it.  From then on it is a local
file like any other.  That fetch happens server-side, so the browser still never
talks to a third party.

Two directories, and which one a file is in decides who may overrule it.
``art_dir()`` holds the bytes the repository owns -- committed, baked into the
image, never written at runtime.  ``art_cache_dir()`` holds what the lazy fill
downloaded, which is per-deployment state living on a Docker volume.  **Owned
wins**: a cached file is only ever what some earlier boot believed the printing
to be, and a pin in ``art_pins.json`` can change that belief.
"""

from __future__ import annotations

import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from automtg.cards.images import (
    ART_CROP,
    CardArt,
    CardIndex,
    art_cache_dir,
    art_dir,
    image_url,
)

#: Card ids are generated from card names by the loader, so this is a tight
#: whitelist rather than a guess.  It is also the path-traversal guard: the id
#: goes into a filename, so ".." and separators must be unrepresentable.
CARD_ID = re.compile(r"^[a-z0-9_]{1,80}$")

#: A catalog card is addressed by its Scryfall uuid rather than by a slug of its
#: name.  Slugs are not reversible -- "Aesi, Tyrant of Gyre Strait" and
#: "Aesi Tyrant of Gyre Strait" collapse to the same thing -- and the uuid is
#: already the index's primary handle.
SCRYFALL_ID = re.compile(r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")

HEADERS = {"User-Agent": "CommanderBlitz/0.1 (+https://commanderblitz.com)"}
TIMEOUT = 15


@dataclass
class ArtStore:
    """Local art, plus the ability to fill a gap once.

    Owns a negative set so an unresolvable card -- the five custom designs, most
    often -- costs one lookup per process rather than one per request.  A board
    with a custom card on it re-requests that image on every re-render.
    """

    images: dict[str, CardArt]
    #: The owned bytes: committed, in the image, read-only.
    directory: Path
    index: CardIndex | None = None
    allow_fetch: bool = True
    #: Where a lazy fill writes.  ``None`` means "beside the owned bytes",
    #: which is what a caller holding a single directory wants -- a test with
    #: one ``tmp_path``, or any code that has no cache to offer.
    cache: Path | None = None

    def __post_init__(self) -> None:
        self._missing: set[str] = set()
        self._lock = threading.Lock()
        if self.cache is None:
            self.cache = self.directory

    # -- paths ----------------------------------------------------------

    def reload(self, registry, index: CardIndex | None) -> None:
        """Adopt a freshly imported card pool.

        The negative set is dropped with it: a card that had no art because it
        was not in the registry at boot may well have one now, and keeping the
        old set would cache that "no" forever.
        """
        with self._lock:
            self.images = _resolve_images(registry, index)
            self._missing = set()

    def path_for(self, card_id: str) -> Path:
        """This card's art, or where a fill would put it.

        Owned bytes win outright.  A cached file under the same name is a copy
        of whatever printing an earlier boot resolved, and the committed answer
        is the one that was reviewed -- so a file shipped in the image is never
        overruled by one sitting in the volume.
        """
        owned = self.directory / f"{card_id}.jpg"
        if owned.is_file():
            return owned
        return self.cache / f"{card_id}.jpg"

    def cached_ids(self) -> set[str]:
        ids: set[str] = set()
        for directory in {self.directory, self.cache}:
            if directory.exists():
                ids |= {p.stem for p in directory.glob("*.jpg")}
        return ids

    def url_for(self, card_id: str) -> str | None:
        """What the client should put in ``<img src>``, or ``None`` for a card
        with no printing -- which is a real answer, not an error."""
        art = self.images.get(card_id)
        if art is not None and not art.has_printing:
            return None
        if art is None and self.index is None:
            return None
        return f"/art/{card_id}.jpg"

    def artist_for(self, card_id: str) -> str | None:
        art = self.images.get(card_id)
        return art.artist if art else None

    # -- resolution -----------------------------------------------------

    def remote_for(self, card_id: str) -> str | None:
        """The CDN URL to fill from.  Server-side only."""
        art = self.images.get(card_id)
        if art is not None:
            return art.remote_url(ART_CROP)
        # Not an engine card: a catalog result, addressed by its Scryfall uuid.
        if SCRYFALL_ID.match(card_id):
            return image_url(card_id, ART_CROP)
        return None

    def resolve(self, card_id: str) -> Path | None:
        """A readable file for this card, fetching once if need be."""
        if not (CARD_ID.match(card_id) or SCRYFALL_ID.match(card_id)):
            return None

        path = self.path_for(card_id)
        if path.is_file():
            return path
        if not self.allow_fetch or card_id in self._missing:
            return None

        with self._lock:
            # Another thread may have filled it while we waited.
            if path.is_file():
                return path
            if card_id in self._missing:
                return None
            url = self.remote_for(card_id)
            if url is None or not self._download(url, path):
                self._missing.add(card_id)
                return None
            return path

    def _download(self, url: str, path: Path) -> bool:
        request = urllib.request.Request(url, headers=HEADERS)
        temp = path.with_suffix(".part")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = response.read()
            if not payload:
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(payload)
            temp.replace(path)
            return True
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            temp.unlink(missing_ok=True)
            return False


def _resolve_images(registry, index: CardIndex | None) -> dict[str, CardArt]:
    """Where each card's art comes from.

    ``registry_images.json`` is the committed answer for the authored cards.
    Generated cards have their own file beside them, written at import time; it
    is deliberately a second file rather than an edit to the committed one, so a
    refresh of the catalog can never sweep an imported card into an artifact
    that is under version control.

    **The authored layer wins.**  ``load_game_data`` already drops a generated
    *card* whose card has since been authored -- a proxy exists only because
    nobody had written that card yet, and once somebody has, the real one wins.
    This map has to obey the same rule, and used to do the opposite: the
    overlay was applied with ``update`` and overrode the committed answer.

    That is not theoretical.  ``pool.images.json`` is append-only -- the
    importer ``update``s entries in and never re-resolves one -- so a card
    records whichever printing the catalog chose on the day its deck was
    imported, and keeps it forever.  When Sheoldred, the Apocalypse was pinned
    to the Dominaria United art, the committed answer changed and every
    deployment that had imported her deck before the pin went on serving the
    Secret Lair printing out of the overlay, with the pin merged and live.
    """
    from automtg.cards.images import (
        build_registry_images,
        generated_images_path,
        read_registry_images,
    )

    images = read_registry_images()
    if not images and index is not None:
        images = build_registry_images(registry, index)
    for card_id, art in read_registry_images(generated_images_path()).items():
        images.setdefault(card_id, art)
    return images


def build_store(registry, index: CardIndex | None, *, allow_fetch: bool = True) -> ArtStore:
    """Resolve the engine's cards against ``registry_images.json``.

    Falls back to resolving live from the index when that file is absent, and to
    an empty map when neither exists -- a fresh clone must still start a game,
    it just draws text frames.
    """
    return ArtStore(
        images=_resolve_images(registry, index),
        directory=art_dir(),
        cache=art_cache_dir(),
        index=index,
        allow_fetch=allow_fetch,
    )

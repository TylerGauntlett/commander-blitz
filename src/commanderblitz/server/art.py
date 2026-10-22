"""Serving card art from this server, never from Scryfall.

The client is only ever given ``/art/{card_id}.jpg``, optionally with
``?p={scryfall_id}`` when the seat's deck chose a printing of its own.  What
sits behind that path is a local file either way, so a game keeps rendering when
Scryfall is rate limiting, down, or blocked -- which is the whole reason the
bytes were downloaded in the first place.

``?p=`` is a *query* rather than a different path on purpose: the card id stays
in the URL, which is what lets this module tell a transforming card's back face
from its front (one Scryfall id, two faces) and fall back to the card's own art
when a deck names a printing that cannot be fetched.

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

Between them sits the **store**, ``art_store_dir()``: the catalog's art, crawled
ahead of time by ``scripts/backfill_art.py`` and committed like the owned bytes
(ADR 0021).  It is keyed by printing, so it answers for a card through the
printing the card resolves to.  Owned beats store beats cache, and the lazy fill
is only what happens when all three come up empty -- ``fell_through`` counts how
often, which is the number the crawl exists to drive to zero.

A desktop sidecar has an **upstream**, the hosted site, and its lazy fill asks
that site's store before Scryfall: one crawl serves every device.
"""

from __future__ import annotations

import re
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from commanderblitz.cards.images import (
    ART_CROP,
    CardArt,
    CardIndex,
    art_cache_dir,
    art_dir,
    art_store_dir,
    build_registry_images,
    generated_images_path,
    image_url,
    read_registry_images,
    read_store_state,
    store_name,
    store_path,
)
from commanderblitz.cards.schema import SCRYFALL_ID

#: Card ids are generated from card names by the loader, so this is a tight
#: whitelist rather than a guess.  It is also the path-traversal guard: the id
#: goes into a filename, so ".." and separators must be unrepresentable.
CARD_ID = re.compile(r"^[a-z0-9_]{1,80}$")

#: The back face of a printing, addressed by its store name.  The front needs
#: no pattern of its own: it is a bare ``SCRYFALL_ID``, which ``/art`` already
#: serves for the catalog.  This is what a sidecar asks its upstream for.
BACK_FILE = re.compile(SCRYFALL_ID.pattern.removesuffix("$") + "_back$")

#: A catalog card is addressed by its Scryfall uuid rather than by a slug of its
#: name.  Slugs are not reversible -- "Aesi, Tyrant of Gyre Strait" and
#: "Aesi Tyrant of Gyre Strait" collapse to the same thing -- and the uuid is
#: already the index's primary handle.  ``SCRYFALL_ID`` itself is imported from
#: ``cards.images`` rather than defined here: a deck file carries printing ids
#: too, and one pattern used in two places cannot drift from itself.

HEADERS = {"User-Agent": "CommanderBlitz/0.1 (+https://commanderblitz.com)"}
TIMEOUT = 15

#: Parallel fills in one ``prefetch``.  Scryfall asks for 50-100 ms between
#: requests from one client; six in flight against a CDN that serves static
#: files is well inside what it tolerates and makes a 100-card deck a matter
#: of seconds rather than a minute.
PREFETCH_WORKERS = 6


@dataclass
class PrefetchReport:
    """What ``ArtStore.prefetch`` found and fetched."""

    #: Files that were not there and are now.
    fetched: int = 0
    #: Files that were already there.
    cached: int = 0
    #: Card ids with no art at the end of it -- no printing anywhere, or a
    #: fetch that failed.  Those are remembered as missing and not retried.
    failed: list[str] = field(default_factory=list)


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
    #: The crawled catalog art, keyed by printing.  ``None`` is a store with no
    #: such layer, which is what every caller but ``build_store`` wants.
    store: Path | None = None
    #: The hosted origin a sidecar asks before Scryfall.  ``None`` on the site.
    upstream: str | None = None
    #: The last crawl's summary, for ``/health``.
    store_state: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._missing: set[str] = set()
        #: Downloads the lazy fill attempted since boot: lookups that neither
        #: the owned bytes, the store nor the cache could answer.
        self.fell_through = 0
        #: Guards ``images``, ``_missing`` and ``_inflight``.  Never held
        #: across a download: see ``_fill``.
        self._lock = threading.Lock()
        #: One gate per file being fetched, so two requests for the same card
        #: produce one download and requests for different cards proceed at
        #: once.  A global lock around the download used to serialise every
        #: fill in the process, which was invisible on a board that fills one
        #: card at a time and a minute-long stall for ``prefetch``.
        self._inflight: dict[str, threading.Lock] = {}
        if self.cache is None:
            self.cache = self.directory
        self._index_owned()

    def _index_owned(self) -> None:
        #: Which card's owned file shows a given face of a given printing, so a
        #: request by printing -- a catalog hover, a deck's choice, a sidecar
        #: asking upstream -- is answered from ``data/art`` too.  The crawl
        #: skips what is owned, so without this those would fall through.
        self._owned: dict[tuple[str, bool], str] = {
            (art.scryfall_id, art.back): card_id
            for card_id, art in self.images.items()
            if art.scryfall_id
        }

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
            self._index_owned()

    def path_for(self, card_id: str) -> Path:
        """This card's art, or where a fill would put it.

        Owned bytes win outright.  A cached file under the same name is a copy
        of whatever printing an earlier boot resolved, and the committed answer
        is the one that was reviewed -- so a file shipped in the image is never
        overruled by one sitting in the volume.  The store sits between them:
        committed too, but crawled rather than reviewed, so a pin that lands in
        ``data/art`` still wins over it.
        """
        owned = self.directory / f"{card_id}.jpg"
        if owned.is_file():
            return owned
        face = self._face_for(card_id)
        committed = self.committed(*face) if face else None
        if committed is not None:
            return committed
        return self.cache / f"{card_id}.jpg"

    def committed(self, scryfall_id: str, back: bool) -> Path | None:
        """A committed file showing this face of this printing, if there is one.

        The owned bytes first, then the store: the same order ``path_for``
        keeps.  ``scripts/backfill_art.py`` asks this too, to skip what is
        already had.
        """
        owner = self._owned.get((scryfall_id, back))
        if owner is not None and (owned := self.directory / f"{owner}.jpg").is_file():
            return owned
        if self.store is None:
            return None
        path = store_path(self.store, scryfall_id, back=back)
        return path if path.is_file() else None

    def cached_ids(self) -> set[str]:
        ids: set[str] = set()
        for directory in {self.directory, self.cache}:
            if directory.exists():
                ids |= {p.stem for p in directory.glob("*.jpg")}
        return ids

    def url_for(self, card_id: str, *, printing: str | None = None) -> str | None:
        """What the client should put in ``<img src>``, or ``None`` for a card
        with no printing -- which is a real answer, not an error.

        ``printing`` is a deck's own choice of illustration, and it wins: the
        author picked it, and it is what makes their deck recognisable.  It is
        expressed as a query rather than a different path so that the card id
        stays in the URL -- which is what lets ``resolve`` know whether this is
        a card's *back* face, and what to fall back to when the printing cannot
        be fetched.  A printing the base map already agrees with adds nothing
        but a cache miss, so it is dropped.
        """
        art = self.images.get(card_id)
        # Answered *before* the artless check below: a card we have no catalog
        # printing for, whose deck named one, does have art now.
        if (
            printing is not None
            and SCRYFALL_ID.match(printing)
            and (art is None or art.scryfall_id != printing)
        ):
            return f"/art/{card_id}.jpg?p={printing}"
        if art is not None and not art.has_printing:
            return None
        if art is None and self.index is None:
            return None
        return f"/art/{card_id}.jpg"

    def artist_for(self, card_id: str) -> str | None:
        art = self.images.get(card_id)
        return art.artist if art else None

    # -- resolution -----------------------------------------------------

    def _face_for(
        self, card_id: str, *, printing: str | None = None
    ) -> tuple[str, bool] | None:
        """Which printing, and which face of it, this card shows.

        A ``printing`` names the illustration but not the *face*: a transforming
        card's two faces share one Scryfall id and differ only by ``back``.  So
        back-ness is read off the card's own catalog entry, which is the one
        thing the deck cannot tell us and the registry always can.
        """
        art = self.images.get(card_id)
        if printing is not None and SCRYFALL_ID.match(printing):
            return printing, bool(art and art.back)
        if art is not None:
            return (art.scryfall_id, art.back) if art.scryfall_id else None
        # Not an engine card: a catalog result, addressed by its Scryfall uuid.
        if SCRYFALL_ID.match(card_id):
            return card_id, False
        return None

    def remote_for(self, card_id: str, *, printing: str | None = None) -> str | None:
        """The CDN URL a fill would end at.  Server-side only."""
        face = self._face_for(card_id, printing=printing)
        return image_url(face[0], ART_CROP, back=face[1]) if face else None

    def _remotes(self, scryfall_id: str, back: bool) -> list[str]:
        """Where a fill of this face may come from, in the order to ask.

        The upstream first, by the store's own name for the file, so a Deck
        is served by the site's crawl; Scryfall behind it, so a site that is
        down costs the Deck nothing it had before.
        """
        urls = [image_url(scryfall_id, ART_CROP, back=back)]
        if self.upstream:
            urls.insert(0, f"{self.upstream}/art/{store_name(scryfall_id, back=back)}")
        return urls

    def _printing_path(self, printing: str, *, back: bool) -> Path:
        """Where a deck-chosen printing is cached.

        Named for the printing, not the card, so two decks that chose the same
        illustration share one file -- and so does the catalog hover path, which
        already writes ``{uuid}.jpg``.  Neither name can collide with a card's
        own file: ``CARD_ID`` forbids hyphens, so no card id is ever uuid-shaped.
        """
        assert self.cache is not None  # set in __post_init__
        return self.cache / (f"{printing}_back.jpg" if back else f"{printing}.jpg")

    def resolve(self, card_id: str, *, printing: str | None = None) -> Path | None:
        """A readable file for this card, fetching once if need be.

        A deck's chosen ``printing`` is tried first and **falls back to the
        card's own art** if it cannot be had.  That fallback is not politeness:
        the catalog keeps one row per card name, so a printing from a deck list
        cannot be validated against anything before it is served, and the honest
        failure for a dud id is the illustration we do have -- not a hole.
        """
        if BACK_FILE.match(card_id):
            return self._resolve_face(card_id.removesuffix("_back"), True)
        if not (CARD_ID.match(card_id) or SCRYFALL_ID.match(card_id)):
            return None

        if printing is not None and SCRYFALL_ID.match(printing):
            found = self._resolve_printing(card_id, printing)
            if found is not None:
                return found

        path = self.path_for(card_id)
        if path.is_file():
            return path
        face = self._face_for(card_id)
        return self._fill(card_id, path, lambda: self._remotes(*face) if face else [])

    def _resolve_printing(self, card_id: str, printing: str) -> Path | None:
        """The deck's illustration, or ``None`` to fall back to the card's own."""
        return self._resolve_face(*self._face_for(card_id, printing=printing))

    def _resolve_face(self, printing: str, back: bool) -> Path | None:
        """One face of one printing: committed, then cached, then a fill."""
        committed = self.committed(printing, back)
        if committed is not None:
            return committed
        path = self._printing_path(printing, back=back)
        if path.is_file():
            return path
        # Keyed by printing and face, never by card id: a printing that cannot
        # be fetched must not also blacklist the card's ordinary art.
        key = f"{printing}|{back}"
        return self._fill(key, path, lambda: self._remotes(printing, back))

    def _fill(self, key: str, path: Path, remotes: Callable[[], list[str]]) -> Path | None:
        """Fetch ``path`` once, under a gate that is this file's and no other's.

        The store lock is taken only to consult or update the bookkeeping;
        the download itself runs under ``key``'s own gate.  A second caller
        for the same key waits on that gate and then finds the file; a caller
        for a different key does not wait at all.
        """
        if not self.allow_fetch or key in self._missing:
            return None
        with self._lock:
            if key in self._missing:
                return None
            gate = self._inflight.setdefault(key, threading.Lock())
        with gate:
            # Whoever held the gate before us either wrote the file or
            # recorded the miss.
            if path.is_file():
                return path
            with self._lock:
                if key in self._missing:
                    return None
            urls = remotes()
            filled = any(self._download(url, path) for url in urls)
            with self._lock:
                self._inflight.pop(key, None)
                if urls:
                    self.fell_through += 1
                if not filled:
                    self._missing.add(key)
            return path if filled else None

    def prefetch(
        self,
        requests: Iterable[tuple[str, str | None]],
        *,
        workers: int = PREFETCH_WORKERS,
    ) -> PrefetchReport:
        """Make every ``(card_id, printing)`` in ``requests`` a local file now.

        For the desktop build, whose next launch may be offline: a deck
        imported on the train has to carry its art with it.  Each request is
        exactly what one ``GET /art/{card_id}.jpg[?p=printing]`` would do,
        including the fall-back to the card's own art when the printing cannot
        be had -- so what the board asks for later is already on disk.
        """
        report = PrefetchReport()
        todo: list[tuple[str, str | None]] = []
        for card_id, printing in requests:
            if self._on_disk(card_id, printing):
                report.cached += 1
            else:
                todo.append((card_id, printing))
        if not todo:
            return report
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            found = list(
                pool.map(lambda req: self.resolve(req[0], printing=req[1]), todo)
            )
        for (card_id, _), path in zip(todo, found, strict=True):
            if path is None:
                report.failed.append(card_id)
            else:
                report.fetched += 1
        return report

    def _on_disk(self, card_id: str, printing: str | None) -> bool:
        if printing is not None and SCRYFALL_ID.match(printing):
            back = bool((art := self.images.get(card_id)) and art.back)
            if self.committed(printing, back) or self._printing_path(printing, back=back).is_file():
                return True
        return self.path_for(card_id).is_file()

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


def spread_across_faces(printings: dict[str, dict], registry, art: ArtStore) -> dict[str, dict]:
    """``printings``, plus the other faces of the cards in it.

    A deck list names the front (`bloodline_keeper`); the back is a card id of
    its own that no list ever mentions, and the moment the permanent transforms
    ``card_view`` starts sending that id.  Without this the deck's illustration
    would vanish mid-flip -- the same class of bug ``with_other_faces`` documents.

    A face only inherits when it shares the front's catalog printing, which is
    exactly the transform case: one Scryfall id, two faces, told apart by
    ``back``.  A meld half or an adventure's other side has a printing of its
    own, and inheriting onto it would fetch the wrong picture outright.
    """
    out = dict(printings)
    pending = list(printings)
    while pending:
        card_id = pending.pop()
        if card_id not in registry:
            continue
        base = art.images.get(card_id)
        card = registry.get(card_id)
        for face in (card.back_face, card.second_face):
            if not face or face in out:
                continue
            other = art.images.get(face)
            if base is None or other is None or other.scryfall_id != base.scryfall_id:
                continue
            out[face] = out[card_id]
            pending.append(face)
    return out


def with_other_faces(ids: set[str], registry) -> set[str]:
    """``ids`` plus every face reachable from them.

    A deck list names `henrika_domnathi_henrika_infernal_seer`; the moment that
    creature transforms, `state.card_of` starts answering with the back face and
    `card_view` sends `henrika_infernal_seer` as the `card_id`.  If that id is
    not in the client's image map it draws the hatched "no art" plate -- on a
    card whose art is sitting in `data/art` under exactly that name.  The same
    applies to `second_face`: an adventure or a modal DFC's other half is
    serialized under its own id while it is the face being shown.

    Transitive and loop-guarded rather than one hop: nothing prints a chain
    today, and a map that quietly stopped one face short is the bug this
    function exists to fix.
    """
    out = set(ids)
    pending = list(ids)
    while pending:
        card_id = pending.pop()
        # `registry.get` raises on a miss, and a deck naming an unknown card is
        # already refused at load time -- so the membership test is a guard
        # against a *generated* pool that has moved under us, not against a
        # typo, and it costs one dict lookup.
        if card_id not in registry:  # pragma: no cover
            continue
        card = registry.get(card_id)
        for face in (card.back_face, card.second_face):
            if face and face not in out:
                out.add(face)
                pending.append(face)
    return out


def deck_art_requests(deck, registry, art: ArtStore) -> list[tuple[str, str | None]]:
    """Every ``(card_id, printing)`` a board showing ``deck`` will ask for.

    The deck's cards and their other faces, each with the printing the deck
    chose for it or ``None`` for the catalog's own -- the same answer
    ``/api/images?game_id=`` gives seat by seat, computed once for a deck so
    ``ArtStore.prefetch`` can fetch it before any game is dealt.
    """
    chosen = spread_across_faces(deck.printings, registry, art)
    return [
        (card_id, (chosen.get(card_id) or {}).get("scryfall_id"))
        for card_id in sorted(with_other_faces(deck.unique_ids(), registry))
    ]


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

    images = read_registry_images()
    if not images and index is not None:
        images = build_registry_images(registry, index)
    for card_id, art in read_registry_images(generated_images_path()).items():
        images.setdefault(card_id, art)
    return images


def build_store(
    registry,
    index: CardIndex | None,
    *,
    allow_fetch: bool = True,
    upstream: str | None = None,
) -> ArtStore:
    """Resolve the engine's cards against ``registry_images.json``.

    Falls back to resolving live from the index when that file is absent, and to
    an empty map when neither exists -- a fresh clone must still start a game,
    it just draws text frames.  A checkout without the store is the same: the
    layer is simply empty.
    """
    store = art_store_dir()
    return ArtStore(
        images=_resolve_images(registry, index),
        directory=art_dir(),
        cache=art_cache_dir(),
        index=index,
        allow_fetch=allow_fetch,
        store=store,
        upstream=upstream,
        store_state=read_store_state(store),
    )

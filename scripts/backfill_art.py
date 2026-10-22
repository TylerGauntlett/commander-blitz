"""Crawl the catalog's art into ``data/art_store/``, once, at Scryfall's pace.

    python scripts/backfill_art.py                  # up to --limit new files
    python scripts/backfill_art.py --limit 50
    python scripts/backfill_art.py --dry-run        # count what is still wanted

The store is the third layer ``ArtStore`` serves from, behind the committed
``data/art/`` and ahead of the lazy cache; ADR 0021 is the decision and
``.github/workflows/art-backfill.yml`` is what runs this on a schedule and
commits what it fetched.

**What is wanted**: every printing the index resolves (one per name, and the
back face where a card has one), every pin in ``art_pins.json``, and every
printing a shipped deck chose -- less whatever ``ArtStore.committed`` already
answers, which covers the owned bytes as well as the store itself.

**Resumable by construction.**  A face with a committed file is never fetched
again; a download is written to a ``.part`` and renamed, so an interrupted run
leaves a whole file or none; a printing the CDN does not have is recorded in
``_unavailable.json`` and never asked for again.  The record is written on the
way out of an interrupted run too, so nothing learned is lost.  A failure that
is not a "not found" is left for the next run.

Like ``fetch_card_art.py``, it makes no Scryfall API calls: every id comes from
the committed index, pins and decks, so only the image CDN is touched.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from commanderblitz.cards.images import (
    ART_CROP,
    STORE_STATE,
    STORE_UNAVAILABLE,
    art_pins_path,
    art_store_dir,
    image_url,
    load_index,
    store_name,
    store_path,
)

# Scryfall asks for a descriptive User-Agent and ~50-100ms between requests.
HEADERS = {"User-Agent": "CommanderBlitz/0.1 (+https://commanderblitz.com)"}
DELAY = 0.1
TIMEOUT = 30
#: New files one run may add.  What one scheduled pull request carries, so
#: each stays a reviewable, pushable size; ADR 0021 says why it is capped.
LIMIT = 2000


@dataclass(frozen=True, order=True)
class Face:
    """One face of one printing: the unit the store holds a file for."""

    scryfall_id: str
    back: bool = False

    @property
    def name(self) -> str:
        return store_name(self.scryfall_id, back=self.back)


@dataclass
class Report:
    wanted: int = 0
    #: Already committed when the run reached them.
    held: int = 0
    fetched: int = 0
    #: Recorded as not on the CDN, this run or an earlier one.
    unavailable: int = 0
    #: Failed for a reason worth retrying; left for the next run.
    failed: list[str] = field(default_factory=list)
    #: True when ``limit`` stopped the run with faces still to fetch.
    capped: bool = False


def fetch(url: str) -> bytes | None:
    """The bytes, or ``None`` when the CDN says it has no such file.

    Anything else -- a timeout, a 5xx, a dropped connection -- raises, because
    the next run should try it again and a ``None`` would record it forever.
    """
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read() or None
    except urllib.error.HTTPError as error:
        if error.code in (403, 404, 410):
            return None
        raise


def read_unavailable(store: Path) -> set[str]:
    try:
        names = json.loads((store / STORE_UNAVAILABLE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {n for n in names if isinstance(n, str)} if isinstance(names, list) else set()


def backfill(
    wanted: Iterable[Face],
    store: Path,
    *,
    committed: Callable[[Face], bool],
    fetch: Callable[[str], bytes | None] = fetch,
    limit: int = LIMIT,
    delay: float = DELAY,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Report:
    """Fetch every wanted face the store lacks, up to ``limit`` new files."""
    faces = sorted(set(wanted))
    unavailable = read_unavailable(store)
    report = Report(wanted=len(faces))
    for stray in store.glob("*/*.part"):
        stray.unlink()
    try:
        for face in faces:
            if committed(face):
                report.held += 1
                continue
            if face.name in unavailable:
                continue
            if report.fetched >= limit:
                report.capped = True
                break
            url = image_url(face.scryfall_id, ART_CROP, back=face.back)
            try:
                payload = fetch(url)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                report.failed.append(f"{face.name}: {error}")
                continue
            finally:
                if delay:
                    time.sleep(delay)
            if payload is None:
                unavailable.add(face.name)
                continue
            path = store_path(store, face.scryfall_id, back=face.back)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".part")
            temp.write_bytes(payload)
            temp.replace(path)
            report.fetched += 1
            report.held += 1
    finally:
        report.unavailable = len(unavailable)
        _write_record(store, report, unavailable, now())
    return report


def _write_record(store: Path, report: Report, unavailable: set[str], at: datetime) -> None:
    store.mkdir(parents=True, exist_ok=True)
    (store / STORE_UNAVAILABLE).write_text(
        json.dumps(sorted(unavailable), indent=0) + "\n", encoding="utf-8"
    )
    # `held` counts only the faces the run reached; a capped or interrupted
    # run says so rather than reporting a total it never measured.
    state = {
        "last_run": at.isoformat(timespec="seconds"),
        "wanted": report.wanted,
        "held": report.held,
        "unavailable": report.unavailable,
        "complete": not report.capped and not report.failed,
    }
    (store / STORE_STATE).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------
# what is wanted
# ----------------------------------------------------------------------


def wanted_faces(index, data, art) -> set[Face]:
    """Every face the store should hold, before subtracting what is had.

    ``art`` is the server's own ``ArtStore``: a deck's printings are read
    through ``deck_art_requests``, which is exactly what a board showing that
    deck will ask ``/art`` for, faces and all.
    """
    from commanderblitz.server.art import deck_art_requests

    faces: set[Face] = set()
    if index is not None:
        for entry in index.iter_all():
            faces.add(Face(entry.scryfall_id))
            if entry.has_back_face:
                faces.add(Face(entry.scryfall_id, back=True))
    for pin in _pins().values():
        faces.add(Face(pin["scryfall_id"]))
    for deck in data.decks.values():
        for card_id, printing in deck_art_requests(deck, data.registry, art):
            if printing is not None:
                own = art.images.get(card_id)
                faces.add(Face(printing, back=bool(own and own.back)))
    return faces


def _pins() -> dict[str, dict]:
    try:
        return json.loads(art_pins_path().read_text(encoding="utf-8")).get("pins", {})
    except (OSError, ValueError):
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=LIMIT, help="new files this run may add")
    parser.add_argument("--delay", type=float, default=DELAY, help="seconds between requests")
    parser.add_argument("--dry-run", action="store_true", help="count what is still wanted")
    args = parser.parse_args(argv)

    from commanderblitz.cards.registry import default_registry
    from commanderblitz.server.art import build_store

    index = load_index()
    if index is None:
        print("no card index; run scripts/build_card_index.py first", file=sys.stderr)
        return 1
    data = default_registry()
    art = build_store(data.registry, index, allow_fetch=False)
    wanted = wanted_faces(index, data, art)

    def committed(face: Face) -> bool:
        return art.committed(face.scryfall_id, face.back) is not None

    store = art_store_dir()
    if args.dry_run:
        unavailable = read_unavailable(store)
        todo = [f for f in wanted if not committed(f) and f.name not in unavailable]
        print(f"wanted {len(wanted)}, still to fetch {len(todo)}")
        return 0

    report = backfill(wanted, store, committed=committed, limit=args.limit, delay=args.delay)
    print(
        f"wanted {report.wanted}, held {report.held}, fetched {report.fetched}, "
        f"unavailable {report.unavailable}, failed {len(report.failed)}"
        + (" (capped)" if report.capped else "")
    )
    for line in report.failed[:20]:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

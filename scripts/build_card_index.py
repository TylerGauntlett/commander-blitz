"""Turn a Scryfall bulk dump into the committed card index.

    python scripts/build_card_index.py                   # downloads if needed
    python scripts/build_card_index.py --refresh         # always re-pull
    python scripts/build_card_index.py --check           # CI: is the index current?
    python scripts/build_card_index.py --no-download     # offline; use what is cached
    python scripts/build_card_index.py --no-art          # skip the image download

**Nothing has to be gathered by hand.**  With no cached bundle this fetches the
current one from Scryfall's bulk-data API into ``data/catalog/bulk/`` and leaves
it there gzipped, so the next run is free and ``--check`` stays offline.

Scryfall reissues these dumps constantly, so this is a refresh you re-run, not a
one-off.  The bundle is ~74 MB gzipped and is never committed; the ~7 MB index
built from it is, so a fresh clone needs no bulk-data dependency at all.

Two artifacts come out:

``data/catalog/cards.sqlite``
    One row per distinct English card name that has art -- ~37k.  Read lazily,
    and only by the catalog search endpoint.

``data/catalog/registry_images.json``
    One entry per card the engine ships -- ~20 KB.  Read at server boot.  This
    is the split that keeps a 37k-row load off the trainer and the arena.

Stdlib only, so it runs without the venv.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.request
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from automtg.cards.images import (
    ART_CROP,
    COLUMNS,
    SCHEMA,
    CardIndex,
    build_registry_images,
    catalog_path,
    read_registry_images,
    registry_images_path,
    write_registry_images,
)
from automtg.cards.registry import data_dir, default_registry

BULK_DIR = data_dir() / "catalog" / "bulk"
BULK_DATA_API = "https://api.scryfall.com/bulk-data"
HEADERS = {"User-Agent": "CommanderBlitz/0.1 (+https://commanderblitz.com)", "Accept": "application/json"}

#: Which Scryfall bundle to pull.
#:
#: `default_cards` is every card in English, one row per printing -- ~74 MB
#: gzipped. `all_cards` is the same thing in every language at ~372 MB, and we
#: throw all the non-English rows away, so it costs five times the download for
#: nothing. `oracle_cards` is smaller still but keeps only one printing per
#: card, which takes away the choice of *which* printing has the best scan.
DEFAULT_BULK_TYPE = "default_cards"

#: Better scans win.  Ranked rather than boolean because Scryfall distinguishes
#: four states and only the top one is worth preferring unconditionally.
IMAGE_STATUS_RANK = {"highres_scan": 3, "lowres": 2, "placeholder": 1, "missing": 0}

#: Printings that would win a tie-break while being the wrong card.  Art series
#: are the dangerous ones: 2,650 of them carry a real card's exact name but show
#: a different, borderless illustration.
EXCLUDED_LAYOUTS = frozenset({"art_series"})
EXCLUDED_SET_TYPES = frozenset({"memorabilia", "funny"})


# ----------------------------------------------------------------------
# source resolution
# ----------------------------------------------------------------------


def newest_bundle(directory: Path) -> Path | None:
    candidates = [p for pattern in ("*.jsonl", "*.jsonl.gz") for p in directory.glob(pattern)]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def resolve_source(explicit: str | None) -> Path | None:
    """A bundle to read, without downloading anything."""
    if explicit:
        return Path(explicit)
    found = newest_bundle(BULK_DIR)
    if found is not None:
        return found
    env = os.environ.get("AUTOMTG_CARD_CATALOG")
    return Path(env) if env else None


def bulk_entry(kind: str) -> dict:
    request = urllib.request.Request(BULK_DATA_API, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        catalog = json.load(response)
    entry = next((e for e in catalog.get("data", []) if e.get("type") == kind), None)
    if entry is None:
        available = ", ".join(sorted(e.get("type", "?") for e in catalog.get("data", [])))
        raise SystemExit(f"Scryfall has no bulk type {kind!r}. Available: {available}")
    return entry


def download_bundle(kind: str = DEFAULT_BULK_TYPE) -> Path:
    """Fetch the current bundle into the drop directory, gzipped.

    Uses ``jsonl_download_uri`` -- newline-delimited and gzipped, which is both
    what the parser wants and a tenth of the size. The file is kept compressed:
    `default_cards` is ~74 MB as a `.gz` against ~600 MB expanded, and gzip
    streams line by line perfectly well.
    """
    entry = bulk_entry(kind)
    url = entry.get("jsonl_download_uri")
    if not url:
        raise SystemExit(
            f"Scryfall's {kind!r} entry has no jsonl_download_uri; the bulk-data "
            "API shape has changed and this script needs updating."
        )

    BULK_DIR.mkdir(parents=True, exist_ok=True)
    stamp = (entry.get("updated_at") or "")[:10]
    target = BULK_DIR / f"{kind}-{stamp}.jsonl.gz"
    if target.exists():
        print(f"already have {target.name}")
        return target

    size = entry.get("compressed_size") or 0
    print(f"downloading {kind} ({size / 1024 / 1024:.0f} MB compressed) -> {target.name}")
    temp = target.with_suffix(".part")
    request = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as out:
        shutil.copyfileobj(response, out, length=1 << 20)
    temp.replace(target)

    # A newer bundle supersedes the old ones; keeping them only wastes disk and
    # makes "which one did this build read" ambiguous.
    for stale in BULK_DIR.glob("*.jsonl*"):
        if stale != target and stale.suffix in (".gz", ".jsonl"):
            stale.unlink(missing_ok=True)
            print(f"  removed superseded {stale.name}")
    return target


def missing_source_message() -> str:
    return (
        f"No Scryfall bulk dump found, and --no-download was given.\n\n"
        f"  Drop one in:  {BULK_DIR}\n"
        f"  Get one from: https://scryfall.com/docs/api/bulk-data\n\n"
        f"Nothing in that directory is committed -- see data/catalog/bulk/README.md."
    )


# ----------------------------------------------------------------------
# extraction
# ----------------------------------------------------------------------


def face_images(record: dict) -> dict | None:
    """The image set for the front of a card.

    Two shapes hide behind ``card_faces`` and mixing them up loses ~4,000 cards.
    Transform / modal_dfc / double_faced_token have **no** top-level
    ``image_uris`` -- each face carries its own.  Split / adventure / flip are
    one physical card, so the top-level set is the only one and the faces have
    none.  Preferring the top level and falling back to face 0 handles both.
    """
    images = record.get("image_uris")
    if images:
        return images
    faces = record.get("card_faces") or []
    return faces[0].get("image_uris") if faces else None


def is_wanted(record: dict, *, include_funny: bool) -> bool:
    if record.get("lang") != "en" or record.get("digital") or record.get("oversized"):
        return False
    if record.get("layout") in EXCLUDED_LAYOUTS:
        return False
    if not include_funny and record.get("set_type") in EXCLUDED_SET_TYPES:
        return False
    images = face_images(record)
    return bool(images and images.get(ART_CROP))


def sort_key(record: dict) -> tuple:
    """A *total* order, so two builds of the same dump are byte-identical.

    Every component before the last is a preference; ``id`` at the end is what
    makes it deterministic when a card has two equally good printings.
    """
    # Every element reads "bigger is better", so `better()` is a plain `>`.
    return (
        IMAGE_STATUS_RANK.get(record.get("image_status"), 0),
        1 if record.get("highres_image") else 0,
        0 if record.get("promo") else 1,
        0 if record.get("textless") else 1,
        record.get("released_at") or "",
    )


def better(candidate: dict, incumbent: dict) -> bool:
    """Is ``candidate`` the printing we would rather show?"""
    left, right = sort_key(candidate), sort_key(incumbent)
    if left != right:
        return left > right
    # Equal on every preference: fall back to a stable, arbitrary total order.
    lset, rset = candidate.get("set") or "", incumbent.get("set") or ""
    if lset != rset:
        return lset < rset
    return (candidate.get("id") or "") < (incumbent.get("id") or "")


#: Layouts whose ``card_faces`` are two halves of **one** physical card, printed
#: side by side and both castable from hand. A player holding Gallifrey Falls //
#: No More reads both halves at once.
#:
#: Deliberately **not** `adventure` or `flip`, though both are also one physical
#: card. Their front face is the permanent and the pipeline's conventions are
#: built around that; widening them changes what several shipped cards claim,
#: which is its own piece of work rather than a rider on this one.
_HALVES_LAYOUTS = frozenset({"split"})


def _oracle_text(record: dict, front: dict) -> str:
    """The printed text of the card, both halves where there are two.

    Scryfall gives a split card no top-level ``oracle_text`` and one per face, so
    taking the front's was taking half the card. Every consumer downstream reads
    this column -- the authoring packet a worker writes from, and the residual
    gate -- so a split card's second half was invisible to both: nothing showed
    it to the author and nothing noticed it missing.

    Only for layouts whose faces are halves of one physical card. A transforming
    card's back is a different face of a different object; the authoring
    pipeline links it as a companion entry instead.
    """
    text = record.get("oracle_text")
    if text:
        return text
    faces = record.get("card_faces") or []
    if record.get("layout") in _HALVES_LAYOUTS and len(faces) > 1:
        return "\n".join(f.get("oracle_text", "") for f in faces if f.get("oracle_text"))
    return front.get("oracle_text", "") or ""


def to_row(record: dict) -> tuple:
    faces = record.get("card_faces") or []
    front = faces[0] if faces else {}

    def pick(key: str, default=None):
        value = record.get(key)
        if value in (None, ""):
            value = front.get(key, default)
        return value if value is not None else default

    return (
        record["name"],
        record["id"],
        record.get("oracle_id"),
        record.get("set"),
        record.get("rarity"),
        record.get("layout"),
        pick("type_line", ""),
        pick("mana_cost", ""),
        float(record.get("cmc") or 0.0),
        pick("power"),
        pick("toughness"),
        "".join(pick("colors", []) or []),
        "".join(record.get("color_identity") or []),
        1 if record.get("layout") in ("token", "double_faced_token") else 0,
        pick("artist"),
        _oracle_text(record, front),
        # Comma-joined: no keyword or mana symbol contains a comma, so the split
        # on the read side is exact.  `keywords` is card-level on Scryfall even
        # for double-faced cards, so `pick` only matters for the other two.
        ",".join(record.get("keywords") or []),
        ",".join(pick("produced_mana", []) or []),
        # Popularity, for the card-authoring queue: 32k cards and finite effort,
        # so implement the ones people play. Absent for ~12% of printings.
        record.get("edhrec_rank"),
    )


def open_bundle(source: Path):
    """Read a bundle, gzipped or not.

    Scryfall serves ``.jsonl.gz``, and there is no reason to spend 600 MB of
    disk decompressing it: gzip streams line by line just as happily, so the
    bundle stays compressed on disk and the parser never notices.
    """
    if source.suffix == ".gz":
        return gzip.open(source, "rt", encoding="utf-8")
    return source.open(encoding="utf-8")


def dedupe_key(record: dict) -> tuple[str, int]:
    """One winner per ``(name, is a token)``, not per name.

    87 names are printed both as a real card and as a token -- Tarmogoyf,
    Champion of Wits, Adorned Pouncer.  Keying on the name alone let whichever
    printing won the sort evict the other, which made those 87 real cards
    unreachable by name.  Harmless while the catalog was only a search box;
    fatal to a deck importer that has to turn a name into a playable card.
    """
    return (
        record.get("name") or "",
        1 if record.get("layout") in ("token", "double_faced_token") else 0,
    )


def extract_records(records: Iterable[dict], *, include_funny: bool = False) -> list[tuple]:
    """Reduce records to one winning printing per ``(name, is a token)``.

    Split out of :func:`extract` so the dedupe can be tested without inventing a
    bulk dump on disk -- it is the part with the judgement in it.
    """
    best: dict[tuple[str, int], dict] = {}
    for record in records:
        if not is_wanted(record, include_funny=include_funny):
            continue
        if not record.get("name"):
            continue
        key = dedupe_key(record)
        incumbent = best.get(key)
        if incumbent is None or better(record, incumbent):
            best[key] = record
    # Sorted by the same pair the table is keyed on, so two builds of one dump
    # stay byte-identical.
    return sorted((to_row(r) for r in best.values()), key=lambda row: (row[0], row[13]))


def extract(source: Path, *, include_funny: bool, limit: int | None = None) -> list[tuple]:
    """One streaming pass.  Never holds the dump in memory, only the winners."""

    def stream():
        nonlocal scanned
        with open_bundle(source) as handle:
            for line in handle:
                line = line.strip()
                if not line or line in ("[", "]"):
                    continue
                scanned += 1
                if limit and scanned > limit:
                    break
                try:
                    yield json.loads(line.rstrip(","))
                except json.JSONDecodeError:
                    continue

    scanned = 0
    rows = extract_records(stream(), include_funny=include_funny)
    print(f"  scanned {scanned:,} records -> {len(rows):,} distinct printings")
    return rows


# ----------------------------------------------------------------------
# writing
# ----------------------------------------------------------------------


def write_index(rows: list[tuple], target: Path, meta: dict[str, str]) -> None:
    """Build into a temp file and swap, so an interrupted run cannot leave a
    half-written index behind a committed filename."""
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".sqlite.tmp")
    os.close(handle)
    temp = Path(temp_name)
    try:
        con = sqlite3.connect(temp)
        con.executescript(SCHEMA)
        placeholders = ", ".join("?" * len(COLUMNS))
        con.executemany(f"INSERT INTO cards VALUES ({placeholders})", rows)
        con.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
        con.commit()
        con.execute("VACUUM")
        con.close()
        try:
            os.replace(temp, target)
        except PermissionError as error:
            # Windows refuses to replace a file another process has open, and
            # the dev server holds the index open for the whole of its life.
            # The bare WinError 5 gives no hint of that, so say it plainly.
            raise SystemExit(
                f"Cannot replace {target}: another process is holding it open.\n"
                f"Stop the API server (uvicorn) and re-run.\n"
                f"  original error: {error}"
            ) from error
    finally:
        temp.unlink(missing_ok=True)


def previous_rows(path: Path) -> dict[tuple[str, int], str]:
    """``(name, is_token) -> scryfall_id`` for the committed index.

    Keyed on the pair the table is keyed on, so the change summary and
    ``--check`` both see a token and its same-named card as two rows rather than
    as one row flapping between two ids on every build.
    """
    if not path.exists():
        return {}
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        rows = {
            (name, int(is_token or 0)): scryfall_id
            for name, is_token, scryfall_id in con.execute(
                "SELECT name, is_token, scryfall_id FROM cards"
            )
        }
        con.close()
        return rows
    except sqlite3.Error:
        return {}


def _label(key: tuple[str, int]) -> str:
    name, is_token = key
    return f"{name} (token)" if is_token else name


def summarise(before: dict[tuple[str, int], str], rows: list[tuple]) -> None:
    after = {(row[0], row[13]): row[1] for row in rows}
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(n for n in set(after) & set(before) if after[n] != before[n])
    print(f"  rows {len(before):,} -> {len(after):,}")
    print(f"  added {len(added):,}  removed {len(removed):,}  reprinted {len(changed):,}")
    for label, keys in (("added", added), ("removed", removed), ("reprinted", changed)):
        for key in keys[:5]:
            print(f"    {label}: {_label(key)}")
        if len(keys) > 5:
            print(f"    {label}: ... and {len(keys) - 5:,} more")


# ----------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--catalog", help="explicit path to a bulk .jsonl or .jsonl.gz")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="always pull the current bundle from Scryfall, even if one is cached",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="never reach the network; fail if no bundle is cached locally",
    )
    parser.add_argument(
        "--bulk-type",
        default=DEFAULT_BULK_TYPE,
        help=f"Scryfall bulk type to pull (default {DEFAULT_BULK_TYPE})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild in memory and compare; exit 1 on drift, 0 when no dump is present",
    )
    parser.add_argument("--no-art", action="store_true", help="skip the image download")
    parser.add_argument("--include-funny", action="store_true", help="keep Un-set printings")
    parser.add_argument("--limit", type=int, help="stop after N records (for tests)")
    parser.add_argument("--out", help="output directory (default data/catalog)")
    args = parser.parse_args()

    # Downloading is the default path, not an opt-in. Requiring someone to
    # hand-gather a 600 MB file first made this reproducible only on the one
    # machine that happened to have it.
    source = resolve_source(args.catalog)
    cached = source is not None and source.exists()
    may_download = not args.no_download and not args.catalog and not args.check
    if may_download and (args.refresh or not cached):
        source = download_bundle(args.bulk_type)

    if source is None or not source.exists():
        if args.check:
            # `--check` never downloads: it is a CI gate, and a gate that pulls
            # 74 MB on every run is a gate nobody keeps.
            print("SKIP: no Scryfall bulk dump cached; cannot verify the index is current")
            return 0
        print(missing_source_message(), file=sys.stderr)
        return 2

    out_dir = Path(args.out) if args.out else catalog_path().parent
    index_file = out_dir / "cards.sqlite"

    print(f"reading {source}")
    started = time.time()
    rows = extract(source, include_funny=args.include_funny, limit=args.limit)
    if not rows:
        print("no usable records found -- is this a Scryfall bulk dump?", file=sys.stderr)
        return 2

    before = previous_rows(index_file)

    if args.check:
        after = {(row[0], row[13]): row[1] for row in rows}
        if after == before:
            print(f"index is current ({len(after):,} rows)")
            return 0
        print("index is STALE -- run: python scripts/build_card_index.py", file=sys.stderr)
        summarise(before, rows)
        return 1

    summarise(before, rows)
    meta = {
        "source_name": source.name,
        "source_bytes": str(source.stat().st_size),
        "source_mtime": datetime.fromtimestamp(source.stat().st_mtime, UTC).isoformat(),
        "built_at": datetime.now(UTC).isoformat(),
        "rows": str(len(rows)),
        "builder": "scripts/build_card_index.py",
    }
    write_index(rows, index_file, meta)
    size_mb = index_file.stat().st_size / 1024 / 1024
    print(f"wrote {index_file} ({size_mb:.1f} MB) in {time.time() - started:.0f}s")

    # The small artifact: resolve every card the engine actually ships.
    index = CardIndex(index_file)
    registry = default_registry().registry
    images = build_registry_images(registry, index)
    index.close()

    target = out_dir / "registry_images.json" if args.out else registry_images_path()
    write_registry_images(images, target)
    resolved = sum(1 for art in images.values() if art.has_printing)
    print(f"wrote {target} ({resolved}/{len(images)} engine cards resolved)")
    for card_id, art in sorted(images.items()):
        if not art.has_printing:
            print(f"    no printing: {card_id}")

    if not args.no_art:
        print()
        from fetch_card_art import fetch_all

        fetch_all(read_registry_images(target))

    return 0


if __name__ == "__main__":
    sys.exit(main())

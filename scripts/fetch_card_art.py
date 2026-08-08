"""Download card art into ``data/art/``, once, so the app owns its images.

    python scripts/fetch_card_art.py
    python scripts/fetch_card_art.py --only sol_ring forest
    python scripts/fetch_card_art.py --dry-run

Normally you do not run this directly -- ``build_card_index.py`` calls it at the
end, so one command takes a fresh Scryfall dump all the way to owned bytes.

The architecture is the one ``mockups/fetch_art.py`` established and
``docs/card-hydration.md`` asked for: fetch once, store in the repo, skip what is
already there, no service running anywhere.  What changed is that it makes **zero
Scryfall API calls** -- the printing ids come from the committed index, so only
the image CDN is touched, and a re-run costs nothing.

Files are keyed on the engine ``card_id``, not a slug of the card name: two token
defs are both named "Vampire", so a name slug would collide and one would
silently overwrite the other.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automtg.cards.images import (
    ART_CROP,
    CardArt,
    art_dir,
    read_registry_images,
)

# Scryfall asks for a descriptive User-Agent and ~50-100ms between requests.
HEADERS = {"User-Agent": "AutoMTG/0.1"}
DELAY = 0.1
TIMEOUT = 30


def manifest_path() -> Path:
    return art_dir() / "manifest.json"


def art_file(card_id: str) -> Path:
    return art_dir() / f"{card_id}.jpg"


def download(url: str, path: Path) -> int | None:
    """Bytes written, or ``None`` if the fetch failed.

    Writes via a temp file and renames, so an interrupted download cannot leave
    a truncated JPEG that later runs would happily skip as "already present".
    """
    request = urllib.request.Request(url, headers=HEADERS)
    temp = path.with_suffix(".part")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            payload = response.read()
        if not payload:
            return None
        temp.write_bytes(payload)
        temp.replace(path)
        return len(payload)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
        print(f"  download failed: {error}")
        temp.unlink(missing_ok=True)
        return None


def fetch_all(
    images: dict[str, CardArt],
    *,
    only: set[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """Fetch every missing crop.  Returns the number downloaded."""
    directory = art_dir()
    directory.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict] = {}
    if manifest_path().exists():
        try:
            manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}

    wanted = sorted(images) if only is None else sorted(set(images) & only)
    fetched = skipped = artless = failed = 0

    for card_id in wanted:
        art = images[card_id]
        if not art.has_printing:
            # Expected for the handful of custom cards; the client draws a plate.
            artless += 1
            continue

        path = art_file(card_id)
        if path.exists() and not force:
            skipped += 1
            manifest.setdefault(
                card_id, {"file": path.name, "scryfall_id": art.scryfall_id, "artist": art.artist}
            )
            continue

        url = art.remote_url(ART_CROP)
        if dry_run:
            print(f"would fetch {card_id} <- {url}")
            fetched += 1
            continue

        print(f"fetch {card_id}")
        size = download(url, path)
        time.sleep(DELAY)
        if size is None:
            failed += 1
            continue
        fetched += 1
        manifest[card_id] = {
            "file": path.name,
            "scryfall_id": art.scryfall_id,
            "artist": art.artist,
            "bytes": size,
        }

    if not dry_run:
        manifest_path().write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    total = sum(p.stat().st_size for p in directory.glob("*.jpg"))
    print(
        f"art: {fetched} fetched, {skipped} already present, {artless} have no printing, "
        f"{failed} failed -- {len(manifest)} files, {total / 1024 / 1024:.1f} MB"
    )
    return fetched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", nargs="*", help="restrict to these engine card ids")
    parser.add_argument("--force", action="store_true", help="re-download files already present")
    parser.add_argument("--dry-run", action="store_true", help="list what would be fetched")
    args = parser.parse_args()

    images = read_registry_images()
    if not images:
        print(
            "No registry_images.json. Run: python scripts/build_card_index.py",
            file=sys.stderr,
        )
        return 2

    fetch_all(
        images,
        only=set(args.only) if args.only else None,
        force=args.force,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Pull the real Magic mana symbols.

Written for the card-face prototypes; direction D shipped, so these are now the
client's symbols too and the script mirrors them into
`frontend/public/symbols/` on every run.

The client used to draw mana costs as a bare letter on a CSS disc -- `.pip` in
`frontend/src/styles/cards.css`, fed by `manaPips` in `logic/cardStyle.ts`. It was
a symbol nobody who plays the game recognises. The actual marks are published,
as SVG, from an open endpoint that needs no key:

    https://api.scryfall.com/symbology   ->  [{ symbol: "{G}", svg_uri: ... }, ...]

One call lists every card symbol; each entry carries an `svg_uri`. Same
provenance as the card art this repo already vendors (see docs/card-catalog.md),
and the same architecture: fetch once, store in the repo, skip on re-run, nothing
running anywhere at render time.

    python mockups/cards/fetch_symbols.py

Stdlib only, so it runs without the venv -- matching mockups/fetch_art.py, whose
`get_json` / `download` shape this borrows.

The SVGs are consumed as `<img src="symbols/G.svg">`, never inlined. A mockup has
to open standalone from `file://`, where `fetch()` is blocked by the opaque
origin but `<img>` is not. Scryfall's symbols ship fully coloured, so nothing
needs recolouring through `currentColor` -- which is just as well, because an
`<img>` could not be recoloured anyway.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

SYMBOL_DIR = Path(__file__).parent / "symbols"
MANIFEST = SYMBOL_DIR / "manifest.json"

# The client draws these too, now that direction D shipped -- `ManaSymbol` loads
# them from `/symbols/`, which Vite serves out of `public/` in dev and copies
# into `dist/` on build. Mirrored rather than symlinked or imported: the mockup
# has to keep opening standalone from `file://` with no build step, and the
# client has to keep shipping without reaching into `mockups/`.
#
# Kept in step here so a re-run cannot leave the shipped copy stale, which is a
# failure that shows up as a blank square rather than as an error.
MIRROR_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "symbols"

# Scryfall asks for a descriptive User-Agent and ~50-100ms between requests.
HEADERS = {"User-Agent": "AutoMTG-mockups/0.1", "Accept": "application/json"}
DELAY = 0.1

SYMBOLOGY = "https://api.scryfall.com/symbology"

# What the engine can actually put in front of a player.
#
#   WUBRG + C   mana
#   0-16 + X    generic. The engine caps far below 16, but the whole numeric run
#               is a few KB and a missing numeral is an invisible failure.
#   T Q S E     the four non-mana symbols `SYMBOL_LABELS` in cardStyle.ts covers:
#               tap, untap, snow, energy.
#
# Hybrid and phyrexian costs are rejected by the engine at load time, so they are
# deliberately not downloaded -- a prototype that draws one is drawing a card this
# game cannot contain.
WANTED = ["W", "U", "B", "R", "G", "C"] + [str(n) for n in range(17)] + ["X", "T", "Q", "S", "E"]


def key_for(symbol: str) -> str:
    """`{G}` -> `G`, `{G/U}` -> `G-U`. A filename, not a slug: case matters."""
    return symbol.strip("{}").replace("/", "-")


def get_json(url: str) -> dict | None:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        print(f"  lookup failed: {error}")
        return None


def download(url: str, path: Path) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            path.write_bytes(response.read())
        return True
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        print(f"  download failed: {error}")
        return False


def mirror() -> None:
    """Copy the symbols the client draws into `frontend/public/symbols/`."""
    if not MIRROR_DIR.parent.exists():
        print(f"no {MIRROR_DIR.parent} -- skipping the client mirror")
        return
    MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source in [*sorted(SYMBOL_DIR.glob("*.svg")), MANIFEST]:
        if not source.exists():
            continue
        target = MIRROR_DIR / source.name
        payload = source.read_bytes()
        # Only on a real difference, so a no-op run does not churn mtimes and
        # set every watcher in the repo off.
        if target.exists() and target.read_bytes() == payload:
            continue
        target.write_bytes(payload)
        copied += 1
    print(f"mirrored {copied} file(s) to {MIRROR_DIR}")


def main() -> None:
    SYMBOL_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    # Every symbol already on disk and in the manifest: a second run is free, and
    # so is the symbology call itself if there is nothing left to want.
    missing = [k for k in WANTED if not ((SYMBOL_DIR / f"{k}.svg").exists() and k in manifest)]
    if not missing:
        print(f"all {len(WANTED)} symbols present -- nothing to fetch")
        mirror()
        return

    print(f"listing symbology ({len(missing)} missing)")
    payload = get_json(SYMBOLOGY)
    if payload is None:
        raise SystemExit("symbology unavailable")
    time.sleep(DELAY)

    catalog = {key_for(entry["symbol"]): entry for entry in payload.get("data", [])}

    for key in missing:
        entry = catalog.get(key)
        if entry is None:
            print(f"  {key}: not in symbology -- skipped")
            continue
        url = entry.get("svg_uri")
        if not url:
            print(f"  {key}: no svg_uri -- skipped")
            continue

        path = SYMBOL_DIR / f"{key}.svg"
        print(f"fetch {entry['symbol']}")
        if not download(url, path):
            continue
        time.sleep(DELAY)

        manifest[key] = {
            "symbol": entry["symbol"],
            "file": path.name,
            "english": entry.get("english"),
            "colors": entry.get("colors"),
        }

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\n{len(manifest)} entries in {MANIFEST}")
    mirror()


if __name__ == "__main__":
    main()

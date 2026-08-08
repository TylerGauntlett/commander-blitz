"""Pull card art crops for the board-state mockups.

SUPERSEDED. This only ever covered the twenty cards on the mockup board state.
The real pipeline is scripts/build_card_index.py + scripts/fetch_card_art.py,
which resolves the whole registry from a Scryfall bulk dump -- see
docs/card-catalog.md. Kept so the mockups still open standalone.

Follows the fetch-once, store-in-the-repo, skip-on-rerun architecture the
superseded docs/card-hydration.md asked for -- but not its endpoint. `api2.moxfield.com/v2/cards/search/user` answers a scripted client with
a Cloudflare 403 interstitial, so the id it returns is unreachable and the
`assets.moxfield.net/cards/card-{id}-normal.webp` leg (which does work) has
nothing to key on.

Scryfall's `cards/named` is open, needs no key, and hands back `image_uris.
art_crop` -- which is a strict improvement for this use: Moxfield's asset is the
whole card, so an art band would mean cropping the art back out of a rendered
frame in CSS.

    python mockups/fetch_art.py

Stdlib only, so it runs without the venv.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ART_DIR = Path(__file__).parent / "art"
MANIFEST = ART_DIR / "manifest.json"

# Scryfall asks for a descriptive User-Agent and ~50-100ms between requests.
HEADERS = {"User-Agent": "AutoMTG-mockups/0.1", "Accept": "application/json"}
DELAY = 0.1

# Every distinct card on the mockup board state, plus two that are not on it.
#
# `mockups/cards/` draws one card of each type tone rather than a board, and the
# board state has no artifact and no instant -- two of the eight tones in
# `typeTone`. Sol Ring (data/cards/core.cards.json) and Beast Within
# (data/cards/aesi.cards.json) are real cards in this game's registry, so the
# gallery stays honest about what it contains.
#
# Tokens are looked up differently -- there is no `cards/named` entry for
# "Vampire" the token.
CARDS = [
    "Acidic Slime",
    "Aesi, Tyrant of Gyre Strait",
    "Beast Within",
    "Edgar Markov",
    "Elvish Visionary",
    "Explore",
    "Explosive Vegetation",
    "Falkenrath Noble",
    "Forest",
    "Garruk's Packleader",
    "Gyre Sage",
    # Kept deliberately though it 404s: `aetherling_serpent` in
    # data/cards/aesi.cards.json is a renamed card with no real printing, and it
    # is on the mockup board. Five of the 138 non-token cards across both decks
    # are like this, so 05-planar-art.html has to show the text-frame fallback.
    "Gyre Strait Leviathan",
    "Island",
    "Mountain",
    "Nimble Mongoose",
    "Scoured Barrens",
    "Sol Ring",
    "Thornwood Falls",
    "Vampire Neonate",
    "Vorel of the Hull Clade",
    "Yavimaya Elder",
    "Zendikar's Roil",
]

TOKENS = ["Vampire", "Elemental"]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def get_json(url: str) -> dict | None:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        print(f"  lookup failed: {error}")
        return None


def find_card(name: str, *, token: bool) -> dict | None:
    """The printing to take art from. Tokens have no exact-name endpoint."""
    if token:
        query = urllib.parse.quote(f'!"{name}" t:token')
        payload = get_json(
            f"https://api.scryfall.com/cards/search?q={query}&order=released&dir=desc"
        )
        data = (payload or {}).get("data") or []
        return data[0] if data else None
    query = urllib.parse.quote(name)
    return get_json(f"https://api.scryfall.com/cards/named?exact={query}")


def art_url(card: dict) -> str | None:
    """`image_uris` is absent on multi-faced layouts; take the front face."""
    images = card.get("image_uris")
    if not images:
        faces = card.get("card_faces") or []
        images = faces[0].get("image_uris") if faces else None
    return (images or {}).get("art_crop")


def download(url: str, path: Path) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            path.write_bytes(response.read())
        return True
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        print(f"  download failed: {error}")
        return False


def main() -> None:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    wanted = [(name, False) for name in CARDS] + [(name, True) for name in TOKENS]

    for name, token in wanted:
        key = f"token:{name}" if token else name
        slug = ("token-" if token else "") + slugify(name)
        path = ART_DIR / f"{slug}.jpg"

        # The whole point of storing these in the repo: a second run is free.
        if path.exists() and key in manifest:
            print(f"skip  {name}")
            continue

        print(f"fetch {name}")
        card = find_card(name, token=token)
        time.sleep(DELAY)
        if card is None:
            print("  no match -- mockup falls back to the text frame")
            continue

        url = art_url(card)
        if url is None:
            print("  no art_crop -- mockup falls back to the text frame")
            continue

        if not download(url, path):
            continue
        time.sleep(DELAY)

        manifest[key] = {
            "file": path.name,
            "scryfall_id": card.get("id"),
            "set": card.get("set"),
            "artist": card.get("artist"),
        }

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\n{len(manifest)} entries in {MANIFEST}")


if __name__ == "__main__":
    main()

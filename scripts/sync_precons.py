"""The official Commander precons, as a manifest, and a precon as a deck file.

    python scripts/sync_precons.py                    rewrite data/decks/sources.json
    python scripts/sync_precons.py --missing <id>     the cards of one precon the engine lacks
    python scripts/sync_precons.py --write-deck <id>  write data/decks/<id>.deck.json
    python scripts/sync_precons.py --as-of 2026-10-24 the window's end, instead of today
    python scripts/sync_precons.py --roadmap          one roadmap item per precon not shipped, ranked

"Precon" means a list Wizards sold (ADR 0024). Those lists are published data:
MTGJSON's ``DeckList.json`` names every preconstructed deck with its set and
release date, and its per-deck files carry the exact list and printings. This
reads them and writes ``data/decks/sources.json``: one row per Commander precon
released inside the window, newest first. The window is ``WINDOW_YEARS``, one
constant, so it rolls rather than going stale, and widening it is a change here
and a run of the script.

What counts as a precon, so the shelf promises one thing:

- the deck's type is ``Commander Deck``, and its set's type is ``commander``.
  That leaves out Secret Lair drops and the one-off ``eternal`` products, which
  are sold as collectibles rather than as a Commander release;
- a *Collector's Edition* is the same list as its plain deck in other finishes,
  so it is dropped and the plain deck stands for both.

Each row carries its commanders' names and printings, so the shelf can show a
precon that is not playable yet as a "coming soon" tile.

A run reports every shipped ``precon`` deck whose row is gone: a set that aged
out of the window, to retire from the shelf in the same change.

``--roadmap`` keeps the backlog in step with the manifest: every row without a
deck file has an item ``docs/roadmap/precon-<id>.md``, and the items are ranked
so the queue closes out one set at a time, newest set first, and inside a set
the precon fewest cards short first. A new item gets the batch procedure of the
``precon-sets`` item and the decisions that let ``/extend-roadmap --auto`` build
it; an existing item keeps its text and only its rank moves. Run it after a
manifest refresh, then ``roadmap.py --write``.

Downloads are cached in ``data/catalog/bulk/mtgjson/``, which is gitignored;
``--refresh`` re-pulls them. Stdlib plus the card layer, which ``--missing`` and
``--write-deck`` need to resolve names.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

#: How far back the shelf's precons reach, in years before ``as_of``.
WINDOW_YEARS = 5

MTGJSON = "https://mtgjson.com/api/v5"
HEADERS = {"User-Agent": "CommanderBlitz/0.1 (+https://commanderblitz.com)"}
CACHE = ROOT / "data" / "catalog" / "bulk" / "mtgjson"
MANIFEST = ROOT / "data" / "decks" / "sources.json"
DECKS = ROOT / "data" / "decks"
ROADMAP = ROOT / "docs" / "roadmap"

#: The batch procedure every precon item points at (its heading on the page).
PRECON_SETS_ANCHOR = "#every-precon-native-one-at-a-time-then-every-import"

#: The deck and set types a precon has. See the module docstring.
DECK_TYPE = "Commander Deck"
SET_TYPE = "commander"
COLLECTOR = re.compile(r"collector'?s edition", re.IGNORECASE)


# ----------------------------------------------------------------------
# the window and the rows: pure, and what the tests hold
# ----------------------------------------------------------------------


def window_start(as_of: datetime.date) -> datetime.date:
    """The first day inside the window that ends on ``as_of``."""
    try:
        return as_of.replace(year=as_of.year - WINDOW_YEARS)
    except ValueError:  # 29 February
        return as_of.replace(year=as_of.year - WINDOW_YEARS, day=28)


def in_window(date: str, as_of: datetime.date) -> bool:
    day = datetime.date.fromisoformat(date)
    return window_start(as_of) <= day <= as_of


def precon_id(set_code: str, product: str) -> str:
    """``fdc_calling_all_angels``: the set and the product, never the commander,
    which a favorite or a later reprint may share (ADR 0024)."""
    slug = re.sub(r"[^a-z0-9]+", "_", product.lower().replace("'", "")).strip("_")
    return f"{set_code.lower()}_{slug}"


def manifest_rows(
    deck_list: list[dict], set_list: list[dict], as_of: datetime.date
) -> list[dict]:
    """The manifest's rows from MTGJSON's two lists, newest first."""
    sets = {s["code"]: s for s in set_list}
    rows = []
    for deck in deck_list:
        code = deck["code"]
        if deck.get("type") != DECK_TYPE or COLLECTOR.search(deck["name"]):
            continue
        if sets.get(code, {}).get("type") != SET_TYPE:
            continue
        if not in_window(deck["releaseDate"], as_of):
            continue
        rows.append(
            {
                "id": precon_id(code, deck["name"]),
                "product": deck["name"],
                "set_code": code,
                "set_name": sets[code]["name"],
                "date": deck["releaseDate"],
                "source": f"{MTGJSON}/decks/{deck['fileName']}.json",
            }
        )
    rows.sort(key=lambda r: (r["set_code"], r["id"]))
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def read_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# MTGJSON
# ----------------------------------------------------------------------


def fetch(name: str, *, refresh: bool = False) -> dict:
    """One MTGJSON file's ``data``, from the cache or the network."""
    path = CACHE / name
    if refresh or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(f"{MTGJSON}/{name}", headers=HEADERS)
        with urllib.request.urlopen(request, timeout=120) as response:
            path.write_bytes(response.read())
    return json.loads(path.read_text(encoding="utf-8"))["data"]


def row_for(deck_id: str) -> dict:
    for row in read_manifest()["rows"]:
        if row["id"] == deck_id:
            return row
    raise SystemExit(f"{deck_id} has no row in {MANIFEST.relative_to(ROOT)}")


def published_list(row: dict, *, refresh: bool = False) -> dict:
    return fetch(f"decks/{row['source'].rsplit('/', 1)[1]}", refresh=refresh)


def _names(deck: dict) -> tuple[list[dict], list[dict]]:
    return deck.get("commander", []), deck.get("mainBoard", [])


def commanders_of(deck: dict) -> list[dict]:
    """``[{name, scryfall_id}]``: who heads a precon, with the printing it shipped.

    Held in the manifest so the shelf can show a precon that is not playable
    yet as a "coming soon" tile with its commander's art, without the engine
    knowing the card: art is served by Scryfall id (``/art/{id}.jpg``).
    """
    commanders, _ = _names(deck)
    return [
        {"name": c["name"], "scryfall_id": c.get("identifiers", {}).get("scryfallId", "")}
        for c in commanders
    ]


def missing(row: dict, registry, *, refresh: bool = False) -> list[str]:
    """The names in a precon the authored layer cannot play."""
    commanders, main = _names(published_list(row, refresh=refresh))
    return sorted(
        {c["name"] for c in commanders + main if _resolve(registry, c["name"]) is None}
    )


def _resolve(registry, name: str):
    return registry.by_name(name) or registry.by_name(name.split("//")[0].strip())


def deck_file(row: dict, registry, *, refresh: bool = False) -> dict:
    """A precon as a deck file: the list, its printings and its release.

    Refuses a list with a card the authored layer lacks, like
    ``promote_deck.py``: a shipped deck naming an id that only exists on one
    machine would fail the next boot everywhere else. The editorial fields
    are left for a person; ``tests/cards/test_deck_metadata.py`` asks for them.
    """
    deck = published_list(row, refresh=refresh)
    gaps = missing(row, registry)
    if gaps:
        raise SystemExit(f"{row['id']} has {len(gaps)} card(s) the engine lacks: " + ", ".join(gaps))
    commanders, main = _names(deck)
    printings: dict[str, dict] = {}
    commander_ids: list[str] = []
    counts: dict[str, int] = {}
    for position, card in enumerate(commanders + main):
        card_id = _resolve(registry, card["name"]).id
        if position < len(commanders):
            commander_ids.append(card_id)
        else:
            counts[card_id] = counts.get(card_id, 0) + card["count"]
        scryfall = card.get("identifiers", {}).get("scryfallId")
        if scryfall:
            printings.setdefault(
                card_id,
                {
                    "scryfall_id": scryfall,
                    "artist": card.get("artist"),
                    "set_code": card["setCode"].lower(),
                    "collector_number": card["number"],
                },
            )
    identity = sorted({c for cid in commander_ids for c in registry.get(cid).color_identity})
    return {
        "id": row["id"],
        "name": row["product"],
        "commanders": commander_ids,
        "color_identity": identity,
        "source": "precon",
        "release": {"set_code": row["set_code"], "set_name": row["set_name"], "date": row["date"]},
        "notes": f"{row['set_name']} precon, card for card ({row['source']}).",
        "tags": [],
        "strategy": "",
        "archetype": "",
        "printings": dict(sorted(printings.items())),
        "cards": [{"id": cid, **({"qty": n} if n > 1 else {})} for cid, n in sorted(counts.items())],
    }


def _shipped_precons() -> dict[str, Path]:
    out = {}
    for path in sorted(DECKS.glob("*.deck.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("source", "precon") == "precon":
            out[raw["id"]] = path
    return out


def roadmap_id(row_id: str) -> str:
    return "precon-" + row_id.replace("_", "-")


def effort_for(short: int) -> str:
    """Sized by how many cards the precon lacks: the work is mostly per card."""
    return "S" if short < 15 else "M" if short < 40 else "L"


def item_body(row: dict) -> str:
    rid, product = row["id"], row["product"]
    return f"""
## Today

{product}, the {row["set_name"]} precon released {row["date"]}, is a
coming-soon shell on the shelf: its row `{rid}` is in
`data/decks/sources.json` and there is no `data/decks/{rid}.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing {rid}` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.

## The change

{product} ships native, card for card, as one batch of
[every precon native]({PRECON_SETS_ANCHOR}), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck {rid}`, the
   dossier and the archetype, and the deck joins `PRECONS` in
   `tests/cards/test_deck_legality.py`; its shell leaves the shelf by itself.
4. One `/author-cards` wave over the pending cards the new capabilities reach.

It does not touch another precon's deck.

## Gate

`tests/cards/test_precon_imports.py` over the new deck; one unit test under
`tests/unit/` per capability; the manifest test and
`tests/server/test_upcoming_precons.py` still green; and the sampled
whole-game test able to draw the deck.

## Decisions

- **Scope:** this precon only, taken to 100% in one pull request titled
  `feat(cards):`; the harvest is one `/author-cards` wave and no more.
- **The editorial fields:** the run writes the dossier and picks the closest
  existing `archetype`. It adds no strategy module or `docs/cpus/` page; an
  archetype that visibly misplays the deck is a new item.
- **A capability that needs a rules subsystem the engine does not have**
  (`rules-coverage.md`, not implemented): the run stops there, writes it as its
  own item through `/plan-feature`, adds it to this item's `depends_on`, sets
  this item back to `proposed`, and opens the pull request with the cards and
  capabilities done so far. This item stays until the deck is whole.
"""


def precon_order(pending: list[dict], short: dict[str, int]) -> list[dict]:
    """Set by set, newest set first; inside a set, the precon fewest cards short first."""
    newest: dict[str, str] = {}
    for r in pending:
        newest[r["set_code"]] = max(newest.get(r["set_code"], ""), r["date"])
    # Two stable sorts: the second keeps the first's order inside each set.
    order = sorted(pending, key=lambda r: (r["set_code"], short[r["id"]], r["product"].lower()))
    order.sort(key=lambda r: newest[r["set_code"]], reverse=True)
    return order


def sync_roadmap(rows: list[dict], registry) -> list[str]:
    """Write or re-rank one roadmap item per precon not shipped; returns notes."""
    import roadmap  # scripts/roadmap.py, beside this file

    pending = [r for r in rows if not (DECKS / f"{r['id']}.deck.json").exists()]
    short = {r["id"]: len(missing(r, registry)) for r in pending}
    notes = []
    for rank, row in enumerate(precon_order(pending, short), 1):
        path = ROADMAP / f"{roadmap_id(row['id'])}.md"
        if path.exists():
            item = roadmap.parse_item(path.read_text(encoding="utf-8"), path)
            item.rank = rank
        else:
            item = roadmap.Item(
                id=roadmap_id(row["id"]),
                title=f"{row['product']} ({row['set_name']})",
                area="decks",
                effort=effort_for(short[row["id"]]),
                impact="high",
                why="a coming-soon tile on the shelf becomes a deck a player can pick",
                body=item_body(row).lstrip("\n"),
                rank=rank,
            )
            notes.append(f"planned {item.id}")
        roadmap.write_item(item, ROADMAP)
    wanted = {roadmap_id(r["id"]) for r in pending}
    for path in sorted(ROADMAP.glob("precon-*.md")):
        if path.stem != "precon-sets" and path.stem not in wanted:
            notes.append(f"{path.stem} has no pending row: --done it with its deck, or --drop it")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--as-of", type=datetime.date.fromisoformat, default=datetime.date.today())
    parser.add_argument("--refresh", action="store_true", help="re-pull MTGJSON")
    parser.add_argument("--missing", metavar="ID", help="list the cards a precon lacks")
    parser.add_argument("--write-deck", metavar="ID", help="write a precon's deck file")
    parser.add_argument("--roadmap", action="store_true", help="one ranked roadmap item per precon")
    args = parser.parse_args()

    if args.roadmap:
        from commanderblitz.cards.registry import default_registry

        rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["rows"]
        for note in sync_roadmap(rows, default_registry().registry):
            print(note)
        print("run `python scripts/roadmap.py --write`")
        return 0

    if args.missing or args.write_deck:
        from commanderblitz.cards.registry import default_registry

        registry = default_registry().registry
        row = row_for(args.missing or args.write_deck)
        if args.missing:
            print("\n".join(missing(row, registry, refresh=args.refresh)))
            return 0
        target = DECKS / f"{row['id']}.deck.json"
        if target.exists():
            raise SystemExit(f"{target} already exists; refusing to overwrite it")
        out = deck_file(row, registry, refresh=args.refresh)
        target.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(target)
        return 0

    rows = manifest_rows(
        fetch("DeckList.json", refresh=args.refresh),
        fetch("SetList.json", refresh=args.refresh),
        args.as_of,
    )
    for row in rows:
        row["commanders"] = commanders_of(published_list(row, refresh=args.refresh))
    manifest = {"window_years": WINDOW_YEARS, "as_of": args.as_of.isoformat(), "rows": rows}
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(rows)} precons since {window_start(args.as_of)}")
    ids = {row["id"] for row in rows}
    for deck_id, path in _shipped_precons().items():
        if deck_id not in ids:
            print(f"retire {path.relative_to(ROOT)}: its row left the window")
    return 0


if __name__ == "__main__":
    sys.exit(main())

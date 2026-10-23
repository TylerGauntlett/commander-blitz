"""A deck as a machine needs it to play offline (ADR 0022).

The site builds a **bundle** for an imported deck: the deck file it wrote, the
definition of every card the deck names, and every face and token those cards
reach.  A desktop build **adopts** one.  The two halves live together because
they are one format, and a change to either end is a change to both.

Adopting is a reconciliation, card by card, in the importer's order of trust:

``native``
    A card this machine already has in its authored layer -- what it ships,
    plus any hand-written card it took from the site before.  Its own copy
    wins; the site's definition is not even compiled.
taken as data
    A definition this machine lacks and its loader accepts, together with the
    faces and tokens it reaches.  The site's hand-written cards go to
    ``site.cards.json`` and its proxies to the ordinary pool, so the next
    content update's authored layer replaces either one at load.
a local proxy
    A definition this machine's loader refuses -- the site's vocabulary is
    newer than this engine -- becomes a proxy built from this machine's own
    catalog, with a note that says why, exactly as an unsupported card does.

Every definition is compiled and linked before anything is written, so a card
this machine cannot run never reaches a file the next boot would fail on.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from commanderblitz.engine.carddef import CardDef
from commanderblitz.engine.errors import DslError

from .images import CardIndex
from .importer import (
    ImportReport,
    ResolvedCard,
    count_lands,
    coverage_path,
    decks_dir,
    persist_adopted,
)
from .loader import compile_card
from .loader.linking import link_faces, token_references, validate_token_references
from .moxfield import ImportFailed, Printing
from .proxy import ProxyResult, build_proxy, facts_from_index
from .registry import CardRegistry, DeckList, authored_card_paths, generated_dir, validate_deck
from .schema import CardModel, DeckModel

#: Added to a card the site could say more about than this machine can.
NEWER_RULES = "its rules need a newer version of the app; it plays in full after the next update"


# ----------------------------------------------------------------------
# the site's half
# ----------------------------------------------------------------------


def references(card: CardDef) -> set[str]:
    """Every card id ``card`` cannot be loaded without: its other faces, the
    card it melds into, and every token it can create."""
    faces = (
        card.back_face,
        card.front_face,
        card.second_face,
        card.parent_face,
        card.prepared_face,
        card.melds_into,
    )
    return {face for face in faces if face} | token_references(card)


def closure(ids: Iterable[str], lookup: Callable[[str], CardDef | None]) -> set[str]:
    """``ids`` and everything they reference, transitively.  An id ``lookup``
    cannot find is left out rather than followed."""
    out: set[str] = set()
    pending = list(ids)
    while pending:
        card_id = pending.pop()
        if card_id in out:
            continue
        card = lookup(card_id)
        if card is None:
            continue
        out.add(card_id)
        pending.extend(references(card) - out)
    return out


def card_files() -> list[Path]:
    """Every card file the server loads, in the order its registry trusts them."""
    return authored_card_paths() + sorted((generated_dir() / "cards").glob("*.cards.json"))


def raw_definitions() -> dict[str, dict]:
    """``card id -> its entry in a card file``, first file wins, as the registry
    resolves a clash.  Cached on the files' modification times, so an import
    that rewrites the pool is seen by the next bundle."""
    files = card_files()
    return _read_definitions(tuple((str(path), path.stat().st_mtime_ns) for path in files))


@lru_cache(maxsize=1)
def _read_definitions(stamp: tuple[tuple[str, int], ...]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path, _ in stamp:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        for entry in raw["cards"] if isinstance(raw, dict) else raw:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                out.setdefault(entry["id"], entry)
    return out


def build_bundle(deck: DeckList, registry: CardRegistry, images: Mapping) -> dict:
    """The bundle for an imported deck, in the shape of ``DeckBundle``.

    ``images`` is the art map (``ArtStore.images``): a card the receiving
    machine has never seen needs to know which printing shows it, or it is a
    card with no art there.  Raises ``LookupError`` for a deck with no file
    under ``generated/decks``, which is every precon: those ship everywhere.
    """
    path = decks_dir() / f"{deck.id}.deck.json"
    if not path.is_file():
        raise LookupError(deck.id)
    deck_file = json.loads(path.read_text(encoding="utf-8"))
    ids = closure(deck.unique_ids(), lambda cid: registry.get(cid) if cid in registry else None)
    definitions = raw_definitions()
    coverage = _read_json(coverage_path())
    return {
        "deck": deck_file,
        "cards": [definitions[cid] for cid in sorted(ids) if cid in definitions],
        "coverage": {cid: coverage[cid] for cid in sorted(ids) if cid in coverage},
        "images": {
            cid: (
                None
                if not art.has_printing
                else {"scryfall_id": art.scryfall_id, "artist": art.artist}
                | ({"back": True} if art.back else {})
            )
            for cid in sorted(ids)
            if (art := images.get(cid)) is not None
        },
    }


def _read_json(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


# ----------------------------------------------------------------------
# the device's half
# ----------------------------------------------------------------------


def adopt_bundle(
    bundle: Mapping,
    local: CardRegistry,
    index: CardIndex | None,
    *,
    owner: str = "",
    complete: bool | None = None,
    problems: Iterable[str] = (),
) -> ImportReport:
    """Write a site's bundle as a deck this machine can play, and report it.

    ``local`` is this machine's authored layer (``importer.authored_layer``),
    never the merged pool, for the reason ``importer.resolve_cards`` gives.
    ``owner`` replaces the site's: the deck is this library's here.
    """
    try:
        deck_model = DeckModel.model_validate(bundle["deck"])
    except (KeyError, TypeError, ValidationError) as exc:
        raise ImportFailed("bad_bundle", f"The site sent a deck this app cannot read: {exc}") from None
    raw = {
        entry["id"]: entry
        for entry in bundle.get("cards") or ()
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    coverage = dict(bundle.get("coverage") or {})
    images = dict(bundle.get("images") or {})

    compiled = _compile_each(raw, local)
    accepted: dict[str, CardDef] = {}
    proxies: dict[str, tuple[CardModel, ProxyResult]] = {}
    rename: dict[str, str] = {}
    taken = set(local.ids()) | set(raw)

    def lookup(card_id: str) -> CardDef | None:
        if card_id in local:
            return local.get(card_id)
        return accepted.get(card_id) or compiled.get(card_id)

    for card_id in dict.fromkeys([*deck_model.commanders, *(e.id for e in deck_model.cards)]):
        if card_id in local or card_id in accepted:
            continue
        group = closure([card_id], lookup)
        need = {cid: compiled.get(cid) for cid in group if cid not in local and cid not in accepted}
        if card_id in compiled and all(need.values()) and _links(need, lookup):
            accepted.update(need)  # type: ignore[arg-type]
            continue
        name = (raw.get(card_id) or {}).get("name") or card_id
        entry = None if index is None else index.lookup(name, token=False)
        result = None if entry is None else build_proxy(facts_from_index(entry), taken=taken)
        if result is None or result.model is None:
            raise ImportFailed("unknown_cards", f"1 card(s) not recognised: {name}")
        compile_card(result.model)
        taken.add(result.card_id)
        proxies[result.card_id] = (result.model, result)
        rename[card_id] = result.card_id

    deck_model = _renamed(deck_model, rename).model_copy(
        update={"owner": owner, "complete": complete}
    )
    merged = CardRegistry(
        {c.id: c for c in local}
        | accepted
        | {cid: compile_card(model) for cid, (model, _) in proxies.items()}
    )
    illegal = validate_deck(DeckList.from_model(deck_model), merged)
    if illegal:
        raise ImportFailed("illegal", "; ".join(illegal[:4]))

    resolved = _resolved(deck_model, merged, local, coverage, proxies, rename)
    lands, producing, inert = count_lands(resolved, merged)

    site_cards = {cid: raw[cid] for cid in accepted if cid not in coverage}
    site_proxies = {cid: (raw[cid], coverage[cid]) for cid in accepted if cid in coverage}
    entries: dict[str, dict | None] = {cid: images.get(cid) for cid in accepted}
    for card_id, (model, _) in proxies.items():
        found = None if index is None else index.lookup(model.name, token=False)
        entries[card_id] = (
            None if found is None else {"scryfall_id": found.scryfall_id, "artist": found.artist}
        )
    persist_adopted(deck_model, site_cards, site_proxies, proxies, entries)

    return ImportReport(
        deck_id=deck_model.id,
        deck_name=deck_model.name,
        source_id=deck_model.source_id,
        cards=resolved,
        problems=list(problems),
        lands=lands,
        lands_producing_mana=producing,
        lands_inert=inert,
    )


def _compile_each(raw: Mapping[str, dict], local: CardRegistry) -> dict[str, CardDef]:
    """Every site definition this machine lacks and can compile on its own."""
    out: dict[str, CardDef] = {}
    for card_id, entry in raw.items():
        if card_id in local:
            continue
        try:
            out[card_id] = compile_card(CardModel.model_validate(entry), source="site")
        except (DslError, ValidationError, KeyError, TypeError, ValueError):
            continue
    return out


def _links(group: Mapping[str, CardDef | None], lookup: Callable[[str], CardDef | None]) -> bool:
    """Whether ``group`` links and names only tokens that exist, against the
    cards it references.  ``link_faces`` and ``validate_token_references`` are
    the boot's own checks, run on the neighbourhood rather than the pool."""
    cards: dict[str, CardDef] = {cid: card for cid, card in group.items() if card is not None}
    for card in list(cards.values()):
        for ref in references(card):
            if ref not in cards and (found := lookup(ref)) is not None:
                cards[ref] = found
    try:
        link_faces(cards)
        validate_token_references(cards)
    except (DslError, KeyError):
        return False
    return True


def _renamed(deck: DeckModel, rename: Mapping[str, str]) -> DeckModel:
    """``deck`` with every refused card id replaced by its local proxy's."""
    if not rename:
        return deck
    return deck.model_copy(
        update={
            "commanders": [rename.get(cid, cid) for cid in deck.commanders],
            "cards": [
                entry.model_copy(update={"id": rename.get(entry.id, entry.id)})
                for entry in deck.cards
            ],
            "printings": {rename.get(cid, cid): p for cid, p in deck.printings.items()},
        }
    )


def _resolved(
    deck: DeckModel,
    merged: CardRegistry,
    local: CardRegistry,
    coverage: Mapping[str, dict],
    proxies: Mapping[str, tuple[CardModel, ProxyResult]],
    rename: Mapping[str, str],
) -> list[ResolvedCard]:
    """The report's rows, commanders first, as ``importer.resolve_cards`` orders them."""
    refused = set(rename.values())
    rows: list[ResolvedCard] = []
    for card_id, qty in [*((c, 1) for c in deck.commanders), *((e.id, e.qty) for e in deck.cards)]:
        chosen = deck.printings.get(card_id)
        printing = (
            None
            if chosen is None
            else Printing(
                scryfall_id=chosen.scryfall_id,
                artist=chosen.artist,
                set_code=chosen.set_code,
                collector_number=chosen.collector_number,
            )
        )
        name = merged.get(card_id).name
        if card_id in proxies:
            _, result = proxies[card_id]
            notes = (*result.notes, NEWER_RULES) if card_id in refused else result.notes
            rows.append(ResolvedCard(name, qty, card_id, result.coverage, tuple(notes), printing))
        elif card_id not in local and card_id in coverage:
            verdict = coverage[card_id]
            origin = verdict.get("coverage", "partial")
            rows.append(
                ResolvedCard(
                    name, qty, card_id, origin, tuple(verdict.get("notes", ())), printing
                )
            )
        else:
            rows.append(ResolvedCard(name, qty, card_id, "native", (), printing))
    return rows

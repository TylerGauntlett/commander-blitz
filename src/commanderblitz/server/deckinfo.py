"""Turning a :class:`~commanderblitz.cards.registry.DeckList` into what a client shows.

Two renderings, split by cost.  ``deck_summary`` backs every deck tile in the
catalogue and every seat in a pod, so it is fetched dozens of times and stays
light.  ``deck_detail`` adds the dossier's essays, curve and swap note and is
fetched one deck at a time.

Its own module because the lobby needs a deck summary just as much as the deck
routes do, and a pod importing a private helper out of ``routes`` would be the
wrong direction of dependency.
"""

from __future__ import annotations

import json
import re

from commanderblitz.cards.importer import coverage_path
from commanderblitz.cards.registry import DeckList, GameData

from .art import ArtStore
from .schemas import (
    DeckDetail,
    DeckRatingsDTO,
    DeckSummary,
    ImageRefDTO,
    ReleaseDTO,
    SignatureCardDTO,
)

#: Mana values 1..6 then "7 or more".  A 0-drop is folded into the first bucket:
#: it is a real card the deck can cast on turn one, and a column of its own for
#: the two free artifacts in the format would be almost always empty.
CURVE_BUCKETS = 7


#: What the importer has always written into ``notes``; see ``source_id_of``.
_NOTES_SOURCE = re.compile(r"Imported from Moxfield \(([^)\s]+)\)")


def source_id_of(deck: DeckList) -> str:
    """The Moxfield id a deck came from, or ``""``.

    The field is new; every deck imported before it carries the same id inside
    the note the importer has always written, case intact.  Reading it back
    from there is what lets those decks follow their owner online without a
    re-import.
    """
    if deck.source_id:
        return deck.source_id
    if deck.source != "moxfield":
        return ""
    found = _NOTES_SOURCE.search(deck.notes)
    return found.group(1) if found else ""


def commander_art(deck: DeckList, art: ArtStore | None) -> ImageRefDTO | None:
    """The deck's own picture of its lead commander, or ``None``.

    ``None`` when the deck named no printing for it -- a hand-built favorite,
    an import from before printings were recorded -- and the client then draws
    the catalog's art, exactly as it does for any other card.  A printing the
    catalog already agrees with comes back as the plain card URL, so the tile
    stays on the bytes the repository ships.

    A whole ref, as the board's seat overrides are: the artist is the deck's
    own or nothing, never the catalog printing's illustrator.
    """
    if art is None or not deck.commanders:
        return None
    lead = deck.commanders[0]
    printing = deck.printings.get(lead) or {}
    url = art.url_for(lead, printing=printing.get("scryfall_id"))
    if not printing.get("scryfall_id") or url is None:
        return None
    return ImageRefDTO(card_id=lead, art=url, artist=printing.get("artist") or None)


def deck_summary(deck: DeckList, data: GameData, art: ArtStore | None = None) -> DeckSummary:
    """``art`` is optional only for callers that draw no commander: without it
    ``commander_art`` is ``None`` and a tile falls back to the catalog's pick."""
    coverage = coverage_map()
    simplified = sum(
        qty
        for card_id, qty in (*deck.cards, *((c, 1) for c in deck.commanders))
        # `card_id not in data.registry` is the load-bearing half. The coverage
        # map is written by an *import* and describes the proxies that import
        # generated; a card that has since been authored is played from the
        # authored pool and its proxy is dropped. Without this check, a card
        # implemented after somebody imported a deck containing it goes on being
        # reported as simplified forever -- and it reported three cards of a
        # *precon* as simplified the moment they were authored.
        if card_id not in data.registry and coverage.get(card_id) == "partial"
    )
    return DeckSummary(
        id=deck.id,
        name=deck.name,
        commanders=list(deck.commanders),
        commander_names=[data.registry.get(c).name for c in deck.commanders],
        color_identity=sorted(deck.color_identity),
        card_count=deck.total_cards(),
        notes=deck.notes,
        source=deck.source,
        source_id=source_id_of(deck),
        playable=deck.total_cards() - simplified,
        simplified=simplified,
        tags=list(deck.tags),
        archetype=deck.archetype,
        release=None if deck.release is None else ReleaseDTO(**deck.release),
        starred=deck.starred,
        complete=deck.complete,
        commander_art=commander_art(deck, art),
    )


def deck_detail(deck: DeckList, data: GameData, art: ArtStore) -> DeckDetail:
    """The summary plus everything the dossier shows.

    The curve, the land count and the swap count are *derived from the list*
    rather than authored, so they cannot drift away from the deck they describe.
    """
    summary = deck_summary(deck, data, art)
    curve = [0] * CURVE_BUCKETS
    lands = 0
    for card_id, qty in deck.cards:
        card = data.registry.get(card_id)
        if "Land" in card.type_line:
            lands += qty
            continue
        curve[min(max(card.mana_value, 1), CURVE_BUCKETS) - 1] += qty

    swaps = list(deck.substitutions)
    return DeckDetail(
        **summary.model_dump(),
        ratings=None if deck.ratings is None else DeckRatingsDTO(**deck.ratings),
        strategy=deck.strategy,
        signature=[
            SignatureCardDTO(
                card_id=row["card_id"],
                name=data.registry.get(row["card_id"]).name,
                why=row["why"],
                art_url=art.url_for(row["card_id"]),
            )
            for row in deck.signature
            if row["card_id"] in data.registry
        ],
        curve=curve,
        lands=lands,
        swaps=len(swaps),
        swap_note=swap_note(swaps, data),
    )


def swap_note(swaps: list[dict], data: GameData) -> str:
    """One sentence naming what the engine could not run.

    Assembled here rather than authored per deck so it stays true when a card
    the DSL could not express becomes expressible and the substitution is
    deleted from the deck file.
    """
    if not swaps:
        return ""
    names = []
    for row in swaps:
        slot = row.get("slot", "")
        card = data.registry.get(slot) if slot in data.registry else None
        names.append(card.name if card is not None else slot.replace("_", " ").title())
    if len(names) == 1:
        return (
            f"1 card swapped for an engine-supported equivalent -- {names[0]} needs "
            "a rules feature the engine does not implement yet."
        )
    listed = ", ".join(names[:-1]) + f" and {names[-1]}"
    return (
        f"{len(names)} cards swapped for engine-supported equivalents -- {listed} "
        "each need a rules feature the engine does not implement yet."
    )


def coverage_map() -> dict[str, str]:
    """``card_id -> coverage`` for generated cards.

    Read per request rather than cached: an import writes it, and a stale map
    would report the deck somebody just imported as fully playable.  The file is
    a few KB and absent entirely on a machine that has never imported.
    """

    path = coverage_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # pragma: no cover
        return {}
    return {k: v.get("coverage", "partial") for k, v in raw.items()}

"""Reading a deck list off Moxfield.

the design record (`docs/design-record.md#board-themes`) records that ``api2.moxfield.com`` answers a scripted
client with a Cloudflare 403.  That was measured against ``/v2/cards/search/user``
and it is still true of *that* endpoint; the deck endpoint is open:

    GET https://api2.moxfield.com/v3/decks/all/{publicId}

returns 200 to plain ``urllib`` with an ordinary User-Agent, and carries the
whole list under ``boards.commanders`` and ``boards.mainboard``.

**Rules text and characteristics are read from the payload not at all**: a card's
``name``, its ``quantity`` and which board it was in are what identify it, and
every characteristic comes from our own ``cards.sqlite``, so an imported card's
id and colour identity agree with what ``/api/catalog`` already says about it,
and switching to a different deck site later is an adapter rather than a second
card pipeline.

**Art is the exception, and deliberately so.**  Which of a card's many printings
the author chose is not a characteristic we can derive -- the catalog keeps one
printing per name, so asking it gives everybody the same Sol Ring and the same
Forest.  It is a *choice*, it is the one thing that makes a deck recognisable as
yours, and only the source list knows it.  So the printing's ``scryfall_id`` is
carried through (with ``artist``/``set``/``cn`` alongside it for the benefit of
anyone reading a deck file), and nothing else is.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .schema import SCRYFALL_ID

MOXFIELD_API = "https://api2.moxfield.com/v3/decks/all/{public_id}"
HEADERS = {"User-Agent": "CommanderBlitz/0.1 (+https://commanderblitz.com)", "Accept": "application/json"}
TIMEOUT = 20

#: Accepts a full URL, with or without scheme and ``www``, and also a bare
#: publicId pasted on its own -- which is what somebody who has done this once
#: before will try.
DECK_URL = re.compile(
    r"^(?:https?://)?(?:www\.)?moxfield\.com/decks/([A-Za-z0-9_-]{1,40})", re.I
)
BARE_ID = re.compile(r"^[A-Za-z0-9_-]{6,40}$")

#: The boards that make up a Commander deck here.  `sideboard`, `maybeboard` and
#: `tokens` are deliberately ignored: none of them is part of the 100.
MAIN_BOARDS = ("commanders", "mainboard")

#: Formats whose deck *is* a Commander deck, whatever Moxfield calls the variant.
COMMANDER_FORMATS = frozenset(
    {"commander", "commanderPrecons", "duelCommander", "edh", "brawl", "pauperEdh", "oathbreaker"}
)


class ImportFailed(Exception):
    """A failed import, carrying the code the UI switches on.

    The distinction between 403 and 404 is the whole reason this module does not
    follow the house style of catching every network error together: "that deck
    is private" and "there is no such deck" send a person to two different
    places, and collapsing them sends them to neither.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Printing:
    """The printing the deck's author chose for one card.

    Only ``scryfall_id`` is load-bearing -- every Scryfall image URL is a pure
    function of it.  ``artist``, ``set_code`` and ``collector_number`` are
    carried so a deck file says *which* Lightning Bolt in words, the way
    ``data/catalog/art_pins.json`` does.  ``artist`` has a second job: it is the
    only credit we will ever have for this printing, because the catalog keeps
    one row per card name and almost never the row the author picked.
    """

    scryfall_id: str
    artist: str | None = None
    set_code: str = ""
    collector_number: str = ""


@dataclass(frozen=True)
class ParsedDeck:
    """A deck list as Moxfield describes it, before we know if we can play it."""

    public_id: str
    name: str
    format: str
    commanders: tuple[str, ...] = ()
    cards: tuple[tuple[str, int], ...] = ()
    problems: list[str] = field(default_factory=list)
    #: Card name -> the printing the author chose.  Defaulted, because a
    #: ``ParsedDeck`` is built by hand in a dozen tests and by every caller that
    #: only cares about the list; an absent entry simply means "no preference",
    #: which is what every deck imported before this existed says.
    printings: dict[str, Printing] = field(default_factory=dict)

    def total(self) -> int:
        return len(self.commanders) + sum(qty for _, qty in self.cards)


def parse_public_id(text: str) -> str | None:
    """The deck id in a pasted string, or ``None`` if there is not one."""
    candidate = (text or "").strip()
    if not candidate:
        return None
    match = DECK_URL.match(candidate)
    if match:
        return match.group(1)
    if "moxfield.com" in candidate.lower():
        # A Moxfield link that is not a deck link -- a user page, a search.
        return None
    return candidate if BARE_ID.match(candidate) else None


def fetch_deck(public_id: str, *, opener=urllib.request.urlopen) -> dict:
    """The raw payload.  ``opener`` is injected so tests never touch the network."""
    request = urllib.request.Request(
        MOXFIELD_API.format(public_id=public_id), headers=HEADERS
    )
    try:
        with opener(request, timeout=TIMEOUT) as response:
            payload = response.read()
    # HTTPError first: it subclasses URLError, so the order is load-bearing.
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ImportFailed("not_found", "No deck with that link.") from None
        if exc.code in (401, 403):
            raise ImportFailed(
                "private", "That deck is private. Set it to public and try again."
            ) from None
        raise ImportFailed("unreachable", f"Moxfield answered {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ImportFailed("unreachable", "Could not reach Moxfield.") from None

    try:
        body = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # An HTML body where JSON was promised is a Cloudflare interstitial,
        # which in practice means the deck is not publicly readable.
        raise ImportFailed(
            "private", "That deck is private. Set it to public and try again."
        ) from None
    if not isinstance(body, dict) or "boards" not in body:
        raise ImportFailed(
            "private", "That deck is private. Set it to public and try again."
        )
    return body


def normalise(payload: dict, public_id: str) -> ParsedDeck:
    """Reduce the payload to names and quantities."""
    boards = payload.get("boards") or {}
    commanders: list[str] = []
    cards: list[tuple[str, int]] = []
    problems: list[str] = []
    printings: dict[str, Printing] = {}
    seen_ids: dict[str, set[str]] = {}

    for board_name in MAIN_BOARDS:
        board = boards.get(board_name) or {}
        entries = (board.get("cards") or {}).values()
        # Sorted by name so a re-import of an unchanged deck writes an identical
        # file: dict order here is Moxfield's, and it is not stable.  The
        # printing id breaks ties, because a deck may list one name twice in two
        # illustrations -- and then the name alone leaves the winner to Moxfield.
        for entry in sorted(entries, key=_sort_key):
            card = entry.get("card") or {}
            name = card.get("name")
            if not name:
                continue
            qty = int(entry.get("quantity") or 1)
            if board_name == "commanders":
                commanders.extend([name] * qty)
            else:
                cards.append((name, qty))
            printing = _printing(card)
            if printing is not None:
                seen_ids.setdefault(name, set()).add(printing.scryfall_id)
                # First in the name-sorted walk wins, so a re-import of an
                # unchanged deck writes the same file.  See the problems line
                # below for what that costs.
                printings.setdefault(name, printing)

    for name, ids in sorted(seen_ids.items()):
        if len(ids) > 1:
            # A deck can list one name in several printings -- five Forests,
            # five different illustrations, which is exactly the kind of author
            # this feature is for.  Our unit of identity is the card id, so all
            # five copies share one art.  Say so rather than silently choosing.
            problems.append(
                f"{name} is listed in {len(ids)} printings; one art was used for every copy"
            )

    for ignored, label in (("companions", "companion"), ("signatureSpells", "signature spell")):
        if (boards.get(ignored) or {}).get("count"):
            problems.append(f"{label}s are not modelled and were left out")

    fmt = payload.get("format") or ""
    return ParsedDeck(
        public_id=public_id,
        name=payload.get("name") or "Imported deck",
        format=fmt,
        commanders=tuple(commanders),
        cards=tuple(cards),
        problems=problems,
        printings=printings,
    )


def _sort_key(entry: dict) -> tuple[str, str]:
    card = entry.get("card") or {}
    return (card.get("name") or "", str(card.get("scryfall_id") or ""))


def _printing(card: dict) -> Printing | None:
    """The chosen printing, or ``None`` when the payload does not name one.

    The id is validated here rather than trusted, because it ends up in a URL
    and in a filename.  An entry without one is not an error: it just means this
    card falls back to the catalog's pick, which is the old behaviour.
    """
    scryfall_id = card.get("scryfall_id")
    if not isinstance(scryfall_id, str) or not SCRYFALL_ID.match(scryfall_id):
        return None
    artist = card.get("artist")
    return Printing(
        scryfall_id=scryfall_id,
        artist=artist if isinstance(artist, str) and artist else None,
        set_code=str(card.get("set") or ""),
        collector_number=str(card.get("cn") or ""),
    )


def check_shape(deck: ParsedDeck) -> None:
    """Raise for the things that make a list unplayable before any card lookup."""
    if deck.format and deck.format not in COMMANDER_FORMATS:
        raise ImportFailed(
            "not_commander",
            f"That is a {deck.format} deck. This engine plays Commander.",
        )
    if not deck.commanders:
        raise ImportFailed("no_commander", "That deck has no commander.")
    total = deck.total()
    if total != 100:
        raise ImportFailed(
            "bad_size", f"That list has {total} cards. A Commander deck has 100."
        )


def load(text: str, *, opener=urllib.request.urlopen) -> ParsedDeck:
    """Paste to deck list, with every failure carrying a code."""
    public_id = parse_public_id(text)
    if public_id is None:
        raise ImportFailed("bad_url", "That is not a Moxfield deck link.")
    deck = normalise(fetch_deck(public_id, opener=opener), public_id)
    check_shape(deck)
    return deck

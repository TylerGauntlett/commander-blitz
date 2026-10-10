"""The card registry and deck lists."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from automtg.engine.carddef import CardDef
from automtg.engine.errors import DeckError, DslError

from .loader import load_card_file, load_deck_file
from .loader.linking import link_faces, validate_token_references
from .schema import DeckModel

#: Repo-root ``data/`` directory, overridable for tests via ``AUTOMTG_DATA_DIR``.
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"

#: Commander deck size, including the commander.
COMMANDER_DECK_SIZE = 100


def data_dir() -> Path:
    override = os.environ.get("AUTOMTG_DATA_DIR")
    return Path(override) if override else DEFAULT_DATA_DIR


def authored_card_paths(base: Path | None = None) -> list[Path]:
    """Every hand-written card file, then every machine-authored one.

    ``auto/`` holds cards written by ``automtg.cards.authoring`` -- generated,
    but only after clearing the six gates in ``authoring/verify.py``, so they are
    *authored* in the sense that matters: their behaviour was demonstrated. They
    are committed and playable everywhere, unlike the inert proxies in
    ``data/generated/``.

    Hand-written first so ``CardRegistry.by_name``'s first-wins resolution
    prefers a card a person wrote.  A duplicate id is still a load error, which
    the verifier's registry gate exists to prevent reaching here.
    """
    root = Path(base) if base else data_dir() / "cards"
    return sorted(root.glob("*.cards.json")) + sorted((root / "auto").glob("*.cards.json"))


def generated_dir() -> Path:
    """Where imported decks and their generated cards land.

    Deliberately *not* under ``data/cards`` or ``data/decks``, and deliberately
    gitignored.  Three gates read the authored pool and assume it is exactly what
    the repository ships: ``test_every_card_works`` parametrises over all of it,
    ``test_image_resolution`` pins the artless set at exactly five, and
    ``ai/encoding`` builds an embedding index from it.  If an import could add to
    that pool, ``pytest`` would return a different answer depending on what
    somebody imported last week.

    ``AUTOMTG_GENERATED_DIR`` moves it on its own, leaving the authored data
    where it is.  The desktop build needs that split: it runs the server out of
    a read-only AppImage mount, so the only place an import or a fetched
    illustration can land is a per-user directory beside it.  Every runtime
    write in the package resolves through here, which is what makes one
    variable sufficient.
    """
    override = os.environ.get("AUTOMTG_GENERATED_DIR")
    return Path(override) if override else data_dir() / "generated"


class CardRegistry:
    """Immutable lookup from card id to :class:`CardDef`."""

    __slots__ = ("_by_name", "_cards", "_creature_types")

    def __init__(self, cards: dict[str, CardDef]) -> None:
        self._cards = dict(cards)
        self._by_name: dict[str, CardDef] = {}
        for card in self._cards.values():
            if card.parent_face is not None or card.front_face is not None:
                # A face is not a card anybody can name. Its printed name is
                # real -- the spell half of Emeritus of Woe // Demonic Tutor is
                # called Demonic Tutor, and so is the card 2,600 decks play --
                # but only one of the two is something a deck list, an import or
                # a search can mean, and it is never the face.
                #
                # `setdefault` alone got the right answer here by accident: both
                # entries live in one file, and `demonic_tutor` happens to sort
                # before `demonic_tutor_26156d`. The comment below promises
                # first-wins protects *authored cards from generated ones*, which
                # is a different guarantee and says nothing about a face sharing
                # a file with the card it is named after. `link_faces` has
                # already run by the time this is built, so the question can be
                # asked directly instead of being left to sort order.
                continue
            # Built once rather than scanned per call: importing a 100-card deck
            # does 100 name lookups, and a linear scan makes that quadratic in
            # the pool. `setdefault` is first-wins, and the authored cards are
            # loaded before any generated ones, so an authored card can never be
            # shadowed by a proxy of itself.
            self._by_name.setdefault(card.name, card)
        self._creature_types: frozenset[str] | None = None

    def get(self, def_id: str) -> CardDef:
        try:
            return self._cards[def_id]
        except KeyError:
            raise DslError(f"unknown card id {def_id!r}") from None

    def __contains__(self, def_id: object) -> bool:
        return def_id in self._cards

    def __len__(self) -> int:
        return len(self._cards)

    def __iter__(self) -> Iterator[CardDef]:
        return iter(self._cards.values())

    def ids(self) -> list[str]:
        return sorted(self._cards)

    def by_name(self, name: str) -> CardDef | None:
        return self._by_name.get(name)

    def creature_types(self) -> frozenset[str]:
        """Every creature subtype the pool actually contains.

        A survey rather than the Comprehensive Rules list, for the reason
        `ops_control.MAX_TYPE_CHOICES` gives: a type no card in the game has is
        a choice with no consequence. Cached on first use because both askers --
        `choose_type`'s prompt and `text_change`'s candidate list -- walk the
        whole registry to build it, and the registry is immutable.
        """
        if self._creature_types is None:
            found: set[str] = set()
            for card in self._cards.values():
                if "Creature" in card.types:
                    found.update(card.subtypes)
            self._creature_types = frozenset(found)
        return self._creature_types

    @classmethod
    def from_paths(cls, paths: Iterable[Path]) -> CardRegistry:
        cards: dict[str, CardDef] = {}
        for path in paths:
            for card in load_card_file(path):
                if card.id in cards:
                    raise DslError(f"duplicate card id {card.id!r} in {path.name}")
                cards[card.id] = card
        link_faces(cards)
        validate_token_references(cards)
        return cls(cards)

    def extended_with(self, paths: Iterable[Path]) -> CardRegistry:
        """This pool plus any card in ``paths`` it does not already have.

        Unlike :meth:`from_paths`, a clash is not an error -- the incumbent wins
        and the newcomer is dropped. Used for the generated proxy pool, where a
        collision means the card has since been properly implemented.
        """
        cards = dict(self._cards)
        for path in paths:
            for card in load_card_file(path):
                cards.setdefault(card.id, card)
        link_faces(cards)
        validate_token_references(cards)
        return CardRegistry(cards)

    @classmethod
    def from_dir(cls, directory: Path | None = None) -> CardRegistry:
        base = Path(directory) if directory else data_dir() / "cards"
        paths = authored_card_paths(base)
        if not paths:
            raise DslError(f"no card files found in {base}")
        return cls.from_paths(paths)


@dataclass(frozen=True)
class DeckList:
    """A validated Commander deck list."""

    id: str
    name: str
    commanders: tuple[str, ...]
    color_identity: frozenset[str]
    cards: tuple[tuple[str, int], ...]
    substitutions: tuple[dict, ...] = ()
    notes: str = ""
    source: str = "precon"
    #: The Moxfield public id this was imported from.  See ``DeckModel.source_id``.
    source_id: str = ""
    #: The browser library that imported this.  ``""`` is shared -- a precon, or
    #: an import from before libraries existed.  See ``DeckModel.owner``.
    owner: str = ""
    #: Editorial metadata, authored per deck.  Empty for imported decks, which
    #: is a state the catalogue renders rather than papering over.
    tags: tuple[str, ...] = ()
    ratings: dict | None = None
    strategy: str = ""
    signature: tuple[dict, ...] = ()
    #: ``card id -> {scryfall_id, artist, set_code, collector_number}``: the
    #: printings the source list chose.  Empty for a precon and for anything
    #: imported before the importer recorded them.  See ``DeckModel.printings``.
    printings: dict[str, dict] = field(default_factory=dict)

    def expanded(self) -> list[str]:
        """The 99 non-commander cards, one entry per physical card."""
        out: list[str] = []
        for card_id, qty in self.cards:
            out.extend([card_id] * qty)
        return out

    def total_cards(self) -> int:
        return len(self.expanded()) + len(self.commanders)

    def unique_ids(self) -> set[str]:
        return {c for c, _ in self.cards} | set(self.commanders)

    @staticmethod
    def from_model(model: DeckModel) -> DeckList:
        return DeckList(
            id=model.id,
            name=model.name,
            commanders=tuple(model.commanders),
            color_identity=frozenset(model.color_identity),
            cards=tuple((e.id, e.qty) for e in model.cards),
            substitutions=tuple(s.model_dump() for s in model.substitutions),
            notes=model.notes,
            source=model.source,
            source_id=model.source_id,
            owner=model.owner,
            tags=tuple(model.tags),
            ratings=None if model.ratings is None else model.ratings.model_dump(),
            strategy=model.strategy,
            signature=tuple(s.model_dump() for s in model.signature),
            printings={cid: p.model_dump() for cid, p in model.printings.items()},
        )


def load_decks(directory: Path | None = None) -> dict[str, DeckList]:
    base = Path(directory) if directory else data_dir() / "decks"
    decks: dict[str, DeckList] = {}
    for path in sorted(base.glob("*.deck.json")):
        deck = DeckList.from_model(load_deck_file(path))
        if deck.id in decks:
            raise DeckError(f"duplicate deck id {deck.id!r}")
        decks[deck.id] = deck
    return decks


def validate_deck(deck: DeckList, registry: CardRegistry) -> list[str]:
    """Check Commander construction rules.  Returns a list of problems (empty = legal)."""
    problems: list[str] = []

    for card_id in sorted(deck.unique_ids()):
        if card_id not in registry:
            problems.append(f"unknown card id {card_id!r}")
    if problems:
        return problems

    total = deck.total_cards()
    if total != COMMANDER_DECK_SIZE:
        problems.append(f"deck has {total} cards, expected {COMMANDER_DECK_SIZE}")

    if not deck.commanders:
        problems.append("deck has no commander")
    for cmd_id in deck.commanders:
        card = registry.get(cmd_id)
        if not card.is_legendary:
            problems.append(f"commander {cmd_id!r} is not legendary")
        # 903.3: a legendary creature, or a card that says it "can be your
        # commander". A legendary planeswalker without that line cannot lead a
        # deck -- the check used to wave every one of them through.
        if not (card.is_creature or card.can_be_commander):
            problems.append(f"commander {cmd_id!r} is not a creature")

    identity: set[str] = set()
    for cmd_id in deck.commanders:
        identity |= set(registry.get(cmd_id).color_identity)
    if deck.color_identity and set(deck.color_identity) != identity:
        problems.append(
            f"declared color identity {sorted(deck.color_identity)} "
            f"!= commander identity {sorted(identity)}"
        )

    for card_id, qty in deck.cards:
        card = registry.get(card_id)
        if not set(card.color_identity).issubset(identity):
            problems.append(
                f"{card_id!r} identity {sorted(card.color_identity)} "
                f"is outside {sorted(identity)}"
            )
        # 903.5b in full: one copy unless the card is a basic land or its own
        # text says otherwise, and "otherwise" is sometimes a number rather than
        # a blank cheque.  `deck_copy_limit` is `None` when there is no ceiling.
        limit = card.deck_copy_limit
        if limit is not None and qty > limit:
            allowed = (
                "is not a basic land"
                if limit == 1
                else f"a deck can have up to {limit} of them"
            )
            problems.append(f"{card_id!r} appears {qty} times but {allowed}")
        if card.is_token:
            problems.append(f"{card_id!r} is a token and cannot be in a deck")
        if card.front_face is not None:
            # The back face of a transforming card is not a card you own a copy
            # of. A deck listing one would be 100 cards with a free 5/5 lord in
            # it, and every other check here would pass.
            problems.append(
                f"{card_id!r} is the back face of {card.front_face!r} and cannot be in a deck"
            )
        if card.parent_face is not None:
            # Nor is the Adventure half, the Aftermath half or one half of a
            # split card -- and this one is worse than the back face, because
            # the half *is* castable on its own and a deck listing it would get
            # the spell without the creature attached.
            problems.append(
                f"{card_id!r} is the second face of {card.parent_face!r} "
                f"and cannot be in a deck"
            )

    seen: set[str] = set()
    for card_id, _ in deck.cards:
        if card_id in seen:
            problems.append(f"{card_id!r} listed twice")
        seen.add(card_id)
    for cmd_id in deck.commanders:
        if cmd_id in seen:
            problems.append(f"commander {cmd_id!r} also appears in the 99")

    return problems


@dataclass
class GameData:
    """Everything needed to start a game: the card pool and the deck lists."""

    registry: CardRegistry
    decks: dict[str, DeckList] = field(default_factory=dict)
    #: The order a lobby hands decks to CPUs before it falls back to sorted ids.
    #: Empty except when the fixture decks are loaded, which pin it so that every
    #: seeded test keeps dealing the same opponents.
    seating: tuple[str, ...] = ()

    def deck(self, deck_id: str) -> DeckList:
        try:
            return self.decks[deck_id]
        except KeyError:
            raise DeckError(
                f"unknown deck {deck_id!r} (available: {sorted(self.decks)})"
            ) from None


def fixture_decks_dir() -> Path:
    return data_dir() / "decks" / "fixtures"


def load_game_data(
    *, include_generated: bool = False, include_fixtures: bool = False
) -> GameData:
    """Compile the card pool and the deck lists.

    The authored layer always comes first, so ``CardRegistry.by_name`` resolves
    to a hand-written card whenever one exists and a generated proxy can never
    shadow ``forest``.

    ``include_fixtures`` adds ``data/decks/fixtures/``: the retired first
    Edgar and Aesi lists, which hundreds of seeded tests were written against.
    They are not in the catalogue a player sees.
    """
    paths = authored_card_paths()
    if not paths:
        raise DslError(f"no card files found in {data_dir() / 'cards'}")
    deck_dirs = [data_dir() / "decks"]
    seating: tuple[str, ...] = ()
    if include_fixtures:
        deck_dirs.append(fixture_decks_dir())
        seating_file = fixture_decks_dir() / "seating.json"
        if seating_file.exists():
            seating = tuple(json.loads(seating_file.read_text(encoding="utf-8")))

    registry = CardRegistry.from_paths(paths)
    if include_generated:
        # Proxies whose card has since been *authored* are dropped rather than
        # merged. A proxy exists only because nobody had written that card yet;
        # once somebody has, the real one wins and the stale copy is obsolete.
        #
        # This is not a tidiness question. `from_paths` raises on a duplicate id,
        # so without the skip the server stops booting the first time the card
        # pipeline implements something that is already sitting in somebody's
        # imported deck -- and the deck goes on referencing the id either way, so
        # it silently picks up the real rules. Which is the point.
        registry = registry.extended_with(
            sorted((generated_dir() / "cards").glob("*.cards.json"))
        )
        deck_dirs.append(generated_dir() / "decks")
    decks: dict[str, DeckList] = {}
    for directory in deck_dirs:
        for deck_id, deck in load_decks(directory).items():
            if deck_id in decks:
                raise DeckError(f"duplicate deck id {deck_id!r}")
            decks[deck_id] = deck
    return GameData(registry=registry, decks=decks, seating=seating)


@lru_cache(maxsize=4)
def default_registry() -> GameData:
    """The authored layer alone -- what the tests and the trainer see.

    It includes the fixture decks, so a seeded test keeps meaning the game it
    was written against. Cached because card compilation is pure and the files
    never change during a run; a self-play session would otherwise re-parse 200
    cards per game.
    """
    return load_game_data(include_fixtures=True)


def fixture_decks_enabled() -> bool:
    """Whether the server should serve the fixture decks (test servers only)."""
    return os.environ.get("AUTOMTG_FIXTURE_DECKS") == "1"


@lru_cache(maxsize=2)
def server_registry() -> GameData:
    """The authored layer plus anything imported -- what the server serves.

    Separate from :func:`default_registry` so that importing a deck cannot
    change the answer any test gives.  Invalidated by
    ``automtg.server.app``'s reload hook after an import writes new files;
    clearing this cache alone is not enough, because :class:`SessionRegistry`
    holds the :class:`GameData` it was built with.
    """
    return load_game_data(include_generated=True, include_fixtures=fixture_decks_enabled())

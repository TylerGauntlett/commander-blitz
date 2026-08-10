"""The card registry and deck lists."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from automtg.engine.carddef import CardDef
from automtg.engine.errors import DeckError, DslError

from .loader import load_card_file, load_deck_file, validate_token_references
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
    """
    return data_dir() / "generated"


class CardRegistry:
    """Immutable lookup from card id to :class:`CardDef`."""

    __slots__ = ("_by_name", "_cards")

    def __init__(self, cards: dict[str, CardDef]) -> None:
        self._cards = dict(cards)
        # Built once rather than scanned per call: importing a 100-card deck
        # does 100 name lookups, and a linear scan makes that quadratic in the
        # pool.  `setdefault` is first-wins, and the authored cards are loaded
        # before any generated ones, so an authored card can never be shadowed.
        self._by_name: dict[str, CardDef] = {}
        for card in self._cards.values():
            self._by_name.setdefault(card.name, card)

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

    @classmethod
    def from_paths(cls, paths: Iterable[Path]) -> CardRegistry:
        cards: dict[str, CardDef] = {}
        for path in paths:
            for card in load_card_file(path):
                if card.id in cards:
                    raise DslError(f"duplicate card id {card.id!r} in {path.name}")
                cards[card.id] = card
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
    #: Editorial metadata, authored per deck.  Empty for imported decks, which
    #: is a state the catalogue renders rather than papering over.
    tags: tuple[str, ...] = ()
    ratings: dict | None = None
    strategy: str = ""
    signature: tuple[dict, ...] = ()

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
            tags=tuple(model.tags),
            ratings=None if model.ratings is None else model.ratings.model_dump(),
            strategy=model.strategy,
            signature=tuple(s.model_dump() for s in model.signature),
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
        if not (card.is_creature or "Planeswalker" in card.types):
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
        if qty > 1 and not card.is_basic:
            problems.append(f"{card_id!r} appears {qty} times but is not a basic land")
        if card.is_token:
            problems.append(f"{card_id!r} is a token and cannot be in a deck")

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

    def deck(self, deck_id: str) -> DeckList:
        try:
            return self.decks[deck_id]
        except KeyError:
            raise DeckError(
                f"unknown deck {deck_id!r} (available: {sorted(self.decks)})"
            ) from None


def load_game_data(*, include_generated: bool = False) -> GameData:
    """Compile the card pool and the deck lists.

    The authored layer always comes first, so ``CardRegistry.by_name`` resolves
    to a hand-written card whenever one exists and a generated proxy can never
    shadow ``forest``.
    """
    paths = authored_card_paths()
    if not paths:
        raise DslError(f"no card files found in {data_dir() / 'cards'}")
    deck_dirs = [data_dir() / "decks"]

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
    return GameData(registry=registry, decks=decks)


@lru_cache(maxsize=4)
def default_registry() -> GameData:
    """The authored layer alone -- what the tests and the trainer see.

    Cached because card compilation is pure and the files never change during a
    run; a self-play session would otherwise re-parse 200 cards per game.
    """
    return load_game_data()


@lru_cache(maxsize=2)
def server_registry() -> GameData:
    """The authored layer plus anything imported -- what the server serves.

    Separate from :func:`default_registry` so that importing a deck cannot
    change the answer any test gives.  Invalidated by
    ``automtg.server.app``'s reload hook after an import writes new files;
    clearing this cache alone is not enough, because :class:`SessionRegistry`
    holds the :class:`GameData` it was built with.
    """
    return load_game_data(include_generated=True)

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


class CardRegistry:
    """Immutable lookup from card id to :class:`CardDef`."""

    __slots__ = ("_cards",)

    def __init__(self, cards: dict[str, CardDef]) -> None:
        self._cards = dict(cards)

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
        for card in self._cards.values():
            if card.name == name:
                return card
        return None

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

    @classmethod
    def from_dir(cls, directory: Path | None = None) -> CardRegistry:
        base = Path(directory) if directory else data_dir() / "cards"
        paths = sorted(base.glob("*.cards.json"))
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


@lru_cache(maxsize=4)
def default_registry() -> GameData:
    """Load ``data/`` once per process.

    Cached because card compilation is pure and the files never change during a
    run; a self-play session would otherwise re-parse 200 cards per game.
    """
    registry = CardRegistry.from_dir()
    return GameData(registry=registry, decks=load_decks())

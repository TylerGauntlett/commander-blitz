"""Card definition loading.

Card files are JSON validated by :mod:`automtg.cards.schema` (pydantic) and then
compiled into the immutable :class:`~automtg.engine.carddef.CardDef` objects the
engine consumes.  Validation is strict on purpose: an unknown effect op, an
unknown selector key or a malformed value expression is an error at *load* time,
so ``pytest`` catches a typo in a card file instead of a game crashing.
"""

from .loader import load_card_file, load_cards, load_deck_file
from .registry import CardRegistry, DeckList, default_registry, load_decks

__all__ = [
    "CardRegistry",
    "DeckList",
    "default_registry",
    "load_card_file",
    "load_cards",
    "load_deck_file",
    "load_decks",
]

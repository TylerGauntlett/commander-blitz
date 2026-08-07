"""Validate every card file and deck list.

    python scripts/validate_decks.py

Exits non-zero on the first problem, so it works as a pre-commit or CI gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automtg.cards.registry import CardRegistry, load_decks, validate_deck
from automtg.engine.errors import AutoMtgError


def main() -> int:
    try:
        registry = CardRegistry.from_dir()
    except AutoMtgError as exc:
        print(f"FAIL card files: {exc}")
        return 1

    tokens = sum(1 for card in registry if card.is_token)
    print(f"OK   {len(registry)} cards loaded ({tokens} tokens)")

    decks = load_decks()
    if not decks:
        print("FAIL no deck files found")
        return 1

    failed = False
    for deck_id, deck in sorted(decks.items()):
        problems = validate_deck(deck, registry)
        if problems:
            failed = True
            print(f"FAIL {deck_id}:")
            for problem in problems:
                print(f"       - {problem}")
        else:
            lands = sum(
                qty for card_id, qty in deck.cards if registry.get(card_id).is_land
            )
            print(
                f"OK   {deck_id}: {deck.total_cards()} cards, {lands} lands, "
                f"{len(deck.substitutions)} documented substitutions"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

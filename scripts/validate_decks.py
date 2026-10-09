"""Validate every card file and deck list.

    python scripts/validate_decks.py          the authored decks
    python scripts/validate_decks.py --all    ...and anything imported

Exits non-zero on the first problem, so it works as a pre-commit or CI gate.

**The default is the authored layer only**, and that is not an oversight: this
runs inside `scripts/verify.py`, which has to give the same answer on a fresh
clone as it does on a machine with twenty imported decks. `--all` is for a human
debugging an import that will not load.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automtg.cards.registry import load_game_data, validate_deck
from automtg.engine.errors import AutoMtgError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--all",
        action="store_true",
        help="include imported decks and generated cards from data/generated/",
    )
    args = parser.parse_args()

    try:
        data = load_game_data(include_generated=args.all, include_fixtures=True)
    except AutoMtgError as exc:
        print(f"FAIL card files: {exc}")
        return 1

    registry = data.registry
    tokens = sum(1 for card in registry if card.is_token)
    print(f"OK   {len(registry)} cards loaded ({tokens} tokens)")

    decks = data.decks
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
            # How many of those lands can actually be tapped for mana. An
            # imported deck's fetchlands and creature-lands generate as inert
            # permanents, and a mana base that is quietly three short is the
            # hardest thing about an import to notice from the board.
            producing = sum(
                qty
                for card_id, qty in deck.cards
                if registry.get(card_id).is_land
                and any(a.is_mana_ability for a in registry.get(card_id).abilities)
            )
            mana = "" if producing == lands else f" ({producing} make mana)"
            print(
                f"OK   {deck_id}: {deck.total_cards()} cards, {lands} lands{mana}, "
                f"{len(deck.substitutions)} documented substitutions"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

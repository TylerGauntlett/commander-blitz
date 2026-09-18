"""Import a Moxfield deck the way a pasted link does, and say what is not native.

    python .claude/skills/import-moxfield/scripts/deck_status.py <url-or-id>
    python .claude/skills/import-moxfield/scripts/deck_status.py <url-or-id> --json out.json
    python .claude/skills/import-moxfield/scripts/deck_status.py <url-or-id> --pin-list

Runs the same ``importer.import_deck`` a pasted link goes through, so the number
it prints is the number the setup screen would show. It writes ``data/generated/``
(gitignored) unless ``--dry-run`` is given -- that write is what puts the deck's
cards at the front of the authoring queue as ``wanted``.

Exit code 0 when every distinct card resolves ``native``, 1 otherwise, 2 on an
import failure. ``--pin-list`` prints the ``DECK`` tuple for a
``tests/cards/test_<deck>_import.py`` in the shape ``test_lucy_maclean_import.py``
uses.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from automtg.cards.images import load_index  # noqa: E402
from automtg.cards.importer import import_deck  # noqa: E402
from automtg.cards.moxfield import ImportFailed, load  # noqa: E402
from automtg.cards.registry import default_registry  # noqa: E402


def main() -> int:
    # Oracle text carries characters cp1252 has no room for -- U+2212 in
    # Teferi, Master of Time's "-3:" is the one that found this -- and a Windows
    # console defaults to cp1252, so printing a card's notes killed the run
    # before it could write --json. Reconfigure the streams rather than sanitise
    # the text: a deck report should print what the card actually says.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("deck", help="a Moxfield deck URL or bare public id")
    parser.add_argument("--dry-run", action="store_true", help="write nothing to data/generated/")
    parser.add_argument("--json", metavar="PATH", help="also write the report as JSON")
    parser.add_argument(
        "--pin-list", action="store_true", help="print the DECK tuple for the import pin test"
    )
    args = parser.parse_args()

    index = load_index()
    if index is None:
        print("no card catalog; run scripts/build_card_index.py", file=sys.stderr)
        return 2
    try:
        deck = load(args.deck)
        report = import_deck(deck, default_registry().registry, index, dry_run=args.dry_run)
    except ImportFailed as exc:
        print(f"import failed ({exc.code}): {exc}", file=sys.stderr)
        return 2

    if args.pin_list:
        print(f'COMMANDER = "{deck.commanders[0] if deck.commanders else ""}"')
        print("DECK: tuple[tuple[str, int], ...] = (")
        for name, qty in sorted(deck.cards, key=lambda c: c[0].lower()):
            print(f"    ({json.dumps(name)}, {qty}),")
        print(")")
        return 0

    by_origin = {"native": 0, "full": 0, "partial": 0}
    for card in report.cards:
        by_origin[card.origin] = by_origin.get(card.origin, 0) + 1
    not_native = [c for c in report.cards if c.origin != "native"]

    print(f"{report.deck_name}  ({args.deck})")
    print(f"  commander(s)      {', '.join(deck.commanders) or '-'}")
    print(f"  cards             {report.total} total, {len(report.cards)} distinct")
    print(
        f"  native            {by_origin['native']} / {len(report.cards)} distinct"
        f"   (full {by_origin['full']}, partial {by_origin['partial']})"
    )
    print(
        f"  playable          {report.playable} / {report.total}  (simplified {report.simplified})"
    )
    print(
        f"  lands             {report.lands}, producing {report.lands_producing_mana}, inert {report.lands_inert}"
    )
    for problem in report.problems:
        print(f"  problem           {problem}")
    if not_native:
        print(f"\nnot yet native ({len(not_native)}):")
        for card in sorted(not_native, key=lambda c: (c.origin, c.name.lower())):
            print(f"  [{card.origin:7}] {card.name}")
            for note in card.notes:
                print(f"             - {note}")
    else:
        print("\nevery distinct card is native")

    if args.json:
        payload = {
            "deck": report.deck_name,
            "deck_id": report.deck_id,
            "source": args.deck,
            "commanders": list(deck.commanders),
            "total": report.total,
            "distinct": len(report.cards),
            "native": by_origin["native"],
            "full": by_origin["full"],
            "partial": by_origin["partial"],
            "playable": report.playable,
            "simplified": report.simplified,
            "lands": report.lands,
            "lands_inert": report.lands_inert,
            "not_native": [
                {"name": c.name, "qty": c.qty, "origin": c.origin, "notes": list(c.notes)}
                for c in not_native
            ],
        }
        Path(args.json).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0 if not not_native else 1


if __name__ == "__main__":
    raise SystemExit(main())

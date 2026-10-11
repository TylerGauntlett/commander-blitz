"""Promote an imported Moxfield deck into a shipped precon.

    python scripts/promote_deck.py data/generated/decks/mox_x.deck.json --id bruvac_the_grandiloquent

An import lives in the gitignored ``data/generated/`` layer, owned by whichever
browser library pasted the link. A precon is committed under ``data/decks/``,
visible to everybody, and named after its commander. This copies the list
across, renames it, records where it came from in ``notes``, and refuses to
promote a deck the authored layer cannot play: every card must already be
native, or the precon would reference ids that only exist on one machine.

The editorial fields (tags, ratings, strategy, signature) are left for a person
to write -- ``tests/cards/test_deck_metadata.py`` fails until they are.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from commanderblitz.cards.registry import DeckList, data_dir, load_game_data, validate_deck
from commanderblitz.cards.schema import DeckModel

#: Key order for the written file: identity first, the 99 last, so a diff of
#: the editorial fields reads top to bottom.
KEY_ORDER = (
    "id", "name", "commanders", "color_identity", "source", "notes", "tags",
    "ratings", "strategy", "signature", "substitutions", "printings", "cards",
)


def promote(source: Path, deck_id: str, name: str | None, url: str | None) -> Path:
    raw = json.loads(source.read_text(encoding="utf-8"))
    model = DeckModel.model_validate(raw)
    target = data_dir() / "decks" / f"{deck_id}.deck.json"
    if target.exists():
        raise SystemExit(f"{target} already exists; refusing to overwrite it")

    data = load_game_data()
    commander = data.registry.get(model.commanders[0])
    moxfield_name = model.name
    out = model.model_dump(exclude_defaults=True)
    out.update(
        id=deck_id,
        name=name or commander.name,
        source="precon",
        notes=(
            f'Moxfield list "{moxfield_name}"'
            + (f" ({url})" if url else "")
            + ". Promoted from an import, card for card."
        ),
    )
    out.pop("owner", None)

    problems = validate_deck(DeckList.from_model(DeckModel.model_validate(out)), data.registry)
    if problems:
        raise SystemExit(f"{deck_id} is not playable from the authored layer:\n  " + "\n  ".join(problems))

    ordered = {key: out[key] for key in KEY_ORDER if key in out}
    ordered.update({k: v for k, v in out.items() if k not in ordered})
    target.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("source", type=Path, help="an imported deck file in data/generated/decks/")
    parser.add_argument("--id", required=True, help="the precon's deck id (the commander's card id)")
    parser.add_argument("--name", help="display name; defaults to the commander's name")
    parser.add_argument("--url", help="the Moxfield link, recorded in notes")
    args = parser.parse_args()
    print(promote(args.source, args.id, args.name, args.url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Turning a deck list into cards this engine can deal.

Three outcomes per card, and the order matters:

``native``
    A card somebody hand-wrote.  Reused whole -- real rules, existing art, the
    id every precon already uses.  This is why an imported deck's Forests are
    ``forest`` and not ``forest_a1b2c3``.
``full``
    Generated, and nothing was lost: a vanilla creature, a land, a Signet.
``partial``
    Generated, with the non-keyword rules text inert.  Every simplification is
    listed so the report can say what it did.

A card absent from the catalog entirely is a **failure**, not a fourth outcome:
a 99-card deck is not a deck, and quietly dropping the card is how somebody ends
up wondering why their commander never shows up.

Everything written lands under ``data/generated/`` (gitignored), and nothing here
touches ``data/cards/`` or ``data/decks/``.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from automtg.engine.errors import DslError

from .images import CardIndex, generated_images_path
from .loader import compile_card
from .moxfield import ImportFailed, ParsedDeck
from .proxy import ProxyResult, build_proxy, facts_from_index
from .registry import CardRegistry, DeckList, generated_dir, validate_deck
from .schema import CardModel, DeckModel

Origin = Literal["native", "full", "partial"]

#: One writer at a time.  Starlette serves from a threadpool, and two imports
#: interleaving would merge each other's half of the pool.
_WRITE_LOCK = threading.Lock()


@dataclass(frozen=True)
class ResolvedCard:
    name: str
    qty: int
    card_id: str
    origin: Origin
    notes: tuple[str, ...] = ()


@dataclass
class ImportReport:
    """What the import did, in the terms the screen shows it."""

    deck_id: str
    deck_name: str
    source_id: str
    cards: list[ResolvedCard]
    problems: list[str]
    #: Counted here rather than by the route, because a *dry run* writes nothing
    #: and so has no registry to count against -- and a dry run is exactly when
    #: somebody wants to know their mana base is three lands short.
    lands: int = 0
    lands_producing_mana: int = 0

    @property
    def total(self) -> int:
        return sum(c.qty for c in self.cards)

    @property
    def playable(self) -> int:
        """Cards whose printed text is fully represented."""
        return sum(c.qty for c in self.cards if c.origin in ("native", "full"))

    @property
    def simplified(self) -> int:
        return sum(c.qty for c in self.cards if c.origin == "partial")


def cards_path() -> Path:
    return generated_dir() / "cards" / "pool.cards.json"


def coverage_path() -> Path:
    return generated_dir() / "cards" / "pool.coverage.json"


def decks_dir() -> Path:
    return generated_dir() / "decks"


def deck_id_for(public_id: str) -> str:
    """``mox_<publicId>``, lowercased.

    Lowercased because the id is both a filename and a ``deck-${id}`` test hook,
    and Windows filenames are case-insensitive while the tests are not.  A
    re-import overwrites in place, which is the whole of the collision handling
    this needs.
    """
    import hashlib
    import re

    slug = public_id.lower()
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", slug):
        slug = hashlib.sha256(public_id.encode()).hexdigest()[:12]
    return f"mox_{slug.replace('-', '_')}"


# ----------------------------------------------------------------------
# reconciliation
# ----------------------------------------------------------------------


def resolve_cards(
    deck: ParsedDeck, registry: CardRegistry, index: CardIndex | None
) -> tuple[list[ResolvedCard], dict[str, tuple[CardModel, ProxyResult]], list[str]]:
    """``(resolved, cards to write, names we could not place)``.

    ``registry`` must be the **authored** layer, not the server's merged one.
    Given the merged registry, re-importing a deck finds the proxies the first
    import wrote and calls them ``native`` -- so the same deck would report 88
    playable the first time and 100 the second, and the second number is a lie.
    """
    resolved: list[ResolvedCard] = []
    generated: dict[str, tuple[CardModel, ProxyResult]] = {}
    missing: list[str] = []
    taken = set(registry.ids())

    wanted: list[tuple[str, int]] = [(n, 1) for n in deck.commanders]
    wanted += list(deck.cards)

    for name, qty in wanted:
        native = registry.by_name(name) or registry.by_name(_front_face(name))
        if native is not None:
            resolved.append(ResolvedCard(name, qty, native.id, "native"))
            continue

        entry = None
        if index is not None:
            # `token=False`: 87 names are printed both ways, and a deck can hold
            # the card but never the token.
            entry = index.lookup(name, token=False) or index.lookup(
                _front_face(name), token=False
            )
        if entry is None:
            missing.append(name)
            continue

        result = build_proxy(facts_from_index(entry), taken=taken)
        if result.model is None:
            missing.append(f"{name} ({result.error})")
            continue
        try:
            compile_card(result.model)
        except DslError as exc:
            # Should be unreachable -- `test_proxy_against_the_catalog` compiles
            # every row in the catalog -- but a card that cannot compile must
            # never reach a file, or the *next* boot fails instead of this
            # request.
            missing.append(f"{name} (could not be generated: {exc})")
            continue

        taken.add(result.card_id)
        generated[result.card_id] = (result.model, result)
        resolved.append(
            ResolvedCard(name, qty, result.card_id, result.coverage, result.notes)
        )

    return resolved, generated, missing


def _front_face(name: str) -> str:
    return name.split("//")[0].strip()


def build_deck_model(deck: ParsedDeck, resolved: list[ResolvedCard], registry) -> DeckModel:
    """A deck list in the same shape the precons are written in."""
    # `resolve_cards` walks commanders first and then the 99, in order, and
    # `import_deck` refuses to get here with anything unresolved -- so the split
    # is positional and every entry is present.
    split = len(deck.commanders)
    commander_ids = list(dict.fromkeys(c.card_id for c in resolved[:split]))
    entries = [{"id": c.card_id, "qty": c.qty} for c in resolved[split:]]

    identity: set[str] = set()
    for cid in commander_ids:
        identity |= set(registry.get(cid).color_identity)

    return DeckModel(
        id=deck_id_for(deck.public_id),
        name=deck.name,
        commanders=commander_ids,
        color_identity=sorted(identity),
        cards=entries,
        notes=f"Imported from Moxfield ({deck.public_id}).",
        source="moxfield",
    )


# ----------------------------------------------------------------------
# writing
# ----------------------------------------------------------------------


def _write_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def persist(
    deck_model: DeckModel,
    generated: dict[str, tuple[CardModel, ProxyResult]],
    entries: dict[str, dict | None],
) -> None:
    """Merge the new cards into the pool, then write the deck.

    Cards before the deck, always.  A deck file naming ids that were never
    written breaks ``load_decks`` at the *next* boot rather than in this request,
    which is by far the worst failure this feature could have.
    """
    with _WRITE_LOCK:
        pool = _read_json(cards_path(), {"cards": []})
        by_id = {c["id"]: c for c in pool.get("cards", [])}
        for card_id, (model, _) in generated.items():
            by_id[card_id] = model.model_dump(exclude_defaults=True, exclude_none=True)

        coverage = _read_json(coverage_path(), {})
        for card_id, (_, result) in generated.items():
            coverage[card_id] = {
                "coverage": result.coverage,
                "notes": list(result.notes),
            }

        images = _read_json(generated_images_path(), {})
        images.update(entries)

        _write_atomic(cards_path(), {"cards": [by_id[k] for k in sorted(by_id)]})
        _write_atomic(coverage_path(), coverage)
        _write_atomic(generated_images_path(), images)
        _write_atomic(
            decks_dir() / f"{deck_model.id}.deck.json",
            deck_model.model_dump(exclude_defaults=True),
        )


def delete_deck(deck_id: str) -> bool:
    """Remove an imported deck.  Its cards stay: they cost a few KB and the next
    import probably wants them."""
    path = decks_dir() / f"{deck_id}.deck.json"
    if not path.exists():
        return False
    path.unlink()
    return True


# ----------------------------------------------------------------------
# the whole thing
# ----------------------------------------------------------------------


def import_deck(
    deck: ParsedDeck,
    registry: CardRegistry,
    index: CardIndex | None,
    *,
    dry_run: bool = False,
) -> ImportReport:
    """Reconcile, validate, and -- unless this is a dry run -- write.

    ``registry`` is the authored layer.  See :func:`resolve_cards` for why that
    matters more than it looks.
    """
    if index is None:
        raise ImportFailed(
            "no_catalog", "No card catalog on this machine; run scripts/build_card_index.py."
        )

    resolved, generated, missing = resolve_cards(deck, registry, index)
    if missing:
        shown = ", ".join(missing[:6]) + ("..." if len(missing) > 6 else "")
        raise ImportFailed("unknown_cards", f"{len(missing)} card(s) not recognised: {shown}")

    # Validate against a registry that can actually see the generated cards,
    # because `validate_deck` resolves every id through it.
    merged = CardRegistry({**{c.id: c for c in registry}, **{
        cid: compile_card(model) for cid, (model, _) in generated.items()
    }})
    deck_model = build_deck_model(deck, resolved, merged)
    problems = validate_deck(DeckList.from_model(deck_model), merged)
    if problems:
        raise ImportFailed("illegal", "; ".join(problems[:4]))

    lands = producing = 0
    for entry in resolved:
        card = merged.get(entry.card_id)
        if not card.is_land:
            continue
        lands += entry.qty
        if any(a.is_mana_ability for a in card.abilities):
            producing += entry.qty

    report = ImportReport(
        deck_id=deck_model.id,
        deck_name=deck_model.name,
        source_id=deck.public_id,
        cards=resolved,
        problems=list(deck.problems),
        lands=lands,
        lands_producing_mana=producing,
    )
    if dry_run:
        return report

    entries: dict[str, dict | None] = {}
    for card_id, (_, result) in generated.items():
        entry = index.lookup(result.model.name, token=False)
        entries[card_id] = (
            None
            if entry is None
            else {"scryfall_id": entry.scryfall_id, "artist": entry.artist}
        )
    persist(deck_model, generated, entries)
    return report

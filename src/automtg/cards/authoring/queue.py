"""What to implement next, and what happened last time.

There are ~32,000 cards and finite effort, so the order is the most consequential
thing in this package. Alphabetical order is worth nothing: it spends the first
thousand units of work on cards nobody has ever put in a deck.

Two signals, in order:

1. **A card somebody actually tried to play.** Anything in an imported deck under
   ``data/generated/`` goes first. Those are cards a real person put in a real
   list and then watched do nothing.
2. **EDHREC rank.** Sol Ring, Command Tower, Arcane Signet. Covers 88% of
   printings; the rest sort last rather than being dropped.

The queue is also the *record of failure*, and that is half its value. A card
that could not be expressed stores the reason, so "these 400 cards all need a
union selector" is a roadmap rather than a mystery, and the next run does not
spend anything rediscovering it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from ..images import CardIndex, load_index
from ..registry import CardRegistry, data_dir

#: ``pending``      never attempted
#: ``done``         written to ``data/cards/auto/`` and passing every gate
#: ``failed``       attempted, rejected; ``reason`` says by which gate
#: ``unexpressible`` the DSL cannot say this at all -- needs engine work first
Status = Literal["pending", "done", "failed", "unexpressible"]

#: ``Entry.gate`` for a card that is in the pool and *plays*, but does not do
#: everything it prints -- found by ``automtg.cards.authoring.fidelity`` and
#: written by ``scripts/audit_cards.py --open-deficits``.
#:
#: It needs its own value because every other part of this package reads "in the
#: registry" as "done": :meth:`Queue.refresh` never queues a card the engine
#: already plays, and ``author_cards.select`` refuses one by name. Both are right
#: about cards that are simply missing, and both were wrong about these.
FIDELITY_GATE = "fidelity"


def queue_path() -> Path:
    return data_dir() / "authoring" / "queue.json"


def auto_cards_dir() -> Path:
    return data_dir() / "cards" / "auto"


@dataclass
class Entry:
    name: str
    scryfall_id: str
    status: Status = "pending"
    #: Which gate rejected it, and what it said.  The whole point of writing
    #: failures down: the tail becomes measurable instead of anecdotal.
    gate: str | None = None
    reason: str = ""
    #: What produced the card, when one was produced: a template name, or a model.
    source: str = ""
    edhrec_rank: int | None = None
    #: True when this card is in a deck somebody imported.
    wanted: bool = False


@dataclass
class Queue:
    entries: dict[str, Entry] = field(default_factory=dict)

    # -- persistence ----------------------------------------------------

    @staticmethod
    def load(path: Path | None = None) -> Queue:
        target = path or queue_path()
        if not target.exists():
            return Queue()
        raw = json.loads(target.read_text(encoding="utf-8"))
        return Queue(entries={k: Entry(**v) for k, v in raw.get("entries", {}).items()})

    def save(self, path: Path | None = None) -> None:
        target = path or queue_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"entries": {k: asdict(v) for k, v in sorted(self.entries.items())}}
        temp = target.with_suffix(".json.part")
        temp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="",
        )
        temp.replace(target)

    # -- building -------------------------------------------------------

    def refresh(
        self,
        index: CardIndex,
        registry: CardRegistry,
        *,
        wanted: set[str] | None = None,
        limit: int | None = None,
    ) -> Queue:
        """Add cards that need rules, without disturbing what is already recorded.

        Cards the engine already plays are skipped entirely -- both the
        hand-written pool and anything ``auto/`` has produced. A card whose
        status is already known keeps it, so a refresh after a catalog rebuild
        does not throw away a run's worth of results.
        """
        have = {card.name for card in registry}
        wanted = wanted or set()
        added = 0
        for entry in index.iter_by_popularity():
            if limit is not None and added >= limit:
                break
            if entry.name in have or entry.name in self.entries:
                continue
            self.entries[entry.name] = Entry(
                name=entry.name,
                scryfall_id=entry.scryfall_id,
                edhrec_rank=entry.edhrec_rank,
                wanted=entry.name in wanted,
            )
            added += 1
        return self

    # -- reading --------------------------------------------------------

    def next_batch(self, limit: int, *, retry_failed: bool = False) -> list[Entry]:
        """The next cards to work on, best first.

        ``unexpressible`` is never retried *automatically*: it means the engine
        cannot say this yet, and nothing about running the same generator again
        changes that. Those come back when the mechanic that unblocks them ships
        -- and ``retry_failed`` is how that moment is announced. ``/extend-dsl``
        ends by running ``--tier templates --retry`` precisely to collect the
        cards its capability just freed, so excluding them there made the harvest
        step a no-op for the one category it exists to serve: seven conditional
        taplands stayed ``unexpressible`` after the condition they were waiting
        on shipped, and only a by-name run could reach them.
        """
        statuses = {"pending", "failed"}
        if retry_failed:
            statuses.add("unexpressible")
        else:
            statuses.discard("failed")
        candidates = [e for e in self.entries.values() if e.status in statuses]
        candidates.sort(key=_priority)
        return candidates[:limit]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for entry in self.entries.values():
            out[entry.status] = out.get(entry.status, 0) + 1
        return out

    def failures_by_reason(self, top: int = 20) -> list[tuple[str, int]]:
        """The tail, grouped -- this is the roadmap for what to build next."""
        tally: dict[str, int] = {}
        for entry in self.entries.values():
            if entry.status not in ("failed", "unexpressible"):
                continue
            key = f"{entry.gate}: {_summarise(entry.reason)}"
            tally[key] = tally.get(key, 0) + 1
        return sorted(tally.items(), key=lambda kv: -kv[1])[:top]

    def __iter__(self) -> Iterator[Entry]:
        return iter(self.entries.values())

    def __len__(self) -> int:
        return len(self.entries)


def _priority(entry: Entry) -> tuple:
    # Fidelity deficits first, then wanted, then by rank, then by name so the
    # order never wobbles.
    #
    # A fidelity entry outranks even a card somebody imported, because it is not
    # a card that does nothing -- it is a card that is *already in a shipped
    # deck*, already being played, and quietly doing less than it prints. A
    # missing card announces itself the first time somebody counts on it; this
    # kind never does.
    return (
        0 if entry.gate == FIDELITY_GATE else 1,
        0 if entry.wanted else 1,
        entry.edhrec_rank if entry.edhrec_rank is not None else 10**9,
        entry.name,
    )


def _summarise(reason: str) -> str:
    """Collapse a reason to its shape, so a hundred cards failing the same way
    group into one line rather than a hundred."""
    import re

    text = re.sub(r"'[^']*'", "'X'", reason)
    text = re.sub(r"\b\d+\b", "N", text)
    return text[:110]


def wanted_names(registry: CardRegistry | None = None) -> set[str]:
    """Card names that appear in a deck somebody imported.

    Read from ``data/generated/`` -- the proxies the importer wrote. A card in
    there is a card a real person put in a real deck and then watched do nothing,
    which is a far better signal than any global popularity number.
    """
    from ..registry import generated_dir

    pool = generated_dir() / "cards" / "pool.cards.json"
    if not pool.exists():
        return set()
    try:
        raw = json.loads(pool.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # pragma: no cover
        return set()
    return {c["name"] for c in raw.get("cards", []) if "name" in c}


def build(limit: int | None = None) -> Queue:
    """The queue as it should be right now, loaded, refreshed and saved."""
    from ..registry import default_registry

    index = load_index()
    if index is None:
        raise RuntimeError("no card catalog; run scripts/build_card_index.py")
    queue = Queue.load()
    queue.refresh(index, default_registry().registry, wanted=wanted_names(), limit=limit)
    return queue

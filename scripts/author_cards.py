"""Implement cards, in batches, and refuse to ship any that cannot prove they work.

    python scripts/author_cards.py --report              what is playable, and what is blocking the rest
    python scripts/author_cards.py --tier templates      translate everything the templates can
    python scripts/author_cards.py --tier templates --limit 200 --dry-run

The engine plays a few hundred of ~32,000 cards; everything else imports as an
inert proxy. This is the loop that closes that gap without anybody hand-writing
32,000 JSON files.

Order is the most consequential thing here, so it is not alphabetical: cards from
a deck somebody actually imported come first, then EDHREC rank. See
``automtg.cards.authoring.queue``.

**Nothing is written that has not demonstrated its behaviour.** Every candidate
runs the six gates in ``automtg.cards.authoring.verify`` -- including one that
casts it in a real position and checks the board afterwards -- because
``compile_card`` validates vocabulary, not meaning, and a card that compiles
cleanly and does the wrong thing is worse than one that does nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automtg.cards.authoring import templates as T
from automtg.cards.authoring import verify as V
from automtg.cards.authoring.queue import Entry, Queue, auto_cards_dir, build, wanted_names
from automtg.cards.images import load_index
from automtg.cards.proxy import facts_from_index
from automtg.cards.registry import CardRegistry, data_dir, default_registry

BATCH_FILE = "templates.cards.json"


def _hand_written() -> CardRegistry:
    """The pool a candidate is verified against: everything except ``auto/``.

    Verifying against a registry that already contains the card would make the
    duplicate-id gate meaningless, and a card must be judged on whether it can
    join the pool, not on whether it is already in it.
    """
    return CardRegistry.from_paths(sorted((data_dir() / "cards").glob("*.cards.json")))


def _load_batch() -> tuple[dict, dict]:
    path = auto_cards_dir() / BATCH_FILE
    cards = json.loads(path.read_text(encoding="utf-8"))["cards"] if path.exists() else []
    exp_path = auto_cards_dir() / "expectations.json"
    expectations = json.loads(exp_path.read_text(encoding="utf-8")) if exp_path.exists() else {}
    return {c["id"]: c for c in cards}, expectations


def _write_batch(cards: dict, expectations: dict) -> None:
    auto_cards_dir().mkdir(parents=True, exist_ok=True)
    _atomic(
        auto_cards_dir() / BATCH_FILE,
        {"cards": [cards[k] for k in sorted(cards)]},
    )
    _atomic(auto_cards_dir() / "expectations.json", expectations)


def _atomic(path: Path, payload: object) -> None:
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="",
    )
    temp.replace(path)


def run_templates(queue: Queue, limit: int, *, dry_run: bool, retry: bool) -> dict[str, int]:
    index = load_index()
    registry = _hand_written()
    cards, expectations = _load_batch()
    taken = set(registry.ids()) | set(cards)

    tally = {"written": 0, "no_template": 0, "rejected": 0, "skipped": 0}
    for entry in queue.next_batch(limit, retry_failed=retry):
        result = _attempt(entry, index, registry, taken, tally)
        if result is None:
            continue
        payload, expectation, used = result
        if not dry_run:
            cards[payload["id"]] = payload
            expectations[payload["id"]] = expectation
            taken.add(payload["id"])
        entry.status = "done"
        entry.source = f"template:{','.join(used)}"
        entry.gate = None
        entry.reason = ""
        tally["written"] += 1

    if not dry_run:
        _write_batch(cards, expectations)
        queue.save()
    return tally


def _attempt(entry: Entry, index, registry: CardRegistry, taken: set[str], tally: dict):
    catalog = index.by_scryfall_id(entry.scryfall_id) or index.lookup(entry.name, token=False)
    if catalog is None:
        entry.status = "failed"
        entry.gate = "catalog"
        entry.reason = "not in the catalog any more"
        tally["skipped"] += 1
        return None

    result = T.translate(facts_from_index(catalog), taken=taken)
    if not result.ok:
        # "No template for X" is not a failure to record as unexpressible -- an
        # agent may well manage it. It is only a statement about this tier.
        entry.status = "pending" if "no template" in result.reason else "unexpressible"
        entry.gate = "template"
        entry.reason = result.reason
        tally["no_template"] += 1
        return None

    payload = result.model.model_dump(exclude_defaults=True, exclude_none=True)
    payload["source"] = "auto"
    verdict = V.verify(payload, result.expectation, registry, oracle_text=catalog.oracle_text)
    if not verdict.ok:
        entry.status = "failed"
        entry.gate = verdict.failed_gate
        entry.reason = verdict.reason
        tally["rejected"] += 1
        return None
    return payload, result.expectation, result.used


def report(queue: Queue) -> None:
    registry = default_registry().registry
    index = load_index()
    total = sum(1 for _ in index.iter_by_popularity()) if index else 0
    auto = len(_load_batch()[0])

    print(f"playable            {len(registry):>7,}  ({len(registry) - auto:,} by hand, {auto:,} authored)")
    print(f"catalog             {total:>7,}")
    if total:
        print(f"coverage            {len(registry) / total * 100:>6.1f}%")
    print()
    counts = queue.counts()
    print(f"queue               {len(queue):>7,}  {counts}")
    wanted = sum(1 for e in queue if e.wanted and e.status != "done")
    print(f"  in your decks     {wanted:>7,}  (worked on first)")

    blockers = queue.failures_by_reason(top=15)
    if blockers:
        print("\nwhat is blocking the rest -- this is the roadmap:")
        for reason, count in blockers:
            print(f"  {count:>5}  {reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tier", choices=["templates"], help="which generator to run")
    parser.add_argument("--limit", type=int, default=200, help="how many cards to attempt")
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--retry", action="store_true", help="re-attempt cards that failed")
    parser.add_argument("--refresh", type=int, default=6000, help="how much catalog to queue")
    parser.add_argument("--report", action="store_true", help="coverage and blockers, then exit")
    args = parser.parse_args()

    if load_index() is None:
        print("no card catalog; run scripts/build_card_index.py", file=sys.stderr)
        return 2

    queue = build(limit=args.refresh)
    queue.refresh(load_index(), default_registry().registry, wanted=wanted_names())

    if args.report or not args.tier:
        report(queue)
        return 0

    tally = run_templates(queue, args.limit, dry_run=args.dry_run, retry=args.retry)
    verb = "would write" if args.dry_run else "wrote"
    print(
        f"{verb} {tally['written']}  |  no template {tally['no_template']}  "
        f"|  rejected by a gate {tally['rejected']}  |  skipped {tally['skipped']}"
    )
    if not args.dry_run and tally["written"]:
        print("\nre-run `python scripts/verify.py` before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

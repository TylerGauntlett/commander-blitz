"""Implement cards, in batches, and refuse to ship any that cannot prove they work.

    python scripts/author_cards.py --report              what is playable, and what is blocking the rest
    python scripts/author_cards.py --tier templates      translate everything the templates can
    python scripts/author_cards.py --tier templates --limit 200 --dry-run
    python scripts/author_cards.py --tier agent --card "Rhystic Study"

The engine plays a few hundred of ~32,000 cards; everything else imports as an
inert proxy. This is the loop that closes that gap without anybody hand-writing
32,000 JSON files.

Order is the most consequential thing here, so it is not alphabetical: cards from
a deck somebody actually imported come first, then EDHREC rank. See
``automtg.cards.authoring.queue``.

``--card`` overrides that order for one named card, which is a different job with
the same machinery: somebody needs *this* card now, for a deck or a test, and
does not want it to wait behind eleven thousand more popular ones.

**Nothing is written that has not demonstrated its behaviour.** Every candidate
runs the six gates in ``automtg.cards.authoring.verify`` -- including one that
casts it in a real position and checks the board afterwards -- because
``compile_card`` validates vocabulary, not meaning, and a card that compiles
cleanly and does the wrong thing is worse than one that does nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automtg.cards.authoring import packet as P
from automtg.cards.authoring import templates as T
from automtg.cards.authoring import verify as V
from automtg.cards.authoring.queue import (
    FIDELITY_GATE,
    Entry,
    Queue,
    auto_cards_dir,
    build,
    wanted_names,
)
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


def select(queue: Queue, names: list[str] | None, limit: int, *, retry: bool) -> list[Entry] | None:
    """Which cards this run is about: the queue's own order, or ones named.

    A named card is *added* to the queue when it is not already there, rather
    than handled off to the side, so its verdict is recorded in the same place as
    everything else -- a card asked for by name and rejected is exactly as much a
    part of the roadmap as one that came up by rank.

    Returns ``None`` when a name does not resolve, having already said so: a typo
    that silently authored nothing would look identical to a card the templates
    could not finish.
    """
    if not names:
        return queue.next_batch(limit, retry_failed=retry)

    index = load_index()
    # A hand-written card is never in the queue -- ``refresh`` skips everything
    # the engine already plays -- so "not in the queue" cannot be read as "not
    # implemented", or asking for Sol Ring by name would hand out work to
    # reimplement it.
    playable = {card.name.lower() for card in default_registry().registry}
    batch: list[Entry] = []
    missing = False
    for name in names:
        entry = next((e for e in queue if e.name.lower() == name.lower()), None)
        if entry is None:
            found = index.lookup(name, token=False)
            if found is None:
                missing = True
                _suggest(index, name)
                continue
            entry = Entry(
                name=found.name,
                scryfall_id=found.scryfall_id,
                edhrec_rank=found.edhrec_rank,
            )
            if found.name.lower() not in playable:
                queue.entries[found.name] = entry
        # Playable is not the same as correct, and this is the only place that
        # knows the difference. `scripts/audit_cards.py --open-deficits` marks a
        # card whose implementation does not cover everything it prints, and such
        # a card has to be workable *because* it is in the pool: it is in a
        # shipped deck, being played, quietly doing less than it says.
        if entry.gate == FIDELITY_GATE and entry.status != "done":
            batch.append(entry)
            continue
        if entry.status == "done" or entry.name.lower() in playable:
            print(f"{entry.name}: already playable, nothing to do")
            continue
        batch.append(entry)
    return None if missing else batch


def _suggest(index, name: str) -> None:
    """A name that did not resolve, with the near misses the catalog does have."""
    _, near = index.search(name, limit=5)
    hint = "; did you mean: " + ", ".join(e.name for e in near) if near else ""
    print(f"no card named {name!r} in the catalog{hint}", file=sys.stderr)


def run_templates(queue: Queue, batch: list[Entry], *, dry_run: bool) -> dict[str, int]:
    index = load_index()
    registry = _hand_written()
    cards, expectations = _load_batch()
    taken = set(registry.ids()) | set(cards)

    tally = {"written": 0, "no_template": 0, "rejected": 0, "skipped": 0}
    for entry in batch:
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


def write_packets(batch: list[Entry]) -> int:
    """Hand out work for the cards no template can finish.

    A packet per card, self-contained, on disk. The reader may be a session or an
    unattended API worker; both read the same file and write the same answer, so
    the second costs no rework once the first has proved the loop.
    """
    index = load_index()
    registry = _hand_written()
    written = 0
    for entry in batch:
        catalog = index.by_scryfall_id(entry.scryfall_id) or index.lookup(
            entry.name, token=False
        )
        if catalog is None:
            continue
        packet = P.build_packet(catalog, registry, entry.reason or "not attempted")
        P.write_packet(packet)
        written += 1
    return written


def _card_span(raw: str, card_id: str) -> tuple[int, int] | None:
    """The exact character range of one card object inside a card file.

    Found by brace matching rather than by reserializing the file.
    ``data/cards/*.cards.json`` is hand-formatted -- arrays of scalars stay
    inline, ``_comment`` headers carry prose -- and ``json.dumps`` would reflow
    every card in the file, so deleting one card would land as a whole-file diff
    with the actual deletion buried in it.
    """
    match = re.search(rf'"id":\s*"{re.escape(card_id)}"', raw)
    if match is None:
        return None
    start = raw.rfind("{", 0, match.start())
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(raw)):
        char = raw[i]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == '"':
            in_string = not in_string
        elif not in_string:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return start, i + 1
    return None


def _drop_hand_written(card_ids: set[str]) -> int:
    """Remove superseded cards from ``data/cards/*.cards.json``.

    Not optional, and not cosmetic. ``registry.authored_card_paths`` returns the
    hand-written files *before* ``auto/``, and ``CardRegistry.by_name`` is
    first-wins, so a corrected card left sitting behind its predecessor never
    reaches a game -- the run would report success and change nothing.
    """
    removed = 0
    for path in sorted((data_dir() / "cards").glob("*.cards.json")):
        raw = path.read_text(encoding="utf-8")
        changed = False
        for card_id in sorted(card_ids):
            span = _card_span(raw, card_id)
            if span is None:
                continue
            start, end = span
            # Take the separating comma with the object, so the array stays
            # valid whether the card was in the middle or last.
            tail = re.match(r"\s*,", raw[end:])
            if tail:
                end += tail.end()
            else:
                head = re.search(r",\s*$", raw[:start])
                if head:
                    start = head.start()
            raw = raw[:start] + raw[end:]
            # The blank line the object used to sit on would otherwise survive.
            raw = re.sub(r"\n[ \t]*\n([ \t]*[}\]])", r"\n\1", raw)
            removed += 1
            changed = True
        if changed:
            json.loads(raw)  # never leave a card file that does not parse
            path.write_text(raw, encoding="utf-8", newline="")
    return removed


def collect_answers(queue: Queue, *, dry_run: bool, supersede: bool = False) -> dict[str, int]:
    """Verify what came back, and commit only what passes.

    An answer is trusted exactly as far as the six gates trust it, which is the
    whole point: a model that misreads a card produces one that fails gate 5
    rather than one that quietly does the wrong thing in somebody's game.

    ``supersede`` allows an answer to *replace* a hand-written card of the same
    id, which gate 6 otherwise refuses outright. That is the only way to repair
    the cards ``scripts/audit_cards.py`` finds: they are already in the pool, so
    every answer for one is rejected as a duplicate id. It stays behind a flag so
    an ordinary ``--collect`` can never rewrite ``data/cards/`` by accident, and
    the replacement is still verified against a pool with the incumbent removed.
    """
    registry = _hand_written()
    cards, expectations = _load_batch()
    index = load_index()
    by_name = {e.name: e for e in queue}
    in_pool = set(registry.ids())

    tally = {"accepted": 0, "rejected": 0, "superseded": 0}
    superseded: set[str] = set()
    for card_id, answer in P.read_answers().items():
        payload = dict(answer["card"])
        payload["id"] = card_id
        payload["source"] = "auto"
        expectation = answer.get("expectation") or {}

        catalog = index.lookup(payload.get("name", ""), token=False)
        oracle = catalog.oracle_text if catalog else payload.get("oracle_text", "")
        replaces = supersede and card_id in in_pool
        verdict = V.verify(
            payload, expectation, registry, oracle_text=oracle, supersedes=replaces
        )

        entry = by_name.get(payload.get("name", ""))
        if not verdict.ok:
            print(f"  REJECT {card_id}: {verdict.failed_gate} -- {verdict.reason[:90]}")
            if entry is not None:
                entry.status = "failed"
                entry.gate = verdict.failed_gate
                entry.reason = verdict.reason
            tally["rejected"] += 1
            continue

        print(f"  {'supersede' if replaces else 'accept'} {card_id}")
        if not dry_run:
            cards[card_id] = payload
            expectations[card_id] = expectation
        if replaces:
            superseded.add(card_id)
            tally["superseded"] += 1
        if entry is not None:
            entry.status = "done"
            entry.source = "agent"
            entry.gate = None
            entry.reason = ""
        tally["accepted"] += 1

    if not dry_run and tally["accepted"]:
        if superseded:
            _drop_hand_written(superseded)
        _write_batch(cards, expectations)
        queue.save()
    return tally


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
    # Cards that *are* playable and do not do everything they print. They cannot
    # show up under "blocking" below -- that counts failures, and these have not
    # been attempted -- but they outrank everything else in `next_batch`, so
    # leaving them off this summary would make the run order look arbitrary.
    incomplete = sum(1 for e in queue if e.gate == FIDELITY_GATE and e.status != "done")
    if incomplete:
        print(f"  incomplete        {incomplete:>7,}  (playable but not correct; see audit_cards.py)")

    blockers = queue.failures_by_reason(top=15)
    if blockers:
        print("\nwhat is blocking the rest -- this is the roadmap:")
        for reason, count in blockers:
            print(f"  {count:>5}  {reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--tier",
        choices=["templates", "agent"],
        help="templates: translate deterministically. agent: write work packets for the tail",
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="verify the answers written back, and commit the ones that pass",
    )
    parser.add_argument(
        "--card",
        action="append",
        metavar="NAME",
        help="work on this card by name instead of taking the queue's order; repeatable",
    )
    parser.add_argument(
        "--supersede",
        action="store_true",
        help="with --collect: let an answer replace a hand-written card of the same id",
    )
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

    if args.collect:
        tally = collect_answers(queue, dry_run=args.dry_run, supersede=args.supersede)
        line = f"accepted {tally['accepted']}  |  rejected {tally['rejected']}"
        if tally["superseded"]:
            line += f"  |  superseded {tally['superseded']} hand-written card(s)"
        print(line)
        return 0

    if args.report or not args.tier:
        report(queue)
        return 0

    # A named card is worth retrying even when a previous run rejected it: the
    # ask is "I need this one now", not "do whatever is next".
    batch = select(queue, args.card, args.limit, retry=args.retry or bool(args.card))
    if batch is None:
        return 2
    if not batch:
        return 0

    if args.tier == "agent":
        if args.dry_run:
            for entry in batch:
                print(f"would write a packet for {entry.name}")
            return 0
        written = write_packets(batch)
        queue.save()
        print(f"wrote {written} packet(s) to {P.packets_dir()}")
        print(
            "Answer each as "
            f"{P.answers_dir()}/<card_id>.json containing "
            '{"card": {...}, "expectation": {...}}, then re-run with --collect.'
        )
        print(
            "A card the DSL cannot express gets "
            f"{P.gaps_dir()}/<card_id>.json instead -- see scripts/report_gaps.py."
        )
        return 0

    tally = run_templates(queue, batch, dry_run=args.dry_run)
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

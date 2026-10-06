"""Measure the hand-written card pool against what its cards actually print.

    python scripts/audit_cards.py                    what is wrong, grouped
    python scripts/audit_cards.py --card "Gyre Sage" one card, in full
    python scripts/audit_cards.py --fix-oracle       record the printed text
    python scripts/audit_cards.py --fix-text         re-point ability text fields
    python scripts/audit_cards.py --open-deficits    queue the incomplete cards
    python scripts/audit_cards.py --update-baseline  refresh the test baseline
    python scripts/audit_cards.py --check-substitutions

``data/cards/auto/`` is in the pool because it cleared six gates, and
``tests/cards/test_auto_cards.py`` re-runs all six on every test run.
``data/cards/`` predates the pipeline, and for a long time two gates never ran
over it -- residual (is every printed sentence implemented?) and behaviour (does
the card demonstrably do it?).

They could not run, for one reason. A hand-written card's ``oracle_text`` used to
be a human paraphrase written *after* whatever was skipped, so the card's own
record of its text already agreed with the shortcut. Krosan Tusker's oracle text
was "A large boar." -- and against that text, a vanilla 6/5 is a faithful
implementation. The question was begged, so there was nothing to catch.
``--fix-oracle`` recorded the printed text, ``test_its_oracle_text_is_what_it_prints``
keeps it, and ``tests/cards/test_hand_written_cards.py`` now runs all six gates.

This script never repairs a card's *rules*. It records what is true, and hands
the incomplete ones to ``/author-cards``, which routes each back through the same
six gates the authored tier goes through and files a gap record for anything the
DSL cannot say rather than approximating it a second time.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automtg.cards.authoring import fidelity as F
from automtg.cards.authoring import verify as V
from automtg.cards.authoring.queue import FIDELITY_GATE, Entry, Queue
from automtg.cards.images import load_index
from automtg.cards.loader import compile_card
from automtg.cards.registry import CardRegistry, data_dir
from automtg.cards.schema import CardModel

#: Written by ``--update-baseline``, read by ``tests/cards/test_hand_written_cards.py``.
BASELINE = Path(__file__).resolve().parents[1] / "tests" / "cards" / "precon_deficits.json"

#: The expectations the hand-written pool is checked against.  A different file
#: from ``data/cards/auto/expectations.json``, which covers the authored tier.
EXPECTATIONS = Path(__file__).resolve().parents[1] / "tests" / "cards" / "expectations.json"

#: A JSON string value, escapes intact.
def _value(key: str) -> re.Pattern[str]:
    return re.compile(rf'"{key}":\s*"((?:[^"\\]|\\.)*)"')


def hand_written_dir() -> Path:
    return data_dir() / "cards"


def card_files() -> list[Path]:
    return sorted(hand_written_dir().glob("*.cards.json"))


def hand_written() -> CardRegistry:
    """The hand-written layer alone -- ``auto/`` is already audited by its test."""
    return CardRegistry.from_paths(card_files())


def expectations() -> dict[str, dict]:
    if not EXPECTATIONS.exists():
        return {}
    raw = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def run_audit() -> list[F.Deficit]:
    index = load_index()
    if index is None:
        raise SystemExit("no card catalog; run scripts/build_card_index.py")
    return F.audit(hand_written(), index, expectations())


# ----------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------


def report(deficits: list[F.Deficit], *, only: str | None = None) -> None:
    if only:
        wanted = only.casefold()
        mine = [d for d in deficits if wanted in (d.card_id.casefold(), d.name.casefold())]
        if not mine:
            print(f"{only}: no deficits recorded")
            return
        for deficit in mine:
            print(f"  {deficit.kind:<18} {deficit.detail}")
        return

    pool = hand_written()
    # Tokens are excluded: a token has no printing to be measured against, so
    # counting them would make the pool look better than it is.
    audited = sum(1 for card in pool if not card.is_token)
    tally = Counter(d.kind for d in deficits)
    cards = len({d.card_id for d in deficits})

    print(f"hand-written cards audited  {audited:>5}  (of {len(pool)}, tokens excluded)")
    print(f"cards with a deficit        {cards:>5}")
    print()
    for kind in F.KINDS:
        if tally[kind]:
            print(f"  {kind:<20} {tally[kind]:>5}  ({_gloss(kind)})")

    blocked = F.blocking(deficits)
    print()
    print(f"incomplete implementations -- work for /author-cards: {len(blocked)}")
    for card_id in sorted(blocked):
        print(f"  {card_id:<32} {_clip(blocked[card_id], 92)}")


_GLOSSES = {
    "residual": "printed lines nothing implements",
    "spell_text_lost": "a spell prints a mechanic it does not have",
    "text_drift": "implemented, but the ability's text field is a paraphrase",
    "paraphrased_oracle": "oracle_text is not what the card prints -- run --fix-oracle",
    "unasserted": "no behaviour expectation, so gate 5 cannot run",
    "no_catalog_row": "not in the catalog; nothing to check against",
}


def _gloss(kind: str) -> str:
    return _GLOSSES.get(kind, "")


def _clip(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


# ----------------------------------------------------------------------
# repairs -- text only, never rules
# ----------------------------------------------------------------------


def _rewrite(path: Path, edits: dict[str, list[tuple[str, str, str]]]) -> int:
    """Apply ``{card_id: [(key, old, new)]}`` to one file, in place.

    Edited as text rather than reserialized. ``data/cards/*.cards.json`` is
    hand-formatted -- ``"supertypes": ["Legendary"]`` sits on one line, arrays of
    scalars stay inline -- and ``json.dumps`` would reflow all 285 cards, burying
    a dozen real changes in a whole-file diff nobody can review.
    """
    raw = path.read_text(encoding="utf-8")
    # Each card object begins with its id, so the text between one id and the
    # next is exactly one card and a key can be replaced without reaching into
    # a neighbour.
    spans = list(re.finditer(r'"id":\s*"([a-z0-9_]+)"', raw))
    out: list[str] = []
    cursor = 0
    changed = 0
    for i, match in enumerate(spans):
        card_id = match.group(1)
        end = spans[i + 1].start() if i + 1 < len(spans) else len(raw)
        if card_id not in edits:
            continue
        body = raw[match.start() : end]
        for key, old, new in edits[card_id]:
            pattern = _value(key)
            replaced = False

            def swap(m: re.Match[str], old=old, new=new) -> str:
                nonlocal replaced
                if replaced or json.loads(f'"{m.group(1)}"') != old:
                    return m.group(0)
                replaced = True
                # ensure_ascii=False so an em-dash stays an em-dash. Scryfall
                # prints "Landfall —" and the pool has to record the sentence it
                # is being measured against verbatim, or the residual gate is
                # comparing against a transliteration of the card rather than the
                # card. `data/cards/auto/` already stores these raw.
                encoded = json.dumps(new, ensure_ascii=False)[1:-1]
                return m.group(0).replace(m.group(1), encoded, 1)

            body = pattern.sub(swap, body)
            changed += int(replaced)
        out.append(raw[cursor : match.start()])
        out.append(body)
        cursor = end
    out.append(raw[cursor:])
    if changed:
        path.write_text("".join(out), encoding="utf-8", newline="")
    return changed


def fix_oracle(*, dry_run: bool) -> int:
    """Record what each card actually prints, in the pool's own house style.

    The pivot of the whole audit. While ``oracle_text`` is a summary of the
    implementation, the residual gate is checking a card against itself; once it
    is the printing, every omission becomes a concrete, greppable failure.
    """
    index = load_index()
    total = 0
    for path in card_files():
        edits: dict[str, list[tuple[str, str, str]]] = {}
        for payload in json.loads(path.read_text(encoding="utf-8"))["cards"]:
            card = compile_card(CardModel.model_validate(payload))
            if card.is_token:
                continue
            catalog = F.printed_row(card, index)
            if catalog is None or not catalog.oracle_text:
                continue
            printed = F.printed_text(catalog, card.name)
            current = payload.get("oracle_text", "")
            if printed != current:
                edits.setdefault(card.id, []).append(("oracle_text", current, printed))
        if dry_run:
            total += sum(len(v) for v in edits.values())
            for card_id in sorted(edits):
                print(f"  would record printed text for {card_id}")
        else:
            total += _rewrite(path, edits)
    return total


def fix_text(*, dry_run: bool) -> int:
    """Point each ability's ``text`` at the printed line it already implements.

    ``verify._covered`` reads ``text`` as the author's claim about *which printed
    sentence this ability is*, so a paraphrase there is a bookkeeping error, not
    a missing ability -- and it makes a working card look unimplemented.

    Only rewrites where the match is mechanical rather than a judgement call
    (:data:`fidelity.REWRITE_FLOOR`), and never where two abilities compete for
    one line. Everything else stays in the report for a person to read. A
    misdirected rewrite cannot hide a broken card: the line it was taken from
    loses its claimant and re-appears in the residual.
    """
    index = load_index()
    total = 0
    for path in card_files():
        edits: dict[str, list[tuple[str, str, str]]] = {}
        for payload in json.loads(path.read_text(encoding="utf-8"))["cards"]:
            card = compile_card(CardModel.model_validate(payload))
            if card.is_token or not card.abilities:
                continue
            catalog = F.printed_row(card, index)
            if catalog is None or not catalog.oracle_text:
                continue
            printed = F.printed_text(catalog, card.name)
            # Forced first: an ability and a line that can only be each other are
            # a deduction. The scored pass then handles cards with more than one
            # of either, where arity leaves the question open.
            assignments = {
                **F.match_abilities(card, printed, floor=F.REWRITE_FLOOR),
                **F.forced_matches(card, printed),
            }
            for index_, line in assignments.items():
                current = (payload["abilities"][index_].get("text") or "").strip()
                wanted = " ".join(line.split())
                if current and current != wanted:
                    edits.setdefault(card.id, []).append(("text", current, wanted))
        if dry_run:
            total += sum(len(v) for v in edits.values())
            for card_id in sorted(edits):
                print(f"  would re-point {len(edits[card_id])} ability text(s) on {card_id}")
        else:
            total += _rewrite(path, edits)
    return total


# ----------------------------------------------------------------------
# handing the work on
# ----------------------------------------------------------------------


def fix_expectations(*, dry_run: bool) -> int:
    """Give every hand-written card the zone assertion the authored tier uses.

    Gate 5 refuses to pass a card with no expectation at all, so without this the
    gate test could not run over most of the hand-written cards (179 of 213 when
    it was written) and the other five gates went unchecked on them too. Today
    148 of the 192 still carry only a zone assertion. That is the authored tier's
    own floor -- 1,924 of its 2,832 expectations carry nothing more -- and it is a
    real check: it is the difference between "resolved without raising" and
    "ended up where a card of this kind belongs".

    It is deliberately *not* counted as asserting the card's behaviour: `audit`
    still reports a zone-only card as ``unasserted``, so writing these does not
    make the real gap disappear from the report. It only lets the other gates
    run.
    """
    current = expectations()
    added: dict[str, dict] = {}
    for card in sorted(hand_written(), key=lambda c: c.id):
        if card.is_token or card.id in current:
            continue
        if not card.is_permanent:
            added[card.id] = {"zone": "graveyard"}
        elif card.is_aura:
            # An Aura whose own effect can kill its host is correctly binned by
            # state-based actions a moment later; `verify._play_once` allows both
            # and so must this.
            added[card.id] = {"zone": ["battlefield", "graveyard"]}
        else:
            added[card.id] = {"zone": "battlefield"}

    if added and not dry_run:
        raw = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))
        raw.update(added)
        comments = {k: v for k, v in raw.items() if k.startswith("_")}
        rest = {k: raw[k] for k in sorted(raw) if not k.startswith("_")}
        EXPECTATIONS.write_text(
            json.dumps({**comments, **rest}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="",
        )
    return len(added)


def open_deficits(deficits: list[F.Deficit], *, dry_run: bool) -> tuple[int, int]:
    """Sync the queue with the audit: ``(opened, closed)``.

    Without this the deficits are a report nobody acts on: ``Queue.refresh``
    skips every name already in the registry, so no hand-written card has ever
    had an entry, and ``author_cards.select`` refuses a card that is in the pool.
    Both are right that these cards are *playable*; the audit is the first thing
    that knows playable is not the same as correct.

    Closing matters as much as opening. An entry whose deficit is gone is a card
    the next ``/author-cards`` run would hand to a worker to re-author for no
    reason -- and it would rank *first*, because fidelity entries outrank
    everything. Two cards reached that state within an hour of the first repair
    pass, so this is not hypothetical.
    """
    index = load_index()
    queue = Queue.load()
    blocked = F.blocking(deficits)
    by_id = {card.id: card for card in hand_written()}
    still_wrong = {by_id[card_id].name for card_id in blocked}

    opened = 0
    for card_id, why in sorted(blocked.items()):
        card = by_id[card_id]
        catalog = F.printed_row(card, index)
        entry = queue.entries.get(card.name)
        if entry is None:
            entry = Entry(
                name=card.name,
                scryfall_id=catalog.scryfall_id if catalog else "",
                edhrec_rank=catalog.edhrec_rank if catalog else None,
            )
            queue.entries[card.name] = entry
        elif entry.status == "done" and entry.gate != FIDELITY_GATE:
            # A card the pipeline itself authored and that now audits clean is
            # not this script's business.
            continue
        entry.status = "pending"
        entry.gate = FIDELITY_GATE
        entry.reason = _clip(why, 200)
        opened += 1

    closed = 0
    for entry in queue:
        if entry.gate == FIDELITY_GATE and entry.name not in still_wrong:
            entry.status = "done"
            entry.gate = None
            entry.reason = ""
            closed += 1

    if not dry_run:
        queue.save()
    return opened, closed


def failing_cards() -> dict[str, str]:
    """Every hand-written card that does not clear all six gates, and why.

    Runs the gates rather than consulting the audit. The audit's job is to
    explain a deficit to a person in the terms the card is printed in; this one's
    is to be *exactly* what the test will see, so the baseline can never disagree
    with the suite it exists to keep green. Deriving it from the audit instead
    left three cards failing that the audit called clean -- a card with no
    catalog row, one whose name and recorded text disagree, and one whose two
    abilities matched their two printed lines only after they were re-pointed.
    """
    pool = hand_written()
    payloads = {}
    for path in card_files():
        for card in json.loads(path.read_text(encoding="utf-8"))["cards"]:
            payloads[card["id"]] = card

    expected = expectations()
    out: dict[str, str] = {}
    for card in sorted(pool, key=lambda c: c.id):
        if card.is_token:
            continue
        others = CardRegistry({c.id: c for c in pool if c.id != card.id})
        verdict = V.verify(payloads[card.id], expected.get(card.id, {}), others)
        if not verdict.ok:
            out[card.id] = f"{verdict.failed_gate}: {_clip(verdict.reason, 180)}"
    return out


def update_baseline(*, dry_run: bool) -> int:
    """Write the deficit list the gate test reads.

    Generated rather than hand-maintained on purpose. ``/author-cards`` runs
    ``pytest tests/cards`` before it commits and stops on failure; with a
    hand-written strict-xfail list, every *successful* repair would fail the
    suite and abort the run that produced it. A generated baseline turns that
    into "the baseline is stale, re-run --update-baseline", which is true and
    actionable.
    """
    cards = failing_cards()
    payload = {
        "_comment": (
            "Generated by scripts/audit_cards.py --update-baseline. "
            "Cards here do not clear all six authoring gates; "
            "tests/cards/test_hand_written_cards.py xfails them and every other "
            "hand-written card must pass. The list only shrinks -- repair a card "
            "with /author-cards, then regenerate."
        ),
        "cards": cards,
    }
    if not dry_run:
        BASELINE.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="",
        )
    return len(cards)


def check_substitutions() -> None:
    """Which deck substitutions the engine has since outgrown.

    Aesi swaps Scute Swarm out because "copy effects are not implemented" -- and
    ``scute_swarm`` in ``data/cards/auto/`` implements it with
    ``copy_permanent``. Reported, never undone: putting a card back changes the
    deck's composition and is somebody's decision, not a script's.
    """
    registry = CardRegistry.from_dir()
    stale = 0
    for path in sorted((data_dir() / "decks").glob("*.deck.json")):
        deck = json.loads(path.read_text(encoding="utf-8"))
        subs = deck.get("substitutions") or []
        if not subs:
            continue
        print(f"{deck.get('name', path.stem)}")
        for sub in subs:
            slot = sub.get("slot", "")
            playable = slot in registry
            stale += int(playable)
            mark = "NOW PLAYABLE" if playable else "still absent"
            print(f"  {mark:<13} {slot:<32} was: {sub.get('reason', '')[:60]}")
        print()
    print(f"{stale} substitution(s) the engine has outgrown")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--card", metavar="NAME_OR_ID", help="report on one card")
    parser.add_argument("--fix-oracle", action="store_true", help="record the printed text")
    parser.add_argument("--fix-text", action="store_true", help="re-point ability text fields")
    parser.add_argument(
        "--fix-expectations",
        action="store_true",
        help="give cards with no expectation the authored tier's zone assertion",
    )
    parser.add_argument(
        "--open-deficits", action="store_true", help="queue the incomplete cards"
    )
    parser.add_argument(
        "--update-baseline", action="store_true", help="refresh tests/cards/precon_deficits.json"
    )
    parser.add_argument(
        "--check-substitutions", action="store_true", help="deck swaps the engine has outgrown"
    )
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = parser.parse_args()

    if args.check_substitutions:
        check_substitutions()
        return 0

    if args.fix_oracle:
        count = fix_oracle(dry_run=args.dry_run)
        verb = "would record" if args.dry_run else "recorded"
        print(f"{verb} printed oracle text on {count} card(s)")
        return 0

    if args.fix_text:
        count = fix_text(dry_run=args.dry_run)
        verb = "would re-point" if args.dry_run else "re-pointed"
        print(f"{verb} {count} ability text field(s)")
        return 0

    if args.fix_expectations:
        count = fix_expectations(dry_run=args.dry_run)
        verb = "would write" if args.dry_run else "wrote"
        print(f"{verb} a zone assertion for {count} card(s) with none")
        print("these still count as unasserted -- they say nothing about what the card does")
        return 0

    if args.update_baseline:
        count = update_baseline(dry_run=args.dry_run)
        verb = "would record" if args.dry_run else "recorded"
        print(f"{verb} {count} card(s) in {BASELINE.name}")
        return 0

    deficits = run_audit()

    if args.open_deficits:
        opened, closed = open_deficits(deficits, dry_run=args.dry_run)
        verb = "would open" if args.dry_run else "opened"
        print(f"{verb} {opened} queue entrie(s); work them with /author-cards")
        if closed:
            done = "would close" if args.dry_run else "closed"
            print(f"{done} {closed} entrie(s) whose deficit is gone")
        return 0

    report(deficits, only=args.card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

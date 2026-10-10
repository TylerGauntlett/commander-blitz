"""Turn a heap of "I could not express this card" notes into a ranked roadmap.

    python scripts/report_gaps.py                 rewrite docs/unsupported-cards.md
    python scripts/report_gaps.py --top 10        the biggest blockers, to the terminal
    python scripts/report_gaps.py --json          the same, for something else to read

A card the DSL cannot say is not a failure to be worked around -- an approximated
card is the one outcome ``cards/authoring/verify.py`` exists to prevent. It is a
*measurement*, and one refusal is worth very little while a thousand refusals
grouped by what they were waiting for is the whole build order.

So the authoring workers write one gap record per card
(``data/authoring/gaps/<card_id>.json``, see ``cards.authoring.packet.gaps_dir``)
and this collapses them by the capability each one names. "71 cards are waiting
on cycling" is a decision; "Krosan Tusker did not work" is not.

The report is **regenerated wholesale**, never appended. An append-only log drifts
the moment a mechanic ships and its cards stop being blocked, and a roadmap that
is wrong about what is already done is worse than no roadmap.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from commanderblitz.cards.authoring.packet import gaps_dir
from commanderblitz.cards.authoring.queue import Queue
from commanderblitz.cards.registry import data_dir

#: What kind of thing is missing.  Not enforced -- a worker that needs a word not
#: on this list has found something worth reading rather than made a mistake --
#: but listed so the common cases are named consistently and group cleanly.
KINDS = (
    "op",  # a new effect op
    "cost",  # something a cost can be paid with
    "trigger_event",  # a moment the engine does not announce
    "keyword",  # a keyword ability
    "static_effect",  # a continuous effect a static can apply
    "selector",  # a way of naming a set of objects
    "value",  # a way of computing a number
    "replacement",  # a replacement effect
    "decision",  # a question no existing ask_* helper can pose
    "engine",  # a rules subsystem: planeswalkers, sagas, transform
    "token",  # a token create_token cannot name: one entry in tokens.cards.json
)


def report_path() -> Path:
    return Path(__file__).resolve().parents[1] / "docs" / "unsupported-cards.md"


@dataclass
class Need:
    capability: str
    kind: str = ""
    what: str = ""
    why_existing_wont_do: str = ""


@dataclass
class Gap:
    card_id: str
    name: str
    needs: list[Need] = field(default_factory=list)
    blocked_sentences: list[str] = field(default_factory=list)
    closest_existing: list[str] = field(default_factory=list)
    confidence: str = ""
    edhrec_rank: int | None = None


def load_gaps(directory: Path | None = None) -> tuple[list[Gap], list[str]]:
    """Every gap record on disk, and every file that was not one.

    A malformed record is reported rather than raised on: this runs at the end of
    a hundred-card batch, and losing the other ninety-nine to one bad file would
    be a poor trade.
    """
    target = directory or gaps_dir()
    gaps: list[Gap] = []
    problems: list[str] = []
    if not target.exists():
        return gaps, problems

    ranks = _ranks()
    for path in sorted(target.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name}: not readable JSON ({exc})")
            continue
        needs = [
            Need(
                capability=_slug(n.get("capability", "")),
                kind=n.get("kind", ""),
                what=n.get("what", ""),
                why_existing_wont_do=n.get("why_existing_wont_do", ""),
            )
            for n in raw.get("needs", [])
            if isinstance(n, dict) and n.get("capability")
        ]
        if not needs:
            problems.append(f"{path.name}: no `needs` naming a capability")
            continue
        name = raw.get("name", "")
        gaps.append(
            Gap(
                card_id=raw.get("card_id") or path.stem,
                name=name,
                needs=needs,
                blocked_sentences=[s for s in raw.get("blocked_sentences", []) if s],
                closest_existing=[s for s in raw.get("closest_existing", []) if s],
                confidence=raw.get("confidence", ""),
                edhrec_rank=ranks.get(name),
            )
        )
    return gaps, problems


def _ranks() -> dict[str, int]:
    """EDHREC rank by card name, so the report can say which gap costs the most.

    Read from the authoring queue, which already carries it. Absent queue, absent
    ranks -- the report is still useful ordered by card count alone.
    """
    try:
        return {e.name: e.edhrec_rank for e in Queue.load() if e.edhrec_rank is not None}
    except (OSError, json.JSONDecodeError, TypeError):  # pragma: no cover
        return {}


def _slug(text: str) -> str:
    """One spelling per capability, so `Cycling` and `cycling ` do not split it."""
    return "-".join(text.strip().lower().replace("_", "-").split())


def group(gaps: list[Gap]) -> list[tuple[str, list[Gap]]]:
    """Capabilities, most cards first.

    A card needing two capabilities is counted under both: it is blocked until
    *each* of them ships, and hiding it from either list would understate that
    one's cost.
    """
    by_capability: dict[str, list[Gap]] = defaultdict(list)
    for gap in gaps:
        for capability in {n.capability for n in gap.needs}:
            by_capability[capability].append(gap)
    return sorted(by_capability.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def _cards(n: int) -> str:
    return "card" if n == 1 else "cards"


def _best_rank(gaps: list[Gap]) -> int | None:
    ranks = [g.edhrec_rank for g in gaps if g.edhrec_rank is not None]
    return min(ranks) if ranks else None


def as_json(gaps: list[Gap]) -> dict:
    return {
        "cards_blocked": len(gaps),
        "capabilities": [
            {
                "capability": capability,
                "cards": len(blocked),
                "best_edhrec_rank": _best_rank(blocked),
                "kinds": sorted(
                    {n.kind for g in blocked for n in g.needs if n.capability == capability and n.kind}
                ),
                "needs": sorted(
                    {
                        n.what
                        for g in blocked
                        for n in g.needs
                        if n.capability == capability and n.what
                    }
                ),
                "card_ids": sorted(g.card_id for g in blocked),
            }
            for capability, blocked in group(gaps)
        ],
    }


def render(gaps: list[Gap], problems: list[str]) -> str:
    grouped = group(gaps)
    out: list[str] = [
        "# Cards the DSL cannot say yet",
        "",
        "<!-- Generated by scripts/report_gaps.py from data/authoring/gaps/. Do not edit by hand. -->",
        "",
        "Every card here was read by an authoring worker that judged it *not expressible*",
        "and declined to approximate it — see [card-authoring.md](card-authoring.md). The",
        "grouping is the point: one card that did not work is an anecdote, and seventy",
        "waiting on the same missing mechanic is a build order.",
        "",
        "Clear the top entry with `/extend-dsl <capability>`, then re-run",
        "`python scripts/author_cards.py --tier templates --retry` to harvest what it unblocks.",
        "",
    ]

    if not grouped:
        out += ["No gap records. Either nothing has been triaged yet, or the DSL", "covers everything attempted so far.", ""]
        return "\n".join(out)

    out += [
        f"**{len(gaps)} {_cards(len(gaps))}** blocked by **{len(grouped)}** "
        f"{'capability' if len(grouped) == 1 else 'capabilities'}.",
        "",
        "| capability | cards | best EDHREC rank | kind |",
        "|---|---:|---:|---|",
    ]
    for capability, blocked in grouped:
        rank = _best_rank(blocked)
        kinds = sorted({n.kind for g in blocked for n in g.needs if n.capability == capability and n.kind})
        out.append(
            f"| [{capability}](#{capability}) | {len(blocked)} | "
            f"{rank if rank is not None else '—'} | {', '.join(kinds) or '—'} |"
        )
    out.append("")

    for capability, blocked in grouped:
        out += [f"## {capability}", "", f"Blocks **{len(blocked)}** {_cards(len(blocked))}.", ""]

        seen: set[tuple[str, str]] = set()
        for gap in blocked:
            for need in gap.needs:
                if need.capability != capability:
                    continue
                key = (need.what, need.why_existing_wont_do)
                if key in seen or not need.what:
                    continue
                seen.add(key)
                out.append(f"- **({need.kind or 'unknown'})** {need.what}")
                if need.why_existing_wont_do:
                    out.append(f"  <br>Why the existing vocabulary won't do: {need.why_existing_wont_do}")
        out.append("")

        out += ["<details><summary>Cards waiting on this</summary>", ""]
        for gap in sorted(blocked, key=lambda g: (g.edhrec_rank or 10**9, g.name)):
            rank = f" (rank {gap.edhrec_rank})" if gap.edhrec_rank is not None else ""
            out.append(f"- **{gap.name}**{rank} — `{gap.card_id}`")
            for sentence in gap.blocked_sentences:
                out.append(f"  - {sentence}")
        out += ["", "</details>", ""]

    if problems:
        out += ["## Malformed records", "", "These files are in `data/authoring/gaps/` but could not be read:", ""]
        out += [f"- {p}" for p in problems]
        out.append("")

    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="print the data instead of writing the doc")
    parser.add_argument("--top", type=int, help="print the N biggest blockers instead of writing the doc")
    args = parser.parse_args()

    gaps, problems = load_gaps()
    for problem in problems:
        print(f"warning: {problem}", file=sys.stderr)

    if args.json:
        print(json.dumps(as_json(gaps), indent=2))
        return 0

    if args.top:
        if not gaps:
            print("no gap records yet")
            return 0
        grouped = group(gaps)[: args.top]
        print(f"{len(gaps)} {_cards(len(gaps))} blocked by {len(grouped)}:")
        for capability, blocked in grouped:
            print(f"  {len(blocked):>5}  {capability}")
        return 0

    path = report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(gaps, problems), encoding="utf-8", newline="")
    where = path.relative_to(data_dir().parent) if data_dir().parent in path.parents else path
    n = len(group(gaps))
    print(
        f"wrote {where}  ({len(gaps)} {_cards(len(gaps))}, "
        f"{n} {'capability' if n == 1 else 'capabilities'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Inline the shared masters into all three handheld-board mockups.

Same contract as `../rail/inline.py`, `../seat/inline.py` and
`../handheld/inline.py`, for the same reason: a mockup has to open standalone
from file://, file:// blocks the fetch a module import would need, and three
hand-inlined copies of one file quietly stop being the same file.

    python inline.py           re-inline every master into all three
    python inline.py --check   exit 1 if any file is stale, print which

Three masters travel into every file:

    _board.css  the bezel, the deck grid, the information strip, the opponent
                seat, the player orb, the lanes and the card face, the hand, and
                the whole shared grammar of the rail
    _board.js   the fixture, the builders, the reader, the two holds, the review
                keys, the deck fit, `BOARD.mount()`
    assert.js   the gates, so `BOARD_ASSERT()` works in a console with no server

`_board.css` carrying the rail's grammar is `../rail/`'s arrangement, kept for
`../rail/`'s reason: uniformity is the thesis, so a file that restyled the row
would be disproving the claim it exists to make. A file adds only the shape of
its own list -- and on this round it also gets one hook into the board, `mark`,
which paints a rim on a card the list is talking about. Nothing else about the
1280x800 screen is a file's to change.

The markers are load-bearing and must stay exactly as written:

    /* <<< BEGIN _board.css >>> */  ...  /* <<< END _board.css >>> */
    // <<< BEGIN _board.js >>>      ...  // <<< END _board.js >>>
    // <<< BEGIN assert.js >>>     ...  // <<< END assert.js >>>

Stdlib only, no arguments, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent

# CSS first, so a file that has lost both marker pairs reports the one nearer
# the top of the document -- the easier of the two to put back.
MASTERS = [
    ("_board.css", "/* <<< BEGIN _board.css >>> */", "/* <<< END _board.css >>> */"),
    ("_board.js", "// <<< BEGIN _board.js >>>", "// <<< END _board.js >>>"),
    ("assert.js", "// <<< BEGIN assert.js >>>", "// <<< END assert.js >>>"),
]


def splice(html: str, payload: str, begin: str, end: str, name: str) -> str:
    i = html.find(begin)
    j = html.find(end)
    # A file gets the masters it declares. Absent markers are not an error.
    if i < 0 and j < 0:
        return html
    if i < 0 or j < 0:
        raise SystemExit(f"{name}: has one of {begin!r} / {end!r} but not the other")
    if j < i:
        raise SystemExit(f"{name}: END marker precedes BEGIN")
    if html.find(begin, i + 1) >= 0:
        raise SystemExit(f"{name}: {begin!r} appears more than once")
    return html[: i + len(begin)] + "\n" + payload + "\n" + html[j:]


def main() -> int:
    check = "--check" in sys.argv

    payloads = []
    for filename, begin, end in MASTERS:
        path = HERE / filename
        if not path.exists():
            raise SystemExit(f"missing {path}")
        payloads.append((path.read_text(encoding="utf-8").rstrip("\n"), begin, end))

    files = sorted(HERE.glob("*.html"))
    if not files:
        raise SystemExit("no .html files here yet")

    stale: list[str] = []
    for path in files:
        html = original = path.read_text(encoding="utf-8")
        for payload, begin, end in payloads:
            html = splice(html, payload, begin, end, path.name)
        if html == original:
            continue
        stale.append(path.name)
        if not check:
            path.write_text(html, encoding="utf-8")

    if check:
        if stale:
            print("stale, run `python inline.py`: " + ", ".join(stale))
            return 1
        print(f"{len(files)} files up to date with the masters")
        return 0

    print(
        f"inlined into {len(stale) or 'no'} of {len(files)} files"
        + (": " + ", ".join(stale) if stale else " (all were current)")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

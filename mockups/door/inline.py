#!/usr/bin/env python3
"""Inline the shared masters into all five door mockups.

Same contract as `../handheld-board/inline.py`, `../rail/inline.py` and
`../seat/inline.py`, for the same reason: a mockup has to open standalone from
file://, file:// blocks the fetch a module import would need, and five
hand-inlined copies of one file quietly stop being the same file.

    python inline.py           re-inline every master into all five
    python inline.py --check   exit 1 if any file is stale, print which

The masters that travel into a file are the ones it declares markers for:

    _door.css   the bezel and the deck, the card plate, the row and its
                arithmetic, the sheen, the cold state, and the two floors
    _door.js    the three cards, the pad, the spring, `poseOf`, and
                `DOOR.mount()` with the two seams `measure.mjs` drives
    _art.js     the drawn ground, card frame and card illustrations. Only the
                file that uses them declares the markers, which is why this is
                not an error for the four that do not
    assert.js   the gates, so `DOOR_ASSERT()` works in a console with no server

The markers are load-bearing and must stay exactly as written:

    /* <<< BEGIN _door.css >>> */  ...  /* <<< END _door.css >>> */
    // <<< BEGIN _door.js >>>      ...  // <<< END _door.js >>>
    // <<< BEGIN _art.js >>>       ...  // <<< END _art.js >>>
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
    ("_door.css", "/* <<< BEGIN _door.css >>> */", "/* <<< END _door.css >>> */"),
    ("_door.js", "// <<< BEGIN _door.js >>>", "// <<< END _door.js >>>"),
    ("_art.js", "// <<< BEGIN _art.js >>>", "// <<< END _art.js >>>"),
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

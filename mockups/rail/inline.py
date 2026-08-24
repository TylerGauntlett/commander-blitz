#!/usr/bin/env python3
"""Inline the shared masters into all three rail mockups.

Same contract as `../seat/inline.py` and `../handheld/inline.py`, for the same
reason: a mockup has to open standalone from file://, file:// blocks the fetch a
module import would need, and three hand-inlined copies of one file quietly stop
being the same file.

    python inline.py           re-inline every master into all three
    python inline.py --check   exit 1 if any file is stale, print which

Three masters travel into every file:

    _rail.css   the bezel, the ghosted board, the palette, and the shared
                grammar of the rail -- the row, the numeral chip, the commit
                panel, the marks, the holds
    _rail.js    the shell, the two holds, the review keys, `RAIL.mount()`
    assert.js   the gates, so `RAIL_ASSERT()` works in a console with no server

`_rail.css` carrying the grammar is the one real difference from the seat round,
where the shared master deliberately withheld it. There, uniformity was the thing
being argued about and a shared plate style would have answered it for all five.
Here uniformity is the thesis -- 02 and 03 are 01's grammar carried into two
other decisions -- so a file that restyled the row would be disproving the claim
it exists to make. A file adds only the shape of its own list.

The markers are load-bearing and must stay exactly as written:

    /* <<< BEGIN _rail.css >>> */  ...  /* <<< END _rail.css >>> */
    // <<< BEGIN _rail.js >>>      ...  // <<< END _rail.js >>>
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
    ("_rail.css", "/* <<< BEGIN _rail.css >>> */", "/* <<< END _rail.css >>> */"),
    ("_rail.js", "// <<< BEGIN _rail.js >>>", "// <<< END _rail.js >>>"),
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
